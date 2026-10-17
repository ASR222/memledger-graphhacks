"""MemLedger MCP server: read-only, rule-following access to shared memory.

Any MCP client (Claude Desktop, Claude Code, Cursor...) becomes another
reader of the team's memory. Unlike raw Cypher, these tools apply the memory
rules: quarantined claims are never returned as beliefs, revoked facts are
gone, and every answer carries fact ids for citation.

    python -m memledger.mcp_server                       # stdio (Claude Desktop)
    python -m memledger.mcp_server --http --port 8001    # streamable HTTP at /mcp
"""
import argparse
from datetime import datetime

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import memory, trust
from . import scenario as S
from .db import get_db

INSTRUCTIONS = """MemLedger is the shared memory of an incident-response agent team, stored as a
graph in FalkorDB. Each tenant (customer) has its own graph and an incident id.

How to answer questions with these tools:
- Start with list_incidents, then current_beliefs for the incident.
- Only facts returned by current_beliefs are beliefs. Cite them by fact id, e.g. [f-1a2b3c4d].
- Disputes are unconfirmed claims from untrusted or hedged sources. Mention them only as
  unconfirmed; never state them as fact.
- Use explain_fact to say who wrote a fact, from which source, what it was based on and
  what it replaced.
- Use beliefs_at for "what did we believe at <time>" questions.
- These tools are read-only. Revoking sources and promoting claims are operator actions
  done in the MemLedger console."""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                            openWorldHint=False)

mcp = MCPServer("memledger", instructions=INSTRUCTIONS, version="1.0")


# ---------------------------------------------------------------- helpers

def _graph_exists(tenant: str) -> bool:
    memory.graph(tenant)                                   # validates the name
    return f"memory_{tenant}" in get_db().list_graphs()


def _need(tenant: str) -> None:
    try:
        ok = _graph_exists(tenant)
    except ValueError as e:
        raise ToolError(str(e))
    if not ok:
        raise ToolError(f"tenant {tenant!r} has no memory yet; call list_incidents")


def _subject(tenant: str, subject: str | None) -> str:
    if subject:
        return subject
    try:
        return S.load(tenant)["subject"]
    except FileNotFoundError:
        raise ToolError(f"pass the incident id as subject; tenant {tenant!r} has no default")


def _time_ms(value: str) -> int:
    """Accept ISO 8601 (with offset) or epoch milliseconds."""
    v = value.strip()
    if v.isdigit():
        return int(v)
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        raise ToolError("time must be ISO 8601, e.g. 2026-10-17T13:55:00+05:30, or epoch ms")
    if dt.tzinfo is None:
        raise ToolError("include a UTC offset in the time, e.g. +05:30")
    return int(dt.timestamp() * 1000)


def _iso(ms: int | None) -> str | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="minutes")


def _run(fn, *a):
    try:
        return fn(*a)
    except memory.MemoryError_ as e:
        raise ToolError(str(e))


# ---------------------------------------------------------------- tools

@mcp.tool(annotations=READ_ONLY)
def list_incidents() -> dict:
    """List tenants (customers) and their incident ids. Start here."""
    graphs = {g.removeprefix("memory_") for g in get_db().list_graphs() if g.startswith("memory_")}
    out = []
    for t in sorted(graphs):
        try:
            sc = S.load(t)
            out.append({"tenant": t, "incident": sc["subject"], "title": sc["title"]})
        except FileNotFoundError:
            out.append({"tenant": t, "incident": None, "title": None})
    return {"incidents": out}


@mcp.tool(annotations=READ_ONLY)
def current_beliefs(tenant: str, subject: str | None = None) -> dict:
    """What the team currently believes about an incident, with fact ids to cite,
    plus unconfirmed disputed claims listed separately (never state those as fact)."""
    _need(tenant)
    subj = _subject(tenant, subject)
    canon = memory.canon(subj)
    beliefs = [{"id": f["id"], "predicate": f["predicate"], "value": f["object"],
                "since": _iso(f["since"]), "written_by": f["writer"]}
               for f in memory.read_active(tenant, subj)]
    unconfirmed = [{"predicate": d["predicate"], "claimed": d["claimed"], "contradicts": d["believed"]}
                   for d in memory.disputes(tenant) if d["subject"] == canon]
    return {"incident": canon, "beliefs": beliefs, "unconfirmed_disputes": unconfirmed}


@mcp.tool(annotations=READ_ONLY)
def explain_fact(tenant: str, fact_id: str) -> dict:
    """Why a fact is (or was) believed: who wrote it, its sources, what it was based on,
    what it replaced, its current status, and every version of that field over time."""
    _need(tenant)
    w = memory.why(tenant, fact_id)
    if w is None:
        raise ToolError(f"no fact {fact_id!r} in {tenant}")
    versions = memory.versions(tenant, w["subject"], w["predicate"])
    return {"id": w["id"], "predicate": w["predicate"], "value": w["object"], "status": w["status"],
            "written_by": w["agents"], "sources": w["sources"],
            "based_on": [u for u in w["upstream"] if u.startswith("f")],
            "replaced": w["replaced"],
            "versions": [{"value": v["object"], "status": v["status"], "from": _iso(v["valid_from"]),
                          "to": _iso(v.get("valid_to"))} for v in versions]}


@mcp.tool(annotations=READ_ONLY)
def beliefs_at(tenant: str, time: str, subject: str | None = None) -> dict:
    """What the team believed at a moment in the past. `time` is ISO 8601 with an
    offset (e.g. 2026-10-17T13:55:00+05:30) or epoch milliseconds."""
    _need(tenant)
    t = _time_ms(time)
    canon = memory.canon(_subject(tenant, subject))
    return {"incident": canon, "time": _iso(t),
            "beliefs": [{"id": f["id"], "predicate": f["predicate"], "value": f["object"]}
                        for f in memory.as_of(tenant, t) if f["subject"] == canon]}


@mcp.tool(annotations=READ_ONLY)
def stale_conclusions(tenant: str) -> dict:
    """Current facts that were concluded from a belief the team no longer holds."""
    _need(tenant)
    return {"stale": memory.stale(tenant)}


@mcp.tool(annotations=READ_ONLY)
def source_trust(tenant: str) -> dict:
    """Every information source with its trust score and whether it is compromised,
    plus the claims waiting in quarantine."""
    _need(tenant)
    return {"threshold_note": "sources below the threshold only produce quarantined claims",
            "sources": trust.trust_table(tenant),
            "quarantine": [{"id": q["id"], "predicate": q["predicate"], "value": q["object"],
                            "sources": q["sources"], "disputes": q["disputes"]}
                           for q in trust.quarantine(tenant)]}


@mcp.tool(annotations=READ_ONLY)
def blast_radius(tenant: str, source: str) -> dict:
    """Preview what revoking a source would withdraw (direct and derived facts, by agent).
    Read-only: it does not revoke anything."""
    _need(tenant)
    return _run(trust.blast_radius, tenant, source)


@mcp.tool(annotations=READ_ONLY)
def session_history(tenant: str, session: str) -> dict:
    """The turns the agents logged in one session, oldest first."""
    _need(tenant)
    return {"session": session, "turns": [{"agent": h["agent"], "at": _iso(h["at"]), "text": h["text"][:500]}
                                          for h in memory.history(tenant, session)]}


# ---------------------------------------------------------------- entry point

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    a = ap.parse_args(argv)
    if a.http:
        mcp.run("streamable-http", host=a.host, port=a.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
