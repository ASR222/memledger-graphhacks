import pytest

from memledger import memory as m

T = "acme"


def ep(id, agent, source, now, session="s1", text="..."):
    return m.log_episode(T, id=id, agent=agent, source=source,
                         session=session, text=text, now=now)


def fact(id, agent, source, episode, predicate, obj, now, subject="INC-42", parents=()):
    return m.write_fact(T, id=id, agent=agent, source=source, episode=episode,
                        subject=subject, predicate=predicate, object=obj,
                        now=now, parents=parents)


def status(fid):
    return m.why(T, fid)["status"]


def test_supersede():
    ep("e1", "investigator", "app-logs", 110)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool exhaustion", 111)
    ep("e2", "investigator", "runbook", 200, session="s2")
    r = fact("f2", "investigator", "runbook", "e2", "root_cause", "bad deploy v2.3.1", 201)
    assert r["closed"] == 1 and r["status"] == "active"
    assert status("f1") == "closed"
    assert [x["object"] for x in m.read_active(T, "inc-42")] == ["bad-deploy-v2.3.1"]
    assert m.why(T, "f2")["replaced"] == ["db-pool-exhaustion"]
    v = m.versions(T, "INC-42", "root_cause")
    assert [x["status"] for x in v] == ["closed", "active"] and v[0]["valid_to"] == 201


def test_quarantine_invisible():
    ep("e1", "investigator", "fwd-logs", 210)
    r = fact("f1", "investigator", "fwd-logs", "e1", "root_cause", "ddos", 211)
    assert r["status"] == "quarantined"
    assert m.read_active(T, "inc-42") == []
    assert m.as_of(T, 999) == []


def test_quarantined_does_not_close_active():
    ep("e1", "investigator", "runbook", 100)
    fact("f1", "investigator", "runbook", "e1", "root_cause", "bad deploy", 101)
    ep("e2", "investigator", "fwd-logs", 110)
    fact("f2", "investigator", "fwd-logs", "e2", "root_cause", "ddos", 111)
    assert status("f1") == "active"


def test_corroboration_promotes():
    ep("e1", "investigator", "app-logs", 100)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 101)
    ep("e2", "investigator", "fwd-logs", 110)
    fact("f2", "investigator", "fwd-logs", "e2", "root_cause", "ddos", 111)
    ep("e3", "triage", "alerts", 120)
    r = fact("f3", "triage", "alerts", "e3", "root_cause", "DDoS", 121)
    assert r == {"id": "f2", "status": "active", "closed": 1, "conflicts": 0,
                 "corroborated": True, "promoted": True, "ignored": False}
    assert status("f1") == "closed"
    assert set(m.why(T, "f2")["sources"]) == {"fwd-logs", "alerts"}


def test_low_trust_corroboration_stays_quarantined():
    ep("e1", "investigator", "fwd-logs", 100)
    fact("f1", "investigator", "fwd-logs", "e1", "root_cause", "ddos", 101)
    ep("e2", "triage", "fwd-logs", 110)
    r = fact("f2", "triage", "fwd-logs", "e2", "root_cause", "ddos", 111)
    assert r["status"] == "quarantined" and r["corroborated"]


def test_duplicate_corroborates():
    ep("e1", "triage", "alerts", 100)
    fact("f1", "triage", "alerts", "e1", "affects_service", "payments-api", 101)
    ep("e2", "investigator", "app-logs", 110)
    r = fact("f2", "investigator", "app-logs", "e2", "affects_service", "Payments API", 111)
    assert r["id"] == "f1" and r["corroborated"]
    assert len(m.read_active(T, "inc-42")) == 1
    assert m.read_active(T, "inc-42")[0]["writer"] == "triage"


def test_as_of():
    ep("e1", "investigator", "app-logs", 110)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 111)
    ep("e2", "investigator", "runbook", 200)
    fact("f2", "investigator", "runbook", "e2", "root_cause", "bad deploy", 201)
    assert [x["object"] for x in m.as_of(T, 150)] == ["db-pool"]
    assert [x["object"] for x in m.as_of(T, 250)] == ["bad-deploy"]
    assert m.as_of(T, 50) == []


def test_revoke_cascade():
    # unrelated, trusted
    ep("e0", "triage", "alerts", 100)
    fact("f0", "triage", "alerts", "e0", "affects_service", "payments-api", 101)
    # poisoned chain across three agents, three hops deep
    ep("e1", "triage", "webhook", 110)
    fact("f1", "triage", "webhook", "e1", "root_cause", "cache outage", 111)
    ep("e2", "investigator", "runbook", 120)
    fact("f2", "investigator", "runbook", "e2", "mitigation", "flush cache", 121, parents=["f1"])
    ep("e3", "comms", "runbook", 130)
    fact("f3", "comms", "runbook", "e3", "status", "mitigating", 131, parents=["f2"])
    ep("e4", "comms", "runbook", 140)
    fact("f4", "comms", "runbook", "e4", "owner", "cache team", 141, parents=["f3"])

    out = m.revoke(T, "webhook", 300)
    assert {r["id"] for r in out} == {"f1", "f2", "f3", "f4"}
    assert {r["writer"] for r in out} == {"triage", "investigator", "comms"}
    assert status("f0") == "active"
    assert [x["id"] for x in m.read_active(T, "inc-42")] == ["f0"]
    # history still shows what was believed before the revocation
    assert {x["id"] for x in m.as_of(T, 200)} == {"f0", "f1", "f2", "f3", "f4"}
    # a compromised source cannot write again
    ep("e5", "triage", "alerts", 310)
    with pytest.raises(m.CompromisedSource):
        fact("f5", "triage", "webhook", "e5", "root_cause", "x", 311)


def test_revoke_hits_episode_derived_facts():
    # facts reach the source through their Episode as well as directly
    ep("e1", "triage", "webhook", 110)
    fact("f1", "triage", "webhook", "e1", "severity", "sev1", 111)
    out = m.revoke(T, "webhook", 200)
    assert [r["id"] for r in out] == ["f1"]


def test_parent_must_be_active():
    ep("e1", "investigator", "fwd-logs", 100)
    fact("f1", "investigator", "fwd-logs", "e1", "root_cause", "ddos", 101)
    ep("e2", "investigator", "runbook", 110)
    with pytest.raises(m.InvalidParent):
        fact("f2", "investigator", "runbook", "e2", "mitigation", "block ip", 111, parents=["f1"])
    with pytest.raises(m.InvalidParent):
        fact("f3", "investigator", "runbook", "e2", "mitigation", "x", 112, parents=["nope"])


def test_why():
    ep("e1", "triage", "alerts", 100)
    fact("f1", "triage", "alerts", "e1", "root_cause", "bad deploy", 101)
    ep("e2", "investigator", "runbook", 110)
    fact("f2", "investigator", "runbook", "e2", "mitigation", "rollback", 111, parents=["f1"])
    w = m.why(T, "f2")
    assert w["agents"] == ["investigator"]
    assert w["sources"] == ["runbook"]
    assert set(w["upstream"]) == {"e2", "f1", "e1"}
    assert ["f2", "f1", "alerts"] in w["paths"]
    assert m.why(T, "missing") is None


def test_bad_predicate():
    ep("e1", "triage", "alerts", 100)
    with pytest.raises(ValueError):
        fact("f1", "triage", "alerts", "e1", "likes", "pizza", 101)


def test_unknown_references():
    with pytest.raises(m.UnknownReference):
        ep("e1", "ghost", "alerts", 100)
    ep("e1", "triage", "alerts", 100)
    with pytest.raises(m.UnknownReference):
        fact("f1", "triage", "nowhere", "e1", "severity", "sev1", 101)
    with pytest.raises(m.UnknownReference):
        fact("f1", "triage", "alerts", "missing-ep", "severity", "sev1", 101)


def test_history_and_snapshot():
    ep("e1", "triage", "alerts", 100, session="s1", text="p99 4s")
    ep("e2", "comms", "runbook", 90, session="s1", text="earlier")
    ep("e3", "comms", "runbook", 300, session="s2")
    assert [h["id"] for h in m.history(T, "s1")] == ["e2", "e1"]
    snap = m.snapshot(T)
    assert {n["label"] for n in snap["nodes"]} >= {"Agent", "Source", "Episode"}
    assert any(e["type"] == "LOGGED" for e in snap["edges"])


def test_stale_derived_facts():
    ep("e1", "investigator", "app-logs", 110)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 111)
    fact("f2", "investigator", "app-logs", "e1", "mitigation", "raise pool size", 112, parents=["f1"])
    assert m.stale(T) == []
    ep("e2", "investigator", "runbook", 200)
    fact("f3", "investigator", "runbook", "e2", "root_cause", "bad deploy", 201)
    s = m.stale(T)
    assert s == [{"id": "f2", "predicate": "mitigation", "object": "raise-pool-size",
                  "based_on": "f1", "based_on_value": "db-pool", "now_believed": "bad-deploy"}]
