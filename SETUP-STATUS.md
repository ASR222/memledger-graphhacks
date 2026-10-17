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
| C1 | Move the inline Cypher in agents/team.py into queries.py; regenerate README; remove the xfail (SUB.md §2) | D-SUB | todo | - | - | memledger/agents/team.py; memledger/queries.py; README.md; tests/test_readme.py | - |
| C2a | Apply the seed + as_of patch (SCN.md §12) and tests/test_patch.py; remove the SCN xfail | D-SUB | todo | - | - | memledger/queries.py; tests/test_patch.py; tests/test_scenario.py | - |
| C2b | Apply the cross-process lock patch (TEN.md §5) | D-SUB | todo | - | - | memledger/memory.py | - |
| C3 | Live run with Gemini: try_extract, demo live, fix aliases/expectations, commit the extraction cache | C2a | todo | - | - | data/.extract_cache.json; memledger/config.py; data/acme/scenario.json; data/globex/scenario.json | - |
| C4 | Cross-agent revoke cascade in the scenario (SCN.md §9) | C3 | todo | - | - | data/acme/scenario.json; memledger/scenario.py; data/acme/eval_questions.json; tests/test_scenario.py; tests/test_eval.py | - |
| C5 | Deploy to Cloud Run (DEP.md) and pass smoke.py --full | C3; D-VENDOR | todo | - | - | resource:cloud-run | - |
| C6 | Benchmark against real FalkorDB 6.x; save the output | D-TEN | todo | - | - | resource:bench-db | - |
| C7 | Write README intro, numbers, AI_DISCLOSURE in your own words | C1; C3; C5; C6 | todo | - | - | README.md; AI_DISCLOSURE.md | - |
| C8 | Rehearse explaining the model and queries (SUB.md §3) | D-SUB | todo | - | - | - | - |
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
