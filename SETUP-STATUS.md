# SETUP-STATUS

The shared task board for MemLedger. **Claim a task here before you touch its files.** Rules are in `INSTRUCTIONS.md` §5; `python scripts/status.py check` must pass before every push.

Statuses: `todo` · `in-progress` · `review` · `done` · `blocked`. Owner is a person or an agent name. Locks are the files (or folders ending in `/`, or `resource:` names) a task may change; two active tasks may never share a lock.

## Tasks

| ID | Task | Depends on | Status | Owner | Branch | Locks | Updated |
|---|---|---|---|---|---|---|---|
| S1 | Apply SETUP.md: repo skeleton, pyproject, compose, env example | - | done | claude | main | pyproject.toml; docker-compose.yml; .env.example; .gitignore | 2026-10-17 22:16 |
| D-MEM | Apply Mem.md v2: memory core + its tests (expect 23 passed) | S1 | done | claude | main | memledger/config.py; memledger/db.py; memledger/queries.py; memledger/schema.py; memledger/memory.py; memledger/__init__.py; tests/conftest.py; tests/test_memory.py; tests/test_tenancy.py | 2026-10-17 22:17 |
| D-EXT | Apply EXT.md: extraction, ingest (expect 67) | D-MEM | done | claude | main | memledger/extract.py; memledger/ingest.py; scripts/try_extract.py; tests/test_extract.py; tests/test_conflicts.py; tests/test_ingest.py | 2026-10-17 22:18 |
| D-TRU | Apply TRU.md: trust, CLI, query block (expect 83) | D-EXT | done | claude | main | memledger/queries.py; memledger/trust.py; scripts/trust.py; scripts/__init__.py; tests/test_trust.py | 2026-10-17 22:19 |
| D-AGT | Apply AGT.md: agents, query block (expect 99) | D-TRU | done | claude | main | memledger/queries.py; memledger/agents/; scripts/run_team.py; tests/test_agents.py | 2026-10-17 22:20 |
| D-SCN | Apply SCN.md: scenario data, runner, demo CLI (expect 113, 1 xfailed) | D-AGT | done | claude | main | data/; memledger/scenario.py; scripts/demo.py; tests/test_scenario.py | 2026-10-17 22:23 |
| D-API | Apply API.md: API + console (expect 125, 1 xfailed once D-VENDOR is done) | D-SCN | done | claude | main | memledger/api.py; memledger/static/index.html; memledger/static/style.css; memledger/static/app.js; tests/test_api.py | 2026-10-17 22:26 |
| D-VENDOR | Download force-graph 1.47.4 into memledger/static/vendor/ (API.md §9) | D-API | done | claude | main | memledger/static/vendor/ | 2026-10-17 22:27 |
| D-MCP | Apply MCP.md: MCP server (expect 130, 1 skipped, 1 xfailed) | D-API | done | claude | main | memledger/mcp_server.py; tests/test_mcp.py | 2026-10-17 22:29 |
| D-TEN | Apply TEN.md: tenancy, bench, query block (expect 136) | D-MCP | done | claude | main | memledger/queries.py; memledger/tenancy.py; scripts/bench.py; tests/test_tenants.py | 2026-10-17 22:29 |
| D-EVL | Apply EVL.md: evaluation (expect 143, 1 skipped, 2 xfailed) | D-TEN | done | claude | main | data/acme/eval_questions.json; memledger/evaluate.py; scripts/eval.py; tests/test_eval.py | 2026-10-17 22:31 |
| D-DEP | Apply DEP.md: container, deploy, smoke (expect 149) | D-EVL | done | claude | main | Dockerfile; .dockerignore; .gcloudignore; requirements.txt; memledger/serve.py; scripts/deploy.sh; scripts/smoke.py; tests/test_deploy.py | 2026-10-17 22:32 |
| D-SUB | Apply SUB.md: README, disclosure, generator (expect 150, 1 skipped, 3 xfailed) | D-DEP | done | claude | main | README.md; AI_DISCLOSURE.md; scripts/readme_queries.py; tests/test_readme.py | 2026-10-17 22:33 |
| C1 | Move the inline Cypher in agents/team.py into queries.py; regenerate README; remove the xfail (SUB.md §2) | D-SUB | done | claude | main | memledger/agents/team.py; memledger/queries.py; README.md; tests/test_readme.py | 2026-10-17 22:34 |
| C2a | Apply the seed + as_of patch (SCN.md §12) and tests/test_patch.py; remove the SCN xfail | D-SUB | done | claude | main | memledger/queries.py; tests/test_patch.py; tests/test_scenario.py; README.md | 2026-10-17 22:36 |
| C2b | Apply the cross-process lock patch (TEN.md §5) | D-SUB | done | claude | main | memledger/memory.py | 2026-10-17 22:37 |
| C2c | Fix queries.SEED so all Sources are created on real FalkorDB 6.x (found in C6) | C2a | done | claude | main | memledger/queries.py; memledger/schema.py; tests/test_patch.py; README.md; docs/bench-results.txt | 2026-10-17 22:42 |
| C3 | Live run with Gemini: try_extract, demo live, fix aliases/expectations, commit the extraction cache | C2a | done | claude | main | data/.extract_cache.json; memledger/config.py; data/acme/scenario.json; data/globex/scenario.json | 2026-10-18 02:35 |
| C4 | Cross-agent revoke cascade in the scenario (SCN.md §9) | C3 | done | claude | main | data/acme/scenario.json; memledger/scenario.py; data/acme/eval_questions.json; tests/test_scenario.py; tests/test_eval.py; data/acme/alerts_s3.json; data/acme/golden_claims.json; tests/test_api.py | 2026-10-18 06:11 |
| C5 | Deploy to Cloud Run (DEP.md) and pass smoke.py --full | C3; D-VENDOR | done | claude | main | resource:cloud-run | 2026-10-18 06:02 |
| C6 | Benchmark against real FalkorDB 6.x; save the output | D-TEN | done | claude | main | resource:bench-db; docs/bench-results.txt | 2026-10-17 22:40 |
| C7 | Write README intro, numbers, AI_DISCLOSURE in your own words | C1; C3; C5; C6 | todo | - | - | README.md; AI_DISCLOSURE.md | - |
| C8 | Rehearse explaining the model and queries (SUB.md §3) | D-SUB | todo | - | - | - | - |
| C9 | Gemini rate-limit resilience: retry 429 honoring retryDelay, backoff, fallback model | D-SUB | done | claude | main | memledger/llm_retry.py; memledger/extract.py; memledger/agents/llm.py; memledger/config.py; tests/test_llm_retry.py | 2026-10-17 22:59 |
| C10 | C3 follow-ups: relax incident-scope prompt rule, daily-quota fast fallback, agent 429 no crash | C3; C9 | done | claude | main | memledger/extract.py; memledger/llm_retry.py; memledger/scenario.py; scripts/demo.py; data/.extract_cache.json; tests/test_extract.py; tests/test_llm_retry.py; tests/test_scenario.py | 2026-10-18 04:41 |
| D-SCN2 | Update docs/SCN.md (timeline §2, §9) for acme steps 16-20 (C4) | C4 | done | claude | main | docs/SCN.md | 2026-10-18 06:15 |
| C12 | Cache safety before C11: never cache fallback-model answers under the main model's key; check C10 v1-reuse impact on acme 5/7/8/16/17/20 | C10; C4 | done | claude | main | memledger/extract.py; memledger/llm_retry.py; tests/test_llm_retry.py; tests/test_extract.py; scripts/demo.py | 2026-10-18 06:23 |
| C11 | Fill extraction cache for the deployed config (acme --extract live --agents offline on gemini-3.5-flash, no fallback); redeploy with EXTRACT=cache | C12 | blocked | claude | main | data/.extract_cache.json; resource:cloud-run | 2026-10-18 07:28 |
| C13 | /demo landing page: YouTube demo hero, user guide, project info; eye-tracker (Watcher) in the header | C5 | done | claude | main | memledger/static/demo.html; memledger/static/demo.css; memledger/static/demo.js; memledger/api.py; tests/test_api.py | 2026-10-18 09:43 |
| V1 | Record the 3-minute video (SUB.md §6) | C5; C7 | todo | - | - | resource:cloud-run | - |
| V2 | Submit on WeMakeDevs, Track 02 (SUB.md §8 checklist) | V1; C8 | todo | - | - | - | - |

## Log

Append one line per change, newest last: `YYYY-MM-DD HH:MM owner: what changed`.

- 2026-10-17 19:40 claude: board created; nothing applied to the repo yet from this board's point of view (mark tasks you already did as done, with a log line)
- 2026-10-17 22:16 claude: claimed S1 on main
- 2026-10-17 22:16 claude: S1 -> done (tests: bare pytest 1 collection error (no module 'scripts', pre-existing; no conftest until D-MEM); python -m pytest 7 passed 2 failed (test_collab copies live board, expects S1 todo); applied SETUP.md: pyproject, compose, .env.example, .gitignore; next: D-MEM)
- 2026-10-17 22:17 claude: claimed D-MEM on main
- 2026-10-17 22:17 claude: D-MEM -> done (tests: python -m pytest 29 passed 3 failed (all test_collab board tests); excl collab 23 passed (matches expected); bare pytest fails conftest import (memledger not pip-installed in venv; pip install -e . would fix); applied Mem.md: config, db, queries, schema, memory, __init__, conftest, test_memory, test_tenancy; next: D-EXT)
- 2026-10-17 22:18 claude: claimed D-EXT on main
- 2026-10-17 22:18 claude: D-EXT -> done (tests: 73 passed 3 failed (test_collab board tests); excl collab 67 passed (matches expected); applied EXT.md: extract, ingest, test_extract/conflicts/ingest; try_extract.py copied by hand from EXT.md s17 (apply_docs does not pick it up); not run live (needs GEMINI_API_KEY); next: D-TRU)
- 2026-10-17 22:19 claude: claimed D-TRU on main
- 2026-10-17 22:19 claude: D-TRU -> done (tests: 89 passed 3 failed (test_collab board tests); excl collab 83 passed (matches expected); applied TRU.md: trust.py, scripts/trust.py, test_trust.py, TRU query block appended to queries.py; README query regen deferred (README not in locks); next: D-AGT)
- 2026-10-17 22:20 claude: claimed D-AGT on main
- 2026-10-17 22:20 claude: D-AGT -> done (tests: 105 passed 3 failed (test_collab board tests); excl collab 99 passed (matches expected); applied AGT.md: memledger/agents/*, test_agents.py, AGT query block appended; run_team.py copied by hand from AGT.md s14 (apply_docs misses it); not run live (needs GEMINI_API_KEY); next: D-SCN)
- 2026-10-17 22:23 claude: claimed D-SCN on main
- 2026-10-17 22:23 claude: D-SCN -> done (tests: 119 passed 3 failed (test_collab board tests) 1 xfailed; excl collab 113 passed 1 xfailed (matches expected); applied SCN.md: data/acme, data/globex, memledger/scenario.py, scripts/demo.py, tests/test_scenario.py; demo not run live; next: D-API)
- 2026-10-17 22:25 claude: claimed D-API on main
- 2026-10-17 22:26 claude: D-API -> done (tests: 130 passed 4 failed (3 test_collab board + test_ui_is_served awaiting vendor) 1 xfailed; excl collab 124 passed 1 failed (vendor) 1 xfailed (125 after D-VENDOR); applied API.md: memledger/api.py, static/index.html, style.css, app.js, tests/test_api.py; next: D-VENDOR)
- 2026-10-17 22:26 claude: claimed D-VENDOR on main
- 2026-10-17 22:27 claude: D-VENDOR -> done (tests: 125 passed 1 xfailed excl collab (full: 131 passed 3 failed test_collab board 1 xfailed); added memledger/static/vendor/force-graph.min.js v1.47.4 (164859 B, sha256 829a1d9e..., jsdelivr==unpkg); README credit not added (outside Locks); next: see board)
- 2026-10-17 22:27 claude: claimed D-MCP on main
- 2026-10-17 22:29 claude: D-MCP -> done (tests: 130 passed, 1 skipped, 1 xfailed (collab deselected; full run 136 passed, 3 collab board failures); added memledger/mcp_server.py + tests/test_mcp.py; next: D-TEN)
- 2026-10-17 22:29 claude: claimed D-TEN on main
- 2026-10-17 22:29 claude: D-TEN -> done (tests: 136 passed, 1 skipped, 1 xfailed (collab deselected; full run 142 passed, 3 collab board failures); added memledger/tenancy.py, scripts/bench.py, tests/test_tenants.py + tenancy query block; next: D-EVL)
- 2026-10-17 22:30 claude: claimed D-EVL on main
- 2026-10-17 22:31 claude: D-EVL -> done (tests: 143 passed, 1 skipped, 2 xfailed (collab deselected; full run 149 passed, 3 collab board failures); added data/acme/eval_questions.json, memledger/evaluate.py, scripts/eval.py, tests/test_eval.py; next: D-DEP)
- 2026-10-17 22:31 claude: claimed D-DEP on main
- 2026-10-17 22:32 claude: D-DEP -> done (tests: 149 passed, 1 skipped, 2 xfailed (collab deselected; full run 155 passed, 3 collab board failures); added Dockerfile, .dockerignore, .gcloudignore, requirements.txt, memledger/serve.py, scripts/deploy.sh, scripts/smoke.py, tests/test_deploy.py; next: D-SUB)
- 2026-10-17 22:32 claude: claimed D-SUB on main
- 2026-10-17 22:33 claude: D-SUB -> done (tests: 150 passed, 1 skipped, 3 xfailed (collab deselected; full run 155 passed, 4 collab board failures, fresh-board assumptions); moved README.md and AI_DISCLOSURE.md to root, added scripts/readme_queries.py, tests/test_readme.py, regenerated README queries (35); force-graph credit already present; next: C1)
- 2026-10-17 22:33 claude: claimed C1 on main
- 2026-10-17 22:34 claude: C1 -> done (tests: 151 passed, 1 skipped, 2 xfailed (collab deselected; full run 155 passed, 5 collab board failures, fresh-board assumptions); moved Team.route inline Cypher to queries.SOURCE_KIND, regenerated README queries (36), removed C1 xfail in tests/test_readme.py; next: C2)
- 2026-10-17 22:35 claude: claimed C2a on main
- 2026-10-17 22:36 claude: C2a -> done (tests: 156 passed, 1 skipped (collab deselected), 0 xfailed; SEED ON CREATE, REVOKE revoked_from, AS_OF from promotion; test_patch.py added; SCN xfail removed; README regenerated (added to locks); next: C3)
- 2026-10-17 22:36 claude: claimed C2b on main
- 2026-10-17 22:37 claude: C2b -> done (tests: 156 passed, 1 skipped (excl. test_collab); applied TEN.md §5 cross-process FalkorDB lock (_tenant_lock) in memory.py; next: see board)
- 2026-10-17 22:38 claude: claimed C6 on main
- 2026-10-17 22:40 claude: C6 -> done (FalkorDB 6.0.2 Docker: threads 134 w/s p99 88ms, 3644 r/s p99 14ms; 8 procs/1 tenant 248 w/s p99 527ms; 0 errors, I1 ok, no leaks - only with seed shim: queries.SEED creates 1 of 5 Sources on 6.x (needs fix task); saved to docs/bench-results.txt)
- 2026-10-17 22:41 claude: claimed C2c on main
- 2026-10-17 22:42 claude: C2c -> done (tests: 157 passed, 1 skipped (excl. test_collab); root cause: FalkorDB 6.x runs a 2nd UNWIND..MERGE after an aggregating WITH only once, so SEED made 1/5 Sources; fix: agents MERGEd via FOREACH; bench on 6.0.2 without shim: 0 errors; next: C3)
- 2026-10-17 22:57 claude: claimed C9 on main
- 2026-10-17 22:59 claude: C9 -> done (tests: 166 passed, 1 skipped (test_collab deselected); added memledger/llm_retry.py (retry 429/503 honoring retryDelay, backoff 2..60s, fallback model) used by GeminiLLM and GeminiChat; env GEMINI_MAX_RETRIES=5, GEMINI_FALLBACK_MODEL; next: C3)
- 2026-10-17 23:01 claude: claimed C3 on main
- 2026-10-18 02:35 claude: C3 -> done (tests: 166 passed, 1 skipped (test_collab deselected); globex: 7/7 checks ok (4 steps); acme: 20/31 ok, 8 x, 3 ~ (soft, agent steps 3/6/9) on live run, 21/31 after alias fix (step 7 verified on cached raw); changed: GEMINI_MODEL default gemini-3.5-flash (2.5-flash 404 for this key), ALIASES for live spellings incl. block-it-at-the-edge, committed extraction cache (37 entries); follow-ups: (1) extract.py prompt 'claims about the incident named in INCIDENT only' makes live Gemini return {claims: []} for webhook.json and app-logs, which never name inc-42, so acme step 8 stores nothing and steps 10/11/14 fail as a cascade; relax the rule + bump PROMPT_VERSION; (2) llm_retry retries a daily-quota 429 (retryDelay ~23h) with 61s sleeps before falling back; treat retryDelay > MAX_BACKOFF as no-retry; (3) demo crashes with a traceback on a 429 from an agent step instead of reporting it; (4) try_extract runbook: live model omits the ruled_out db-pool-exhaustion; free tier 20 req/day on gemini-3.5-flash, exhausted, agents ran on gemini-3.5-flash-lite; next: C4, C5)
- 2026-10-18 04:27 claude: claimed C10 on main
- 2026-10-18 04:41 claude: C10 -> done (tests: 173 passed, 1 skipped (test_collab deselected); acme: 26/31 live (extract live, agents offline; was 20/31): step 8 now stores root_cause=redis-outage, but flush-cache mitigation still missing -> steps 8/10/11/14 fail + step 9 soft; flash daily quota exhausted so every call fell back to flash-lite at once (no sleeps), and lite drops the recommended action (flash returned it in a probe); cache not committed (lite answers under flash key, agent texts carry random fact ids); changed: extract.py prompt ext-v2 (input-stream scope, keep claims that disagree with KNOWN VALUES, recommended action = mitigation) + COMPAT_PROMPT_VERSIONS reuses non-empty ext-v1 cache; llm_retry.is_daily_quota -> no retry; scenario.Runner reports agent 429/503 as a failed hard check; follow-up: when flash quota resets rerun demo --extract live (step 8 webhook) and commit cache; next: C4)
- 2026-10-18 05:50 claude: claimed C5 on main
- 2026-10-18 06:02 claude: C5 -> done (live: https://memledger-720170616128.asia-south1.run.app; smoke.py --full PASS (19 steps, 0 failed); region asia-south1; project multi-agent-ai-platform-a63ca; image asia-south1-docker.pkg.dev/multi-agent-ai-platform-a63ca/memledger/memledger:0baea84; EXTRACT=golden, AGENTS=offline, no Gemini key; next: step 8 cache rebuild (agents offline), then redeploy with EXTRACT=cache; C7)
- 2026-10-18 11:35 claude: C5 deploy details. Public demo is deployed WITHOUT a Gemini key: no secret, no GEMINI_* env var, nothing in the image. scripts/deploy.sh was NOT used (it requires a key and grants IAM); deviation approved by the project lead. Built locally and pushed instead of `--source`, so Cloud Build stays disabled and no build IAM changed. New resources only: Artifact Registry repo `memledger` (asia-south1), service account `memledger-run` (no roles), Cloud Run service `memledger`. Nothing existing (cortex-* services, secrets, IAM) was touched.
  - Image tag: `asia-south1-docker.pkg.dev/multi-agent-ai-platform-a63ca/memledger/memledger:0baea84` (commit 0baea84; contains data/.extract_cache.json with 41 entries; no .env, no data/.demo_state.json).
  - Build and push: `docker build -t $IMG . && docker push $IMG`
  - Deploy command (exact): `gcloud run deploy memledger --project=multi-agent-ai-platform-a63ca --region=asia-south1 --image=asia-south1-docker.pkg.dev/multi-agent-ai-platform-a63ca/memledger/memledger:0baea84 --service-account=memledger-run@multi-agent-ai-platform-a63ca.iam.gserviceaccount.com --allow-unauthenticated --min-instances=0 --max-instances=1 --cpu=1 --memory=512Mi --cpu-boost --timeout=300 --concurrency=40 --set-env-vars=MEMLEDGER_EXTRACT=golden,MEMLEDGER_AGENTS=offline,MEMLEDGER_ALLOW_RESET=1,MEMLEDGER_EMBEDDED_DB=1`
  - Cold start (Cloud Run logs, revision memledger-00001-82z): instance start 06:00:43.31Z, tenants seeded 06:00:46.43Z, STARTUP TCP probe passed 06:00:47.57Z on the first attempt = 4.3 s, against the default probe budget of 240 s (TCP, period 240 s, failureThreshold 1). cpu-boost on. Startup only seeds the tenants; the story is replayed on request, not at startup. Local: 1.3 s, memory ~81 MiB of 512 MiB.
  - Smoke output (`python scripts/smoke.py https://memledger-720170616128.asia-south1.run.app --full`):
        Smoke test: https://memledger-720170616128.asia-south1.run.app
          ✓ console page  679 ms
          ✓ graph library served
          ✓ health  {'ok': True, 'extract': 'golden', 'agents': 'offline', 'allow_reset': True}  165 ms
          ✓ tenants reachable (database connected)  185 ms
          ✓ tenant acme has a scenario
          ✓ tenant globex has a scenario
          ✓ globex: reset  HTTP 200
          ✓ globex step  1 observe           306 ms
          ✓ globex step  2 observe           196 ms
          ✓ globex step  3 status_update     204 ms
          ✓ globex step  4 isolation         175 ms
          ✓ acme: reset  HTTP 200
          ✓ acme step  1 observe           232 ms
          ✓ acme step  2 observe           220 ms
          ✓ acme step  3 investigate       181 ms
          ✓ acme step  4 status_update     185 ms
          ✓ acme step  5 observe           230 ms
          ✓ acme step  6 investigate       263 ms
          ✓ acme step  7 observe           200 ms
          ✓ acme step  8 observe           266 ms
          ✓ acme step  9 status_update     223 ms
          ✓ acme step 10 preview           186 ms
          ✓ acme step 11 revoke            233 ms
          ✓ acme step 12 status_update     210 ms
          ✓ acme step 13 ask               208 ms
          ✓ acme step 14 as_of             173 ms
          ✓ acme step 15 isolation         223 ms
        PASS
- 2026-10-18 11:36 claude: FINDING for the acme step 8 session. The extraction cache key includes the KNOWN VALUES in the graph at that step (extract.py Extractor.key). The committed cache came from C3's run with --agents live, so with --agents offline (what the public deploy uses) acme steps 5, 7 and 8 miss the cache -> extraction_failed (verified: demo.py --extract cache --agents offline fails at [5, 7, 8]; smoke --full fails the same way). That is why C5 is deployed with EXTRACT=golden. To switch the deploy to EXTRACT=cache, build the cache with `demo.py --tenant acme --extract live --agents offline --reset --all` (and globex likewise), commit data/.extract_cache.json, confirm `demo.py --extract cache --agents offline` passes for both tenants, then rebuild the image and redeploy with MEMLEDGER_EXTRACT=cache.
- 2026-10-18 06:07 claude: claimed C4 on main
- 2026-10-18 11:50 claude: C4 locks += data/acme/alerts_s3.json; data/acme/golden_claims.json (new forged-alert input and its golden claims)
- 2026-10-18 12:00 claude: C4 locks += tests/test_api.py (its full-demo test hard-codes 15 acme steps)
- 2026-10-18 06:11 claude: C4 -> done (tests: 174 passed, 1 skipped (test_collab deselected); acme steps 16-20 (session s3) added after step 15: forged checkout-api alert on the alerts feed (triage) -> investigator failover conclusion citing it (offline_parent) -> preview alerts: radius spans triage 3, investigator 1, comms 1 (step-4 status derived from the step-1 alert facts) -> revoke alerts withdraws exactly the preview's 5 facts, runbook facts stand -> comms rebuilds status from survivors. Steps 1-15 and their cache keys unchanged. New extraction calls in cache/live mode: 3 (step 16 alerts_s3.json, step 17 investigator text, step 20 comms text); golden needs none. scenario.py: OfflineChat.parent + expect key radius_agents. Not changed: eval questions (scores unchanged), docs/SCN.md (§2 timeline/§9 still describe 15 steps). Deployed demo still runs 15 steps until the next redeploy; next: step 8 cache rebuild with --agents offline --all (now 20 steps) then redeploy; C7)
- 2026-10-18 11:46 claude: redeployed 20-step acme on golden: revision memledger-00002-wqr, image asia-south1-docker.pkg.dev/multi-agent-ai-platform-a63ca/memledger/memledger:5100cd6, same flags/env (golden, offline, no key); smoke.py --full PASS incl. acme steps 16-20
- 2026-10-18 06:14 claude: claimed D-SCN2 on main
- 2026-10-18 06:15 claude: D-SCN2 -> done (docs/SCN.md: §2 timeline rows 16-20, §9 rewritten (webhook: one agent; alerts: three agents, extraction/caching note), plus §1 story bullet for session 3 and feature-table row so the doc stays consistent; tests 174 passed, 1 skipped)
- 2026-10-18 06:21 claude: claimed C12 on main
- 2026-10-18 06:23 claude: C12 -> done (tests: 175 passed, 1 skipped (test_collab deselected). (1) C9 finding fixed by NOT caching fallback answers: llm_retry.generate(on_answer=) reports the model that answered, GeminiLLM.last_model records it, Extractor caches only when the main model answered; test_fallback_answers_are_never_cached. (2) C10 finding: probe replayed acme 1-20 with --agents offline against the committed cache (41 entries, model gemini-3.5-flash): NO v2 or v1 key exists for steps 5, 7, 8, 16, 20 (step 17 made no call in the cache-only replay because step 16 missed; in C11 its key depends on live step-16 output). Steps 3-20 all miss; only steps 1-2 hit (non-empty ext-v1 answers for alerts.json, logs.txt). The global reuse rule does not affect C11's target steps, so no --refresh-steps was added (scripts/demo.py untouched). Note for C11: steps 1-2 will reuse their v1 answers, which is intended by the C10 rule; next: C11)
- 2026-10-18 11:54 claude: post-submission follow-ups from the C2c/C9/C10/C4 code review (left as-is by C12; the 2 C11-relevant findings were handled in C12):
  - llm_retry.with_retry sleeps on the request thread (up to ~5x61 s per model x 2 models): in live API mode that exceeds Cloud Run's 300 s timeout and holds threadpool slots. Harmless while the deploy is offline.
  - llm_retry._DAILY_RE matches 'daily'/'per day' anywhere in the error text, not only in the QuotaFailure quotaId, so a per-minute 429 can skip retries.
  - scenario.Runner: an agent 429 mid-step leaves earlier tool writes in the graph, yet marks the step failed and advances progress.
  - OfflineChat: an offline_parent that matches no active fact silently yields 'Nothing to change.' (step 17 is soft, so only the unit test catches it).
  - acme step 18 hard-checks radius_agents for triage and comms only; with live agents the investigator can be missing and the 'three agents' narration would be false. Consider a soft check for investigator.
  - Extractor breaks out of its own attempts on any transient error, so GEMINI_MAX_RETRIES=1 makes a single 503 fail extraction (untested behaviour change from C9).
  - llm_retry parses retryDelay twice (a walk over the details and a regex over the message); merge them.
  - GeminiLLM and GeminiChat duplicate the client/fallback/sleep plumbing for llm_retry.generate.

- 2026-10-18 07:08 claude: claimed C11 on main
- 2026-10-18 07:15 claude: C11 blocked: live run stopped on a DAILY-quota 429 at step 20 after 8 successful gemini-3.5-flash calls (steps 3,4,5,6,7,9,16,17; no fallback, spaced >=12 s). Step 8 (webhook) got NO answer: its call failed after llm_retry's retries (non-daily transient 429/503), so it was dropped as extraction_failed and steps 8/10/11/14 failed; those retries likely used the remaining daily requests. Per instructions: nothing committed (data/.extract_cache.json restored), site stays on EXTRACT=golden, no second run. A copy of the partial cache is in the session scratch dir (/tmp/claude-1000/cache_c11_partial.json); only its step 3-7 entries are on the correct chain (steps 9/16/17 were keyed on a graph missing step 8). Resume after the next quota reset (~12:30 IST tomorrow, after the deadline), or with a paid tier/second key: rerun acme from step 1; 11 calls expected.
- 2026-10-18 07:28 claude: C11 blocked: WON'T-FIX BEFORE SUBMISSION (project lead's decision). Root cause: fact ids are random (memory.new_id uses uuid4) and Comms' status text cites them ([f-xxxxxxxx]); that text is extracted, so the cache keys for steps 4/9/12/20 differ every run and never replay. In cache mode step 4 misses, no status is stored, and the known values at step 5 no longer match the live run's key, so every later step misses. Cached answers also quote the old ids as evidence, which the validator rejects. So no live run can build a replayable EXTRACT=cache + offline cache without a code change. No calls were made on the new key. Site stays on EXTRACT=golden (passes all 20 steps). Post-submission fix: make scenario fact ids deterministic, or strip [f-...] citations from text in both Extractor.key and evidence validation; then rerun C11 (~7 calls; the step 3/5/6/7 entries in data/.cache_c11_partial.json, git-ignored locally, stay valid). Note: the earlier 11-call dry-run estimate missed this because golden answered every miss.
- 2026-10-18 13:00 claude: C11 = won't-fix before submission (project lead). Site stays on EXTRACT=golden. The second key's quota is reserved for the video's live clip; C11 used none of it. Post-submission items:
  - Root cause: memory.new_id() uses uuid4, and Comms' status text cites fact ids ([f-xxxxxxxx]). That text is extracted, so cache keys for agent text (acme steps 4/9/12/20) differ every run and never replay; the chain then diverges from step 5 on.
  - Fix option A: deterministic fact ids in scenario runs (e.g. derived from tenant, step clock and a sequence). Touches the memory core and most tests.
  - Fix option B: strip [f-...] citations from the text in both Extractor.key and evidence validation, so agent-text answers replay across runs. Smaller, contained in extract.py.
  - After either fix: rerun C11 (~7 calls) reusing the step 3/5/6/7 entries in data/.cache_c11_partial.json (git-ignored locally), replay acme and globex, then redeploy with MEMLEDGER_EXTRACT=cache.
- 2026-10-18 09:38 claude: claimed C13 on main
- 2026-10-18 09:43 claude: C13 -> done (tests: 176 passed, 1 skipped (test_collab deselected); /demo landing page (demo.html/css/js): YouTube hero (set DEMO_VIDEO at the top of static/demo.js; empty shows a placeholder), problem, graph model + memory rules + the REVOKE query, the 20-step INC-42 story, console user guide + walkthrough, local setup, modes, API + MCP, eval scorecard (16/16 vs 8, verified with scripts/eval.py golden/offline), limits/FAQ. Header has the Watcher eye tracker ported to vanilla JS (no build step). Route GET /demo in api.py; test_demo_page_is_served. Not screenshot-verified (headless Chromium lacks libnss3 here). Not deployed yet: redeploy after the video URL is set.)
