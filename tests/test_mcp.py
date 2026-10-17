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
