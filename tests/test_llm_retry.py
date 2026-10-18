"""Rate-limit resilience for Gemini calls: fake errors, fake sleep, no network."""
import pytest
from google.genai import errors

from memledger import extract as X
from memledger import llm_retry as R
from memledger.agents.llm import GeminiChat


def rate_limited(delay=None):
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}] if delay else []
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                              "message": "quota exceeded", "details": details}})


def daily_quota():
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                                "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}]},
               {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "82800s"}]
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                              "message": "quota exceeded", "details": details}})


def unavailable():
    return errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "overloaded"}})


class Resp:
    text = '{"claims": []}'


class Client:
    """generate_content pops one outcome per call: an exception to raise or a response."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.models_called = []
        self.models = self

    def generate_content(self, model, **kw):
        self.models_called.append(model)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def run(client, **kw):
    sleeps = []
    kw.setdefault("fallback", "")
    resp = R.generate(client, "main", sleep=sleeps.append, jitter=lambda: 0.5, contents="x", **kw)
    return resp, sleeps


def test_honors_retry_delay():
    client = Client([rate_limited("37s"), Resp()])
    resp, sleeps = run(client)
    assert isinstance(resp, Resp) and sleeps == [37.5]


def test_retry_delay_parsed_from_message_when_details_missing():
    e = RuntimeError("429 RESOURCE_EXHAUSTED. {'retryDelay': '12s'}")
    e.code = 429
    assert R.retry_delay(e) == 12.0 and R.retry_delay(rate_limited()) is None


def test_backs_off_without_retry_delay_and_caps():
    client = Client([unavailable()] * 6 + [Resp()])
    resp, sleeps = run(client, attempts=7)
    assert isinstance(resp, Resp) and sleeps == [2, 4, 8, 16, 32, 60]


def test_gives_up_after_n_attempts():
    client = Client([rate_limited()] * 3)
    with pytest.raises(errors.ClientError):
        run(client, attempts=3)
    assert client.models_called == ["main"] * 3


def test_falls_back_to_fallback_model():
    client = Client([rate_limited(), rate_limited(), Resp()])
    resp, sleeps = run(client, attempts=2, fallback="backup")
    assert isinstance(resp, Resp) and client.models_called == ["main", "main", "backup"]


def test_fallback_also_exhausted_raises():
    client = Client([rate_limited()] * 4)
    with pytest.raises(errors.ClientError):
        run(client, attempts=2, fallback="backup")
    assert client.models_called == ["main", "main", "backup", "backup"]


def test_non_transient_errors_not_retried():
    bad = errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "bad"}})
    client = Client([bad, Resp()])
    with pytest.raises(errors.ClientError):
        run(client, fallback="backup")
    assert client.models_called == ["main"]


def test_extractor_uses_retry_and_reports_failure_once(monkeypatch):
    monkeypatch.setattr(R.config, "GEMINI_MAX_RETRIES", 2)
    client = Client([rate_limited("1s")] * 2)
    sleeps = []
    llm = X.GeminiLLM(model="main", client=client, fallback_model="", sleep=sleeps.append)
    ex = X.Extractor(llm, sleep=sleeps.append)
    kept, dropped = ex.extract("Severity is sev1.", "INC-42")
    assert kept == [] and dropped[0]["reason"] == "extraction_failed"
    assert client.models_called == ["main", "main"] and len(sleeps) == 1 and 1 <= sleeps[0] < 2


def test_agent_chat_retries_rate_limits():
    from google.genai import types

    class Cand:
        content = types.Content(role="model", parts=[types.Part.from_text(text="hi")])

    class ChatResp:
        candidates = [Cand()]
        function_calls = None

    client = Client([rate_limited("3s"), ChatResp()])
    sleeps = []
    chat = GeminiChat(model="main", client=client, fallback_model="", sleep=sleeps.append)
    reply = chat.start("SYS", []).send("hello")
    assert reply.text == "hi" and len(sleeps) == 1 and client.models_called == ["main", "main"]


def test_daily_quota_detected():
    assert R.is_daily_quota(daily_quota())
    assert not R.is_daily_quota(rate_limited("30s")) and not R.is_daily_quota(unavailable())


def test_daily_quota_falls_back_without_sleeping():
    client = Client([daily_quota(), Resp()])
    resp, sleeps = run(client, attempts=5, fallback="backup")
    assert isinstance(resp, Resp) and sleeps == [] and client.models_called == ["main", "backup"]


def test_daily_quota_without_fallback_raises_at_once():
    client = Client([daily_quota(), Resp()])
    with pytest.raises(errors.ClientError):
        run(client, attempts=5)
    assert client.models_called == ["main"]
