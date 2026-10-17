# Mem.md — MemLedger Graph Model & Memory Core

Complete context for the memory core of **MemLedger** (GraphHacks 2026, Track 02: Agent Memory & Coordination). This is the source of truth for the graph model, the rules memory follows, every Cypher query, and the Python API that agents call.

**Status:** v2, 17 Oct 2026. Every file in section 11 was run against FalkorDB (embedded, via falkordblite): **23 memory-core tests passed**, and the full suite including `EXT.md`'s extraction, conflict and ingest tests is **67 passed**. Copy the files as they are.

**v2 changes (from EXT.md):** single- vs multi-valued predicates, disputes (`CONFLICTS_WITH`), tentative writes, explicit retraction (`retract`), untrusted echoes ignored, and new reads `known_values`, `disputes`, `source_info`, `fact_info`. If you built from v1, replace `config.py`, `queries.py` and `memory.py` with the versions below; `db.py` and `schema.py` are unchanged.

**Precedence:** if this file and `SETUP.md` section 5 disagree, this file wins. SETUP.md covers installing things; this file covers what the memory core is and how it behaves.

---

## 1. Scope

The memory core is three modules: `queries.py` (all Cypher), `memory.py` (the rules), and `schema.py` (indexes and seed data), plus `db.py` and `config.py`.

**It does:** store episodes and facts with provenance, supersede outdated facts, quarantine untrusted writes, promote corroborated facts, revoke everything derived from a bad source, answer "what do we believe now / then / and why", and keep tenants apart.

**It does not:** call an LLM, parse text, run HTTP, or decide which agent runs next. Extraction (`extract.py`), agents and the API sit on top and only ever call `memory.py`. Nothing outside `memory.py` sends Cypher, except `schema.py` at startup.

---

## 2. Design principles

1. **Memory is a ledger, not a blob.** Every belief records who wrote it, which source it came from, which episode and earlier facts it was derived from, when it became true, and what it replaced.
2. **Never delete beliefs.** Outdated facts are `closed`, poisoned ones are `revoked`. Both keep their `valid_to`. History stays queryable, which is what makes time travel and "why" possible.
3. **Resolution is deterministic.** Same subject + same predicate + different object is a contradiction; the newest active write wins. No LLM decides conflicts. (Research note: deterministic freshness rules beat LLM-based resolution on contradiction benchmarks.)
4. **Untrusted input waits.** Facts from sources below the trust threshold are stored as `quarantined`, invisible to agents, and cannot close trusted facts.
5. **One tenant, one graph.** Isolation is physical (`memory_acme`, `memory_globex`), not a `WHERE tenant = ...` filter that a bug can skip.
6. **Time comes from the caller.** Every write takes `now`. Nothing in the core reads the clock, so the scripted demo replays identically.
7. **The graph is load-bearing.** Revocation, provenance paths and supersession chains are graph traversals. Remove FalkorDB and those features stop existing, which is exactly what the hackathon's anti-decoration rule checks.

---

## 3. Graph model

### 3.1 Picture

```
                    (:Agent)
                    │      │
           LOGGED{at}      WROTE{at, corroborates?}
                    ▼      ▼
 (:Source) ◀─FROM_SOURCE─ (:Episode) ◀─DERIVED_FROM─ (:Fact) ─ABOUT─▶ (:Entity)
     ▲                                                │  │  │
     └──────────────FROM_SOURCE───────────────────────┘  │  │
                                                         │  │
                               DERIVED_FROM (fact→fact) ─┘  └─ SUPERSEDES (new→old)
```

### 3.2 Nodes

| Label | Properties | Created by | Meaning |
|---|---|---|---|
| `Agent` | `id`, `role` | `schema.seed` | A team member: `triage`, `investigator`, `comms` |
| `Source` | `id`, `kind`, `trust` (0–1), `compromised` (bool) | `schema.seed` | Where information comes from. `compromised` flips to true on revoke |
| `Episode` | `id`, `session`, `at`, `text` | `log_episode` | One raw agent turn. Conversation history and the root of provenance |
| `Entity` | `name` | `write_fact` (MERGE) | The thing a fact is about, e.g. `inc-42` |
| `Fact` | `id`, `subject`, `predicate`, `object`, `valid_from`, `valid_to`*, `status`, `trust`, `promoted_at`* | `write_fact` | One belief as a triple. *absent until set |

`Fact.trust` is a copy of the creating source's trust at write time, kept for display.

### 3.3 Edges

| Edge | From → To | Meaning |
|---|---|---|
| `LOGGED {at}` | Agent → Episode | This agent produced this turn |
| `WROTE {at, corroborates?}` | Agent → Fact | Original author (no `corroborates`) or a later agreeing agent (`corroborates: true`) |
| `FROM_SOURCE` | Episode → Source | Where the turn's input came from |
| `FROM_SOURCE` | Fact → Source | Every source that asserted this fact (one, or more after corroboration) |
| `DERIVED_FROM` | Fact → Episode | The turn the fact was extracted from |
| `DERIVED_FROM` | Fact → Fact | The fact was concluded from these earlier facts (`parents`) |
| `ABOUT` | Fact → Entity | The subject of the triple |
| `SUPERSEDES` | Fact → Fact | The new fact replaced this old one |
| `CONFLICTS_WITH {at}` | Fact → Fact | A quarantined claim contradicts this active belief (a dispute) |
| `RETRACTED {at}` | Agent → Fact | This agent ruled the fact out |
| `RETRACTS` | Episode → Fact | The turn in which it was ruled out |

### 3.4 Vocabulary

Predicates are a closed set (`config.PREDICATES`): `root_cause`, `affects_service`, `status`, `owner`, `mitigation`, `severity`. Anything else raises `ValueError`. Contradiction detection only works because two agents describing the same thing must use the same predicate.

**Cardinality** (`config.SINGLE_VALUED`): `root_cause`, `status`, `owner`, `severity` hold one current value, so a new trusted value supersedes the old. `affects_service` and `mitigation` are multi-valued: an incident can hit several services and have several mitigations, so new values add rather than replace. `severity` and `status` also have fixed value sets (`config.VALUE_SETS`); see EXT.md.

Subjects and objects are canonicalized by `canon()`: lowercase, trim, whitespace and underscores become `-`, then `config.ALIASES` maps known variants. `"Payments API"` and `"payments_api"` both become `payments-api`.

---

## 4. Fact lifecycle

```
                        source trust ≥ threshold
   write_fact ─────────────────────────────────▶  ACTIVE  ──newer active fact, same subject+predicate──▶ CLOSED
       │                                            ▲  │
       │ source trust < threshold                   │  └──── source revoked (any hop) ────────────────▶ REVOKED
       ▼                                            │
   QUARANTINED ── same triple from trusted source ──┘
       │
       └──── source revoked ─────────────────────────────────────────────────────────────────────────▶ REVOKED
```

| Status | Agents can read it? | In `as_of`? | Can be superseded? | `valid_to` |
|---|---|---|---|---|
| `active` | yes | yes | yes | absent |
| `quarantined` | no | never | no | absent |
| `closed` | no | for times before `valid_to` | already is | set |
| `revoked` | no | for times before `valid_to` | no | set |

### 4.1 Invariants (the tests check every one)

- **I1.** At most one `active` fact per (subject, predicate) at any time, for single-valued predicates. Multi-valued predicates can have many.
- **I2.** A quarantined write never changes an active fact.
- **I3.** Writing a triple that is already active creates no node. A trusted write adds a corroborating `WROTE` and `FROM_SOURCE`; an untrusted or tentative one is ignored (otherwise revoking a junk source that merely echoed a true fact would revoke the true fact).
- **I4.** A quarantined fact becomes active only when a source at or above the threshold asserts the same triple, or when `promote()` is called explicitly.
- **I5.** `parents` must exist and be `active`. You cannot build on a quarantined, closed or revoked belief.
- **I6.** Revoking a source revokes every `active` or `quarantined` fact connected to it through `FROM_SOURCE`/`DERIVED_FROM` within 6 hops, including facts that reach it only through their Episode.
- **I7.** A compromised source cannot write again (`CompromisedSource`).
- **I8.** Nothing is deleted. Closed and revoked facts remain visible to `as_of` for the period they were valid.
- **I9.** No query crosses tenants. Every function requires a tenant that matches `^[a-z][a-z0-9_]{0,40}$`.
- **I10.** Revoking does not reopen the fact a revoked fact superseded. After revoking a bad root cause, there is no active root cause until a new one is written. This is deliberate: the system should not quietly fall back to an old belief.
- **I11.** Closing a fact does not change facts derived from it. They stay active and are reported by `stale()` so an agent or human can re-check them. Revocation, by contrast, always cascades.

---

## 5. Time model

- `valid_from` = the `now` passed to the write. `valid_to` = the `now` of the close or revoke.
- A fact was believed at time `t` when `valid_from <= t < valid_to` (or `valid_to` absent).
- `Episode.at` and `WROTE.at` record when things were written.
- **Be accurate when describing this:** it is a validity window on one timeline, close to Graphiti's "invalidate, don't delete" approach. It is not full bi-temporal modeling (we don't store real-world time separately from record time). Say "temporal validity windows", not "bi-temporal", unless you add it.
- Use integer epoch milliseconds in production. Tests use small integers (100, 200, …) for readability.
- FalkorDB does not store null properties. `valid_to` is simply absent on live facts; queries test it with `IS NULL`.

---

## 6. Trust model

| Source | kind | trust | Role in the demo |
|---|---|---|---|
| `alerts` | alert_feed | 0.9 | Trusted signal; can promote quarantined facts |
| `runbook` | runbook | 0.9 | Trusted; delivers the session-2 correction |
| `app-logs` | log | 0.7 | Trusted; delivers the wrong session-1 root cause |
| `webhook` | integration | 0.6 | **Passes quarantine.** Agents build on it, then it is found compromised and revoked |
| `fwd-logs` | tool_output | 0.3 | **Always quarantined.** The obvious junk |

Threshold: `TRUST_THRESHOLD = 0.5` (env-configurable). Both poison paths are needed for the demo: quarantine handles junk you can spot, and revocation handles poison you only discover later, after other agents have built on it.

---

## 7. The write algorithm

`write_fact(tenant, agent, source, episode, subject, predicate, object, now, parents=(), id=None)` runs under a per-tenant lock:

```
1. predicate not in vocabulary            → ValueError
2. canonicalize subject and object
3. source missing                         → UnknownReference
   source compromised                     → CompromisedSource
   trusted = trust ≥ threshold AND not tentative
4. any parent missing or not active       → InvalidParent
5. same triple already ACTIVE
      trusted                             → CORROBORATE; return {corroborated: True}
      untrusted                           → return {ignored: True}   (nothing written)
6. same triple QUARANTINED                → CORROBORATE
      trusted                             → PROMOTE (single-valued: closes contradicting active fact); return {promoted: True}
      untrusted                           → return {status: quarantined, corroborated: True}
7. status = active if trusted else quarantined
8. WRITE_FACT
      single-valued + active              → closes contradicting active facts, SUPERSEDES
      single-valued + quarantined         → CONFLICTS_WITH contradicting active facts (a dispute)
      multi-valued                        → no conflict handling, values coexist
      agent or episode missing            → UnknownReference
9. LINK_PARENTS if parents
10. return {id, status, closed, conflicts, corroborated: False, promoted: False, ignored: False}
```

Return shape is always `{"id", "status", "closed", "conflicts", "corroborated", "promoted", "ignored"}`.

`retract(...)` is the second write path: a trusted source explicitly ruling a value out closes the matching active fact with no replacement (`retracted: true`, plus `RETRACTED`/`RETRACTS` edges). Untrusted retractions and retractions of quarantined facts do nothing. Agents should read `status`: if it is `quarantined`, tell the user the claim is pending.

---

## 8. Query reference

All queries live in `memledger/queries.py`. Reads run through `ro_query`.

| Query | Kind | What it does | What to tell judges |
|---|---|---|---|
| `INDEXES` | schema | Lookup indexes on ids and on Fact (subject, predicate, status); full-text on Episode text | The composite index makes contradiction checks an index lookup, not a scan |
| `SEED` | schema | Idempotent MERGE of agents and sources | — |
| `LOG_EPISODE` | write | Stores a turn and links it to agent and source | Persistent conversation history, already part of the provenance graph |
| `WRITE_FACT` | write | Creates the fact with WROTE/FROM_SOURCE/DERIVED_FROM/ABOUT edges; for single-valued predicates, closes contradicting active facts (SUPERSEDES) or, if quarantined, records CONFLICTS_WITH | Updating memory is one atomic graph write. Old beliefs are closed, not overwritten |
| `LINK_PARENTS` | write | Fact → Fact DERIVED_FROM edges | Records the reasoning chain that revocation later follows |
| `CORROBORATE` | write | Adds a source and a corroborating author to an existing fact | Agreement strengthens one node instead of creating duplicates |
| `PROMOTE` | write | Quarantined → active, then supersedes (single-valued only) | Untrusted claims enter memory only after independent confirmation |
| `RETRACT` | write | Closes an active fact that a trusted source ruled out, with no replacement | Agents can say "it's not X" without knowing what it is yet |
| `REVOKE` | write | Marks a source compromised and revokes every fact within 6 hops | **The key query.** One variable-length traversal retracts a lie and everything built on it, across all agents. A vector store cannot do this |
| `SOURCE_INFO` | read | Trust and compromised flag | — |
| `FIND_SAME` | read | Live facts with an identical triple | — |
| `PARENT_STATUS` | read | Status, subject and predicate of proposed parents | Enforces I5 |
| `KNOWN_VALUES` | read | Values already used per predicate for a subject (revoked excluded) | Fed to the extractor so the same thing gets the same name |
| `DISPUTES` | read | Quarantined claims that contradict an active belief | The UI shows contested facts instead of hiding them |
| `READ_ACTIVE` | read | Active facts about one entity, newest first, with original author | The only read agents use, so quarantined and revoked facts can't leak into answers |
| `ALL_ACTIVE` | read | Every active fact in the tenant | Comms uses this for status updates |
| `AS_OF` | read | Beliefs valid at time t | Time travel: "what did we believe at 3 PM?" |
| `FACT_VERSIONS` | read | Every version of a subject+predicate | Shows the supersession chain on screen |
| `WHY` | read | Authors, sources, everything upstream, values replaced | Every answer can explain itself |
| `WHY_PATHS` | read | Each path from a fact to a source, as id lists | Drives path highlighting in the UI |
| `STALE` | read | Active facts derived from a belief that has since been closed | "This mitigation was based on a root cause we no longer believe." Stale reasoning gets flagged, not silently kept |
| `HISTORY` | read | One session's episodes in order | — |
| `NODES`, `EDGES` | read | Whole graph for the UI | Demo-sized graphs only |

### 8.1 The three queries to know by heart

Judges may ask you to explain these without notes.

**WRITE_FACT, second half.**
```cypher
WITH f
OPTIONAL MATCH (old:Fact {subject:$subject, predicate:$predicate, status:'active'})
WHERE $single AND old.id <> f.id AND old.object <> $object
FOREACH (o IN CASE WHEN old IS NULL OR $status <> 'active' THEN [] ELSE [old] END |
  SET o.status = 'closed', o.valid_to = $now
  CREATE (f)-[:SUPERSEDES]->(o))
FOREACH (o IN CASE WHEN old IS NULL OR $status <> 'quarantined' THEN [] ELSE [old] END |
  CREATE (f)-[:CONFLICTS_WITH {at:$now}]->(o))
```
It finds any active fact that contradicts the new one (only for single-valued predicates, `$single`). `OPTIONAL MATCH` keeps the row alive when there is nothing to close; a plain `MATCH` would drop the row and the new fact would never be returned. `FOREACH` over a 0-or-1 element list is Cypher's "do this only if it exists". The first `FOREACH` runs only for active writes (supersede); the second only for quarantined ones (record a dispute, change nothing). That split is invariant I2.

**REVOKE.**
```cypher
MATCH (s:Source {id:$source})<-[:FROM_SOURCE|DERIVED_FROM*1..6]-(f:Fact)
WHERE f.status IN ['active','quarantined']
```
It walks backwards from the source along provenance edges, up to 6 hops, through episodes and derived facts. Hop 1 reaches facts cited directly from the source or episodes from it; hop 2 reaches facts extracted from those episodes; further hops reach facts concluded from those. `DISTINCT` then dedupes facts reachable by several paths.

**AS_OF.**
```cypher
WHERE f.valid_from <= $t AND (f.valid_to IS NULL OR f.valid_to > $t)
  AND f.status <> 'quarantined'
```
Because nothing is deleted and every change sets `valid_to`, any past state of memory can be reconstructed with one filter.

---

## 9. Python API (`memledger/memory.py`)

| Function | Returns | Raises |
|---|---|---|
| `log_episode(tenant, *, agent, source, session, text, now, id=None)` | episode id | `UnknownReference` |
| `write_fact(tenant, *, agent, source, episode, subject, predicate, object, now, parents=(), id=None, tentative=False)` | `{id, status, closed, conflicts, corroborated, promoted, ignored}` | `ValueError`, `UnknownReference`, `CompromisedSource`, `InvalidParent` |
| `retract(tenant, *, agent, source, episode, subject, predicate, object, now)` | closed fact ids | `ValueError`, `UnknownReference`, `CompromisedSource` |
| `promote(tenant, fact_id, now)` | `{id, closed}` | `UnknownReference` |
| `revoke(tenant, source, now)` | `[{id, subject, predicate, object, writer}]` | `UnknownReference` |
| `read_active(tenant, entity)` | `[{id, predicate, object, since, writer}]` | — |
| `all_active(tenant)` | `[{id, subject, predicate, object, since}]` | — |
| `as_of(tenant, t)` | `[{id, subject, predicate, object}]` | — |
| `versions(tenant, subject, predicate)` | `[{id, object, status, valid_from, valid_to}]` | — |
| `why(tenant, fact_id)` | `{id, subject, predicate, object, status, agents, sources, upstream, replaced, paths}` or `None` | — |
| `source_info(tenant, source)` | `{trust, compromised}` or `None` | — |
| `fact_info(tenant, ids)` | `[{id, status, subject, predicate}]` | — |
| `known_values(tenant, subject)` | `{predicate: [values]}` | — |
| `disputes(tenant)` | `[{id, subject, predicate, claimed, against, believed}]` | — |
| `stale(tenant)` | `[{id, predicate, object, based_on, based_on_value, now_believed}]` | — |
| `history(tenant, session)` | `[{id, agent, at, text}]` | — |
| `snapshot(tenant)` | `{nodes: [{nid, label, props}], edges: [{src, type, dst}]}` | — |
| `canon(value)` / `new_id(prefix)` | str | — |

All exception classes subclass `MemoryError_` (the trailing underscore avoids shadowing Python's built-in `MemoryError`). Every function validates the tenant via `db.graph()` and raises `ValueError` for a bad one.

### 9.1 How agents map onto it (Phase 4)

| Agent tool | Calls | Notes |
|---|---|---|
| `remember(text, parents=[])` | `ingest.ingest` (EXT.md) | Agents hand over text; extraction turns it into facts. Agent id, tenant, source, session and `now` are bound by the harness, never chosen by the LLM |
| `recall(entity)` | `read_active` | Only path to memory for agents |
| `history(session)` | `history` | |
| `why(fact_id)` | `why` | Comms cites fact ids in its update |

Revoke, promote and as_of are operator/UI actions, not agent tools.

---

## 10. Worked example — INC-42

This is the demo story, with the graph state after each step. `t` is the `now` value.

| t | Who | Source | Action | Result |
|---|---|---|---|---|
| 100 | triage | alerts | logs "p99 latency 4s on payments-api", writes `affects_service = payments-api` | f1 **active** |
| 110 | investigator | app-logs | writes `root_cause = db-pool-exhaustion` | f2 **active** |
| 112 | investigator | app-logs | writes `mitigation = raise-pool-size`, parents [f2] | f3 **active** |
| — | — | — | *session 1 ends; session 2 starts with empty chat state* | agents must `recall` |
| 200 | investigator | runbook | writes `root_cause = bad-deploy-v2.3.1` | f4 **active**, f2 **closed**, f4 SUPERSEDES f2 |
| — | UI | — | `stale()` | flags f3: `raise-pool-size` was based on `db-pool-exhaustion`, now believed `bad-deploy-v2.3.1` |
| 210 | investigator | fwd-logs | writes `root_cause = ddos` | f5 **quarantined**, f4 untouched |
| 220 | triage | webhook | writes `severity = sev1` (claims cache layer down too) | f6 **active** |
| 230 | comms | runbook | writes `status = mitigating`, parents [f4, f6] | f7 **active** |
| 300 | operator | — | `revoke("webhook")` | f6 and f7 **revoked**; Comms' next status update changes |
| any | — | — | `as_of(150)` | f1, f2, f3: the session-1 beliefs |
| any | — | — | `all_active()` after revoke | f1, f3, f4 |
| any | — | — | `why(f4)` | written by investigator, source runbook, replaced `db-pool-exhaustion` |

Make the revoke beat land: have at least 2–3 facts built on webhook data by different agents, so the revoke visibly removes several nodes at once.

---

## 11. Source files (tested)

Place these at the paths shown. They are the exact files that passed the test run.

### `memledger/config.py`
```python
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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EXTRACT_MODE = os.getenv("EXTRACT_MODE", "live")
EXTRACT_CACHE = os.getenv("EXTRACT_CACHE", "data/.extract_cache.json")

# Canonical names for entities and values, applied after lowercasing.
ALIASES = {
    "payments-api-service": "payments-api",
    "payment-api": "payments-api",
    "payments": "payments-api",
}

# Deepest provenance chain followed by revoke() and why().
MAX_HOPS = 6
```

### `memledger/db.py`
```python
"""FalkorDB connection and the graph-per-tenant rule."""
import re

from falkordb import FalkorDB

from . import config

_db = None  # tests replace this with an embedded falkordblite instance
_TENANT = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


def get_db():
    global _db
    if _db is None:
        _db = FalkorDB(host=config.HOST, port=config.PORT,
                       username=config.USERNAME, password=config.PASSWORD)
    return _db


def graph(tenant: str):
    """Return the tenant's graph. Each tenant is a separate FalkorDB graph."""
    if not isinstance(tenant, str) or not _TENANT.match(tenant):
        raise ValueError(f"invalid tenant: {tenant!r}")
    return get_db().select_graph(f"memory_{tenant}")
```

### `memledger/queries.py`
```python
"""Every Cypher query MemLedger depends on. The README lists these."""

# ---------------------------------------------------------------- schema

# Run once per tenant graph. Re-running raises "already indexed"; ignore it.
INDEXES = [
    "CREATE INDEX FOR (f:Fact) ON (f.id)",
    "CREATE INDEX FOR (f:Fact) ON (f.subject, f.predicate, f.status)",
    "CREATE INDEX FOR (s:Source) ON (s.id)",
    "CREATE INDEX FOR (a:Agent) ON (a.id)",
    "CREATE INDEX FOR (e:Entity) ON (e.name)",
    "CREATE INDEX FOR (ep:Episode) ON (ep.id)",
    "CREATE INDEX FOR (ep:Episode) ON (ep.session)",
    "CREATE FULLTEXT INDEX FOR (ep:Episode) ON (ep.text)",
]

# Seed the tenant's agents and sources. Idempotent.
SEED = """
UNWIND $agents AS a MERGE (x:Agent {id:a.id}) SET x.role = a.role
WITH count(*) AS _
UNWIND $sources AS s MERGE (y:Source {id:s.id})
SET y.kind = s.kind, y.trust = s.trust, y.compromised = false
"""

# ---------------------------------------------------------------- writes

# Store one agent turn as an Episode (persistent conversation history).
LOG_EPISODE = """
MATCH (a:Agent {id:$agent}), (src:Source {id:$source})
CREATE (ep:Episode {id:$id, session:$session, at:$now, text:$text})
CREATE (a)-[:LOGGED {at:$now}]->(ep)
CREATE (ep)-[:FROM_SOURCE]->(src)
RETURN ep.id AS id
"""

# Create a Fact with full provenance. For single-valued predicates
# ($single = true): an active new fact closes every active fact with the same
# subject+predicate and a different object (SUPERSEDES); a quarantined new fact
# only records CONFLICTS_WITH against them. Multi-valued facts never conflict.
WRITE_FACT = """
MATCH (a:Agent {id:$agent}), (src:Source {id:$source}), (ep:Episode {id:$episode})
MERGE (e:Entity {name:$subject})
CREATE (f:Fact {id:$id, subject:$subject, predicate:$predicate, object:$object,
                valid_from:$now, status:$status, trust:src.trust})
CREATE (a)-[:WROTE {at:$now}]->(f)
CREATE (f)-[:FROM_SOURCE]->(src)
CREATE (f)-[:DERIVED_FROM]->(ep)
CREATE (f)-[:ABOUT]->(e)
WITH f
OPTIONAL MATCH (old:Fact {subject:$subject, predicate:$predicate, status:'active'})
WHERE $single AND old.id <> f.id AND old.object <> $object
FOREACH (o IN CASE WHEN old IS NULL OR $status <> 'active' THEN [] ELSE [old] END |
  SET o.status = 'closed', o.valid_to = $now
  CREATE (f)-[:SUPERSEDES]->(o))
FOREACH (o IN CASE WHEN old IS NULL OR $status <> 'quarantined' THEN [] ELSE [old] END |
  CREATE (f)-[:CONFLICTS_WITH {at:$now}]->(o))
WITH f, count(old) AS n
RETURN f.id AS id,
       CASE WHEN $status = 'active' THEN n ELSE 0 END AS closed,
       CASE WHEN $status = 'quarantined' THEN n ELSE 0 END AS conflicts
"""

# Record that a fact was concluded from earlier facts. Revocation follows these.
LINK_PARENTS = """
MATCH (f:Fact {id:$id})
UNWIND $parents AS pid
MATCH (p:Fact {id:pid})
CREATE (f)-[:DERIVED_FROM]->(p)
RETURN count(p) AS linked
"""

# Another agent or source asserts a triple that already exists: add provenance,
# create no new Fact.
CORROBORATE = """
MATCH (f:Fact {id:$id}), (src:Source {id:$source}), (a:Agent {id:$agent})
MERGE (f)-[:FROM_SOURCE]->(src)
CREATE (a)-[:WROTE {at:$now, corroborates:true}]->(f)
RETURN f.id AS id
"""

# Move a quarantined fact to active and, for single-valued predicates,
# supersede whatever it contradicts.
PROMOTE = """
MATCH (q:Fact {id:$id, status:'quarantined'})
SET q.status = 'active', q.promoted_at = $now
WITH q
OPTIONAL MATCH (old:Fact {subject:q.subject, predicate:q.predicate, status:'active'})
WHERE q.predicate IN $single_preds AND old.id <> q.id AND old.object <> q.object
FOREACH (o IN CASE WHEN old IS NULL THEN [] ELSE [old] END |
  SET o.status = 'closed', o.valid_to = $now
  CREATE (q)-[:SUPERSEDES]->(o))
RETURN q.id AS id, count(old) AS closed
"""

# Explicit retraction ("ruled out X"): close the matching active fact without
# a replacement and record who retracted it, from which episode.
RETRACT = """
MATCH (f:Fact {subject:$subject, predicate:$predicate, object:$object, status:'active'})
MATCH (a:Agent {id:$agent}), (ep:Episode {id:$episode})
SET f.status = 'closed', f.valid_to = $now, f.retracted = true
CREATE (a)-[:RETRACTED {at:$now}]->(f)
CREATE (ep)-[:RETRACTS]->(f)
RETURN f.id AS id
"""

# Blast-radius revocation. Mark the source compromised, then revoke every live
# fact that reaches it through FROM_SOURCE / DERIVED_FROM within 6 hops.
REVOKE = """
MATCH (s:Source {id:$source})
SET s.compromised = true
WITH s
MATCH (s)<-[:FROM_SOURCE|DERIVED_FROM*1..6]-(f:Fact)
WHERE f.status IN ['active','quarantined']
WITH DISTINCT f
SET f.status = 'revoked', f.valid_to = $now
WITH f
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
WHERE w.corroborates IS NULL
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, a.id AS writer
"""

# ---------------------------------------------------------------- reads

# Trust and compromise flag for one source.
SOURCE_INFO = """
MATCH (s:Source {id:$id})
RETURN s.trust AS trust, s.compromised AS compromised
"""

# Facts with this exact triple that are still live.
FIND_SAME = """
MATCH (f:Fact {subject:$subject, predicate:$predicate, object:$object})
WHERE f.status IN ['active','quarantined']
RETURN f.id AS id, f.status AS status
"""

# Status, subject and predicate of the facts a new fact is derived from.
PARENT_STATUS = """
UNWIND $ids AS pid
OPTIONAL MATCH (p:Fact {id:pid})
RETURN pid AS id, p.status AS status, p.subject AS subject, p.predicate AS predicate
"""

# Values already used for a subject, per predicate (revoked values excluded).
# Fed to the extractor so it reuses existing spellings.
KNOWN_VALUES = """
MATCH (f:Fact {subject:$subject})
WHERE f.status <> 'revoked'
RETURN f.predicate AS predicate, collect(DISTINCT f.object) AS values
"""

# Quarantined claims that contradict a current belief.
DISPUTES = """
MATCH (q:Fact {status:'quarantined'})-[:CONFLICTS_WITH]->(a:Fact {status:'active'})
RETURN q.id AS id, q.subject AS subject, q.predicate AS predicate,
       q.object AS claimed, a.id AS against, a.object AS believed
ORDER BY q.valid_from
"""

# Current beliefs about one entity. The only read path agents use.
READ_ACTIVE = """
MATCH (f:Fact {status:'active'})-[:ABOUT]->(e:Entity {name:$entity})
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
WHERE w.corroborates IS NULL
RETURN f.id AS id, f.predicate AS predicate, f.object AS object,
       f.valid_from AS since, a.id AS writer
ORDER BY f.valid_from DESC
"""

# Every current belief in the tenant (Comms uses this for status updates).
ALL_ACTIVE = """
MATCH (f:Fact {status:'active'})
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, f.valid_from AS since
ORDER BY f.subject, f.predicate
"""

# What the team believed at time $t. Closed and revoked facts appear if they
# were valid then. Quarantined facts never appear.
AS_OF = """
MATCH (f:Fact)
WHERE f.valid_from <= $t AND (f.valid_to IS NULL OR f.valid_to > $t)
  AND f.status <> 'quarantined'
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate, f.object AS object
ORDER BY f.subject, f.predicate
"""

# Every version of one subject+predicate, oldest first (the supersession chain).
FACT_VERSIONS = """
MATCH (f:Fact {subject:$subject, predicate:$predicate})
RETURN f.id AS id, f.object AS object, f.status AS status,
       f.valid_from AS valid_from, f.valid_to AS valid_to
ORDER BY f.valid_from
"""

# Why is this believed? Writer, sources, everything upstream, values replaced.
WHY = """
MATCH (f:Fact {id:$id})
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
OPTIONAL MATCH (f)-[:FROM_SOURCE]->(s:Source)
OPTIONAL MATCH (f)-[:DERIVED_FROM*1..6]->(up)
OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Fact)
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, f.status AS status,
       collect(DISTINCT a.id) AS agents,
       collect(DISTINCT s.id) AS sources,
       collect(DISTINCT up.id) AS upstream,
       collect(DISTINCT old.object) AS replaced
"""

# Each path from a fact to a source behind it, as node-id lists (UI highlighting).
WHY_PATHS = """
MATCH p = (f:Fact {id:$id})-[:FROM_SOURCE|DERIVED_FROM*1..6]->(s:Source)
RETURN [n IN nodes(p) | coalesce(n.id, n.name)] AS path
"""

# Active facts built on a belief that has since been closed (stale reasoning).
STALE = """
MATCH (f:Fact {status:'active'})-[:DERIVED_FROM*1..6]->(p:Fact {status:'closed'})
OPTIONAL MATCH (p)<-[:SUPERSEDES]-(n:Fact)
RETURN DISTINCT f.id AS id, f.predicate AS predicate, f.object AS object,
       p.id AS based_on, p.object AS based_on_value, n.object AS now_believed
"""

# Conversation history for one session.
HISTORY = """
MATCH (a:Agent)-[:LOGGED]->(ep:Episode {session:$session})
RETURN ep.id AS id, a.id AS agent, ep.at AS at, ep.text AS text
ORDER BY ep.at
"""

# Whole graph for the UI (demo-sized graphs only).
NODES = """
MATCH (n)
RETURN ID(n) AS nid, labels(n)[0] AS label, properties(n) AS props
"""
EDGES = """
MATCH (a)-[r]->(b)
RETURN ID(a) AS src, type(r) AS type, ID(b) AS dst
"""
```

### `memledger/schema.py`
```python
"""Indexes and seed data for a tenant graph."""
from . import queries as Q
from .db import graph

AGENTS = [
    {"id": "triage", "role": "triage"},
    {"id": "investigator", "role": "investigator"},
    {"id": "comms", "role": "comms"},
]

SOURCES = [
    {"id": "alerts",   "kind": "alert_feed",  "trust": 0.9},
    {"id": "runbook",  "kind": "runbook",     "trust": 0.9},
    {"id": "app-logs", "kind": "log",         "trust": 0.7},
    {"id": "webhook",  "kind": "integration", "trust": 0.6},  # passes quarantine; revoked in the demo
    {"id": "fwd-logs", "kind": "tool_output", "trust": 0.3},  # always quarantined
]


def seed(tenant: str) -> None:
    g = graph(tenant)
    for q in Q.INDEXES:
        try:
            g.query(q)
        except Exception as e:  # re-running is fine
            if "already indexed" not in str(e).lower():
                raise
    g.query(Q.SEED, {"agents": AGENTS, "sources": SOURCES})
```

### `memledger/memory.py`
```python
"""MemLedger memory core: the only module that talks to the graph.

Every function takes a tenant. Every write takes `now` (epoch ms) from the
caller, so the scripted demo replays identically.
"""
import re
import threading
import uuid
from collections import defaultdict

from . import config
from . import queries as Q
from .db import graph

# FalkorDB serializes writes per graph, but write_fact is several queries
# (check, then write). This lock makes that sequence atomic per tenant within
# one process. Run a single API process.
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


class MemoryError_(Exception):
    """Base error for memory-rule violations."""


class CompromisedSource(MemoryError_):
    pass


class UnknownReference(MemoryError_):
    pass


class InvalidParent(MemoryError_):
    pass


def canon(value: str) -> str:
    """Lowercase, trim, join words with '-', then apply aliases."""
    v = re.sub(r"[\s_]+", "-", str(value).strip().lower())
    return config.ALIASES.get(v, v)


def new_id(prefix: str = "f") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _rows(res) -> list[dict]:
    names = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    names = [n.decode() if isinstance(n, bytes) else n for n in names]
    return [dict(zip(names, r)) for r in res.result_set]


# ---------------------------------------------------------------- writes

def log_episode(tenant, *, agent, source, session, text, now, id=None) -> str:
    id = id or new_id("ep")
    rows = _rows(graph(tenant).query(Q.LOG_EPISODE, {
        "id": id, "agent": agent, "source": source,
        "session": session, "text": text, "now": now}))
    if not rows:
        raise UnknownReference(f"unknown agent {agent!r} or source {source!r}")
    return id


def _result(id, status, closed=0, conflicts=0, corroborated=False,
            promoted=False, ignored=False) -> dict:
    return {"id": id, "status": status, "closed": closed, "conflicts": conflicts,
            "corroborated": corroborated, "promoted": promoted, "ignored": ignored}


def write_fact(tenant, *, agent, source, episode, subject, predicate, object,
               now, parents=(), id=None, tentative=False) -> dict:
    """Store a belief.

    Returns {"id", "status", "closed", "conflicts", "corroborated", "promoted", "ignored"}.

    A write is *trusted* when the source's trust >= threshold and the claim is
    not tentative (hedged). Order of rules:
      1. predicate must be in the vocabulary
      2. source must exist and not be compromised
      3. parents must exist and be active
      4. identical active triple:      trusted -> corroborate; untrusted -> ignored
         identical quarantined triple: corroborate; promote if trusted
      5. otherwise create: active if trusted, else quarantined.
         Single-valued predicates: active closes contradicting active facts,
         quarantined records CONFLICTS_WITH. Multi-valued: values coexist.
    """
    if predicate not in config.PREDICATES:
        raise ValueError(f"predicate {predicate!r} not in vocabulary")
    subject, obj = canon(subject), canon(object)
    parents = list(parents)
    g = graph(tenant)

    with _locks[tenant]:
        src = _rows(g.ro_query(Q.SOURCE_INFO, {"id": source}))
        if not src:
            raise UnknownReference(f"unknown source {source!r}")
        if src[0]["compromised"]:
            raise CompromisedSource(f"source {source!r} is compromised")
        trusted = src[0]["trust"] >= config.TRUST_THRESHOLD and not tentative

        if parents:
            bad = [p for p in _rows(g.ro_query(Q.PARENT_STATUS, {"ids": parents}))
                   if p["status"] != "active"]
            if bad:
                raise InvalidParent(f"parents must be active facts: {bad}")

        same = _rows(g.ro_query(Q.FIND_SAME, {
            "subject": subject, "predicate": predicate, "object": obj}))
        live = next((r for r in same if r["status"] == "active"), None)
        pending = next((r for r in same if r["status"] == "quarantined"), None)

        if live:
            if not trusted:
                # An untrusted echo adds nothing, and linking it would let a
                # junk source's revocation take down a true belief.
                return _result(live["id"], "active", ignored=True)
            g.query(Q.CORROBORATE, {"id": live["id"], "source": source,
                                    "agent": agent, "now": now})
            return _result(live["id"], "active", corroborated=True)

        if pending:
            g.query(Q.CORROBORATE, {"id": pending["id"], "source": source,
                                    "agent": agent, "now": now})
            if trusted:
                r = _rows(g.query(Q.PROMOTE, {"id": pending["id"], "now": now,
                                              "single_preds": sorted(config.SINGLE_VALUED)}))[0]
                return _result(pending["id"], "active", closed=r["closed"],
                               corroborated=True, promoted=True)
            return _result(pending["id"], "quarantined", corroborated=True)

        id = id or new_id("f")
        status = "active" if trusted else "quarantined"
        rows = _rows(g.query(Q.WRITE_FACT, {
            "id": id, "agent": agent, "source": source, "episode": episode,
            "subject": subject, "predicate": predicate, "object": obj,
            "status": status, "now": now,
            "single": predicate in config.SINGLE_VALUED}))
        if not rows:
            raise UnknownReference(f"unknown agent {agent!r} or episode {episode!r}")
        if parents:
            g.query(Q.LINK_PARENTS, {"id": id, "parents": parents})
        return _result(id, status, closed=rows[0]["closed"],
                       conflicts=rows[0]["conflicts"])


def retract(tenant, *, agent, source, episode, subject, predicate, object, now) -> list[str]:
    """Close an active fact because a source explicitly ruled it out.

    Only trusted, uncompromised sources can retract. Returns the closed fact
    ids ([] when nothing active matched or the source is not trusted).
    """
    if predicate not in config.PREDICATES:
        raise ValueError(f"predicate {predicate!r} not in vocabulary")
    g = graph(tenant)
    with _locks[tenant]:
        src = _rows(g.ro_query(Q.SOURCE_INFO, {"id": source}))
        if not src:
            raise UnknownReference(f"unknown source {source!r}")
        if src[0]["compromised"]:
            raise CompromisedSource(f"source {source!r} is compromised")
        if src[0]["trust"] < config.TRUST_THRESHOLD:
            return []
        rows = _rows(g.query(Q.RETRACT, {
            "subject": canon(subject), "predicate": predicate, "object": canon(object),
            "agent": agent, "episode": episode, "now": now}))
    return [r["id"] for r in rows]


def promote(tenant, fact_id, now) -> dict:
    with _locks[tenant]:
        rows = _rows(graph(tenant).query(Q.PROMOTE, {
            "id": fact_id, "now": now, "single_preds": sorted(config.SINGLE_VALUED)}))
    if not rows:
        raise UnknownReference(f"{fact_id!r} is not a quarantined fact")
    return rows[0]


def revoke(tenant, source, now) -> list[dict]:
    """Mark a source compromised and revoke everything that depends on it."""
    with _locks[tenant]:
        g = graph(tenant)
        if not _rows(g.ro_query(Q.SOURCE_INFO, {"id": source})):
            raise UnknownReference(f"unknown source {source!r}")
        return _rows(g.query(Q.REVOKE, {"source": source, "now": now}))


# ---------------------------------------------------------------- reads

def source_info(tenant, source) -> dict | None:
    rows = _rows(graph(tenant).ro_query(Q.SOURCE_INFO, {"id": source}))
    return rows[0] if rows else None


def fact_info(tenant, ids) -> list[dict]:
    """[{id, status, subject, predicate}] for each id (status None if missing)."""
    return _rows(graph(tenant).ro_query(Q.PARENT_STATUS, {"ids": list(ids)}))


def known_values(tenant, subject) -> dict[str, list[str]]:
    rows = _rows(graph(tenant).ro_query(Q.KNOWN_VALUES, {"subject": canon(subject)}))
    return {r["predicate"]: sorted(r["values"]) for r in rows}


def disputes(tenant) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.DISPUTES))


def read_active(tenant, entity) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.READ_ACTIVE, {"entity": canon(entity)}))


def all_active(tenant) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.ALL_ACTIVE))


def as_of(tenant, t) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.AS_OF, {"t": t}))


def versions(tenant, subject, predicate) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.FACT_VERSIONS, {
        "subject": canon(subject), "predicate": predicate}))


def stale(tenant) -> list[dict]:
    """Active facts derived from a belief that was later closed. Review these."""
    return _rows(graph(tenant).ro_query(Q.STALE))


def why(tenant, fact_id) -> dict | None:
    g = graph(tenant)
    rows = _rows(g.ro_query(Q.WHY, {"id": fact_id}))
    if not rows:
        return None
    out = rows[0]
    out["paths"] = [r["path"] for r in _rows(g.ro_query(Q.WHY_PATHS, {"id": fact_id}))]
    return out


def history(tenant, session) -> list[dict]:
    return _rows(graph(tenant).ro_query(Q.HISTORY, {"session": session}))


def snapshot(tenant) -> dict:
    """Nodes and edges for the UI."""
    g = graph(tenant)
    return {"nodes": _rows(g.ro_query(Q.NODES)), "edges": _rows(g.ro_query(Q.EDGES))}
```

`memledger/__init__.py` is an empty file.

---

## 12. Tests

Run without Docker (embedded FalkorDB):

```bash
uv pip install -e ".[dev]"     # needs pytest and falkordblite
pytest -q                      # expect: 23 passed (67 with EXT.md's tests)
```

| Test | Invariant |
|---|---|
| `test_supersede` | I1, I8 |
| `test_quarantine_invisible` | quarantined facts never read |
| `test_quarantined_does_not_close_active` | I2 |
| `test_corroboration_promotes` | I4 |
| `test_low_trust_corroboration_stays_quarantined` | I4 |
| `test_duplicate_corroborates` | I3, canonicalization |
| `test_as_of` | time travel |
| `test_revoke_cascade` | I6, I7, I8 (3 agents, 4 facts, 3 hops) |
| `test_revoke_hits_episode_derived_facts` | I6 via Episode |
| `test_parent_must_be_active` | I5 |
| `test_why` | provenance paths |
| `test_bad_predicate` | vocabulary |
| `test_unknown_references` | bad agent / source / episode |
| `test_history_and_snapshot` | history order, UI dump |
| `test_stale_derived_facts` | stale reasoning detection |
| `test_no_leak` | I9 |
| `test_revoke_is_tenant_scoped` | I9 |
| `test_invalid_tenant` (6 cases) | I9 |

### `tests/conftest.py`
```python
import os
import tempfile

import pytest
from redislite.falkordb_client import FalkorDB as LiteFalkorDB

from memledger import db, schema


@pytest.fixture(scope="session")
def lite_server():
    """One embedded FalkorDB for the whole run, shut down at the end.

    Starting a server per test and never closing it leaves stray processes
    that make pytest hang on exit.
    """
    lite = LiteFalkorDB(os.path.join(tempfile.mkdtemp(), "test.db"))
    yield lite
    lite.close()


@pytest.fixture(autouse=True)
def lite_db(lite_server, monkeypatch):
    """Empty graphs for every test, both tenants seeded."""
    for name in lite_server.list_graphs():
        lite_server.select_graph(name).delete()
    monkeypatch.setattr(db, "_db", lite_server)
    for t in ("acme", "globex"):
        schema.seed(t)
    yield lite_server
```

### `tests/test_memory.py`
```python
import pytest

from memledger import memory as m

T = "acme"


def ep(id, agent, source, now, session="s1", text="..."):
    return m.log_episode(T, id=id, agent=agent, source=source,
                         session=session, text=text, now=now)


def fact(id, agent, source, episode, predicate, obj, now, subject="INC-42", parents=()):
    return m.write_fact(T, id=id, agent=agent, source=source, episode=episode,
                        subject=subject, predicate=predicate, object=obj,
                        now=now, parents=parents)


def status(fid):
    return m.why(T, fid)["status"]


def test_supersede():
    ep("e1", "investigator", "app-logs", 110)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool exhaustion", 111)
    ep("e2", "investigator", "runbook", 200, session="s2")
    r = fact("f2", "investigator", "runbook", "e2", "root_cause", "bad deploy v2.3.1", 201)
    assert r["closed"] == 1 and r["status"] == "active"
    assert status("f1") == "closed"
    assert [x["object"] for x in m.read_active(T, "inc-42")] == ["bad-deploy-v2.3.1"]
    assert m.why(T, "f2")["replaced"] == ["db-pool-exhaustion"]
    v = m.versions(T, "INC-42", "root_cause")
    assert [x["status"] for x in v] == ["closed", "active"] and v[0]["valid_to"] == 201


def test_quarantine_invisible():
    ep("e1", "investigator", "fwd-logs", 210)
    r = fact("f1", "investigator", "fwd-logs", "e1", "root_cause", "ddos", 211)
    assert r["status"] == "quarantined"
    assert m.read_active(T, "inc-42") == []
    assert m.as_of(T, 999) == []


def test_quarantined_does_not_close_active():
    ep("e1", "investigator", "runbook", 100)
    fact("f1", "investigator", "runbook", "e1", "root_cause", "bad deploy", 101)
    ep("e2", "investigator", "fwd-logs", 110)
    fact("f2", "investigator", "fwd-logs", "e2", "root_cause", "ddos", 111)
    assert status("f1") == "active"


def test_corroboration_promotes():
    ep("e1", "investigator", "app-logs", 100)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 101)
    ep("e2", "investigator", "fwd-logs", 110)
    fact("f2", "investigator", "fwd-logs", "e2", "root_cause", "ddos", 111)
    ep("e3", "triage", "alerts", 120)
    r = fact("f3", "triage", "alerts", "e3", "root_cause", "DDoS", 121)
    assert r == {"id": "f2", "status": "active", "closed": 1, "conflicts": 0,
                 "corroborated": True, "promoted": True, "ignored": False}
    assert status("f1") == "closed"
    assert set(m.why(T, "f2")["sources"]) == {"fwd-logs", "alerts"}


def test_low_trust_corroboration_stays_quarantined():
    ep("e1", "investigator", "fwd-logs", 100)
    fact("f1", "investigator", "fwd-logs", "e1", "root_cause", "ddos", 101)
    ep("e2", "triage", "fwd-logs", 110)
    r = fact("f2", "triage", "fwd-logs", "e2", "root_cause", "ddos", 111)
    assert r["status"] == "quarantined" and r["corroborated"]


def test_duplicate_corroborates():
    ep("e1", "triage", "alerts", 100)
    fact("f1", "triage", "alerts", "e1", "affects_service", "payments-api", 101)
    ep("e2", "investigator", "app-logs", 110)
    r = fact("f2", "investigator", "app-logs", "e2", "affects_service", "Payments API", 111)
    assert r["id"] == "f1" and r["corroborated"]
    assert len(m.read_active(T, "inc-42")) == 1
    assert m.read_active(T, "inc-42")[0]["writer"] == "triage"


def test_as_of():
    ep("e1", "investigator", "app-logs", 110)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 111)
    ep("e2", "investigator", "runbook", 200)
    fact("f2", "investigator", "runbook", "e2", "root_cause", "bad deploy", 201)
    assert [x["object"] for x in m.as_of(T, 150)] == ["db-pool"]
    assert [x["object"] for x in m.as_of(T, 250)] == ["bad-deploy"]
    assert m.as_of(T, 50) == []


def test_revoke_cascade():
    # unrelated, trusted
    ep("e0", "triage", "alerts", 100)
    fact("f0", "triage", "alerts", "e0", "affects_service", "payments-api", 101)
    # poisoned chain across three agents, three hops deep
    ep("e1", "triage", "webhook", 110)
    fact("f1", "triage", "webhook", "e1", "root_cause", "cache outage", 111)
    ep("e2", "investigator", "runbook", 120)
    fact("f2", "investigator", "runbook", "e2", "mitigation", "flush cache", 121, parents=["f1"])
    ep("e3", "comms", "runbook", 130)
    fact("f3", "comms", "runbook", "e3", "status", "mitigating", 131, parents=["f2"])
    ep("e4", "comms", "runbook", 140)
    fact("f4", "comms", "runbook", "e4", "owner", "cache team", 141, parents=["f3"])

    out = m.revoke(T, "webhook", 300)
    assert {r["id"] for r in out} == {"f1", "f2", "f3", "f4"}
    assert {r["writer"] for r in out} == {"triage", "investigator", "comms"}
    assert status("f0") == "active"
    assert [x["id"] for x in m.read_active(T, "inc-42")] == ["f0"]
    # history still shows what was believed before the revocation
    assert {x["id"] for x in m.as_of(T, 200)} == {"f0", "f1", "f2", "f3", "f4"}
    # a compromised source cannot write again
    ep("e5", "triage", "alerts", 310)
    with pytest.raises(m.CompromisedSource):
        fact("f5", "triage", "webhook", "e5", "root_cause", "x", 311)


def test_revoke_hits_episode_derived_facts():
    # facts reach the source through their Episode as well as directly
    ep("e1", "triage", "webhook", 110)
    fact("f1", "triage", "webhook", "e1", "severity", "sev1", 111)
    out = m.revoke(T, "webhook", 200)
    assert [r["id"] for r in out] == ["f1"]


def test_parent_must_be_active():
    ep("e1", "investigator", "fwd-logs", 100)
    fact("f1", "investigator", "fwd-logs", "e1", "root_cause", "ddos", 101)
    ep("e2", "investigator", "runbook", 110)
    with pytest.raises(m.InvalidParent):
        fact("f2", "investigator", "runbook", "e2", "mitigation", "block ip", 111, parents=["f1"])
    with pytest.raises(m.InvalidParent):
        fact("f3", "investigator", "runbook", "e2", "mitigation", "x", 112, parents=["nope"])


def test_why():
    ep("e1", "triage", "alerts", 100)
    fact("f1", "triage", "alerts", "e1", "root_cause", "bad deploy", 101)
    ep("e2", "investigator", "runbook", 110)
    fact("f2", "investigator", "runbook", "e2", "mitigation", "rollback", 111, parents=["f1"])
    w = m.why(T, "f2")
    assert w["agents"] == ["investigator"]
    assert w["sources"] == ["runbook"]
    assert set(w["upstream"]) == {"e2", "f1", "e1"}
    assert ["f2", "f1", "alerts"] in w["paths"]
    assert m.why(T, "missing") is None


def test_bad_predicate():
    ep("e1", "triage", "alerts", 100)
    with pytest.raises(ValueError):
        fact("f1", "triage", "alerts", "e1", "likes", "pizza", 101)


def test_unknown_references():
    with pytest.raises(m.UnknownReference):
        ep("e1", "ghost", "alerts", 100)
    ep("e1", "triage", "alerts", 100)
    with pytest.raises(m.UnknownReference):
        fact("f1", "triage", "nowhere", "e1", "severity", "sev1", 101)
    with pytest.raises(m.UnknownReference):
        fact("f1", "triage", "alerts", "missing-ep", "severity", "sev1", 101)


def test_history_and_snapshot():
    ep("e1", "triage", "alerts", 100, session="s1", text="p99 4s")
    ep("e2", "comms", "runbook", 90, session="s1", text="earlier")
    ep("e3", "comms", "runbook", 300, session="s2")
    assert [h["id"] for h in m.history(T, "s1")] == ["e2", "e1"]
    snap = m.snapshot(T)
    assert {n["label"] for n in snap["nodes"]} >= {"Agent", "Source", "Episode"}
    assert any(e["type"] == "LOGGED" for e in snap["edges"])


def test_stale_derived_facts():
    ep("e1", "investigator", "app-logs", 110)
    fact("f1", "investigator", "app-logs", "e1", "root_cause", "db pool", 111)
    fact("f2", "investigator", "app-logs", "e1", "mitigation", "raise pool size", 112, parents=["f1"])
    assert m.stale(T) == []
    ep("e2", "investigator", "runbook", 200)
    fact("f3", "investigator", "runbook", "e2", "root_cause", "bad deploy", 201)
    s = m.stale(T)
    assert s == [{"id": "f2", "predicate": "mitigation", "object": "raise-pool-size",
                  "based_on": "f1", "based_on_value": "db-pool", "now_believed": "bad-deploy"}]
```

### `tests/test_tenancy.py`
```python
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
```

---

## 13. Concurrency and limits

- FalkorDB serializes writes per graph and never blocks reads. Different tenants write in parallel.
- `write_fact` is several queries (check, then write). A per-tenant `threading.Lock` makes that atomic **within one process**. Run one API process. With several processes, two agents could both create the same new triple; the fix would be a FalkorDB-side uniqueness check, which is out of scope for the hackathon.
- **What to claim:** many concurrent readers, per-tenant parallel writes, serialized writes within a tenant. **Don't claim** unlimited parallel writes to one graph.
- `snapshot()` returns the whole graph. Fine for the demo; paginate for anything larger.
- Revocation follows at most `MAX_HOPS = 6`. If you change it, change the literal `*1..6` in `REVOKE`, `WHY`, `WHY_PATHS` and `STALE` too (Cypher can't parameterize path lengths).

---

## 14. Deliberate non-features

Say these confidently if asked. Each was cut on purpose.

- **No automatic cascade on close (I11).** A superseded root cause doesn't automatically kill the mitigation built on it, because the mitigation might still be right. `stale()` flags it for review instead. Good next step if time allows: have Investigator call `stale()` at the start of each turn.
- **No automatic reinstatement after revoke (I10).** Silently restoring an older belief is its own correctness risk.
- **No embeddings in the core.** Entities resolve by canonical name and aliases. Similarity search can be added later through FalkorDB's vector index without changing the model.
- **No LLM in conflict resolution.** Detection is structural (same subject + predicate), resolution is newest-wins.
- **No per-role write permissions yet.** Planned stretch (TRU-5): Comms cannot write `root_cause`.
- **No forgetting/decay.** Closed facts are history, not clutter, because every read filters by status.

---

## 15. Judge talking points

- "Most multi-agent memory is a shared blob where the last write wins. MemLedger is a ledger: every belief has a writer, a source, a validity window and a path."
- "Updating memory closes the old fact instead of overwriting it, so we can answer what we believed at any point in time."
- "Untrusted input is quarantined until a trusted source agrees."
- "When a belief changes, anything reasoned from it is flagged as stale."
- "When we find out a source lied, one Cypher traversal retracts it and everything built on it, across every agent, and every remaining answer can still show its path."
- "Each customer gets a separate graph, so isolation is physical, not a filter."
- "Take FalkorDB out and revocation, provenance and time travel stop existing. The graph is the product."
