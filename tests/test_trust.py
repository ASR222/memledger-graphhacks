"""Trust, quarantine and revocation (TRU.md)."""
import json

import pytest

from memledger import memory as m
from memledger import trust
from memledger.extract import Extractor
from memledger.ingest import ingest
from scripts import trust as cli

T = "acme"


def ep(id, agent, source, now):
    return m.log_episode(T, id=id, agent=agent, source=source, session="s1", text=id, now=now)


def w(id, agent, source, episode, predicate, obj, now, **kw):
    return m.write_fact(T, id=id, agent=agent, source=source, episode=episode,
                        subject="INC-42", predicate=predicate, object=obj, now=now, **kw)


def status(fid):
    return m.why(T, fid)["status"]


def poisoned_story():
    """webhook passes quarantine and gets built on by three agents."""
    ep("e0", "triage", "alerts", 100)
    w("f0", "triage", "alerts", "e0", "affects_service", "payments-api", 101)
    ep("e1", "triage", "webhook", 110)
    w("f1", "triage", "webhook", "e1", "severity", "sev1", 111)
    w("f2", "triage", "webhook", "e1", "mitigation", "flush cache", 112)
    ep("e2", "investigator", "runbook", 120)
    w("f3", "investigator", "runbook", "e2", "owner", "cache team", 121, parents=["f2"])
    ep("e3", "comms", "runbook", 130)
    w("f4", "comms", "runbook", "e3", "status", "mitigating", 131, parents=["f3", "f0"])
    ep("e4", "triage", "fwd-logs", 140)
    w("f5", "triage", "fwd-logs", "e4", "severity", "sev3", 141)  # quarantined dispute


# ---------------------------------------------------------------- trust model

def test_trust_table():
    poisoned_story()
    rows = {r["id"]: r for r in trust.trust_table(T)}
    assert [r["id"] for r in trust.trust_table(T)][:2] == ["alerts", "runbook"]
    assert rows["webhook"]["trusted"] and rows["webhook"]["active"] == 2
    assert not rows["fwd-logs"]["trusted"] and rows["fwd-logs"]["quarantined"] == 1
    m.revoke(T, "webhook", 200)
    rows = {r["id"]: r for r in trust.trust_table(T)}
    assert rows["webhook"]["compromised"] and not rows["webhook"]["trusted"]
    assert rows["webhook"]["revoked"] == 2 and rows["webhook"]["active"] == 0


def test_threshold_boundary(monkeypatch):
    from memledger import config
    monkeypatch.setattr(config, "TRUST_THRESHOLD", 0.6)
    ep("e1", "triage", "webhook", 100)          # trust 0.6: exactly at the threshold
    assert w("f1", "triage", "webhook", "e1", "severity", "sev2", 101)["status"] == "active"
    monkeypatch.setattr(config, "TRUST_THRESHOLD", 0.61)
    ep("e2", "triage", "webhook", 110)
    assert w("f2", "triage", "webhook", "e2", "mitigation", "x", 111)["status"] == "quarantined"


def test_set_trust_affects_future_writes_only():
    ep("e1", "triage", "app-logs", 100)
    w("f1", "triage", "app-logs", "e1", "severity", "sev2", 101)
    assert trust.set_trust(T, "app-logs", 0.2) == {"id": "app-logs", "trust": 0.2}
    assert status("f1") == "active"
    ep("e2", "triage", "app-logs", 110)
    assert w("f2", "triage", "app-logs", "e2", "mitigation", "x", 111)["status"] == "quarantined"


def test_set_trust_rejects_bad_input():
    with pytest.raises(ValueError):
        trust.set_trust(T, "alerts", 1.5)
    with pytest.raises(m.UnknownReference):
        trust.set_trust(T, "nowhere", 0.5)
    m.revoke(T, "webhook", 100)
    with pytest.raises(m.CompromisedSource):
        trust.set_trust(T, "webhook", 0.9)


# ---------------------------------------------------------------- quarantine

def test_quarantine_list_shows_disputes():
    poisoned_story()
    q = trust.quarantine(T)
    assert [x["id"] for x in q] == ["f5"]
    assert q[0]["sources"] == ["fwd-logs"] and q[0]["writer"] == "triage"
    assert q[0]["disputes"] == {"fact": "f1", "believed": "sev1"}


def test_quarantined_facts_are_invisible_everywhere_agents_look():
    poisoned_story()
    seen = {f["id"] for f in m.read_active(T, "inc-42")} | {f["id"] for f in m.all_active(T)}
    assert "f5" not in seen
    assert "f5" not in {f["id"] for f in m.as_of(T, 10**9)}


def test_operator_promote():
    poisoned_story()
    r = trust.promote(T, "f5", 300)
    assert r["closed"] == 1 and status("f5") == "active" and status("f1") == "closed"
    with pytest.raises(m.UnknownReference):
        trust.promote(T, "f5", 301)          # no longer quarantined


# ---------------------------------------------------------------- revocation

def test_blast_radius_is_a_dry_run_matching_revoke():
    poisoned_story()
    preview = trust.blast_radius(T, "webhook")
    ids = {f["id"] for f in preview["facts"]}
    assert ids == {"f1", "f2", "f3", "f4"}
    assert all(status(i) == "active" for i in ids)          # nothing changed
    assert preview["by_agent"] == {"triage": 2, "investigator": 1, "comms": 1}
    assert {f["id"]: f["direct"] for f in preview["facts"]} == \
        {"f1": True, "f2": True, "f3": False, "f4": False}
    assert (preview["direct"], preview["derived"]) == (2, 2)
    assert {f["id"]: f["hops"] for f in preview["facts"]}["f4"] == 3
    done = {f["id"] for f in m.revoke(T, "webhook", 200)}
    assert done == ids


def test_revoke_source_report():
    poisoned_story()
    r = trust.revoke_source(T, "webhook", 200)
    assert r["revoked"] == ["f1", "f2", "f3", "f4"]
    assert status("f0") == "active" and status("f5") == "quarantined"
    assert trust.blast_radius(T, "webhook")["facts"] == []   # second revoke finds nothing
    assert trust.revoke_source(T, "webhook", 300)["revoked"] == []


def test_revoke_reports_newly_stale_facts():
    ep("e1", "investigator", "app-logs", 100)
    w("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 101)
    w("f2", "investigator", "app-logs", "e1", "mitigation", "raise pool", 102, parents=["f1"])
    ep("e2", "investigator", "runbook", 110)
    w("f3", "investigator", "runbook", "e2", "root_cause", "bad deploy", 111)
    r = trust.revoke_source(T, "fwd-logs", 200)
    assert r["revoked"] == [] and [s["id"] for s in r["stale"]] == ["f2"]


def test_revoked_value_is_not_suggested_and_can_be_reasserted():
    poisoned_story()
    trust.revoke_source(T, "webhook", 200)
    assert "flush-cache" not in m.known_values(T, "inc-42").get("mitigation", [])
    ep("e9", "investigator", "runbook", 300)
    r = w("f9", "investigator", "runbook", "e9", "mitigation", "flush cache", 301)
    assert r["status"] == "active" and r["id"] == "f9"       # fresh fact, clean provenance
    assert m.why(T, "f9")["sources"] == ["runbook"]


def test_revoke_unknown_source():
    with pytest.raises(m.UnknownReference):
        trust.blast_radius(T, "nowhere")
    with pytest.raises(m.UnknownReference):
        trust.revoke_source(T, "nowhere", 1)


def test_as_of_still_shows_revoked_beliefs_for_their_window():
    poisoned_story()
    trust.revoke_source(T, "webhook", 200)
    before = {f["id"] for f in m.as_of(T, 150)}
    after = {f["id"] for f in m.as_of(T, 250)}
    assert {"f1", "f2", "f3", "f4"} <= before and not ({"f1", "f2", "f3", "f4"} & after)


# ---------------------------------------------------------------- role permissions

class Scripted:
    model = "scripted"

    def __init__(self, claims):
        self.claims = claims

    def __call__(self, system, user):
        return json.dumps({"claims": self.claims})


TEXT = "Root cause is deploy v2.3.1. Declaring SEV-1 for payments-api now."


def test_role_filter_drops_disallowed_predicates(tmp_path):
    claims = [{"predicate": "root_cause", "value": "bad deploy v2.3.1", "certainty": "stated",
               "evidence": "Root cause is deploy v2.3.1"},
              {"predicate": "severity", "value": "sev1", "certainty": "stated",
               "evidence": "Declaring SEV-1 for payments-api now"}]
    inner = Extractor(Scripted(claims), cache_path=str(tmp_path / "c.json"))
    r = ingest(T, extractor=trust.RoleFilteredExtractor(inner, "comms"), agent="comms",
               source="runbook", session="s1", subject="INC-42", text=TEXT, now=100)
    assert r["written"] == []
    assert {(d["reason"], d["item"]["predicate"]) for d in r["dropped"]} == \
        {("not_permitted", "root_cause"), ("not_permitted", "severity")}
    r = ingest(T, extractor=trust.RoleFilteredExtractor(inner, "triage"), agent="triage",
               source="alerts", session="s1", subject="INC-42", text=TEXT, now=110)
    assert [x["predicate"] for x in r["written"]] == ["severity"]


def test_role_table():
    assert trust.allowed("investigator", "root_cause")
    assert not trust.allowed("comms", "root_cause")
    assert not trust.allowed("stranger", "status")


# ---------------------------------------------------------------- CLI

def test_cli(capsys):
    poisoned_story()
    assert cli.main(["sources"]) == 0
    assert "webhook" in capsys.readouterr().out
    assert cli.main(["revoke", "webhook"]) == 1                    # dry run without --yes
    out = capsys.readouterr().out
    assert "4 fact(s) depend on webhook: 2 direct, 2 derived" in out and "Dry run" in out
    assert status("f1") == "active"
    assert cli.main(["revoke", "webhook", "--yes"]) == 0
    assert "Revoked 4 fact(s)" in capsys.readouterr().out
    assert cli.main(["quarantine"]) == 0
    assert "f5" in capsys.readouterr().out
