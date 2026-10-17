"""Scenario evaluation (EVL.md)."""
import json

import pytest

from memledger import evaluate as E
from memledger import scenario as S
from memledger import trust
from memledger.agents import team as team_mod
from memledger.agents import tools as tools_mod
from memledger.extract import Extractor
from memledger import queries as Q
from scripts import eval as cli

# The SCN.md §12 patch fixes time travel for claims that were never believed.
PATCHED = "revoked_from" in Q.REVOKE
LEDGER = 16 if PATCHED else 15


def rehearsal():
    sc = S.load("acme")
    return Extractor(S.GoldenLLM(sc), mode="live", model_name="golden"), S.OfflineChat()


@pytest.fixture(scope="module")
def result(tmp_path_factory, lite_server):
    from memledger import db
    db._db = lite_server
    for name in lite_server.list_graphs():
        lite_server.select_graph(name).delete()
    ex, llm = rehearsal()
    return E.run(ex, llm, "acme", state_path=tmp_path_factory.mktemp("e") / "s.json")


def by_id(res, qid):
    return next(r for r in res["rows"] if r["id"] == qid)


def test_scores(result):
    s = result["score"]
    assert result["questions"] == 16
    assert s == {"No shared memory (per-session log)": 4, "Shared log, last write wins": 5,
                 "Shared log + trust filter + delete on revoke": 8, "MemLedger": LEDGER}


def test_memledger_misses_at_most_q16(result):
    wrong = [r["id"] for r in result["rows"] if not r["correct"]["MemLedger"]]
    assert wrong == ([] if PATCHED else ["Q16"])
    if not PATCHED:
        assert by_id(result, "Q16")["answers"]["MemLedger"] == ["bad-deploy-v2.3.1", "redis-outage"]


@pytest.mark.xfail(not PATCHED, strict=True, reason="needs the as_of patch in SCN.md section 12")
def test_q16_after_patch(result):
    assert by_id(result, "Q16")["correct"]["MemLedger"]


def test_traps_catch_the_baselines(result):
    lww = "Shared log, last write wins"
    assert by_id(result, "Q6")["answers"][lww] == ["ddos"]                # untrusted poison wins
    assert by_id(result, "Q7")["answers"][lww] == ["resolved"]            # injection wins
    assert by_id(result, "Q9")["answers"]["Shared log + trust filter + delete on revoke"] == ["redis-outage"]
    assert by_id(result, "Q13")["answers"]["Shared log + trust filter + delete on revoke"] == []
    assert all(r["step_ok"] for r in result["rows"])


def test_stream_was_recorded_and_hooks_restored(result):
    assert result["revocations"] and result["revocations"][0][1] == "webhook"
    sources = {c["source"] for c in result["claims"]}
    assert {"alerts", "app-logs", "runbook", "fwd-logs", "webhook", "reasoning"} <= sources
    assert any(c["certainty"] == "ruled_out" for c in result["claims"])
    from memledger.ingest import ingest
    assert team_mod.ingest is ingest and tools_mod.ingest is ingest
    assert trust.revoke_source.__name__ == "revoke_source"


def test_table(result):
    md = E.table(result)
    assert md.splitlines()[0].startswith("| Q | Tests |") and f"**{LEDGER}/16**" in md


def claim(t, session, source, pred, value, cert="stated"):
    return E.Claim(t, session, source, "x", pred, value, cert)


def test_log_baseline_semantics():
    st = E.Stream(claims=[
        claim(1, "s1", "alerts", "root_cause", "a"),
        claim(2, "s2", "fwd-logs", "root_cause", "b"),
        claim(3, "s2", "webhook", "mitigation", "m1"),
        claim(4, "s2", "runbook", "mitigation", "m2"),
        claim(5, "s2", "runbook", "mitigation", "m1", "ruled_out"),
    ], revocations=[(6, "webhook")])
    tr = {"alerts": 0.9, "fwd-logs": 0.3, "webhook": 0.6, "runbook": 0.9}
    a, b, c = E.baselines(st, tr)
    cur = {"kind": "current", "predicate": "root_cause"}
    mit = {"kind": "current", "predicate": "mitigation"}
    assert b.answer(cur, 10, "s2") == {"b"}                 # newest wins
    assert c.answer(cur, 10, "s2") == {"a"}                 # untrusted filtered
    assert a.answer(cur, 10, "s1") == {"a"} and a.answer(cur, 10, "s2") == {"b"}
    assert b.answer(mit, 10, "s2") == {"m1", "m2"}          # ruled_out ignored, multi accumulates
    assert c.answer(mit, 10, "s2") == {"m2"}                # revoked source deleted
    assert c.answer(mit, 5, "s2") == {"m1", "m2"}           # before the revocation
    assert b.answer({"kind": "at", "predicate": "root_cause", "time": "1970-01-01T00:00:00.001+00:00"},
                    10, "s2") == {"a"}
    assert b.answer({"kind": "from_source", "source": "webhook"}, 10, "s2") == {"m1"}
    assert b.answer({"kind": "stale", "predicate": "mitigation"}, 10, "s2") == set()


def test_cli_writes_results(tmp_path, capsys):
    out = str(tmp_path / "res")
    assert cli.main(["--extract", "golden", "--agents", "offline", "--out", out]) == 0
    assert f"**{LEDGER}/16**" in capsys.readouterr().out
    data = json.loads(open(out + ".json").read())
    assert data["score"]["MemLedger"] == LEDGER and open(out + ".md").read().startswith("Mode:")
