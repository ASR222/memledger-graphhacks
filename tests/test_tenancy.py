import pytest

from memledger import db
from memledger import memory as m


def test_no_leak():
    m.log_episode("acme", id="e1", agent="triage", source="alerts",
                  session="s1", text="secret acme incident", now=100)
    m.write_fact("acme", id="f1", agent="triage", source="alerts", episode="e1",
                 subject="INC-42", predicate="severity", object="sev1", now=101)
    assert m.read_active("globex", "inc-42") == []
    assert m.all_active("globex") == []
    assert m.as_of("globex", 999) == []
    assert m.history("globex", "s1") == []
    assert m.why("globex", "f1") is None
    assert len(m.all_active("acme")) == 1


def test_revoke_is_tenant_scoped():
    for t in ("acme", "globex"):
        m.log_episode(t, id="e1", agent="triage", source="webhook",
                      session="s1", text="x", now=100)
        m.write_fact(t, id="f1", agent="triage", source="webhook", episode="e1",
                     subject="INC-1", predicate="severity", object="sev2", now=101)
    m.revoke("acme", "webhook", 200)
    assert m.all_active("acme") == []
    assert len(m.all_active("globex")) == 1


@pytest.mark.parametrize("bad", ["acme; DROP", "", "Acme", "a b", "../x", None])
def test_invalid_tenant(bad):
    with pytest.raises(ValueError):
        db.graph(bad)
