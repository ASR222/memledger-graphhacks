from memledger import memory as m, schema


def ep(i, src, t):
    m.log_episode("acme", id=i, agent="investigator", source=src, session="s1", text=i, now=t)


def test_reseed_keeps_compromised():
    m.revoke("acme", "webhook", 100)
    schema.seed("acme")
    assert m.source_info("acme", "webhook")["compromised"] is True


def test_promoted_fact_believed_only_from_promotion():
    ep("e1", "fwd-logs", 100)
    m.write_fact("acme", id="f1", agent="investigator", source="fwd-logs", episode="e1",
                 subject="INC-42", predicate="root_cause", object="ddos", now=101)
    m.promote("acme", "f1", 200)
    assert m.as_of("acme", 150) == []
    assert [f["id"] for f in m.as_of("acme", 250)] == ["f1"]


def test_revoked_while_quarantined_never_in_history():
    ep("e1", "fwd-logs", 100)
    m.write_fact("acme", id="f1", agent="investigator", source="fwd-logs", episode="e1",
                 subject="INC-42", predicate="root_cause", object="ddos", now=101)
    ep("e2", "webhook", 110)
    m.write_fact("acme", id="f2", agent="investigator", source="webhook", episode="e2",
                 subject="INC-42", predicate="severity", object="sev1", now=111)
    m.revoke("acme", "fwd-logs", 200)
    m.revoke("acme", "webhook", 200)
    assert [f["id"] for f in m.as_of("acme", 150)] == ["f2"]
