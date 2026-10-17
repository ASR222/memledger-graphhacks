"""Tenancy and concurrency (TEN.md)."""
import json

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.client.client import Client

from memledger import memory as m
from memledger import tenancy
from memledger.api import create_app
from memledger.mcp_server import mcp
from scripts import bench


def ep(t, i, now, src="alerts"):
    return m.log_episode(t, id=i, agent="triage", source=src, session="s1", text=i, now=now)


def test_create_is_idempotent_and_never_resets():
    assert tenancy.create("newco") == {"tenant": "newco", "created": True}
    m.revoke("newco", "webhook", 100)
    assert tenancy.create("newco") == {"tenant": "newco", "created": False}
    assert m.source_info("newco", "webhook")["compromised"] is True
    assert "newco" in tenancy.names()


def test_stats_export_and_forget():
    ep("acme", "e1", 100)
    m.write_fact("acme", id="f1", agent="triage", source="alerts", episode="e1",
                 subject="INC-42", predicate="severity", object="sev1", now=101)
    st = tenancy.stats("acme")
    assert st["nodes"]["Agent"] == 3 and st["nodes"]["Fact"] == 1 and st["facts"] == {"active": 1}
    dump = tenancy.export("acme")
    json.dumps(dump)
    assert any(n["label"] == "Fact" for n in dump["nodes"])
    gone = tenancy.forget("acme")
    assert gone["deleted"] and gone["nodes"] >= 10 and gone["ms"] >= 0
    assert not tenancy.exists("acme") and m.all_active("globex") == []
    assert tenancy.forget("acme") == {"tenant": "acme", "deleted": False, "ms": 0.0, "nodes": 0}
    with pytest.raises(KeyError):
        tenancy.export("acme")


def test_same_ids_in_two_tenants_are_independent():
    for t, v in (("acme", "sev1"), ("globex", "sev3")):
        ep(t, "e1", 100)
        m.write_fact(t, id="f1", agent="triage", source="alerts", episode="e1",
                     subject="INC-1", predicate="severity", object=v, now=101)
    assert m.why("acme", "f1")["object"] == "sev1" and m.why("globex", "f1")["object"] == "sev3"
    m.revoke("acme", "alerts", 200)
    assert m.why("acme", "f1")["status"] == "revoked" and m.why("globex", "f1")["status"] == "active"


def test_i1_checker_catches_a_violation():
    ep("acme", "e1", 100)
    m.write_fact("acme", id="f1", agent="triage", source="alerts", episode="e1",
                 subject="INC-1", predicate="severity", object="sev1", now=101)
    assert tenancy.i1_violations("acme") == []
    m.graph("acme").query("CREATE (:Fact {id:'fx', subject:'inc-1', predicate:'severity', "
                          "object:'sev2', status:'active', valid_from:102})")
    v = tenancy.i1_violations("acme")
    assert len(v) == 1 and sorted(v[0]["objects"]) == ["sev1", "sev2"]


def test_api_and_mcp_cannot_cross_tenants(tmp_path):
    ep("acme", "e1", 100)
    m.write_fact("acme", id="f-0000aaaa", agent="triage", source="alerts", episode="e1",
                 subject="INC-42", predicate="severity", object="sev1", now=101)
    c = TestClient(create_app("golden", "offline", state_path=tmp_path / "d.json"))
    assert c.get("/api/acme/facts/f-0000aaaa/why").status_code == 200
    assert c.get("/api/globex/facts/f-0000aaaa/why").status_code == 404
    assert "f-0000aaaa" not in json.dumps(c.get("/api/globex/graph").json())

    async def go():
        async with Client(mcp) as cl:
            r = await cl.call_tool("explain_fact", {"tenant": "globex", "fact_id": "f-0000aaaa"})
            return r.is_error
    assert anyio.run(go)


def test_concurrent_threads_keep_invariants():
    res = bench.run(tenants=3, readers=6, writers=2, seconds=1.5)
    assert res["errors"] == 0, res["error_samples"]
    assert res["i1_violations"] == {} and res["cross_tenant_leaks"] == []
    assert res["writes"]["n"] > 20 and res["reads"]["n"] > 100
    assert set(res["facts"]) == {"bench0", "bench1", "bench2"}
    for t in ("bench0", "bench1", "bench2"):
        tenancy.forget(t)
