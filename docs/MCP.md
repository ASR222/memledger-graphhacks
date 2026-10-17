# MCP.md — MemLedger over MCP

Complete context for giving outside AI clients (Claude Desktop, Claude Code, any MCP client) access to MemLedger's memory: two MCP servers, what each is for, how to configure them safely, and the demo beat. Covers workstream MCP on the build board (MCP-1, MCP-2).

**Status (17 Oct 2026):**
- Every file in section 10 was run. The full suite is **131 passed, 1 expected failure** (the Mem.md bug from SCN.md §12): the 125 from earlier docs plus 6 new MCP tests.
- **Two tests start real server processes.** One launches MemLedger's server with `python -m memledger.mcp_server` over stdio, as Claude Desktop does, against FalkorDB on TCP. The other launches the **official `@falkordb/mcpserver` 1.3.0** with Node and checks its read-only settings (§4).
- The official-server test is skipped unless `FALKORDB_MCP_JS` points at its `dist/index.js`. Without it the suite is 130 passed, 1 skipped, 1 expected failure.
- **Not yet verified:** inside the Claude Desktop app itself. The config in §5 is standard but untested here.

**This file is additive. It does not change any earlier doc.** It adds:

| File | Purpose |
|---|---|
| `memledger/mcp_server.py` | MemLedger MCP server: 8 read-only tools that follow the memory rules |
| `tests/test_mcp.py` | 6 tests |

Dependency: **`mcp==2.2.0`** (the Python MCP SDK). Pin it. The 2.x SDK renamed `FastMCP` to `MCPServer` and changed field names, so 1.x tutorials won't match this code.

---

## 1. Two servers, two jobs

| | **MemLedger MCP** (this file) | **FalkorDB MCP** (official, sponsor's) |
|---|---|---|
| What it exposes | Memory-level tools: current beliefs, explain a fact, beliefs at a time, disputes, trust, blast radius | Raw graph access: `query_graph`, `query_graph_readonly`, `list_graphs`, schema tools, `delete_graph` |
| Follows memory rules | **Yes.** Quarantined claims are never returned as beliefs; revoked facts are gone; answers carry fact ids | **No.** Raw Cypher sees everything, including quarantined and revoked facts, unless the query filters by status |
| Can change memory | No (all tools read-only) | Yes, unless strict read-only mode is on (§4) |
| Best for | "What caused INC-42 and why?", the fourth-agent demo | Showing judges the raw graph, ad-hoc Cypher, schema exploration |

**Use both.** The FalkorDB server shows the sponsor's tooling working on your graph. The MemLedger server shows the point of the project: an outside agent gets the team's memory with the same rules the internal agents follow.

**Demo line:** "Raw Cypher can see the quarantined DDoS claim. Our MCP server won't hand it over as a belief. That's the difference between a database and a memory."

---

## 2. MemLedger MCP tools

All tools are annotated read-only (`readOnlyHint: true`, `destructiveHint: false`). The server sends instructions to the client telling the model to cite fact ids and never state disputes as fact.

| Tool | Arguments | Returns |
|---|---|---|
| `list_incidents` | — | tenants with incident id and title. **Start here** |
| `current_beliefs` | `tenant`, `subject?` | `beliefs` (id, predicate, value, since, written_by) and, separately, `unconfirmed_disputes` |
| `explain_fact` | `tenant`, `fact_id` | value, status, written_by, sources, based_on (fact ids), replaced, versions over time |
| `beliefs_at` | `tenant`, `time`, `subject?` | beliefs at that moment. `time` is ISO 8601 **with an offset** or epoch ms |
| `stale_conclusions` | `tenant` | facts concluded from a belief no longer held |
| `source_trust` | `tenant` | trust table and quarantined claims |
| `blast_radius` | `tenant`, `source` | what revoking would withdraw. **Preview only** |
| `session_history` | `tenant`, `session` | logged turns |

`subject` defaults to the tenant's scenario incident. Times come back as ISO 8601 in the server's local timezone, with the offset.

**Errors** come back as readable tool errors the model can act on: unknown tenant or no graph yet, invalid tenant name, unknown fact, unknown source, a time without an offset, an unparseable time.

**Why no write tools.** An outside client has no agent identity, role or source in the trust model. Letting it write would either bypass provenance or need a new agent and source with their own trust score. Revoking and promoting are operator actions in the console. If you want it later: add an `external` agent and a low-trust `mcp` source so everything an outside model says starts in quarantine.

---

## 3. Running the MemLedger MCP server

```bash
pip install "mcp==2.2.0"
python -m memledger.mcp_server                       # stdio (Claude Desktop, Claude Code)
python -m memledger.mcp_server --http --port 8001    # streamable HTTP at http://127.0.0.1:8001/mcp
```

It reads `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD` like the rest of MemLedger (via `config.py`), so it points at the same database as the API and agents.

**Over stdio, nothing may print to stdout.** Stdout is the protocol channel, so a stray `print` in code the server imports corrupts it. Log to stderr.

**HTTP mode has no authentication.** Keep it on `127.0.0.1`, or put it behind something that checks a token, before exposing it.

---

## 4. The official FalkorDB MCP server: use strict read-only

Tested against `@falkordb/mcpserver` **1.3.0** (MIT) and its tool list: `query_graph`, `query_graph_readonly`, `list_graphs`, `get_graph_schema`, `get_node_schema`, `get_relationship_schema`, `delete_graph`.

**`FALKORDB_DEFAULT_READONLY=true` is not enough.** It only sets the default; the model can pass `readOnly: false` to `query_graph`, and `delete_graph` ignores it. In the test, with only that setting, a write succeeded and **a graph was deleted.** With **`FALKORDB_STRICT_READONLY=true`** both were refused (`test_official_server_strict_read_only`). The README's Claude Desktop example sets neither, so add both:

```json
"env": {
  "FALKORDB_HOST": "localhost",
  "FALKORDB_PORT": "6379",
  "FALKORDB_DEFAULT_READONLY": "true",
  "FALKORDB_STRICT_READONLY": "true"
}
```

Graph names are `memory_<tenant>` (for example `memory_acme`).

### Cypher to give the model (raw graph, rule-following)

If you ask Claude questions through the FalkorDB server, tell it these filters. Otherwise it may report quarantined or revoked claims as facts.

```cypher
// current beliefs about the incident
MATCH (f:Fact {subject:'inc-42', status:'active'})
RETURN f.id, f.predicate, f.object ORDER BY f.predicate

// unconfirmed disputes
MATCH (q:Fact {status:'quarantined'})-[:CONFLICTS_WITH]->(a:Fact {status:'active'})
RETURN q.object AS claimed, a.object AS believed

// provenance of one fact
MATCH p = (f:Fact {id:$id})-[:FROM_SOURCE|DERIVED_FROM*1..6]->(s:Source) RETURN p

// everything a source touched
MATCH p = (:Source {id:'webhook'})<-[:FROM_SOURCE|DERIVED_FROM*1..6]-(:Fact) RETURN p
```

The schema tools work as-is: `get_graph_schema` on `memory_acme` lists the labels (Agent, Source, Episode, Entity, Fact, and Handoff once a handoff exists) and relationship types.

---

## 5. Connecting clients (MCP-2)

### Claude Desktop

Edit `claude_desktop_config.json` (on macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`, per the FalkorDB README) and restart the app.

```json
{
  "mcpServers": {
    "memledger": {
      "command": "/ABSOLUTE/PATH/TO/memledger/.venv/bin/python",
      "args": ["-m", "memledger.mcp_server"],
      "env": {
        "PYTHONPATH": "/ABSOLUTE/PATH/TO/memledger",
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6379"
      }
    },
    "falkordb": {
      "command": "npx",
      "args": ["-y", "@falkordb/mcpserver@1.3.0"],
      "env": {
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6379",
        "FALKORDB_DEFAULT_READONLY": "true",
        "FALKORDB_STRICT_READONLY": "true"
      }
    }
  }
}
```

- Use the **absolute path to the venv's Python**, so the app uses the interpreter that has `mcp`, `falkordb` and MemLedger's dependencies installed.
- `PYTHONPATH` lets `-m memledger.mcp_server` import the package regardless of the app's working directory. The scenario files are found relative to the package, so the working directory doesn't matter.
- Pin `@falkordb/mcpserver@1.3.0` (the tested version) rather than `@latest`.
- For a deployed FalkorDB Cloud instance, set host, port, username and password to the cloud values.

### Claude Code

Syntax from the Claude Code MCP docs (`claude mcp add [options] <name> -- <command> [args...]`; `--env` needs another option between it and the name):

```bash
claude mcp add --env FALKORDB_HOST=localhost --env FALKORDB_PORT=6379 \
  --env PYTHONPATH=$(pwd) --transport stdio memledger \
  -- $(pwd)/.venv/bin/python -m memledger.mcp_server

claude mcp add --env FALKORDB_HOST=localhost --env FALKORDB_PORT=6379 \
  --env FALKORDB_DEFAULT_READONLY=true --env FALKORDB_STRICT_READONLY=true \
  --transport stdio falkordb -- npx -y @falkordb/mcpserver@1.3.0

# or, with the HTTP server running:
claude mcp add --transport http memledger http://127.0.0.1:8001/mcp
```

Run these from the repo root (`$(pwd)`). Add `--scope project` to share them with the repo via `.mcp.json`.

### Inspector (no Claude needed)

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m memledger.mcp_server
```

---

## 6. The demo beat (video step after the scripted story)

Run the story to step 9 (before the revoke) so the disputes are live, then in Claude Desktop with both servers connected:

1. **"What caused INC-42 in acme, and why do we believe it? Use the memledger tools."** Expect: deploy v2.3.1 [fact id], written by the investigator from the runbook, replacing DB pool exhaustion; DDoS and Redis mentioned only as unconfirmed.
2. **"Now use the falkordb tools: list every root_cause fact in memory_acme with its status."** Expect: all four, including `ddos` (quarantined) and `db-pool-exhaustion` (closed). The raw graph has everything.
3. Say the line from §1: the database holds every claim; the memory layer decides what's a belief.
4. Run step 11 (revoke) in the console, then ask again: **"Is the cache flush still a mitigation?"** Expect no, and `beliefs_at` 13:55 shows it was.
5. Optional: **"Delete the graph memory_scratch"** through the FalkorDB server. Strict read-only refuses. (Create `memory_scratch` first with `schema.seed("scratch")`, never use a real tenant.)

Live model wording varies. Rehearse once and keep the questions exactly as written.

---

## 7. Tests

```bash
pytest -q                                            # 130 passed, 1 skipped, 1 xfailed
# include the official server:
npm pack @falkordb/mcpserver@1.3.0 && tar xzf falkordb-mcpserver-1.3.0.tgz \
  && (cd package && npm install --omit=dev)
FALKORDB_MCP_JS=$PWD/package/dist/index.js pytest -q   # 131 passed, 1 xfailed
```

| Test | Checks |
|---|---|
| `test_tools_are_listed_and_read_only` | 8 tools, all annotated read-only and non-destructive; server instructions sent |
| `test_beliefs_follow_memory_rules` | quarantined DDoS and Redis are not beliefs but appear as unconfirmed disputes; explain_fact provenance and versions; blast radius; trust table; history; stale |
| `test_revoked_facts_disappear_and_history_remains` | after revoke, flush-cache is gone from current beliefs, still in beliefs_at 13:55; blast radius empty |
| `test_errors_are_readable` | no graph, invalid tenant, unknown fact, bad time, time without offset, unknown source; epoch ms accepted |
| `test_stdio_server_process` | a real `python -m memledger.mcp_server` process over stdio against FalkorDB on TCP |
| `test_official_server_strict_read_only` | real `@falkordb/mcpserver` 1.3.0: read-only query works; strict mode blocks write and delete; default-read-only alone does not |

The real-process tests use falkordblite's TCP option (`serverconfig={"port": ...}`), so no Docker is needed.

---

## 8. Known limits

- **Read-only only.** Outside clients can't add observations (§2 explains why and how to add it later).
- **No auth on HTTP mode** (§3). stdio has none to need: only the launching app can talk to it.
- **Times use the server's local timezone** in responses (with offset). On Cloud Run that will be UTC.
- **`beliefs_at` inherits the Mem.md as_of bug** until patched: the quarantined-then-revoked `redis-outage` appears at 13:55. Avoid that question in the video, or apply SCN.md §12.
- **Claude Desktop itself not tested here.** If the server doesn't appear, check the app's MCP logs for the Python path and import errors first.

---

## 9. Judge talking points

- "Claude Desktop is a fourth agent on the team. It reads the same memory through MCP, with the same rules."
- "With the raw FalkorDB server you see every claim ever made. Through MemLedger's server you get what the team actually believes, with citations."
- "We run the FalkorDB MCP server in strict read-only mode. We tested that the default read-only flag alone still lets a model delete a graph."

---

## 10. Source files (tested)

### `memledger/mcp_server.py`
```python
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
```

### `tests/test_mcp.py`
```python
"""MCP servers (MCP.md): MemLedger's own, and the official FalkorDB one."""
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters
from redislite.falkordb_client import FalkorDB as LiteFalkorDB

from memledger import db, schema
from memledger import scenario as S
from memledger.extract import Extractor
from memledger.mcp_server import mcp

ROOT = Path(__file__).resolve().parents[1]


def story(upto: int, state):
    sc = S.load("acme")
    r = S.Runner(sc, Extractor(S.GoldenLLM(sc), mode="live", model_name="golden"),
                 S.OfflineChat(), state_path=state)
    r.reset()
    r.run_until(upto)


async def call(client, name, args=None):
    r = await client.call_tool(name, args or {})
    text = r.content[0].text
    return r.is_error, (text if r.is_error else json.loads(text))


def run(coro):
    return anyio.run(coro)


# ---------------------------------------------------------------- in-process

def test_tools_are_listed_and_read_only():
    async def go():
        async with Client(mcp) as c:
            tools = (await c.list_tools()).tools
            assert "Only facts returned by current_beliefs are beliefs" in c.instructions
            return tools
    tools = run(go)
    assert {t.name for t in tools} == {"list_incidents", "current_beliefs", "explain_fact", "beliefs_at",
                                       "stale_conclusions", "source_trust", "blast_radius", "session_history"}
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)


def test_beliefs_follow_memory_rules(tmp_path):
    story(9, tmp_path / "s.json")

    async def go():
        async with Client(mcp) as c:
            _, inc = await call(c, "list_incidents")
            _, cur = await call(c, "current_beliefs", {"tenant": "acme"})
            rc = next(b for b in cur["beliefs"] if b["predicate"] == "root_cause")
            _, why = await call(c, "explain_fact", {"tenant": "acme", "fact_id": rc["id"]})
            _, radius = await call(c, "blast_radius", {"tenant": "acme", "source": "webhook"})
            _, src = await call(c, "source_trust", {"tenant": "acme"})
            _, hist = await call(c, "session_history", {"tenant": "acme", "session": "s1"})
            _, stale = await call(c, "stale_conclusions", {"tenant": "acme"})
            return inc, cur, why, radius, src, hist, stale
    inc, cur, why, radius, src, hist, stale = run(go)
    assert {"tenant": "acme", "incident": "INC-42", "title": "payments-api latency spike"} in inc["incidents"]
    values = {b["value"] for b in cur["beliefs"]}
    assert "bad-deploy-v2.3.1" in values and "flush-cache" in values
    assert "ddos" not in values and "redis-outage" not in values            # quarantined: not beliefs
    assert {d["claimed"] for d in cur["unconfirmed_disputes"]} == {"ddos", "redis-outage"}
    assert all(b["id"].startswith("f-") for b in cur["beliefs"])
    assert why["sources"] == ["runbook"] and why["replaced"] == ["db-pool-exhaustion"]
    assert [v["status"] for v in why["versions"]][:2] == ["closed", "active"]
    assert {f["object"] for f in radius["facts"]} == {"flush-cache", "redis-outage"}
    assert any(s["id"] == "fwd-logs" and not s["trusted"] for s in src["sources"])
    assert hist["turns"][0]["agent"] == "triage"
    assert any(s["predicate"] == "status" for s in stale["stale"])


def test_revoked_facts_disappear_and_history_remains(tmp_path):
    story(11, tmp_path / "s.json")

    async def go():
        async with Client(mcp) as c:
            _, cur = await call(c, "current_beliefs", {"tenant": "acme"})
            _, then = await call(c, "beliefs_at", {"tenant": "acme", "time": "2026-10-17T13:55:00+05:30"})
            _, radius = await call(c, "blast_radius", {"tenant": "acme", "source": "webhook"})
            return cur, then, radius
    cur, then, radius = run(go)
    assert "flush-cache" not in {b["value"] for b in cur["beliefs"]}
    assert "flush-cache" in {b["value"] for b in then["beliefs"]}
    assert radius["facts"] == []


def test_errors_are_readable(tmp_path):
    story(2, tmp_path / "s.json")

    async def go():
        async with Client(mcp) as c:
            return [await call(c, "current_beliefs", {"tenant": "nobody", "subject": "x"}),
                    await call(c, "current_beliefs", {"tenant": "Bad Name"}),
                    await call(c, "explain_fact", {"tenant": "acme", "fact_id": "f-00000000"}),
                    await call(c, "beliefs_at", {"tenant": "acme", "time": "yesterday"}),
                    await call(c, "beliefs_at", {"tenant": "acme", "time": "2026-10-17T13:55:00"}),
                    await call(c, "blast_radius", {"tenant": "acme", "source": "nowhere"}),
                    await call(c, "beliefs_at", {"tenant": "acme", "time": "1792143300000"})]
    out = run(go)
    assert [e for e, _ in out] == [True, True, True, True, True, True, False]
    assert "has no memory yet" in out[0][1] and "invalid tenant" in out[1][1]
    assert "no fact" in out[2][1] and "ISO 8601" in out[3][1] and "UTC offset" in out[4][1]
    assert "unknown source" in out[5][1]


# ---------------------------------------------------------------- real processes

def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def tcp_falkordb(monkeypatch, tmp_path):
    """An embedded FalkorDB listening on TCP, so other processes can reach it."""
    port = free_port()
    lite = LiteFalkorDB(os.path.join(tempfile.mkdtemp(), "tcp.db"), serverconfig={"port": str(port)})
    monkeypatch.setattr(db, "_db", lite)
    yield port
    lite.close()


def test_stdio_server_process(tcp_falkordb, tmp_path):
    """Start `python -m memledger.mcp_server` as Claude Desktop would and query it."""
    story(5, tmp_path / "s.json")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "memledger.mcp_server"], cwd=str(ROOT),
        env={**os.environ, "FALKORDB_HOST": "127.0.0.1", "FALKORDB_PORT": str(tcp_falkordb),
             "PYTHONPATH": str(ROOT)})

    async def go():
        async with Client(params) as c:
            return await call(c, "current_beliefs", {"tenant": "acme"})
    err, cur = run(go)
    assert not err and "bad-deploy-v2.3.1" in {b["value"] for b in cur["beliefs"]}


OFFICIAL = os.getenv("FALKORDB_MCP_JS")   # path to @falkordb/mcpserver's dist/index.js


@pytest.mark.skipif(not OFFICIAL, reason="set FALKORDB_MCP_JS to test the official FalkorDB MCP server")
def test_official_server_strict_read_only(tcp_falkordb, tmp_path):
    story(9, tmp_path / "s.json")
    schema.seed("scratch")

    def params(**env):
        return StdioServerParameters(command="node", args=[OFFICIAL], env={
            **os.environ, "FALKORDB_HOST": "127.0.0.1", "FALKORDB_PORT": str(tcp_falkordb), **env})

    q = "MATCH (f:Fact {subject:'inc-42', status:'active'}) RETURN f.predicate, f.object"

    async def go(p):
        async with Client(p) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            ro = await c.call_tool("query_graph_readonly", {"graphName": "memory_acme", "query": q})
            write = await c.call_tool("query_graph", {"graphName": "memory_acme",
                                                      "query": "CREATE (:Probe) RETURN 1", "readOnly": False})
            delete = await c.call_tool("delete_graph", {"graphName": "memory_scratch", "confirmDelete": True})
            return names, ro, write, delete

    names, ro, write, delete = run(lambda: go(params(FALKORDB_DEFAULT_READONLY="true",
                                                     FALKORDB_STRICT_READONLY="true")))
    assert {"query_graph_readonly", "query_graph", "delete_graph", "list_graphs"} <= names
    assert not ro.is_error and "bad-deploy-v2.3.1" in ro.content[0].text
    assert write.is_error and delete.is_error
    assert "memory_scratch" in db.get_db().list_graphs()

    # Without strict mode, "default read-only" does NOT stop a write or a delete.
    _, _, write2, delete2 = run(lambda: go(params(FALKORDB_DEFAULT_READONLY="true")))
    assert not write2.is_error and not delete2.is_error
    assert "memory_scratch" not in db.get_db().list_graphs()
```

---

Sources: [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) (the `claude mcp add` syntax); `@falkordb/mcpserver` 1.3.0 README and source on npm (tools, environment variables, read-only behavior, Claude Desktop config path).
