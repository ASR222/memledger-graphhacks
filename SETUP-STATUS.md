# SETUP-STATUS

The shared task board for MemLedger. **Claim a task here before you touch its files.** Rules are in `INSTRUCTIONS.md` §5; `python scripts/status.py check` must pass before every push.

Statuses: `todo` · `in-progress` · `review` · `done` · `blocked`. Owner is a person or an agent name. Locks are the files (or folders ending in `/`, or `resource:` names) a task may change; two active tasks may never share a lock.

## Tasks

| ID | Task | Depends on | Status | Owner | Branch | Locks | Updated |
|---|---|---|---|---|---|---|---|
| S1 | Apply SETUP.md: repo skeleton, pyproject, compose, env example | - | done | claude | main | pyproject.toml; docker-compose.yml; .env.example; .gitignore | 2026-10-17 22:16 |
| D-MEM | Apply Mem.md v2: memory core + its tests (expect 23 passed) | S1 | done | claude | main | memledger/config.py; memledger/db.py; memledger/queries.py; memledger/schema.py; memledger/memory.py; memledger/__init__.py; tests/conftest.py; tests/test_memory.py; tests/test_tenancy.py | 2026-10-17 22:17 |
| D-EXT | Apply EXT.md: extraction, ingest (expect 67) | D-MEM | todo | - | - | memledger/extract.py; memledger/ingest.py; scripts/try_extract.py; tests/test_extract.py; tests/test_conflicts.py; tests/test_ingest.py | - |
| D-TRU | Apply TRU.md: trust, CLI, query block (expect 83) | D-EXT | todo | - | - | memledger/queries.py; memledger/trust.py; scripts/trust.py; scripts/__init__.py; tests/test_trust.py | - |
| D-AGT | Apply AGT.md: agents, query block (expect 99) | D-TRU | todo | - | - | memledger/queries.py; memledger/agents/; scripts/run_team.py; tests/test_agents.py | - |
| D-SCN | Apply SCN.md: scenario data, runner, demo CLI (expect 113, 1 xfailed) | D-AGT | todo | - | - | data/; memledger/scenario.py; scripts/demo.py; tests/test_scenario.py | - |
| D-API | Apply API.md: API + console (expect 125, 1 xfailed once D-VENDOR is done) | D-SCN | todo | - | - | memledger/api.py; memledger/static/index.html; memledger/static/style.css; memledger/static/app.js; tests/test_api.py | - |
| D-VENDOR | Download force-graph 1.47.4 into memledger/static/vendor/ (API.md §9) | D-API | todo | - | - | memledger/static/vendor/ | - |
| D-MCP | Apply MCP.md: MCP server (expect 130, 1 skipped, 1 xfailed) | D-API | todo | - | - | memledger/mcp_server.py; tests/test_mcp.py | - |
| D-TEN | Apply TEN.md: tenancy, bench, query block (expect 136) | D-MCP | todo | - | - | memledger/queries.py; memledger/tenancy.py; scripts/bench.py; tests/test_tenants.py | - |
| D-EVL | Apply EVL.md: evaluation (expect 143, 1 skipped, 2 xfailed) | D-TEN | todo | - | - | data/acme/eval_questions.json; memledger/evaluate.py; scripts/eval.py; tests/test_eval.py | - |
| D-DEP | Apply DEP.md: container, deploy, smoke (expect 149) | D-EVL | todo | - | - | Dockerfile; .dockerignore; .gcloudignore; requirements.txt; memledger/serve.py; scripts/deploy.sh; scripts/smoke.py; tests/test_deploy.py | - |
| D-SUB | Apply SUB.md: README, disclosure, generator (expect 150, 1 skipped, 3 xfailed) | D-DEP | todo | - | - | README.md; AI_DISCLOSURE.md; scripts/readme_queries.py; tests/test_readme.py | - |
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
