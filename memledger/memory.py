"""MemLedger memory core: the only module that talks to the graph.

Every function takes a tenant. Every write takes `now` (epoch ms) from the
caller, so the scripted demo replays identically.
"""
import re
import threading
import uuid
from collections import defaultdict

from . import config
from . import queries as Q
from .db import graph

# FalkorDB serializes writes per graph, but write_fact is several queries
# (check, then write). This lock makes that sequence atomic per tenant within
# one process. Run a single API process.
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


class MemoryError_(Exception):
    """Base error for memory-rule violations."""


class CompromisedSource(MemoryError_):
    pass


class UnknownReference(MemoryError_):
    pass


class InvalidParent(MemoryError_):
    pass


def canon(value: str) -> str:
    """Lowercase, trim, join words with '-', then apply aliases."""
    v = re.sub(r"[\s_]+", "-", str(value).strip().lower())
    return config.ALIASES.get(v, v)


def new_id(prefix: str = "f") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _rows(res) -> list[dict]:
    names = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    names = [n.decode() if isinstance(n, bytes) else n for n in names]
    return [dict(zip(names, r)) for r in res.result_set]


# ---------------------------------------------------------------- writes

def log_episode(tenant, *, agent, source, session, text, now, id=None) -> str:
    id = id or new_id("ep")
    rows = _rows(graph(tenant).query(Q.LOG_EPISODE, {
        "id": id, "agent": agent, "source": source,
        "session": session, "text": text, "now": now}))
    if not rows:
        raise UnknownReference(f"unknown agent {agent!r} or source {source!r}")
    return id


def _result(id, status, closed=0, conflicts=0, corroborated=False,
            promoted=False, ignored=False) -> dict:
    return {"id": id, "status": status, "closed": closed, "conflicts": conflicts,
            "corroborated": corroborated, "promoted": promoted, "ignored": ignored}


def write_fact(tenant, *, agent, source, episode, subject, predicate, object,
               now, parents=(), id=None, tentative=False) -> dict:
    """Store a belief.

    Returns {"id", "status", "closed", "conflicts", "corroborated", "promoted", "ignored"}.

    A write is *trusted* when the source's trust >= threshold and the claim is
    not tentative (hedged). Order of rules:
      1. predicate must be in the vocabulary
      2. source must exist and not be compromised
      3. parents must exist and be active
      4. identical active triple:      trusted -> corroborate; untrusted -> ignored
         identical quarantined triple: corroborate; promote if trusted
      5. otherwise create: active if trusted, else quarantined.
         Single-valued predicates: active closes contradicting active facts,
         quarantined records CONFLICTS_WITH. Multi-valued: values coexist.
    """
    if predicate not in config.PREDICATES:
        raise ValueError(f"predicate {predicate!r} not in vocabulary")
    subject, obj = canon(subject), canon(object)
    parents = list(parents)
    g = graph(tenant)

    with _locks[tenant]:
        src = _rows(g.ro_query(Q.SOURCE_INFO, {"id": source}))
        if not src:
            raise UnknownReference(f"unknown source {source!r}")
        if src[0]["compromised"]:
            raise CompromisedSource(f"source {source!r} is compromised")
        trusted = src[0]["trust"] >= config.TRUST_THRESHOLD and not tentative

        if parents:
            bad = [p for p in _rows(g.ro_query(Q.PARENT_STATUS, {"ids": parents}))
                   if p["status"] != "active"]
            if bad:
                raise InvalidParent(f"parents must be active facts: {bad}")

        same = _rows(g.ro_query(Q.FIND_SAME, {
            "subject": subject, "predicate": predicate, "object": obj}))
        live = next((r for r in same if r["status"] == "active"), None)
        pending = next((r for r in same if r["status"] == "quarantined"), None)

        if live:
            if not trusted:
                # An untrusted echo adds nothing, and linking it would let a
                # junk source's revocation take down a true belief.
                return _result(live["id"], "active", ignored=True)
            g.query(Q.CORROBORATE, {"id": live["id"], "source": source,
                                    "agent": agent, "now": now})
            return _result(live["id"], "active", corroborated=True)

        if pending:
            g.query(Q.CORROBORATE, {"id": pending["id"], "source": source,
                                    "agent": agent, "now": now})
            if trusted:
                r = _rows(g.query(Q.PROMOTE, {"id": pending["id"], "now": now,
                                              "single_preds": sorted(config.SINGLE_VALUED)}))[0]
                return _result(pending["id"], "active", closed=r["closed"],
                               corroborated=True, promoted=True)
            return _result(pending["id"], "quarantined", corroborated=True)

        id = id or new_id("f")
        status = "active" if trusted else "quarantined"
        rows = _rows(g.query(Q.WRITE_FACT, {
            "id": id, "agent": agent, "source": source, "episode": episode,
            "subject": subject, "predicate": predicate, "object": obj,
            "status": status, "now": now,
            "single": predicate in config.SINGLE_VALUED}))
        if not rows:
            raise UnknownReference(f"unknown agent {agent!r} or episode {episode!r}")
        if parents:
            g.query(Q.LINK_PARENTS, {"id": id, "parents": parents})
        return _result(id, status, closed=rows[0]["closed"],
                       conflicts=rows[0]["conflicts"])


def retract(tenant, *, agent, source, episode, subject, predicate, object, now) -> list[str]:
    """Close an active fact because a source explicitly ruled it out.

    Only trusted, uncompromised sources can retract. Returns the closed fact
    ids ([] when nothing active matched or the source is not trusted).
    """
    if predicate not in config.PREDICATES:
        raise ValueError(f"predicate {predicate!r} not in vocabulary")
    g = graph(tenant)
    with _locks[tenant]:
        src = _rows(g.ro_query(Q.SOURCE_INFO, {"id": source}))
        if not src:
            raise UnknownReference(f"unknown source {source!r}")
        if src[0]["compromised"]:
            raise CompromisedSource(f"source {source!r} is compromised")
        if src[0]["trust"] < config.TRUST_THRESHOLD:
            return []
        rows = _rows(g.query(Q.RETRACT, {
            "subject": canon(subject), "predicate": predicate, "object": canon(object),
            "agent": agent, "episode": episode, "now": now}))
    return [r["id"] for r in rows]


def promote(tenant, fact_id, now) -> dict:
    with _locks[tenant]:
        rows = _rows(graph(tenant).query(Q.PROMOTE, {
            "id": fact_id, "now": now, "single_preds": sorted(config.SINGLE_VALUED)}))
    if not rows:
        raise UnknownReference(f"{fact_id!r} is not a quarantined fact")
    return rows[0]


def revoke(tenant, source, now) -> list[dict]:
    """Mark a source compromised and revoke everything that depends on it."""
    with _locks[tenant]:
        g = graph(tenant)
        if not _rows(g.ro_query(Q.SOURCE_INFO, {"id": source})):
            raise UnknownReference(f"unknown source {source!r}")
        return _rows(g.query(Q.REVOKE, {"source": source, "now": now}))


# ---------------------------------------------------------------- reads

def source_info(tenant, source) -> dict | None:
    rows = _rows(graph(tenant).ro_query(Q.SOURCE_INFO, {"id": source}))
    return rows[0] if rows else None


def fact_info(tenant, ids) -> list[dict]:
    """[{id, status, subject, predicate}] for each id (status None if missing)."""
    return _rows(graph(tenant).ro_query(Q.PARENT_STATUS, {"ids": list(ids)}))


def known_values(tenant, subject) -> dict[str, list[str]]:
    rows = _rows(graph(tenant).ro_query(Q.KNOWN_VALUES, {"subject": canon(subject)}))
    return {r["predicate"]: sorted(r["values"]) for r in rows}


def disputes(tenant) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.DISPUTES))


def read_active(tenant, entity) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.READ_ACTIVE, {"entity": canon(entity)}))


def all_active(tenant) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.ALL_ACTIVE))


def as_of(tenant, t) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.AS_OF, {"t": t}))


def versions(tenant, subject, predicate) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.FACT_VERSIONS, {
        "subject": canon(subject), "predicate": predicate}))


def stale(tenant) -> list[dict]:
    """Active facts derived from a belief that was later closed. Review these."""
    return _rows(graph(tenant).ro_query(Q.STALE))


def why(tenant, fact_id) -> dict | None:
    g = graph(tenant)
    rows = _rows(g.ro_query(Q.WHY, {"id": fact_id}))
    if not rows:
        return None
    out = rows[0]
    out["paths"] = [r["path"] for r in _rows(g.ro_query(Q.WHY_PATHS, {"id": fact_id}))]
    return out


def history(tenant, session) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.HISTORY, {"session": session}))


def snapshot(tenant) -> dict:
    """Nodes and edges for the UI."""
    g = graph(tenant)
    return {"nodes": _rows(g.ro_query(Q.NODES)), "edges": _rows(g.ro_query(Q.EDGES))}
