"""Configuration for MemLedger. Values come from the environment (.env)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass

HOST = os.getenv("FALKORDB_HOST", "localhost")
PORT = int(os.getenv("FALKORDB_PORT", "6379"))
USERNAME = os.getenv("FALKORDB_USERNAME") or None
PASSWORD = os.getenv("FALKORDB_PASSWORD") or None

# Facts from sources below this trust are quarantined until corroborated.
TRUST_THRESHOLD = float(os.getenv("TRUST_THRESHOLD", "0.5"))

# Closed vocabulary. The extractor may only emit these predicates.
PREDICATES = frozenset({
    "root_cause", "affects_service", "status", "owner", "mitigation", "severity",
})

# Single-valued predicates hold one current value: a new trusted value
# supersedes the old one. Multi-valued predicates accumulate values.
SINGLE_VALUED = frozenset({"root_cause", "status", "owner", "severity"})
MULTI_VALUED = PREDICATES - SINGLE_VALUED

# Predicates with a fixed set of values. Anything else is dropped.
VALUE_SETS = {
    "severity": frozenset({"sev1", "sev2", "sev3", "sev4"}),
    "status": frozenset({"investigating", "identified", "mitigating", "monitoring", "resolved"}),
}
VALUE_SYNONYMS = {
    "severity": {"critical": "sev1", "high": "sev2", "medium": "sev3", "low": "sev4"},
    "status": {"open": "investigating", "investigation": "investigating",
               "root-cause-identified": "identified", "in-progress": "mitigating",
               "fix-deployed": "monitoring", "fixed": "resolved", "closed": "resolved"},
}

# Extraction (Gemini). EXTRACT_MODE: live | cache_only
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or None
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
# Rate limits (429/503): calls per model before giving up, and an optional
# model tried with the same policy once the main one is still rate-limited.
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "5"))
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL") or None
EXTRACT_MODE = os.getenv("EXTRACT_MODE", "live")
EXTRACT_CACHE = os.getenv("EXTRACT_CACHE", "data/.extract_cache.json")

# Canonical names for entities and values, applied after lowercasing.
ALIASES = {
    "payments-api-service": "payments-api",
    "payment-api": "payments-api",
    "payments": "payments-api",
    # value spellings seen from live Gemini (C3)
    "signing-certificate-expired": "expired-signing-certificate",
    "rotate-the-signing-certificate": "rotate-signing-certificate",
    "connection-pool-exhausted-on-primary-db": "db-pool-exhaustion",
    "connection-pool-exhausted": "db-pool-exhaustion",
    "connection-pool-exhaustion": "db-pool-exhaustion",
    "deploy-v2.3.1": "bad-deploy-v2.3.1",
    "roll-back-to-v2.3.0": "rollback-to-v2.3.0",
    "ddos-from-1.2.3.4": "ddos",
    "block-1.2.3.4-at-the-edge": "block-1.2.3.4-at-edge",
    "block-it-at-the-edge": "block-1.2.3.4-at-edge",  # "DDoS from 1.2.3.4, block it at the edge"
    "block-it-at-edge": "block-1.2.3.4-at-edge",
    "redis-cluster-down": "redis-outage",
    "flush-cache-on-all-nodes": "flush-cache",
}

# Deepest provenance chain followed by revoke() and why().
MAX_HOPS = 6
