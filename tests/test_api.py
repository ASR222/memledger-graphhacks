"""HTTP API (API.md). Rehearsal mode: golden extraction, offline agents."""
import pytest
from fastapi.testclient import TestClient

from memledger.api import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app("golden", "offline", state_path=tmp_path / "demo.json", allow_reset=True)
    return TestClient(app)


def run_demo(client, tenant="acme", upto=None):
    assert client.post(f"/api/{tenant}/demo/reset").status_code == 200
    n = upto or len(client.get(f"/api/{tenant}/demo").json()["steps"])
    out = []
    for _ in range(n):
        r = client.post(f"/api/{tenant}/demo/next")
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


def test_health_and_tenants(client):
    assert client.get("/api/health").json() == {"ok": True, "extract": "golden", "agents": "offline",
                                                 "allow_reset": True}
    t = {x["tenant"]: x for x in client.get("/api/tenants").json()}
    assert t["acme"]["subject"] == "INC-42" and t["globex"]["subject"] == "INC-7"


def test_full_demo_over_http(client):
    run_demo(client, "globex")
    steps = run_demo(client, "acme")
    assert len(steps) == 15 and all(s["ok"] for s in steps)
    assert steps[10]["action"] == "revoke" and len(steps[10]["output"]["revoked"]) == 2
    assert client.get("/api/acme/demo").json()["last_step"] == 15
    r = client.post("/api/acme/demo/next")
    assert r.status_code == 409 and "finished" in r.json()["detail"]


def test_demo_needs_reset_first(client, lite_db):
    lite_db.select_graph("memory_acme").delete()
    assert client.post("/api/acme/demo/next").status_code == 409


def test_graph_shape(client):
    run_demo(client, upto=8)
    g = client.get("/api/acme/graph").json()
    ids = {n["id"] for n in g["nodes"]}
    assert all(l["source"] in ids and l["target"] in ids for l in g["links"])
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"agent", "source", "fact", "handoff"} <= kinds and "episode" not in kinds
    facts = [n for n in g["nodes"] if n["kind"] == "fact"]
    assert {n["status"] for n in facts} >= {"active", "closed", "quarantined"}
    types = {l["type"] for l in g["links"]}
    assert {"SUPERSEDES", "CONFLICTS_WITH", "DERIVED_FROM", "FROM_SOURCE", "WROTE", "CARRIES"} <= types
    with_eps = client.get("/api/acme/graph?episodes=true").json()
    assert any(n["kind"] == "episode" for n in with_eps["nodes"])


def test_graph_at_time(client):
    run_demo(client, upto=11)
    from memledger.scenario import iso_ms
    g = client.get(f"/api/acme/graph?at={iso_ms('2026-10-17T13:55:00+05:30')}").json()
    facts = {n["name"]: n for n in g["nodes"] if n["kind"] == "fact"}
    assert facts["mitigation = flush-cache"]["believed_at"] is True
    assert facts["root_cause = db-pool-exhaustion"]["believed_at"] is False
    early = client.get(f"/api/acme/graph?at={iso_ms('2026-10-17T10:05:00+05:30')}").json()
    assert "root_cause = bad-deploy-v2.3.1" not in {n["name"] for n in early["nodes"]}


def test_why_and_facts(client):
    run_demo(client, upto=5)
    active = client.get("/api/acme/facts").json()["active"]
    rc = next(f for f in active if f["predicate"] == "root_cause")
    w = client.get(f"/api/acme/facts/{rc['id']}/why").json()
    assert w["sources"] == ["runbook"] and w["replaced"] == ["db-pool-exhaustion"]
    assert [v["status"] for v in w["versions"]] == ["closed", "active"]
    assert client.get("/api/acme/facts/f-00000000/why").status_code == 404


def test_trust_routes(client):
    run_demo(client, upto=9)
    src = {s["id"]: s for s in client.get("/api/acme/sources").json()}
    assert src["webhook"]["trusted"] and not src["fwd-logs"]["trusted"]
    q = client.get("/api/acme/quarantine").json()
    assert any(x["object"] == "ddos" and x["disputes"] for x in q)
    radius = client.get("/api/acme/sources/webhook/blast-radius").json()
    rv = client.post("/api/acme/sources/webhook/revoke").json()
    assert sorted(f["id"] for f in radius["facts"]) == rv["revoked"]
    assert client.put("/api/acme/sources/webhook/trust", json={"trust": 0.9}).status_code == 409
    assert client.put("/api/acme/sources/app-logs/trust", json={"trust": 2}).status_code == 422
    assert client.get("/api/acme/sources/nowhere/blast-radius").status_code == 404
    ddos = next(x for x in q if x["object"] == "ddos")
    assert client.post(f"/api/acme/facts/{ddos['id']}/promote").json()["closed"] == 1
    assert client.get("/api/acme/disputes").json() == []


def test_agent_routes(client):
    client.post("/api/acme/demo/reset")
    r = client.post("/api/acme/observe", json={"session": "s1", "source": "alerts",
                                                "text": open("data/acme/alerts.json").read()})
    assert r.status_code == 200 and r.json()["agent"] == "triage"
    assert len(client.get("/api/acme/handoffs/comms").json()) == 1
    u = client.post("/api/acme/status-update", json={"session": "s1"}).json()
    assert u["citations"]["active"] and u["stored"]["stored"][0]["predicate"] == "status"
    assert client.get("/api/acme/handoffs/comms").json() == []
    a = client.post("/api/acme/ask", json={"agent": "comms", "session": "s1", "question": "Root cause?"})
    assert a.status_code == 200 and a.json()["tools"] == ["recall"]
    assert client.post("/api/acme/ask", json={"agent": "boss", "session": "s1", "question": "x"}).status_code == 422
    i = client.post("/api/acme/investigate", json={"session": "s1"}).json()
    assert i["stopped"] == "answered"
    assert client.get("/api/acme/history/s1").json()[0]["agent"] == "triage"
    assert client.post("/api/acme/observe", json={"session": "s1", "source": "nowhere",
                                                   "text": "x"}).status_code == 404


def test_as_of_route(client):
    run_demo(client, upto=11)
    from memledger.scenario import iso_ms
    r = client.get(f"/api/acme/as_of?t={iso_ms('2026-10-17T13:55:00+05:30')}").json()
    assert "flush-cache" in {f["object"] for f in r["facts"]}


def test_bad_tenants(client):
    assert client.get("/api/Bad;Name/graph").status_code == 422
    assert client.get("/api/nobody/graph?subject=x").status_code == 404
    assert client.get("/api/nobody/demo").status_code == 404


def test_reset_can_be_disabled(tmp_path):
    c = TestClient(create_app("golden", "offline", state_path=tmp_path / "d.json", allow_reset=False))
    assert c.post("/api/acme/demo/reset").status_code == 403


def test_ui_is_served(client):
    html = client.get("/").text
    assert "/static/vendor/force-graph.min.js" in html and "/static/app.js" in html
    for f in ("app.js", "style.css", "vendor/force-graph.min.js"):
        assert client.get(f"/static/{f}").status_code == 200
