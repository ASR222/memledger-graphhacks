"""Conflict rules in the memory core."""
from memledger import memory as m

T = "acme"


def ep(id, agent, source, now):
    return m.log_episode(T, id=id, agent=agent, source=source, session="s1", text=id, now=now)


def w(id, agent, source, episode, predicate, obj, now, **kw):
    return m.write_fact(T, id=id, agent=agent, source=source, episode=episode,
                        subject="INC-42", predicate=predicate, object=obj, now=now, **kw)


def status(fid):
    return m.why(T, fid)["status"]


def test_multi_valued_values_coexist():
    ep("e1", "triage", "alerts", 100)
    w("f1", "triage", "alerts", "e1", "affects_service", "payments-api", 101)
    r = w("f2", "triage", "alerts", "e1", "affects_service", "checkout-web", 102)
    assert r["closed"] == 0
    assert {x["object"] for x in m.read_active(T, "inc-42")} == {"payments-api", "checkout-web"}


def test_single_valued_supersedes():
    ep("e1", "triage", "alerts", 100)
    w("f1", "triage", "alerts", "e1", "severity", "sev2", 101)
    r = w("f2", "triage", "alerts", "e1", "severity", "sev1", 102)
    assert r["closed"] == 1 and status("f1") == "closed"


def test_untrusted_contradiction_is_recorded_as_dispute():
    ep("e1", "investigator", "runbook", 100)
    w("f1", "investigator", "runbook", "e1", "root_cause", "bad deploy", 101)
    ep("e2", "investigator", "fwd-logs", 110)
    r = w("f2", "investigator", "fwd-logs", "e2", "root_cause", "ddos", 111)
    assert r["status"] == "quarantined" and r["conflicts"] == 1 and r["closed"] == 0
    assert status("f1") == "active"
    assert m.disputes(T) == [{"id": "f2", "subject": "inc-42", "predicate": "root_cause",
                              "claimed": "ddos", "against": "f1", "believed": "bad-deploy"}]


def test_promoted_dispute_supersedes_and_clears():
    ep("e1", "investigator", "app-logs", 100)
    w("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 101)
    ep("e2", "investigator", "fwd-logs", 110)
    w("f2", "investigator", "fwd-logs", "e2", "root_cause", "ddos", 111)
    ep("e3", "triage", "alerts", 120)
    r = w("f3", "triage", "alerts", "e3", "root_cause", "ddos", 121)
    assert r["promoted"] and r["closed"] == 1
    assert status("f1") == "closed" and m.disputes(T) == []


def test_multi_valued_quarantine_is_not_a_dispute():
    ep("e1", "triage", "alerts", 100)
    w("f1", "triage", "alerts", "e1", "mitigation", "rollback", 101)
    ep("e2", "triage", "fwd-logs", 110)
    r = w("f2", "triage", "fwd-logs", "e2", "mitigation", "block ip", 111)
    assert r["conflicts"] == 0 and m.disputes(T) == []
    m.promote(T, "f2", 120)
    assert status("f1") == "active" and status("f2") == "active"


def test_tentative_from_trusted_source_is_quarantined_then_confirmed():
    ep("e1", "investigator", "runbook", 100)
    w("f1", "investigator", "runbook", "e1", "root_cause", "db pool", 101)
    ep("e2", "investigator", "runbook", 110)
    r = w("f2", "investigator", "runbook", "e2", "root_cause", "bad deploy", 111, tentative=True)
    assert r["status"] == "quarantined" and r["conflicts"] == 1
    assert status("f1") == "active"
    ep("e3", "investigator", "runbook", 120)
    r = w("f3", "investigator", "runbook", "e3", "root_cause", "bad deploy", 121)
    assert r["id"] == "f2" and r["promoted"] and status("f1") == "closed"


def test_untrusted_echo_of_active_fact_is_ignored():
    ep("e1", "triage", "alerts", 100)
    w("f1", "triage", "alerts", "e1", "severity", "sev1", 101)
    ep("e2", "triage", "fwd-logs", 110)
    r = w("f2", "triage", "fwd-logs", "e2", "severity", "sev1", 111)
    assert r["ignored"] and not r["corroborated"]
    assert m.why(T, "f1")["sources"] == ["alerts"]
    # so revoking the junk source cannot take the true fact down
    assert m.revoke(T, "fwd-logs", 200) == []
    assert status("f1") == "active"


def test_retraction_closes_without_replacement():
    ep("e1", "investigator", "app-logs", 100)
    w("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 101)
    w("f2", "investigator", "app-logs", "e1", "mitigation", "raise pool size", 102, parents=["f1"])
    ep("e2", "investigator", "runbook", 200)
    closed = m.retract(T, agent="investigator", source="runbook", episode="e2",
                       subject="INC-42", predicate="root_cause", object="DB pool", now=201)
    assert closed == ["f1"] and status("f1") == "closed"
    assert [x["predicate"] for x in m.read_active(T, "inc-42")] == ["mitigation"]
    assert m.stale(T)[0]["id"] == "f2" and m.stale(T)[0]["now_believed"] is None
    assert [x["object"] for x in m.as_of(T, 150) if x["predicate"] == "root_cause"] == ["db-pool"]


def test_untrusted_retraction_does_nothing():
    ep("e1", "investigator", "runbook", 100)
    w("f1", "investigator", "runbook", "e1", "root_cause", "bad deploy", 101)
    ep("e2", "investigator", "fwd-logs", 110)
    assert m.retract(T, agent="investigator", source="fwd-logs", episode="e2",
                     subject="INC-42", predicate="root_cause", object="bad deploy", now=111) == []
    assert status("f1") == "active"


def test_retraction_ignores_quarantined():
    ep("e1", "investigator", "fwd-logs", 100)
    w("f1", "investigator", "fwd-logs", "e1", "root_cause", "ddos", 101)
    ep("e2", "investigator", "runbook", 110)
    assert m.retract(T, agent="investigator", source="runbook", episode="e2",
                     subject="INC-42", predicate="root_cause", object="ddos", now=111) == []
    assert status("f1") == "quarantined"


def test_known_values_exclude_revoked():
    ep("e1", "triage", "alerts", 100)
    w("f1", "triage", "alerts", "e1", "severity", "sev2", 101)
    ep("e2", "triage", "webhook", 110)
    w("f2", "triage", "webhook", "e2", "mitigation", "flush cache", 111)
    ep("e3", "triage", "fwd-logs", 120)
    w("f3", "triage", "fwd-logs", "e3", "root_cause", "ddos", 121)
    assert m.known_values(T, "INC-42") == {"severity": ["sev2"], "mitigation": ["flush-cache"],
                                           "root_cause": ["ddos"]}
    m.revoke(T, "webhook", 200)
    assert "mitigation" not in m.known_values(T, "INC-42")
