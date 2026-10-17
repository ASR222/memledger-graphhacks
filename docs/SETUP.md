# SETUP.md — MemLedger

Instructions for a coding agent (Claude Code or similar) setting up and building **MemLedger** for GraphHacks (WeMakeDevs × FalkorDB), **Track 02: Agent Memory & Coordination**.

Read this whole file before writing code. Work through the phases in order. Each phase ends with an **acceptance check**; do not start the next phase until it passes. If a check fails twice, stop and report what failed instead of working around it.

---

## 0. What you are building

MemLedger is shared memory for a team of agents, stored as a graph in FalkorDB. Every belief (a `Fact`) records:

- **who** wrote it (`Agent`),
- **where** it came from (`Source`, with a trust score, and the raw `Episode`),
- **when** it was true (`valid_from` / `valid_to`),
- **what it replaced** (`SUPERSEDES`) and **what it was derived from** (`DERIVED_FROM`).

This enables four things the product is judged on:

| Capability | How |
|---|---|
| Supersede outdated facts | A new fact with the same subject + predicate closes the old one instead of piling up |
| Quarantine untrusted writes | Facts from low-trust sources are stored but invisible to agents until corroborated |
| Revoke a bad source everywhere | One traversal marks every fact derived from that source as revoked, across all agents |
| Explain any answer | Return the path from a fact back to its sources, episodes and writers |

Demo scenario: a synthetic incident-response team (**Triage**, **Investigator**, **Comms**) working incident **INC-42** across two sessions, with two tenants (`acme`, `globex`).

### Hard deadline

Submission closes **Sun 18 Oct 2026, 11:59 PM IST**. Target submission is **10 PM IST**. Prefer a working small thing over an unfinished big thing.

---

## 1. Rules for the agent

1. **FalkorDB is the primary and only database.** Do not add Postgres, SQLite, Redis caches or vector DBs. If the product still works with FalkorDB removed, the hackathon considers the graph decoration.
2. **Do not use Graphiti, Mem0, Letta or Cognee.** Write the graph model and Cypher directly. Judges must see our own model and queries.
3. **All Cypher lives in `memledger/queries.py`** as named string constants with a one-line comment each. The README must list every query the product depends on, and this file is that list.
4. **Closed predicate vocabulary.** The LLM may only emit these predicates: `root_cause`, `affects_service`, `status`, `owner`, `mitigation`, `severity`. Reject anything else. Contradiction detection depends on this.
5. **No LLM judges conflicts.** Resolution is deterministic in Cypher: the newest active write wins.
6. **Every memory function takes `now` as an argument** (integer epoch milliseconds). Never call the clock inside `memory.py`. The demo replays a scripted timeline and must be deterministic.
7. **Tenant is required everywhere.** Each tenant is its own graph named `memory_<tenant>`. No function may run a query without a tenant.
8. **Reads use `ro_query`.** Writes use `query`.
9. **No code from earlier projects** (including Cortex AI). Hackathon rules require all main code to be written during the event. Patterns and public libraries are fine.
10. **Track AI assistance.** Append a line to `AI_DISCLOSURE.md` for each significant chunk of AI-written code (file + one sentence). The README must disclose AI use.
11. **Never commit secrets.** `.env` is gitignored; only `.env.example` is committed.

---

## 2. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| uv (recommended) or pip | latest | `uv --version` |
| Docker + Compose | any recent | `docker compose version` |
| Gemini API key | — | from Google AI Studio |
| Node.js (for the MCP server, Saturday) | 18+ | `node --version` |

If Docker is unavailable, tests can run on **falkordblite** (embedded FalkorDB in a pip package). See section 6.

---

## 3. Repository layout

Create exactly this structure. Empty files are fine at first.

```
memledger/
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── SETUP.md
├── AI_DISCLOSURE.md
├── memledger/
│   ├── __init__.py
│   ├── config.py          # env loading, trust threshold, predicate list
│   ├── db.py              # FalkorDB connection + graph-per-tenant helper
│   ├── queries.py         # EVERY Cypher query, as named constants
│   ├── schema.py          # create indexes, seed agents and sources
│   ├── memory.py          # public API: log_episode, write_fact, read_active, as_of, revoke, why, promote
│   ├── extract.py         # Gemini: episode text -> list[Triple]          (Saturday)
│   ├── agents/            # tools.py, triage.py, investigator.py, comms.py, supervisor.py  (Saturday)
│   └── api.py             # FastAPI                                        (Saturday eve)
├── data/
│   ├── acme/              # alerts.json, logs.txt, runbook.md, webhook.json, forwarded_logs.txt
│   └── globex/
├── scripts/
│   ├── seed.py            # create indexes + seed both tenants
│   ├── demo.py            # scripted replay: python scripts/demo.py --step N
│   └── eval.py            # scripted question set                          (Sunday)
└── tests/
    ├── conftest.py
    ├── test_memory.py
    └── test_tenancy.py
```

---

## 4. Phase 1 — Environment (≈1 hour, Friday night)

### 4.1 `docker-compose.yml`

```yaml
services:
  falkordb:
    image: falkordb/falkordb:latest
    ports:
      - "6379:6379"   # database
      - "3000:3000"   # FalkorDB Browser (use it to watch the graph)
    volumes:
      - falkordb_data:/var/lib/falkordb/data
    restart: unless-stopped

volumes:
  falkordb_data:
```

### 4.2 `pyproject.toml`

```toml
[project]
name = "memledger"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "falkordb",
  "langgraph",
  "langchain-google-genai",
  "google-genai",
  "fastapi",
  "uvicorn[standard]",
  "pydantic>=2",
  "python-dotenv",
]

[project.optional-dependencies]
dev = ["pytest", "falkordblite"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### 4.3 `.env.example`

```bash
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_USERNAME=
FALKORDB_PASSWORD=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
TRUST_THRESHOLD=0.5
DEFAULT_TENANT=acme
```

### 4.4 `.gitignore`

```
.env
.venv/
__pycache__/
*.db
.pytest_cache/
```

### 4.5 Commands

```bash
cp .env.example .env              # then fill in GEMINI_API_KEY
docker compose up -d
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

### ✅ Acceptance check — Phase 1

- `docker compose ps` shows falkordb running.
- http://localhost:3000 opens the FalkorDB Browser.
- This prints `[[1]]`:
  ```bash
  python -c "from falkordb import FalkorDB; g=FalkorDB('localhost',6379).select_graph('memory_smoke'); print(g.query('RETURN 1').result_set)"
  ```

---

## 5. Phase 2 — Graph model and memory core (≈4 hours, Friday night)

### 5.1 Graph model

```
(:Agent   {id, role})
(:Source  {id, kind, trust, compromised})
(:Episode {id, session, at, text})
(:Entity  {name})
(:Fact    {id, subject, predicate, object, valid_from, valid_to, status, trust, promoted_at})

(:Agent)-[:LOGGED {at}]->(:Episode)
(:Agent)-[:WROTE {at, corroborates?}]->(:Fact)
(:Episode)-[:FROM_SOURCE]->(:Source)
(:Fact)-[:FROM_SOURCE]->(:Source)
(:Fact)-[:DERIVED_FROM]->(:Episode)
(:Fact)-[:DERIVED_FROM]->(:Fact)
(:Fact)-[:ABOUT]->(:Entity)
(:Fact)-[:SUPERSEDES]->(:Fact)
```

**Fact status lifecycle**

```
            trust >= threshold
 new write ───────────────────▶ active ──(newer fact, same subject+predicate)──▶ closed
     │                            ▲   │
     │ trust < threshold          │   └──(source revoked)──▶ revoked
     ▼                            │
 quarantined ──(corroborated)─────┘
     │
     └──(source revoked)──▶ revoked
```

- `valid_to` is **absent** while a fact is active or quarantined. FalkorDB drops null properties, so never write `valid_to: null`; test with `IS NULL`.
- Revoking a fact does **not** reopen the fact it superseded. This is intentional for now.

### 5.2 `memledger/config.py`

Load `.env` with python-dotenv. Expose:

```python
PREDICATES = {"root_cause", "affects_service", "status", "owner", "mitigation", "severity"}
TRUST_THRESHOLD = float(os.getenv("TRUST_THRESHOLD", "0.5"))
```

### 5.3 `memledger/db.py`

```python
from falkordb import FalkorDB
from . import config

_db = None

def get_db():
    global _db
    if _db is None:
        _db = FalkorDB(host=config.HOST, port=config.PORT,
                       username=config.USERNAME or None, password=config.PASSWORD or None)
    return _db

def graph(tenant: str):
    if not tenant or not tenant.isidentifier():
        raise ValueError(f"invalid tenant: {tenant!r}")
    return get_db().select_graph(f"memory_{tenant}")
```

Make `get_db` overridable so tests can inject a falkordblite instance (section 6).

### 5.4 `memledger/queries.py`

Use these queries verbatim. They have been run against FalkorDB and produce the expected results for the INC-42 scenario.

```python
# --- Schema -------------------------------------------------------------

# Indexes. Run once per tenant graph. Use the DDL form for full-text;
# the older db.idx.fulltext.createNodeIndex procedure is unreliable on 6.x.
INDEXES = [
    "CREATE INDEX FOR (f:Fact) ON (f.id)",
    "CREATE INDEX FOR (f:Fact) ON (f.subject, f.predicate, f.status)",
    "CREATE INDEX FOR (s:Source) ON (s.id)",
    "CREATE INDEX FOR (a:Agent) ON (a.id)",
    "CREATE INDEX FOR (e:Entity) ON (e.name)",
    "CREATE INDEX FOR (ep:Episode) ON (ep.id)",
    "CREATE FULLTEXT INDEX FOR (ep:Episode) ON (ep.text)",
]

# Seed agents and sources for a tenant.
SEED = """
UNWIND $agents AS a MERGE (x:Agent {id:a.id}) SET x.role = a.role
WITH count(*) AS _
UNWIND $sources AS s MERGE (y:Source {id:s.id})
SET y.kind = s.kind, y.trust = s.trust, y.compromised = false
"""

# --- Writes -------------------------------------------------------------

# Record one agent turn (persistent conversation history).
LOG_EPISODE = """
MATCH (a:Agent {id:$agent}), (src:Source {id:$source})
CREATE (ep:Episode {id:$id, session:$session, at:$now, text:$text})
CREATE (a)-[:LOGGED {at:$now}]->(ep)
CREATE (ep)-[:FROM_SOURCE]->(src)
RETURN ep.id
"""

# Is this exact triple already believed (active) or pending (quarantined)?
FIND_SAME = """
MATCH (f:Fact {subject:$subject, predicate:$predicate, object:$object})
WHERE f.status IN ['active','quarantined']
RETURN f.id, f.status
"""

# Create a fact with provenance. If it is active, close any active fact with
# the same subject+predicate but a different object, and link SUPERSEDES.
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
WHERE old.id <> f.id AND old.object <> $object AND $status = 'active'
FOREACH (o IN CASE WHEN old IS NULL THEN [] ELSE [old] END |
  SET o.status = 'closed', o.valid_to = $now
  CREATE (f)-[:SUPERSEDES]->(o))
RETURN f.id AS id, count(old) AS closed
"""

# Record that a fact was derived from earlier facts (enables revocation cascade).
LINK_PARENTS = """
MATCH (f:Fact {id:$id})
UNWIND $parents AS pid
MATCH (p:Fact {id:pid})
CREATE (f)-[:DERIVED_FROM]->(p)
RETURN count(p)
"""

# Another agent/source asserts an existing triple: add provenance, no new node.
CORROBORATE = """
MATCH (f:Fact {id:$id}), (src:Source {id:$source}), (a:Agent {id:$agent})
MERGE (f)-[:FROM_SOURCE]->(src)
CREATE (a)-[:WROTE {at:$now, corroborates:true}]->(f)
RETURN f.id
"""

# Promote a quarantined fact to active and supersede whatever it contradicts.
PROMOTE = """
MATCH (q:Fact {id:$id, status:'quarantined'})
SET q.status = 'active', q.promoted_at = $now
WITH q
OPTIONAL MATCH (old:Fact {subject:q.subject, predicate:q.predicate, status:'active'})
WHERE old.id <> q.id AND old.object <> q.object
FOREACH (o IN CASE WHEN old IS NULL THEN [] ELSE [old] END |
  SET o.status = 'closed', o.valid_to = $now
  CREATE (q)-[:SUPERSEDES]->(o))
RETURN q.id AS id, count(old) AS closed
"""

# Blast-radius revocation: mark the source compromised and revoke every fact
# that traces back to it through FROM_SOURCE / DERIVED_FROM, up to 6 hops.
REVOKE = """
MATCH (s:Source {id:$source})
SET s.compromised = true
WITH s
MATCH (s)<-[:FROM_SOURCE|DERIVED_FROM*1..6]-(f:Fact)
WHERE f.status IN ['active','quarantined']
WITH DISTINCT f
SET f.status = 'revoked', f.valid_to = $now
WITH f
OPTIONAL MATCH (a:Agent)-[:WROTE]->(f)
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate, a.id AS writer
"""

# --- Reads (use ro_query) -----------------------------------------------

# Current beliefs about an entity. The only read path agents use.
READ_ACTIVE = """
MATCH (f:Fact {status:'active'})-[:ABOUT]->(e:Entity {name:$entity})
OPTIONAL MATCH (a:Agent)-[:WROTE]->(f)
RETURN f.id AS id, f.predicate AS predicate, f.object AS object,
       f.valid_from AS since, a.id AS writer
ORDER BY f.valid_from DESC
"""

# What did the team believe at time $t? (closed/revoked facts appear if they
# were valid then; quarantined facts never appear)
AS_OF = """
MATCH (f:Fact)
WHERE f.valid_from <= $t AND (f.valid_to IS NULL OR f.valid_to > $t)
  AND f.status <> 'quarantined'
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate, f.object AS object
ORDER BY f.subject, f.predicate
"""

# Why is this believed? Writers, sources, upstream episodes/facts, replaced values.
WHY = """
MATCH (f:Fact {id:$id})
OPTIONAL MATCH (a:Agent)-[:WROTE]->(f)
OPTIONAL MATCH (f)-[:FROM_SOURCE]->(s:Source)
OPTIONAL MATCH (f)-[:DERIVED_FROM*1..6]->(up)
OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Fact)
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, f.status AS status,
       collect(DISTINCT a.id) AS writers,
       collect(DISTINCT s.id) AS sources,
       collect(DISTINCT up.id) AS upstream,
       collect(DISTINCT old.object) AS replaced
"""

# Full paths from a fact to every source behind it (for UI highlighting).
WHY_PATHS = """
MATCH p = (f:Fact {id:$id})-[:FROM_SOURCE|DERIVED_FROM*1..6]->(s:Source)
RETURN p
"""

# Conversation history for one session.
HISTORY = """
MATCH (a:Agent)-[:LOGGED]->(ep:Episode {session:$session})
RETURN ep.id AS id, a.id AS agent, ep.at AS at, ep.text AS text
ORDER BY ep.at
"""

# Whole graph for the UI (small demo graphs only).
GRAPH_DUMP = """
MATCH (n) OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
"""
```

### 5.5 `memledger/memory.py` — public API

Implement these functions. Every one takes `tenant`; every write takes `now`.

```python
def log_episode(tenant, *, id, agent, source, session, text, now) -> str
def write_fact(tenant, *, id, agent, source, episode, subject, predicate, object,
               now, parents=()) -> dict   # {"id", "status", "closed", "corroborated"}
def read_active(tenant, entity) -> list[dict]
def as_of(tenant, t) -> list[dict]
def revoke(tenant, source, now) -> list[dict]   # affected facts with writer
def why(tenant, fact_id) -> dict
def promote(tenant, fact_id, now) -> dict
def history(tenant, session) -> list[dict]
```

`write_fact` logic, in order:

1. Validate `predicate in PREDICATES`; raise `ValueError` otherwise.
2. Normalize `subject` and `object`: lowercase, strip, spaces → `-`.
3. Run `FIND_SAME`.
   - If an **active** match exists → run `CORROBORATE`, return `{"corroborated": True}`.
   - If a **quarantined** match exists and this write's source is a different source → run `CORROBORATE`, then `PROMOTE`.
4. Otherwise look up the source's trust. `status = "active" if trust >= TRUST_THRESHOLD else "quarantined"`.
5. Run `WRITE_FACT`. If `parents` is non-empty, run `LINK_PARENTS`.

### 5.6 `memledger/schema.py` and `scripts/seed.py`

`seed(tenant)` runs every statement in `INDEXES` (ignore "already indexed" errors) and then `SEED` with:

```python
AGENTS = [
    {"id": "triage", "role": "triage"},
    {"id": "investigator", "role": "investigator"},
    {"id": "comms", "role": "comms"},
]
SOURCES = [
    {"id": "alerts",     "kind": "alert_feed",  "trust": 0.9},
    {"id": "runbook",    "kind": "runbook",     "trust": 0.9},
    {"id": "app-logs",   "kind": "log",         "trust": 0.7},
    {"id": "webhook",    "kind": "integration", "trust": 0.6},  # looks legit, later found compromised -> revocation demo
    {"id": "fwd-logs",   "kind": "tool_output", "trust": 0.3},  # untrusted -> quarantine demo
]
```

`scripts/seed.py` seeds both `acme` and `globex`.

### 5.7 Tests — `tests/test_memory.py`

Use a fixed timeline (`now` = 100, 110, 200, …). Required tests:

| Test | Expected |
|---|---|
| `test_supersede` | Write `root_cause=db-pool-exhaustion` (t=111), then `root_cause=bad-deploy-v2.3.1` (t=201). Old fact is `closed` with `valid_to=201`; `read_active` returns only the new one; a `SUPERSEDES` edge exists. |
| `test_quarantine_invisible` | A fact from `fwd-logs` (trust 0.3) has status `quarantined` and does not appear in `read_active` or `as_of`. |
| `test_corroboration_promotes` | The same triple from `alerts` promotes the quarantined fact to `active` and closes the contradicting active fact. |
| `test_duplicate_corroborates` | Writing an identical active triple again creates no new Fact node. |
| `test_as_of` | `as_of(150)` returns the old root cause; `as_of(250)` returns the new one. |
| `test_revoke_cascade` | Facts from `webhook` plus facts derived from them (via `parents`) across **3 agents and at least 3 hops** are all `revoked`; unrelated facts stay `active`. |
| `test_why` | `why` on a derived fact returns its writer, source, upstream ids and replaced values. |
| `test_bad_predicate` | `write_fact(..., predicate="likes")` raises `ValueError`. |

`tests/test_tenancy.py`:

| Test | Expected |
|---|---|
| `test_no_leak` | After writing to `acme`, every read on `globex` returns empty. |
| `test_invalid_tenant` | `graph("acme; DROP")` raises `ValueError`. |

### ✅ Acceptance check — Phase 2 (gate: **Sat 2 AM IST**)

- `pytest -q` passes all tests above.
- After `python scripts/seed.py`, FalkorDB Browser shows `memory_acme` and `memory_globex` with 3 Agent and 5 Source nodes each.

---

## 6. Running tests without Docker

`falkordblite` embeds FalkorDB in a pip package. In `tests/conftest.py`:

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

One embedded server per test run, wiped before each test and closed at the end. (Starting one per test without closing it leaves stray processes and pytest hangs on exit.) Use the real Docker instance for the demo.

---

## 7. Later phases (summary — expand when you reach them)

These follow the build board. Check the gate before moving on.

### Phase 3 — Extraction and trust (Saturday morning)

- `extract.py`: call Gemini with `response_mime_type="application/json"` and a Pydantic `response_schema` of `list[Triple]` where `Triple = {subject, predicate, object, parents: list[str]}`. Predicates come from `config.PREDICATES` only.
- Cache results in `data/.extract_cache.json` keyed by SHA-256 of the episode text so reruns are free and identical.
- Entity aliases in `config.py` (for example `"payments api" -> "payments-api"`).

### Phase 4 — Agents (Saturday afternoon) — gate **Sat 2 PM IST**

- `agents/tools.py`: `remember`, `recall`, `history`, `why` as LangGraph tools bound to a `(tenant, agent_id)`.
- Triage writes `severity`, `affects_service`. Investigator writes `root_cause`, `mitigation`. Comms reads only and writes `status`.
- Supervisor passes **fact ids** between agents, never copied text.
- Session 2 starts with empty chat state; agents must recall from the graph.
- **If agents are not reading and writing memory by Sat 2 PM, replace LangGraph with a plain function-calling loop.** Report the switch.

### Phase 5 — Scenario data (Saturday)

`data/acme/`:
- `alerts.json` — p99 latency on payments-api (session 1).
- `logs.txt` — DB pool exhaustion lines (session 1, the wrong root cause).
- `runbook.md` — deploy v2.3.1 introduced an N+1 query (session 2, the correction).
- `webhook.json` — plausible-looking integration payload claiming a cache outage; agents derive mitigation and status from it; later revoked.
- `forwarded_logs.txt` — obvious junk claiming a DDoS; must land in quarantine.

`data/globex/` — a different incident (INC-7, auth-service), used only for the isolation test.

### Phase 6 — API and UI (Saturday evening)

FastAPI routes: `POST /chat`, `GET /graph`, `POST /revoke`, `GET /why/{fact_id}`, `GET /as_of?t=`, `GET /tenants`, `GET /history/{session}`. All take `tenant`.

UI: agent log on the left, graph on the right. First version can link to FalkorDB Browser. Upgrade to react-force-graph polling `/graph` every second, coloring nodes by status (active, closed, quarantined, revoked) and by writer.

### Phase 7 — MCP (Saturday evening)

```bash
npx -y @falkordb/mcpserver
```

Point it at the same database (check the package README for its environment variables) and connect Claude Desktop. Use read-only tools only. Demo question: "What caused INC-42, and why do we believe it?"

### Phase 8 — Eval, deploy, submit (Sunday) — freeze **Sun 2 PM IST**

- `scripts/eval.py`: 15 questions with expected answers; compare no memory, an append-only list, and MemLedger.
- Deploy: FalkorDB Cloud + Cloud Run. Wake the DB before recording.
- README: problem, architecture, setup, graph model (copy section 5.1), every query from `queries.py`, why the graph is necessary, eval table, AI disclosure.

---

## 8. Known gotchas

- FalkorDB does not store null properties. Omit `valid_to` instead of setting it to null.
- `OPTIONAL MATCH ... FOREACH (o IN CASE WHEN old IS NULL THEN [] ELSE [old] END | ...)` is the pattern for "update if it exists". A plain `MATCH` would drop the whole row when nothing matches and the new fact would never be created.
- Writes to one graph are serialized; reads never block. Do not claim parallel writes to a single graph in the README or video.
- Parameterize everything. Never build Cypher with f-strings except the graph name, which is validated in `db.graph()`.
- Re-running `INDEXES` raises "already indexed". Catch and ignore that specific error.
- The FalkorDB Cloud free tier can stop when idle. Hit it once before demos.

---

## 9. Definition of done for setup

Setup is complete when:

1. `docker compose up -d && python scripts/seed.py && pytest -q` all succeed from a fresh clone.
2. `memledger/queries.py` contains every query above with a comment each.
3. `README.md` has a Setup section that matches this file.
4. `AI_DISCLOSURE.md` exists and has entries.

Report back with: test output, a screenshot or description of the graph in FalkorDB Browser, and anything in this file that turned out to be wrong.
