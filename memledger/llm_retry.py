"""Rate-limit resilience for Gemini calls.

    resp = generate(client, model, contents=..., config=...)

Retries 429/RESOURCE_EXHAUSTED and 503/UNAVAILABLE, waiting the server's
suggested retryDelay when the error carries one, else exponential backoff
(2, 4, 8, ... capped at MAX_BACKOFF). When retries run out on a transient
error and a fallback model is configured, the fallback gets the same policy.
A daily-quota 429 (QuotaFailure quotaId like "...PerDay...") is not retried:
waiting won't help today, so it goes straight to the fallback model (or is
raised when there is none). Any other error is raised at once, unchanged.
"""
import random
import re
import time

from . import config

MAX_BACKOFF = 60.0
TRANSIENT_CODES = {429, 503}
TRANSIENT_STATUSES = {"RESOURCE_EXHAUSTED", "UNAVAILABLE"}
_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s")
_DAILY_RE = re.compile(r"per_?day|per[ -]day|daily", re.I)


def is_transient(e: BaseException) -> bool:
    """True for rate-limit / overload errors (google.genai.errors.APIError and look-alikes)."""
    return getattr(e, "code", None) in TRANSIENT_CODES or \
        getattr(e, "status", None) in TRANSIENT_STATUSES


def _find_delay(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "retryDelay" and isinstance(v, str):
                m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", v)
                if m:
                    return float(m.group(1))
            d = _find_delay(v)
            if d is not None:
                return d
    elif isinstance(obj, list):
        for v in obj:
            d = _find_delay(v)
            if d is not None:
                return d
    return None


def retry_delay(e: BaseException) -> float | None:
    """The server's suggested wait in seconds (RetryInfo.retryDelay), if any."""
    d = _find_delay(getattr(e, "details", None))
    if d is None:
        m = _DELAY_RE.search(str(e))
        d = float(m.group(1)) if m else None
    return d


def is_daily_quota(e: BaseException) -> bool:
    """True for a 429 caused by a per-day quota, which no short wait will clear."""
    if getattr(e, "code", None) != 429 and getattr(e, "status", None) != "RESOURCE_EXHAUSTED":
        return False
    return bool(_DAILY_RE.search(f"{getattr(e, 'details', '')} {e}"))


def with_retry(fn, *, attempts: int | None = None, sleep=time.sleep, jitter=random.random):
    """Call fn(), retrying transient errors up to `attempts` calls in total."""
    attempts = max(1, attempts if attempts is not None else config.GEMINI_MAX_RETRIES)
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            if not is_transient(e) or is_daily_quota(e) or i == attempts - 1:
                raise
            d = retry_delay(e)
            wait = d + jitter() if d is not None else min(2.0 ** (i + 1), MAX_BACKOFF)
            sleep(min(wait, MAX_BACKOFF + 1))


def generate(client, model: str, *, fallback: str | None = None, attempts: int | None = None,
             sleep=time.sleep, jitter=random.random, **kwargs):
    """client.models.generate_content with retries and an optional fallback model."""
    fallback = config.GEMINI_FALLBACK_MODEL if fallback is None else fallback
    models = [model] + ([fallback] if fallback and fallback != model else [])
    for n, m in enumerate(models):
        try:
            return with_retry(lambda: client.models.generate_content(model=m, **kwargs),
                              attempts=attempts, sleep=sleep, jitter=jitter)
        except Exception as e:
            if not is_transient(e) or n == len(models) - 1:
                raise
