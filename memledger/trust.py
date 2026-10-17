"""Trust, quarantine and revocation: the operator layer.

Agents never call this module. It backs the operator UI, the API's
/sources routes and scripts/trust.py. The rules themselves (who is trusted,
what gets quarantined, what revoke follows) live in memory.py; this module
adds previews, reports, role permissions and a few admin actions.
"""
from collections import defaultdict

from . import config, memory
from . import queries as Q
from .db import graph
from .memory import _rows

# ---------------------------------------------------------------- roles
# Which predicates each agent may write (TRU-5). Enforced on extraction, so a
# disallowed claim is dropped with a reason instead of raising mid-turn.
ROLE_PREDICATES = {
    "triage": frozenset({"severity", "affects_service", "status"}),
    "investigator": frozenset({"root_cause", "mitigation", "affects_service", "owner"}),
    "comms": frozenset({"status"}),
}


def allowed(agent: str, predicate: str) -> bool:
    """Unknown agents may write nothing."""
    return predicate in ROLE_PREDICATES.get(agent, frozenset())


class RoleFilteredExtractor:
    """Wraps an Extractor; drops claims the agent's role may not make.

    Pass it to ingest() instead of the plain extractor:
        ingest(..., extractor=RoleFilteredExtractor(extractor, agent), agent=agent, ...)
    """

    def __init__(self, inner, agent: str):
        self.inner = inner
        self.agent = agent

    def extract(self, text, subject, known=None):
        kept, dropped = self.inner.extract(text, subject, known)
        ok = []
        for c in kept:
            if allowed(self.agent, c.predicate):
                ok.append(c)
            else:
                dropped.append({"reason": "not_permitted", "agent": self.agent,
                                "item": {"predicate": c.predicate, "value": c.value,
                                         "certainty": c.certainty, "evidence": c.evidence}})
        return ok, dropped


# ---------------------------------------------------------------- reads

def trust_table(tenant) -> list[dict]:
    """[{id, kind, trust, compromised, trusted, active, quarantined, revoked}]"""
    rows = _rows(graph(tenant).ro_query(Q.TRUST_TABLE))
    for r in rows:
        r["trusted"] = r["trust"] >= config.TRUST_THRESHOLD and not r["compromised"]
    return rows


def quarantine(tenant) -> list[dict]:
    """Facts waiting for corroboration, with any belief each one disputes."""
    rows = _rows(graph(tenant).ro_query(Q.QUARANTINE))
    against = {d["id"]: d for d in memory.disputes(tenant)}
    for r in rows:
        d = against.get(r["id"])
        r["disputes"] = {"fact": d["against"], "believed": d["believed"]} if d else None
    return rows


def blast_radius(tenant, source) -> dict:
    """What revoke(source) would do, without doing it.

    Returns {"source", "facts": [...], "by_agent": {agent: n}, "direct", "derived"}.
    """
    if memory.source_info(tenant, source) is None:
        raise memory.UnknownReference(f"unknown source {source!r}")
    facts = _rows(graph(tenant).ro_query(Q.BLAST_RADIUS, {"source": source}))
    return _summary(source, facts)


def _summary(source, facts) -> dict:
    by_agent = defaultdict(int)
    for f in facts:
        by_agent[f["writer"]] += 1
    return {"source": source, "facts": facts, "by_agent": dict(by_agent),
            "direct": sum(1 for f in facts if f["direct"]),
            "derived": sum(1 for f in facts if not f["direct"])}


# ---------------------------------------------------------------- actions

def revoke_source(tenant, source, now) -> dict:
    """Preview, revoke, and report what is now stale.

    Returns blast_radius's shape plus "revoked" (ids actually revoked) and
    "stale" (active facts derived from a belief that is no longer active).
    """
    preview = blast_radius(tenant, source)
    done = memory.revoke(tenant, source, now)
    out = _summary(source, preview["facts"])
    out["revoked"] = sorted(f["id"] for f in done)
    out["stale"] = memory.stale(tenant)
    return out


def promote(tenant, fact_id, now) -> dict:
    """Operator confirms a quarantined fact (same effect as trusted corroboration)."""
    return memory.promote(tenant, fact_id, now)


def set_trust(tenant, source, trust: float) -> dict:
    """Change a source's trust for future writes. Existing facts keep their status."""
    if not 0.0 <= trust <= 1.0:
        raise ValueError("trust must be between 0 and 1")
    info = memory.source_info(tenant, source)
    if info is None:
        raise memory.UnknownReference(f"unknown source {source!r}")
    if info["compromised"]:
        raise memory.CompromisedSource(f"source {source!r} is compromised; trust cannot be restored")
    return _rows(graph(tenant).query(Q.SET_TRUST, {"id": source, "trust": float(trust)}))[0]
