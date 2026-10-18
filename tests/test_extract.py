"""Extraction tests. No database, no network."""
import json

from memledger import extract as X


def claim(p, v, c="stated", e=None):
    return {"predicate": p, "value": v, "certainty": c, "evidence": e or v}


def run(claims, text):
    return X.validate({"claims": claims}, text)


TEXT = ("ALERT 09:58 payments-api p99 latency 4s. Severity: SEV-1. "
        "Investigator: connection pool exhausted on primary DB, could not acquire connection.")


def test_grounded_claim_kept():
    kept, dropped = run([claim("affects_service", "payments-api",
                               e="payments-api p99 latency 4s")], TEXT)
    assert [(c.predicate, c.value, c.certainty) for c in kept] == \
        [("affects_service", "payments-api", "stated")]
    assert dropped == []


def test_ungrounded_claim_dropped():
    kept, dropped = run([claim("root_cause", "ddos", e="traffic spike from a DDoS attack")], TEXT)
    assert kept == [] and dropped[0]["reason"] == "ungrounded"


def test_grounding_ignores_case_and_punctuation():
    kept, _ = run([claim("root_cause", "db pool exhaustion",
                         e="Connection pool exhausted on primary DB")], TEXT)
    assert kept[0].value == "db-pool-exhaustion"


def test_short_evidence_dropped():
    kept, dropped = run([claim("severity", "sev1", e="SEV")], TEXT)
    assert kept == [] and dropped[0]["reason"] == "ungrounded"


def test_statement_with_could_not_is_not_hedged():
    kept, _ = run([claim("root_cause", "db pool exhaustion",
                         e="pool exhausted on primary DB, could not acquire connection")], TEXT)
    assert kept[0].certainty == "stated"


def test_hedged_evidence_downgrades_stated():
    text = "This might be a DDoS from 1.2.3.4, unconfirmed."
    kept, _ = run([claim("root_cause", "ddos", e="might be a DDoS from 1.2.3.4")], text)
    assert kept[0].certainty == "suspected"


def test_url_question_mark_is_not_a_hedge():
    text = "Error rate spiked on GET /checkout?id=42 after the deploy of v2.3.1 caused it"
    kept, _ = run([claim("root_cause", "bad deploy v2.3.1",
                         e="GET /checkout?id=42 after the deploy of v2.3.1 caused it")], text)
    assert kept[0].certainty == "stated"


def test_severity_normalized():
    kept, _ = run([claim("severity", "SEV-1", e="Severity: SEV-1")], TEXT)
    assert kept[0].value == "sev1"
    kept, _ = run([claim("severity", "P0", e="Severity: SEV-1")], TEXT)
    assert kept[0].value == "sev1"
    kept, _ = run([claim("severity", "critical", e="Severity: SEV-1")], TEXT)
    assert kept[0].value == "sev1"


def test_value_outside_fixed_set_dropped():
    kept, dropped = run([claim("status", "on fire", e="payments-api p99 latency 4s")], TEXT)
    assert kept == [] and dropped[0]["reason"] == "bad_value"


def test_status_synonym():
    kept, _ = run([claim("status", "fixed", e="payments-api p99 latency 4s")], TEXT)
    assert kept[0].value == "resolved"


def test_value_too_long_dropped():
    long = "the primary database connection pool was exhausted because of many slow queries"
    kept, dropped = run([claim("root_cause", long, e="connection pool exhausted on primary DB")], TEXT)
    assert kept == [] and dropped[0]["reason"] == "bad_value"


def test_malformed_items_dropped():
    kept, dropped = run([{"predicate": "likes", "value": "x", "certainty": "stated", "evidence": "x"},
                         {"predicate": "severity", "value": "sev1"}], TEXT)
    assert kept == [] and [d["reason"] for d in dropped] == ["malformed", "malformed"]
    assert X.validate({"oops": 1}, TEXT)[1][0]["reason"] == "malformed"
    assert X.validate("not a dict", TEXT)[1][0]["reason"] == "malformed"


def test_duplicates_dropped():
    kept, dropped = run([claim("severity", "sev1", e="Severity: SEV-1"),
                         claim("severity", "SEV1", e="Severity: SEV-1")], TEXT)
    assert len(kept) == 1 and dropped[0]["reason"] == "duplicate"


def test_single_valued_last_stated_wins():
    text = "Root cause: DB pool exhaustion. Update: root cause is the bad deploy v2.3.1."
    kept, dropped = run([
        claim("root_cause", "db pool exhaustion", e="Root cause: DB pool exhaustion"),
        claim("root_cause", "bad deploy v2.3.1", e="root cause is the bad deploy v2.3.1"),
    ], text)
    assert [c.value for c in kept] == ["bad-deploy-v2.3.1"]
    assert dropped[0]["reason"] == "overridden_in_episode"


def test_multi_valued_keeps_all():
    text = "Impact on payments-api and also on checkout-web for EU users."
    kept, _ = run([claim("affects_service", "payments-api", e="Impact on payments-api and also"),
                   claim("affects_service", "checkout-web", e="also on checkout-web for EU users")], text)
    assert {c.value for c in kept} == {"payments-api", "checkout-web"}


def test_assert_then_rule_out_same_value_later_wins():
    text = "Root cause is DB pool exhaustion. After review, it is not DB pool exhaustion after all."
    kept, dropped = run([
        claim("root_cause", "db pool exhaustion", e="Root cause is DB pool exhaustion"),
        claim("root_cause", "db pool exhaustion", "ruled_out", e="it is not DB pool exhaustion after all"),
    ], text)
    assert [(c.value, c.certainty) for c in kept] == [("db-pool-exhaustion", "ruled_out")]
    assert dropped[0]["reason"] == "overridden_in_episode"


def test_kept_in_text_order():
    text = "Severity SEV-2 declared. Payments-api is degraded for all users."
    kept, _ = run([claim("affects_service", "payments-api", e="Payments-api is degraded for all users"),
                   claim("severity", "sev2", e="Severity SEV-2 declared")], text)
    assert [c.predicate for c in kept] == ["severity", "affects_service"]


def test_user_prompt_contains_known_values_and_fenced_text():
    p = X.build_user_prompt("hello", "inc-42", {"root_cause": ["db-pool-exhaustion"]})
    assert "INCIDENT: inc-42" in p
    assert "- root_cause: db-pool-exhaustion" in p
    assert p.endswith("<<<\nhello\n>>>")
    assert "(none yet)" in X.build_user_prompt("x", "inc-42", {})


# ---------------------------------------------------------------- Extractor

class FakeLLM:
    model = "fake"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, system, user):
        self.calls.append((system, user))
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


GOOD = json.dumps({"claims": [claim("severity", "sev1", e="Severity: SEV-1")]})


def test_cache_hit_skips_llm(tmp_path):
    llm = FakeLLM([GOOD])
    path = str(tmp_path / "cache.json")
    ex = X.Extractor(llm, cache_path=path, mode="live")
    assert ex.extract(TEXT, "INC-42")[0][0].value == "sev1"
    assert ex.extract(TEXT, "INC-42")[0][0].value == "sev1"
    assert len(llm.calls) == 1
    # a fresh extractor reads the saved cache, so cache_only works offline
    off = X.Extractor(None, cache_path=path, mode="cache_only", model_name="fake")
    assert off.extract(TEXT, "INC-42")[0][0].value == "sev1"


def test_cache_key_depends_on_known_values(tmp_path):
    llm = FakeLLM([GOOD, GOOD])
    ex = X.Extractor(llm, cache_path=str(tmp_path / "c.json"))
    ex.extract(TEXT, "INC-42", {})
    ex.extract(TEXT, "INC-42", {"severity": ["sev2"]})
    assert len(llm.calls) == 2


def test_old_prompt_version_cache_reused_only_when_non_empty(tmp_path, monkeypatch):
    """ext-v2 widened the scope rule: old non-empty answers stay valid, old empty ones are redone."""
    path = str(tmp_path / "c.json")
    old = X.Extractor(FakeLLM([GOOD, json.dumps({"claims": []})]), cache_path=path, model_name="fake")
    monkeypatch.setattr(X, "PROMPT_VERSION", "ext-v1")
    old.extract(TEXT, "INC-42")
    old.extract("Redis cluster down since 09:50.", "INC-42")
    monkeypatch.undo()
    new = X.Extractor(FakeLLM([GOOD]), cache_path=path, model_name="fake")
    assert new.extract(TEXT, "INC-42")[0][0].value == "sev1" and new.llm.calls == []
    new.extract("Redis cluster down since 09:50.", "INC-42")
    assert len(new.llm.calls) == 1        # the empty ext-v1 answer is not reused


def test_prompt_scopes_claims_to_the_filing_incident():
    """Text filed under the incident is in scope even when it never names it (acme webhook.json)."""
    p = X.SYSTEM_PROMPT
    assert "even when it never names it" in p and "different incident" in p
    assert "disagrees with KNOWN VALUES" in p and "recommended" in p
    assert "named in INCIDENT only" not in p


def test_cache_only_miss_is_reported_not_raised(tmp_path):
    ex = X.Extractor(None, cache_path=str(tmp_path / "c.json"), mode="cache_only")
    kept, dropped = ex.extract(TEXT, "INC-42")
    assert kept == [] and dropped[0]["reason"] == "extraction_failed"


def test_retries_then_succeeds():
    sleeps = []
    llm = FakeLLM([RuntimeError("429"), "not json", GOOD])
    ex = X.Extractor(llm, sleep=sleeps.append)
    kept, _ = ex.extract(TEXT, "INC-42")
    assert kept[0].value == "sev1" and sleeps == [1, 2] and len(llm.calls) == 3


def test_gives_up_after_attempts():
    llm = FakeLLM([RuntimeError("500")] * 3)
    ex = X.Extractor(llm, sleep=lambda s: None)
    kept, dropped = ex.extract(TEXT, "INC-42")
    assert kept == [] and dropped[0]["reason"] == "extraction_failed"


def test_prompt_sent_to_llm():
    llm = FakeLLM([GOOD])
    X.Extractor(llm).extract(TEXT, "INC-42", {"severity": ["sev2"]})
    system, user = llm.calls[0]
    assert system == X.SYSTEM_PROMPT
    assert "INCIDENT: inc-42" in user and "- severity: sev2" in user and TEXT in user


def test_gemini_adapter_sends_schema():
    seen = {}

    class Resp:
        text = GOOD

    class Models:
        def generate_content(self, **kw):
            seen.update(kw)
            return Resp()

    class Client:
        models = Models()

    llm = X.GeminiLLM(model="gemini-test", client=Client())
    assert llm("SYS", "USER") == GOOD
    cfg = seen["config"]
    assert seen["model"] == "gemini-test" and seen["contents"] == "USER"
    assert cfg.response_schema is X.ClaimList
    assert cfg.response_mime_type == "application/json"
    assert cfg.temperature == 0 and cfg.system_instruction == "SYS"


def test_schema_converts_for_gemini():
    """The SDK must accept ClaimList as a response schema (enums, no defaults)."""
    from google import genai
    from google.genai import _transformers as t
    s = t.t_schema(genai.Client(api_key="test")._api_client, X.ClaimList)
    item = s.properties["claims"].items
    assert set(item.properties["predicate"].enum) == {p.value for p in X.Predicate}
    assert item.properties["certainty"].enum == ["stated", "suspected", "ruled_out"]
    assert set(item.required) == {"predicate", "value", "certainty", "evidence"}
