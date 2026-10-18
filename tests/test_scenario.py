"""The scripted INC-42 demo and the globex tenant (SCN.md)."""
import json

import pytest

from memledger import memory as m
from memledger import scenario as S
from memledger.extract import Extractor, validate
from scripts import demo


def runner(tenant, tmp_path):
    sc = S.load(tenant)
    ex = Extractor(S.GoldenLLM(sc), mode="live", model_name="golden")
    r = S.Runner(sc, ex, S.OfflineChat(), state_path=tmp_path / "state.json")
    r.reset()
    return r


def test_scenarios_load_and_validate():
    for t in ("acme", "globex"):
        sc = S.load(t)
        assert sc["steps"][0]["n"] == 1


def test_bad_scenario_rejected(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "scenario.json").write_text(json.dumps({"tenant": "bad", "subject": "X", "steps": [
        {"n": 1, "session": "s1", "at": "2026-10-17T10:00:00+05:30", "action": "observe",
         "source": "alerts", "file": "missing.txt"}]}))
    with pytest.raises(S.ScenarioError, match="missing file"):
        S.load("bad", tmp_path)
    (d / "scenario.json").write_text(json.dumps({"tenant": "bad", "subject": "X", "steps": [
        {"n": 1, "session": "s1", "at": "2026-10-17T10:00:00+05:30", "action": "dance"}]}))
    with pytest.raises(S.ScenarioError, match="unknown action"):
        S.load("bad", tmp_path)


def test_golden_claims_are_grounded_and_valid():
    """Every reference claim survives the real validator against its file."""
    for t in ("acme", "globex"):
        sc = S.load(t)
        golden = json.loads((sc["dir"] / "golden_claims.json").read_text())
        for name, claims in golden.items():
            if name.startswith("_"):
                continue
            kept, dropped = validate({"claims": claims}, (sc["dir"] / name).read_text())
            assert dropped == [] and len(kept) == len(claims), (t, name, dropped)


def test_acme_story_all_checks_pass(tmp_path):
    r = runner("acme", tmp_path)
    results = r.run_until(len(r.sc["steps"]))
    failed = [(x.n, c["check"]) for x in results for c in x.checks if not c["ok"]]
    assert failed == []
    assert len(results) == 15 and all(x.checks for x in results)


def test_acme_story_details(tmp_path):
    r = runner("acme", tmp_path)
    res = {x.n: x for x in r.run_until(15)}
    # step 3: a conclusion citing the db-pool root cause
    assert res[3].output["tools"] == ["recall", "stale", "disputes", "conclude"]
    # step 5: runbook supersedes; its explicit "ruled out" finds nothing left to close
    o5 = res[5].output
    assert any(s["predicate"] == "root_cause" and s["replaced"] == 1 for s in o5["stored"])
    assert {d["reason"] for d in o5["dropped"]} == {"nothing_to_retract"}
    # step 6: the stale pool-size mitigation is ruled out
    assert "conclude" in res[6].output["tools"]
    # step 7: prompt injection lands in quarantine; the injected status is dropped by role
    assert {s["status"] for s in res[7].output["stored"]} == {"quarantined"}
    assert {(d["predicate"], d["reason"]) for d in res[7].output["dropped"]} == {("status", "not_permitted")}
    # step 9 vs 12: the update changes after the revoke
    assert "flush-cache" in res[9].output["text"] and "ddos" in res[9].output["text"]
    assert "flush" not in res[12].output["text"]
    assert "rollback-to-v2.3.0" in res[12].output["text"]
    # steps 10/11: preview and revoke agree
    assert {f["id"] for f in res[10].output["facts"]} == set(res[11].output["revoked"])
    # step 13: the why answer
    assert "replaced db-pool-exhaustion" in res[13].output["text"]
    assert "runbook" in res[13].output["text"]


def test_session_two_uses_new_team_objects(tmp_path, monkeypatch):
    made = []
    real = S.Team

    def spy(*a, **k):
        t = real(*a, **k)
        made.append(t)
        return t

    monkeypatch.setattr(S, "Team", spy)
    r = runner("acme", tmp_path)
    r.run_until(5)
    assert len({id(t) for t in made}) == 5


def test_timestamps_come_from_the_scenario(tmp_path):
    r = runner("acme", tmp_path)
    r.run_until(2)
    rc = next(f for f in m.read_active("acme", "inc-42") if f["predicate"] == "root_cause")
    assert rc["since"] == S.iso_ms("2026-10-17T10:04:00+05:30")


def test_globex_story_and_isolation(tmp_path):
    a = runner("acme", tmp_path)
    a.run_until(14)
    g = runner("globex", tmp_path)
    results = g.run_until(4)
    assert all(c["ok"] for x in results for c in x.checks)
    iso = a.run_step(15)
    assert iso.ok and iso.output["other_subject"] == "INC-7"
    assert {f["object"] for f in m.read_active("globex", "inc-7")} >= {"auth-service", "expired-signing-certificate"}


def test_steps_must_run_in_order(tmp_path):
    r = runner("acme", tmp_path)
    with pytest.raises(S.ScenarioError, match="next step is 1"):
        r.run_step(3)
    r.run_step(1)
    assert r.last_step() == 1
    r.reset()
    assert r.last_step() == 0 and m.all_active("acme") == []


def test_hard_check_failure_is_reported(tmp_path):
    r = runner("acme", tmp_path)
    r.sc["steps"][0]["expect"] = {"active": ["severity=sev4"]}
    res = r.run_step(1)
    assert not res.ok and res.checks[0] == {"check": "active: severity=sev4", "ok": False, "soft": False}


def test_soft_check_failure_only_warns(tmp_path):
    r = runner("acme", tmp_path)
    r.sc["steps"][0]["expect"] = {"soft": True, "active": ["owner"]}
    res = r.run_step(1)
    assert res.ok and len(res.warnings) == 1


def test_cli_rehearsal(tmp_path, capsys):
    state = str(tmp_path / "s.json")
    args = ["--extract", "golden", "--agents", "offline", "--state", state]
    assert demo.main(["--list"]) == 0
    assert "INC-42" in capsys.readouterr().out
    assert demo.main(args + ["--reset", "--until", "4"]) == 0
    out = capsys.readouterr().out
    assert "Step 4" in out and "hard checks all passed" in out
    assert demo.main(args + ["--step", "9"]) == 2
    assert "next step is 5" in capsys.readouterr().out
    assert demo.main(args + ["--all"]) == 0
    out = capsys.readouterr().out
    assert "Step 15" in out and "✗ mitigation = flush-cache" in out


def test_cache_mode_without_cache_reports_failures(tmp_path, monkeypatch):
    from memledger import config
    monkeypatch.setattr(config, "EXTRACT_CACHE", str(tmp_path / "none.json"))
    state = str(tmp_path / "s.json")
    rc = demo.main(["--extract", "cache", "--agents", "offline", "--state", state, "--reset", "--step", "1"])
    assert rc == 1            # extraction unavailable -> nothing stored -> hard check fails


def test_as_of_hides_claims_that_were_never_believed(tmp_path):
    r = runner("acme", tmp_path)
    res = {x.n: x for x in r.run_until(14)}
    then = {f"{f['predicate']}={f['object']}" for f in res[14].output["facts"]}
    assert "root_cause=redis-outage" not in then      # it was only ever quarantined
    assert "root_cause=ddos" not in then


def test_isolation_when_other_tenant_never_ran(tmp_path, lite_db):
    r = runner("acme", tmp_path)
    r.run_until(14)
    lite_db.select_graph("memory_globex").delete()
    res = r.run_step(15)
    assert res.ok and res.output["other_exists"] is False


def test_agent_rate_limit_fails_the_step_without_crashing(tmp_path, capsys):
    """A 429 that outlasts retries in an agent step is a failed step, not a traceback."""
    from google.genai import errors

    class RateLimitedChat:
        hint = None

        def start(self, system, tools):
            raise errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                                     "message": "quota exceeded"}})

    r = runner("acme", tmp_path)
    r.run_until(2)
    r.llm = RateLimitedChat()
    res = r.run_step(3)
    assert not res.ok and res.checks[0]["check"].startswith("agent model unavailable: 429")
    assert r.last_step() == 3            # the story can continue
    demo.show(res)
    assert "✗ agent model unavailable: 429 RESOURCE_EXHAUSTED" in capsys.readouterr().out


def test_agent_non_rate_limit_errors_still_raise(tmp_path):
    class Broken:
        hint = None

        def start(self, system, tools):
            raise ValueError("bug")

    r = runner("acme", tmp_path)
    r.run_until(2)
    r.llm = Broken()
    with pytest.raises(ValueError):
        r.run_step(3)
