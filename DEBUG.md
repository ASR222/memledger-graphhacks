---
name: memledger-debug
description: Diagnose and fix MemLedger problems: failing or hanging tests, wrong beliefs in memory, dropped extractions, agent or tool errors, API/console issues, MCP, benchmark races and deployment failures. Use whenever something in MemLedger breaks or behaves unexpectedly.
---

# Debugging MemLedger

This skill covers the MemLedger repo (FalkorDB-backed shared memory for an incident-response agent team). The design docs (`docs/*.md`) are the source of truth for intended behavior; this file is the playbook for when reality differs.

## Method

Follow these in order. Don't skip to editing code.

1. **Reproduce in rehearsal mode first.** No key, no Docker, deterministic:
   `python scripts/demo.py --extract golden --agents offline --reset --until N`, or `pytest -q -k <name>`.
   - If it reproduces, it's our code.
   - If it only happens live, it's model output, the environment or versions.
2. **Find the layer** with the map below. Each layer has its own tests; run just that file.
3. **Look at the graph,** not just the code. Use the Cypher in "Inspect the graph", via FalkorDB Browser (port 3000) or `memledger.memory.snapshot`.
4. **Fix at the lowest layer that's wrong.** A wrong belief is usually a memory-rule or extraction issue, not an agent prompt issue.
5. **Add or adjust a test that would have caught it,** then run the full suite.
6. **Record it.** Add a log line in `SETUP-STATUS.md`. If your fix makes code differ from a doc's code block, say so in the commit message, because `scripts/apply_docs.py` will now report that file as CHANGED.

**Never** edit a test's expected value just to make it pass without understanding why it changed. Several tests encode invariants (I1–I11 in Mem.md, T1–T13 in TRU.md).

## Layer map

| Layer | Files | Tests | Doc |
|---|---|---|---|
| DB connection, tenants | `db.py`, `tenancy.py`, `schema.py` | `test_tenancy.py`, `test_tenants.py` | Mem, TEN |
| Memory rules, Cypher | `memory.py`, `queries.py` | `test_memory.py`, `test_conflicts.py` | Mem, EXT §8 |
| Extraction | `extract.py`, `ingest.py`, `config.py` | `test_extract.py`, `test_ingest.py` | EXT |
| Trust, revocation | `trust.py`, `scripts/trust.py` | `test_trust.py` | TRU |
| Agents, handoffs | `agents/*` | `test_agents.py` | AGT |
| Scenario, demo | `scenario.py`, `scripts/demo.py`, `data/` | `test_scenario.py` | SCN |
| API, console | `api.py`, `static/*` | `test_api.py` (+ the browser) | API |
| MCP | `mcp_server.py` | `test_mcp.py` | MCP |
| Concurrency | `scripts/bench.py` | `test_tenants.py` | TEN |
| Evaluation | `evaluate.py`, `scripts/eval.py` | `test_eval.py` | EVL |
| Deploy | `serve.py`, `Dockerfile`, `scripts/deploy.sh`, `scripts/smoke.py` | `test_deploy.py` | DEP |
| README sync | `scripts/readme_queries.py` | `test_readme.py` | SUB |

## Quick commands

```bash
pytest -q                                   # full suite; know why each skip/xfail exists
pytest -q tests/test_memory.py -k revoke    # one layer, one area
pytest -q -x --lf                           # rerun last failures, stop at first
python scripts/demo.py --list               # scenario steps
python scripts/demo.py --extract golden --agents offline --reset --until 8
python scripts/demo.py --step 9 --force     # rerun one step out of order (state may be odd)
python scripts/trust.py sources | quarantine | preview webhook
python scripts/try_extract.py               # live extraction vs expectations (needs key)
python scripts/smoke.py http://localhost:8080 --full
python scripts/bench.py --embedded --seconds 5
python scripts/status.py check              # task board consistency
```

## Expected test results

After all docs are applied (before tasks C1/C2): **150 passed, 1 skipped, 3 xfailed**.

- **skipped:** `test_official_server_strict_read_only` (needs Node and `FALKORDB_MCP_JS`).
- **xfailed:**
  - `test_as_of_hides_claims_that_were_never_believed`: fixed by patch C2a;
  - `test_q16_after_patch`: fixed by patch C2a;
  - `test_no_cypher_outside_queries_py`: fixed by task C1.
- **These xfails are strict.** When the fix lands, the test reports XPASS and fails until you delete its `xfail` line. That's intended.

## Symptom → cause → fix

### Tests and environment

| Symptom | Cause | Fix |
|---|---|---|
| pytest passes but **hangs on exit**; many `redis-server` processes | an old `conftest.py` that starts one embedded DB per test and never closes it | use the session-scoped fixture (Mem.md v2 §12 / SETUP.md §6); kill strays: `ps -eo pid,args \| awk '/[r]edis-server/ {print $1}' \| xargs kill` |
| `ModuleNotFoundError: mcp.server.fastmcp` | MCP SDK 2.x renamed FastMCP to MCPServer | `pip install "mcp==2.2.0"`; don't follow 1.x tutorials |
| `'Tool' object has no attribute 'inputSchema'` | MCP 2.x uses snake_case fields | `input_schema`, `is_error`, `structured_content` |
| `scripts.*` import fails in tests | missing `scripts/__init__.py` | create it (empty) |
| tests pass locally, numbers differ in Docker | embedded FalkorDB is 4.18.3; Docker `latest` is 6.x | expected; rerun bench and eval on the real DB before quoting numbers |
| `CALL db.idx.fulltext.createNodeIndex` errors on 6.x | old procedure form | the DDL form `CREATE FULLTEXT INDEX FOR (ep:Episode) ON (ep.text)` (already used) |
| a test's `pkill -f something` kills your own shell | the pattern matches the shell's command line | kill by PID file, or `awk '/[p]attern/'` |

### Memory and beliefs

| Symptom | Cause | Fix |
|---|---|---|
| **A revoked source is trusted again** after a restart | `SEED` re-runs `SET compromised = false` on existing sources | patch C2a (`ON CREATE SET`); until then only seed empty graphs (`tenancy.create`) |
| **Time travel shows a claim nobody believed** (`redis-outage` at 13:55) | revoking a quarantined fact sets `valid_to`, so `AS_OF` stops excluding it | patch C2a (`revoked_from`) |
| a promoted fact appears in `as_of` before it was promoted | `AS_OF` uses `valid_from` | patch C2a (`coalesce(promoted_at, valid_from)`) |
| two active values for a one-value field | multi-process writes (race), or a hand-written query | `python -c "from memledger import tenancy; print(tenancy.i1_violations('acme'))"`; apply C2b; one process |
| `IndexError: list index out of range` in `write_fact` under load | two processes promote the same quarantined fact | C2b (lock in FalkorDB) or a single process (`--workers 1`, Cloud Run `--max-instances 1`) |
| a new value didn't replace the old one | predicate is multi-valued (`affects_service`, `mitigation`) | intended; see `config.SINGLE_VALUED` |
| a mitigation stays active after its root cause changed | closing doesn't cascade (I11) | `memory.stale()` lists it; the Investigator should rule it out |
| a revoke left a conclusion active | the conclusion was stored as a **corroboration** (same value already active), which doesn't add parent links | known (SCN.md §9); C4 changes the scenario so the conclusion is new |
| a true fact got revoked with a junk source | taint semantics: corroboration by the revoked source | trusted source re-asserts; untrusted echoes are already ignored |
| a write vanished after `MATCH` returned nothing | `MATCH` instead of `OPTIONAL MATCH` drops the row | keep the `OPTIONAL MATCH … FOREACH (CASE …)` pattern |
| `valid_to: null` is in a query but never matches | FalkorDB doesn't store nulls | omit the property; test with `IS NULL` |

### Extraction

| Symptom | Cause | Fix |
|---|---|---|
| every claim `extraction_failed` | `EXTRACT=cache` with no cache entry for this text (or known values changed) | run once with `--extract live` and commit `data/.extract_cache.json`; key = prompt version + model + subject + text + known values |
| claims dropped as `ungrounded` | Gemini paraphrased the evidence | strengthen "copied verbatim" in the prompt, bump `PROMPT_VERSION`, rerun `try_extract.py` |
| a statement treated as a guess | the hedge list matched (e.g. "may be") | `extract.HEDGES`; "could not" and "?id=" are deliberately not hedges (tests exist) |
| two spellings of one thing cause a fake conflict | value drift | add to `config.ALIASES`; known values are shown to the model, so check the cache key changed |
| `bad_value` for severity or status | outside the fixed set | add a synonym in `config.VALUE_SYNONYMS` |
| a claim dropped as `not_permitted` | role filter (TRU.md §7) | intended; change `trust.ROLE_PREDICATES` only deliberately |
| `overridden_in_episode` | two values for one field in one text; the later wins | intended |

### Agents

| Symptom | Cause | Fix |
|---|---|---|
| Gemini rejects the second turn of a tool loop | the history was rebuilt and lost thought signatures | the adapter appends the model's content verbatim; don't reconstruct parts |
| status update cites unknown ids | the model invented ids | strengthen the citing rule in `roles.COMMON`; the UI strikes them through |
| run ends `max_steps` | the model loops on tools | check the trace (`run.tool_calls`); lower temperature is already 0 |
| `conclude` returns "must cite at least one active fact" | parents missing or not active | intended; parents must be active facts |
| session 2 "doesn't remember" | the agent didn't call `recall` | prompt says to; check the trace |

### API and console

| Symptom | Cause | Fix |
|---|---|---|
| "reset the tenant first" / graph 404 | the tenant has no graph (fresh DB, or FalkorDB Cloud wiped it) | press Reset |
| Next replays step 1 on a full graph | progress file lost on restart while the graph survived | press Reset |
| scripted steps 10–11 show ✗ | you revoked by hand from the Sources tab first | revoke in one place only |
| graph squashed under the side panel | force-graph sized to the window | `sizeGraph()` uses the container size; check `#graph { right: 300px }` |
| no graph drawn, `ForceGraph is not defined` | vendored library missing | API.md §9 |
| labels missing when zoomed out | label threshold | labels scale with zoom (`10 / scale`) |
| quarantine items appear under the Sources tab | `display: flex` overriding `[hidden]` | `[hidden] { display: none !important; }` |

### MCP

| Symptom | Cause | Fix |
|---|---|---|
| Claude Desktop shows no MemLedger tools | wrong Python path or `PYTHONPATH` | absolute venv Python; check the app's MCP logs |
| the server dies or replies garble | something printed to stdout | log to stderr only |
| the official FalkorDB server deleted a graph | only `FALKORDB_DEFAULT_READONLY` was set | also set `FALKORDB_STRICT_READONLY=true` (tested) |

### Deployment

| Symptom | Cause | Fix |
|---|---|---|
| Cloud Build permission error | `roles/run.builder` missing or not propagated | rerun `deploy.sh` after a few minutes |
| secret access denied | missing `secretAccessor` | rerun `deploy.sh` |
| smoke: "unreachable" | wrong URL or service down | `gcloud run services describe …` |
| smoke: "tenants reachable" fails | can't reach FalkorDB | Cloud instance stopped (free tier: after 1 idle day), wrong port (use the Connectivity endpoint), password |
| demo dead days later | FalkorDB Cloud free instance stopped (1 day) or deleted (7 days) | deploy `MODE=embedded` for the judging URL |
| image build: missing `libstdc++` | slim base image | the Dockerfile installs `libstdc++6 libgcc-s1` |

## Inspect the graph

Graph names are `memory_<tenant>`.

```cypher
// current beliefs about the incident
MATCH (f:Fact {subject:'inc-42', status:'active'}) RETURN f.id, f.predicate, f.object, f.valid_from

// every version of one field
MATCH (f:Fact {subject:'inc-42', predicate:'root_cause'})
RETURN f.object, f.status, f.valid_from, f.valid_to ORDER BY f.valid_from

// I1: one-value fields with more than one active value (must be empty)
MATCH (f:Fact {status:'active'}) WHERE f.predicate IN ['root_cause','status','owner','severity']
WITH f.subject AS s, f.predicate AS p, collect(f.object) AS v WHERE size(v) > 1 RETURN s, p, v

// provenance of one fact
MATCH p = (f:Fact {id:$id})-[:FROM_SOURCE|DERIVED_FROM*1..6]->(:Source) RETURN p

// what a source touched, and the status of each
MATCH (s:Source {id:'webhook'})<-[:FROM_SOURCE|DERIVED_FROM*1..6]-(f:Fact) RETURN DISTINCT f.id, f.predicate, f.object, f.status

// disputes
MATCH (q:Fact {status:'quarantined'})-[:CONFLICTS_WITH]->(a:Fact) RETURN q.object, a.object, a.status

// sources: trust and compromise
MATCH (s:Source) RETURN s.id, s.trust, s.compromised

// pending handoffs
MATCH (a:Agent)-[:SENT]->(h:Handoff {delivered:false})-[:TO]->(b:Agent) RETURN a.id, b.id, h.note

// facts with no writer (should be none)
MATCH (f:Fact) WHERE NOT (:Agent)-[:WROTE]->(f) RETURN f.id
```

From Python:

```python
from memledger import memory, tenancy, trust
memory.why("acme", "f-…"); memory.stale("acme"); memory.disputes("acme")
tenancy.stats("acme"); tenancy.i1_violations("acme"); trust.blast_radius("acme", "webhook")
```

## Debug report (paste into the PR or the status log)

```
Symptom:        what you saw, exact error
Reproduce:      command (rehearsal mode if possible), step number
Layer:          from the map
Graph evidence: query + result
Cause:          one sentence
Fix:            what changed, which doc it diverges from (if any)
Test:           the test that now covers it
```
