# MemLedger: agent rules
- ONE TASK PER SESSION. Claim one board task, finish it, write the handoff note
  (`status.py done/release <ID> --note ...`), push, then end the session.
- Load only what the task needs: INSTRUCTIONS.md §5.2 and §5.5, your task's board row, the one
  doc section it names (find it with `grep -n "^## " docs/<Doc>.md`), and your locked files.
  Never read all the docs.
- Read INSTRUCTIONS.md first. Docs are in docs/; the task board is SETUP-STATUS.md.
- Before editing anything: `python scripts/status.py next`, then claim ONE task with
  `python scripts/status.py claim <ID> --owner <agent-name>`; commit and push the board alone.
- Only edit files listed in your task's Locks. Need another file? Add it to the task's locks
  through the board first; if that clashes, stop and report.
- Apply docs only with `python scripts/apply_docs.py --only <Doc> [--write]`. Never use --force.
- All Cypher goes in memledger/queries.py; afterwards run `python scripts/readme_queries.py README.md`.
- Done means: `pytest -q` matches INSTRUCTIONS.md §2 (or better) and `python scripts/status.py check` is OK.
- Something broken? Use the memledger-debug skill (DEBUG.md). Don't change test expectations
  to make a failure go away.
- Never commit secrets. Never claim more than one task at a time.
