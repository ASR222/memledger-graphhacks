"""Ingest: one agent turn -> episode + extracted facts in memory.

The single entry point agents use to turn text into memory.
"""
from dataclasses import asdict

from . import config
from . import memory
from .extract import Extractor


def ingest(tenant, *, extractor: Extractor, agent, source, session, subject, text,
           now, parents=(), episode_id=None) -> dict:
    """Log the turn, extract claims, write them, and report what happened.

    Returns {"episode", "written", "retracted", "dropped"}:
      written   - one entry per stated/suspected claim, with write_fact's result
      retracted - ruled_out claims that closed an active fact
      dropped   - claims rejected by validation or with nothing to act on
    Raises CompromisedSource / UnknownReference before anything is written.
    """
    info = memory.source_info(tenant, source)
    if info is None:
        raise memory.UnknownReference(f"unknown source {source!r}")
    if info["compromised"]:
        raise memory.CompromisedSource(f"source {source!r} is compromised")

    subject = memory.canon(subject)
    ep = memory.log_episode(tenant, agent=agent, source=source, session=session,
                            text=text, now=now, id=episode_id)
    known = memory.known_values(tenant, subject)
    kept, dropped = extractor.extract(text, subject, known)
    report = {"episode": ep, "written": [], "retracted": [], "dropped": dropped}

    # Assertions first, so a replacement supersedes (SUPERSEDES edge) before a
    # retraction of the old value would find nothing to close.
    asserts = [c for c in kept if c.certainty != "ruled_out"]
    denials = [c for c in kept if c.certainty == "ruled_out"]

    for c in asserts:
        usable = _usable_parents(tenant, parents, subject, c.predicate)
        r = memory.write_fact(tenant, agent=agent, source=source, episode=ep,
                              subject=subject, predicate=c.predicate, object=c.value,
                              now=now, parents=usable,
                              tentative=(c.certainty == "suspected"))
        report["written"].append({**asdict(c), **r, "parents": usable})

    for c in denials:
        closed = memory.retract(tenant, agent=agent, source=source, episode=ep,
                                subject=subject, predicate=c.predicate,
                                object=c.value, now=now)
        if closed:
            report["retracted"].append({**asdict(c), "closed": closed})
        else:
            trusted = info["trust"] >= config.TRUST_THRESHOLD
            report["dropped"].append({
                "reason": "nothing_to_retract" if trusted else "untrusted_retraction",
                "item": asdict(c)})
    return report


def _usable_parents(tenant, parents, subject, predicate) -> list[str]:
    """Active parents, minus any about the same subject+predicate.

    A replacement is not derived from the value it replaces; linking it would
    make stale() flag the new fact as soon as the old one closes.
    """
    if not parents:
        return []
    return [p["id"] for p in memory.fact_info(tenant, parents)
            if p["status"] == "active"
            and not (p["subject"] == subject and p["predicate"] == predicate)]
