# INSTRUCTIONS.md — How to use the MemLedger docs

The single entry point for anyone working on MemLedger, person or AI agent. It covers:
- what each doc is for and the order to apply them in;
- how to turn the docs into code (with a script, not by hand);
- how several contributors work at once without overlapping;
- where debugging help lives.

**MemLedger:** shared memory for an incident-response agent team, stored as a graph in FalkorDB. Every belief records who wrote it, its source, when it was valid and what it was based on, so a compromised source can be revoked everywhere in one query. Built for GraphHacks 2026, Track 02.

**Deadline: Sun 18 Oct 2026, 11:59 PM IST** (target 10 PM; SUB.md §7 has the timeline).

**Status (17 Oct 2026):**
- Applying all twelve docs into an empty repo with `scripts/apply_docs.py`, plus this file's tools and the task board, gives **159 passed, 1 skipped, 3 expected failures**.
- The board tools have 9 tests.
- Every diagnostic query in DEBUG.md was run against a real graph.

> ### ⚠ One task per session
> **Each AI session completes exactly one task from `SETUP-STATUS.md`, then ends.** Start a fresh session for the next task.
>
> **Why:** every turn of a session re-sends everything already in its context. Context only grows, so a long session pays again and again for files it read hours ago. The docs total ~516 KB (very roughly 130k tokens). An agent that reads them all and then works for an hour spends most of its budget re-reading.
>
> **How:**
> - Claim one task.
> - Read only this file's relevant section and the one doc section that task needs (sizes in §5.5).
> - Finish, test, mark it done with a handoff line in the board log.
> - **End the session.**
>
> Details in §5.5.

---

## 1. Start here

```bash
# 0. one-time: put every doc in docs/, and this file, SETUP-STATUS.md and DEBUG.md at the repo root
mkdir -p docs && mv SETUP.md Mem.md EXT.md TRU.md AGT.md SCN.md API.md MCP.md TEN.md EVL.md DEP.md SUB.md docs/
# 1. copy scripts/status.py and scripts/apply_docs.py from §9 of this file; create an empty scripts/__init__.py
# 2. see what's free to work on, and claim it
python scripts/status.py next
python scripts/status.py claim S1 --owner <your-name>
# 3. do the task (§4), run its tests, then
python scripts/status.py done S1     # or: review S1
```

If you're an AI agent: read §5.2, §5.5 and §7 before touching anything, and do **one task per session** (§5.5).

---

## 2. The documents

Apply them in this order. Each one is additive on top of the ones before it.

| Doc | What it covers | Adds | Tests after applying |
|---|---|---|---|
| **SETUP.md** | repo skeleton, Docker FalkorDB, pyproject, rules for agents | `pyproject.toml`, `docker-compose.yml`, `.env.example`, `.gitignore` (its §5 code is **superseded** by Mem.md) | — |
| **Mem.md** (v2) | graph model, memory rules, invariants, every core query, the Python API | `config.py`, `db.py`, `queries.py`, `schema.py`, `memory.py`, core tests | 23 |
| **EXT.md** | extraction (Gemini), validation, conflicts, ingest | `extract.py`, `ingest.py`, `try_extract.py`, tests | 67 |
| **TRU.md** | trust, quarantine, revocation, blast radius, role permissions | `trust.py`, `scripts/trust.py`, query block | 83 |
| **AGT.md** | three agents, tools, handoffs, status updates | `agents/`, `scripts/run_team.py`, query block | 99 |
| **SCN.md** | the INC-42 story, input data, demo runner | `data/`, `scenario.py`, `scripts/demo.py` | 113 + 1 xfail |
| **API.md** | HTTP API and the operator console | `api.py`, `static/` (+ vendored graph library, §9 there) | 125 + 1 xfail |
| **MCP.md** | MemLedger MCP server; official FalkorDB MCP setup | `mcp_server.py` | 130 + 1 skip + 1 xfail |
| **TEN.md** | tenancy, tenant admin, concurrency benchmark | `tenancy.py`, `scripts/bench.py`, query block | 136 + 1 skip + 1 xfail |
| **EVL.md** | four memory designs, 16 questions, scorecard | `evaluate.py`, `scripts/eval.py`, questions | 143 + 1 skip + 2 xfail |
| **DEP.md** | container, Cloud Run deploy, smoke test, recovery | `Dockerfile`, `requirements.txt`, `serve.py`, `deploy.sh`, `smoke.py` | 149 + 1 skip + 2 xfail |
| **SUB.md** | submission rules, **your contribution plan (rule 13)**, video script, Q&A prep | `readme_queries.py` (+ `README.md`, `AI_DISCLOSURE.md` drafts as files) | 150 + 1 skip + 3 xfail |
| **INSTRUCTIONS.md** (this) | how to use all of the above; collaboration | `status.py`, `apply_docs.py`, `test_collab.py` | **159 + 1 skip + 3 xfail** |
| **SETUP-STATUS.md** | the task board | — | — |
| **DEBUG.md** | debugging playbook, written as a skill (§8) | — | — |

**What the skip and expected failures mean:**
- **Skip:** the official FalkorDB MCP test, which needs Node.
- **Expected failures:** two time-travel tests, fixed by task C2a, and the "no Cypher outside `queries.py`" check, fixed by task C1. They're strict: when the fix lands, they fail until you remove the `xfail` marker.

**Not verified anywhere yet:** live Gemini (extraction and agents), the Docker image build, the Cloud Run deploy, inside Claude Desktop. Tasks C3 and C5 cover these.

---

## 3. Conventions and precedence

1. **Code blocks in the docs are tested. Copy them verbatim,** with `scripts/apply_docs.py`, not by retyping.
2. **Precedence:** a later doc's copy of a file wins. Mem.md v2 supersedes SETUP.md §5 (`apply_docs.py` never extracts SETUP.md's memory-core code).
3. **Three docs append to `queries.py`** (TRU, AGT, TEN), in that order, after Mem's base. `apply_docs.py` handles it and won't append twice.
4. **No doc changes another doc's files after Mem v2.** Changes to existing code are proposed as patches (SCN.md §12, TEN.md §5) and applied by a task (C2a, C2b).
5. **All Cypher lives in `memledger/queries.py`**, and the README's query list is generated from it (`python scripts/readme_queries.py README.md`).
6. **Once code is edited by hand (tasks C1 onward), the docs are no longer the source for those files.** Never run `apply_docs.py --force` after that.
7. **Pending decisions** (owner: the project lead): apply C2a (seed + time-travel fix), C2b (cross-process lock), C1 (inline query). Until then the three expected failures stay.

---

## 4. Turning docs into code

**Install everything once** (tested versions):

```bash
python -m venv .venv && source .venv/bin/activate
pip install falkordb==1.8.0 redis==8.1.0 fastapi==0.143.3 "uvicorn[standard]==0.53.0" \
  google-genai==2.31.0 pydantic==2.13.5 python-dotenv==1.2.3 falkordblite==0.10.0 \
  pytest httpx "mcp==2.2.0"
```

SETUP.md's `pyproject.toml` also lists `langgraph` and `langchain-google-genai`. They're unused since AGT.md chose a plain tool loop; removing them is optional.

**Apply one doc** (that's what each `D-*` task on the board is):

```bash
python scripts/apply_docs.py --only TRU            # dry run: new / same / CHANGED / appended
python scripts/apply_docs.py --only TRU --write    # write new files, append its query block
pytest -q                                          # compare with the count in §2
```

- **`D-VENDOR`:** download the graph library (API.md §9).
- **`D-SUB`:** also copy the delivered `README.md` and `AI_DISCLOSURE.md` to the repo root, then run `python scripts/readme_queries.py README.md`.
- **Already built some of this by hand** (from SETUP.md or Mem.md v1)? Run the dry run. Files reported **CHANGED** differ from the docs. Compare them, keep what's right, and mark the board task done with a log line saying what you kept.
- **Apply everything at once** (one person, fresh repo): `python scripts/apply_docs.py --write`, then mark S1 to D-SUB done in one commit.

---

## 5. Working together without overlapping

### 5.1 The board

`SETUP-STATUS.md` lists every remaining task with:
- its **dependencies**;
- its **locks**: the files, folders (ending in `/`) or `resource:` names it may change.

`scripts/status.py` enforces two rules:
- **you can only claim a task whose dependencies are done;**
- **no two active tasks may hold the same lock.**

So `C1` and `C2a` (both touch `queries.py`) can't run at the same time, but `C2b` (`memory.py`) can run alongside either.

### 5.2 The loop (everyone, every task)

1. `git pull`.
2. `python scripts/status.py next` and pick a task.
3. `python scripts/status.py claim <ID> --owner <name>`.
4. **Commit and push the board change alone, immediately:** `git commit -am "status: claim <ID>" && git push`.
   - If the push is rejected, someone else changed the board: `git pull --rebase`.
   - If your task is now taken, `release` it and pick another.
   - **The board in `main` is the lock**; a claim only counts once it's pushed.
5. Work on the branch the claim named (`task/<id>`). **Touch only files in your task's locks.** If you need another file, update the task's locks on the board (and push) first, which fails if someone holds it.
6. `pytest -q` and `python scripts/status.py check` must both pass.
7. Open a PR, then `python scripts/status.py review <ID>`, or `done <ID>` if no review is needed. Push.
8. After merge, if you were in review: `done <ID>`.
9. **AI sessions: end the session here** (§5.5). The next task starts in a fresh one.

**Stuck?** `python scripts/status.py block <ID> --note "why"`. **Giving up a task?** `release <ID> --note "how far I got"`.

**Stale claims:** if a task has been `in-progress` with no commits for 3+ hours near the deadline, ask the owner. If there's no answer, the project lead may `release` it with a note.

### 5.3 Hot files

| File | Rule |
|---|---|
| `memledger/queries.py` | one task at a time (it's in every query-changing task's locks); append new queries at the end with a comment; rerun the README generator |
| `README.md` | only C7 and C1 lock it; the query section is generated, never hand-edited |
| `data/acme/scenario.json` | C3 and C4 lock it; changing a step changes eval expectations too |
| `SETUP-STATUS.md` | edit only through `status.py` (or a one-line log entry); always commit it alone |
| `data/.extract_cache.json` | C3 owns it; others don't commit changes to it |
| `tests/conftest.py` | nobody should need to change it; if you do, claim it explicitly |

### 5.4 Commits and PRs

- **Commit messages:** `<ID>: what changed`, e.g. `C1: move SOURCE_KIND into queries.py`. One task per PR.
- **Never** commit `.env`, keys, or `data/.demo_state.json`.
- **A PR description says** which board task it is, the test result line, and whether any file now differs from its doc.

### 5.5 One task per session (saves credits)

**Rule: one board task per AI session.** When the task is done (or blocked, or released), write the handoff line and **end the session**. The next task gets a new session that starts with only what it needs.

**At the start of a session, load only:**
1. `INSTRUCTIONS.md` §5.2 and this section, not the whole file;
2. your task's row in `SETUP-STATUS.md` (`python scripts/status.py show <ID>`);
3. **the one doc section the task names.** Use `grep -n "^## " docs/<Doc>.md` to find it, then read that range only;
4. the files in your task's locks.

**Don't load:**
- other docs;
- whole docs when one section will do;
- the full test output when `-q` will do;
- `DEBUG.md` unless something breaks, and then only the matching table.

For `D-*` tasks you usually don't need to read the doc at all: `apply_docs.py` copies the code and the test count tells you if it worked.

| Doc | Size | Doc | Size |
|---|---|---|---|
| SETUP | 23 KB | API | 67 KB |
| Mem | 57 KB | MCP | 29 KB |
| EXT | 70 KB | TEN | 30 KB |
| TRU | 35 KB | EVL | 34 KB |
| AGT | 54 KB | DEP | 27 KB |
| SCN | 64 KB | SUB | 20 KB |
| INSTRUCTIONS | 31 KB | DEBUG | 12 KB |

**Every session ends with a handoff line,** so the next session doesn't need this one's context:

```bash
python scripts/status.py done <ID> --note "tests: 159 passed; changed X; next: <ID2> can start"
# or, if unfinished:
python scripts/status.py release <ID> --note "did A and B; C left: <exact next step>"
```

The note goes into the board log, which is where the next session picks up. Then commit and push the board, and **end the session.**

**Also cheaper:**
- Run single test files while working (`pytest -q tests/test_x.py`) and the full suite once at the end.
- Use `-q` and `tail` on long outputs.
- Don't paste large files into chat; point to paths.
- If a task turns out bigger than one session, split it on the board (two rows with a dependency) rather than letting one session run long.

---

## 6. Where things stand

- **Docs:** all twelve written and tested in a sandbox. SUB.md §0 explains why your own contribution matters (rule 13).
- **Board:** 24 tasks, all `todo`. If your repo already has some of this, mark those tasks done with a log line.
- **Critical path to submission:** S1 → D-* (or one bulk apply) → C2a → C3 → C5 → C7 → V1 → V2. C1, C2b, C4, C6 and C8 can run alongside.

---

## 7. For AI coding agents (Claude Code and others)

Put this in the repo's `CLAUDE.md` (or your agent's instructions file):

```markdown
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
```

---

## 8. DEBUG.md as a skill

`DEBUG.md` has skill frontmatter (`name: memledger-debug`). To have Claude Code load it automatically in this repo:

```bash
mkdir -p .claude/skills/memledger-debug && cp DEBUG.md .claude/skills/memledger-debug/SKILL.md
```

Keep the root `DEBUG.md` as the human-readable copy. If you change one, copy it to the other.

It contains:
- the debugging method;
- a layer → files → tests map;
- the expected test results and what each skip or expected failure means;
- 46 symptom → cause → fix entries collected from every doc;
- nine diagnostic Cypher queries (all run against a real graph);
- a report template.

---

## 9. Source files (tested)

### `scripts/status.py`
```python
"""Keep SETUP-STATUS.md consistent so contributors never overlap.

    python scripts/status.py check                      # validate the board (run before every push)
    python scripts/status.py next [--owner NAME]        # tasks you can start now
    python scripts/status.py claim ID --owner NAME [--branch BR]
    python scripts/status.py review ID                  # work finished, waiting for a second look
    python scripts/status.py done ID
    python scripts/status.py block ID --note "why"
    python scripts/status.py release ID                 # give a task back (status -> todo)
    python scripts/status.py show [ID]

Rules enforced:
  - a task can be claimed only if all its dependencies are done
  - two active tasks (in-progress or review) may not share a lock
  - active tasks need an owner; done tasks need their dependencies done
Every change appends a line to the Log section.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

BOARD = Path(__file__).resolve().parents[1] / "SETUP-STATUS.md"
COLUMNS = ["ID", "Task", "Depends on", "Status", "Owner", "Branch", "Locks", "Updated"]
STATUSES = {"todo", "in-progress", "review", "done", "blocked"}
ACTIVE = {"in-progress", "review"}


class BoardError(Exception):
    pass


def _split(cell: str) -> list[str]:
    return [] if cell.strip() in ("", "-") else [x.strip() for x in cell.split(";") if x.strip()]


def load(path: Path = BOARD) -> tuple[list[str], list[dict], int, int]:
    """Return (all lines, task rows, index of first row line, index after last row)."""
    lines = path.read_text().splitlines()
    header = next(i for i, l in enumerate(lines) if l.startswith("| ID |"))
    cols = [c.strip() for c in lines[header].strip("|").split("|")]
    if cols != COLUMNS:
        raise BoardError(f"columns must be {COLUMNS}")
    start = header + 2
    end = start
    rows = []
    while end < len(lines) and lines[end].startswith("|"):
        cells = [c.strip() for c in lines[end].strip().strip("|").split("|")]
        if len(cells) != len(COLUMNS):
            raise BoardError(f"line {end + 1}: expected {len(COLUMNS)} cells, got {len(cells)}")
        rows.append(dict(zip(COLUMNS, cells)))
        end += 1
    return lines, rows, start, end


def save(lines, rows, start, end, log: str | None, path: Path = BOARD) -> None:
    body = ["| " + " | ".join(r[c] for c in COLUMNS) + " |" for r in rows]
    lines = lines[:start] + body + lines[end:]
    if log:
        lines.append(f"- {datetime.now().strftime('%Y-%m-%d %H:%M')} {log}")
    path.write_text("\n".join(lines) + "\n")


def overlaps(a: str, b: str) -> bool:
    """Same file, or one is a folder (ends with /) containing the other."""
    if a == b:
        return True
    return (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b))


def problems(rows: list[dict]) -> list[str]:
    out, ids = [], [r["ID"] for r in rows]
    by_id = {r["ID"]: r for r in rows}
    for d in {i for i in ids if ids.count(i) > 1}:
        out.append(f"duplicate id {d}")
    for r in rows:
        if r["Status"] not in STATUSES:
            out.append(f"{r['ID']}: unknown status {r['Status']!r}")
        for dep in _split(r["Depends on"]):
            if dep not in by_id:
                out.append(f"{r['ID']}: unknown dependency {dep}")
            elif r["Status"] in ACTIVE | {"done"} and by_id[dep]["Status"] != "done":
                out.append(f"{r['ID']} is {r['Status']} but dependency {dep} is {by_id[dep]['Status']}")
        if r["Status"] in ACTIVE and r["Owner"] in ("", "-"):
            out.append(f"{r['ID']} is {r['Status']} without an owner")
    active = [r for r in rows if r["Status"] in ACTIVE]
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            for la in _split(a["Locks"]):
                for lb in _split(b["Locks"]):
                    if overlaps(la, lb):
                        out.append(f"lock clash: {a['ID']} ({a['Owner']}) and {b['ID']} ({b['Owner']}) both hold {la if la == lb else la + ' / ' + lb}")
    return out


def clashes(task: dict, rows: list[dict]) -> list[str]:
    return [f"{r['ID']} ({r['Owner']}) holds {lb}" for r in rows
            if r["Status"] in ACTIVE and r["ID"] != task["ID"]
            for la in _split(task["Locks"]) for lb in _split(r["Locks"]) if overlaps(la, lb)]


def claimable(rows: list[dict]) -> list[dict]:
    by_id = {r["ID"]: r for r in rows}
    return [r for r in rows if r["Status"] == "todo"
            and all(by_id.get(d, {}).get("Status") == "done" for d in _split(r["Depends on"]))
            and not clashes(r, rows)]


def _get(rows, tid):
    for r in rows:
        if r["ID"] == tid:
            return r
    raise BoardError(f"no task {tid}")


def main(argv=None, path: Path = BOARD) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "next", "claim", "review", "done", "block", "release", "show"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--owner")
    ap.add_argument("--branch")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    try:
        lines, rows, start, end = load(path)
        if a.cmd == "check":
            p = problems(rows)
            for x in p:
                print(f"✗ {x}")
            counts = {s: sum(r["Status"] == s for r in rows) for s in sorted(STATUSES)}
            print("OK" if not p else "FAIL", counts)
            return 1 if p else 0
        if a.cmd == "next":
            for r in claimable(rows):
                print(f"{r['ID']:<9} {r['Task']}")
            return 0
        if a.cmd == "show":
            for r in rows if not a.id else [_get(rows, a.id)]:
                print(f"{r['ID']:<9} {r['Status']:<11} {r['Owner']:<12} {r['Task']}")
            return 0
        if not a.id:
            raise BoardError("give a task id")
        t = _get(rows, a.id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if a.cmd == "claim":
            if not a.owner:
                raise BoardError("claim needs --owner")
            if t["Status"] != "todo":
                raise BoardError(f"{t['ID']} is {t['Status']} (owner {t['Owner']}); pick another task")
            by_id = {r["ID"]: r for r in rows}
            waiting = [d for d in _split(t["Depends on"]) if by_id[d]["Status"] != "done"]
            if waiting:
                raise BoardError(f"{t['ID']} waits for {', '.join(waiting)}")
            c = clashes(t, rows)
            if c:
                raise BoardError(f"{t['ID']} would overlap: {'; '.join(c)}")
            t.update({"Status": "in-progress", "Owner": a.owner,
                      "Branch": a.branch or f"task/{t['ID'].lower()}", "Updated": now})
            log = f"{a.owner}: claimed {t['ID']} on {t['Branch']}"
        elif a.cmd in ("review", "done"):
            if t["Status"] not in ACTIVE:
                raise BoardError(f"{t['ID']} is {t['Status']}; claim it first")
            t.update({"Status": a.cmd, "Updated": now})
            log = f"{t['Owner']}: {t['ID']} -> {a.cmd}{(' (' + a.note + ')') if a.note else ''}"
        elif a.cmd == "block":
            if not a.note:
                raise BoardError("block needs --note explaining why")
            t.update({"Status": "blocked", "Updated": now})
            log = f"{t['Owner']}: {t['ID']} blocked: {a.note}"
        else:  # release
            log = f"{t['Owner']}: released {t['ID']}{(' (' + a.note + ')') if a.note else ''}"
            t.update({"Status": "todo", "Owner": "-", "Branch": "-", "Updated": now})
        p = problems(rows)
        if p:
            raise BoardError("change would leave the board inconsistent: " + "; ".join(p))
        save(lines, rows, start, end, log, path)
        print(log)
        return 0
    except BoardError as e:
        print(f"✗ {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

### `scripts/apply_docs.py`
```python
"""Copy the tested code out of the MemLedger docs into the repo.

    python scripts/apply_docs.py                         # dry run: what would change, all docs
    python scripts/apply_docs.py --only Mem,EXT          # just these docs
    python scripts/apply_docs.py --only TRU --write      # write new files, append query blocks
    python scripts/apply_docs.py --write --force         # also overwrite files that differ (careful)

Docs are read from docs/ (change with --docs). Order matters and is fixed:
SETUP, Mem, EXT, TRU, AGT, SCN, API, MCP, TEN, EVL, DEP, SUB. A later doc's
copy of a file wins over an earlier one (Mem.md v2 supersedes SETUP.md §5).

Safety: a file that already exists with different content is reported as
CHANGED and left alone unless --force. Once anyone has edited code (tasks
C1 onward), never use --force; apply the doc by hand instead.
"""
import argparse
import re
import sys
from pathlib import Path

ORDER = ["SETUP", "Mem", "EXT", "TRU", "AGT", "SCN", "API", "MCP", "TEN", "EVL", "DEP", "SUB"]
# SETUP.md's code sections for the memory core are v1 and superseded; take only these.
SETUP_ONLY = {"docker-compose.yml", "pyproject.toml", ".env.example", ".gitignore"}
APPEND = {"TRU": "### 13.1 Append", "AGT": "### 18.1 Append", "TEN": "### 10.1 Append"}
FILE_BLOCK = re.compile(r"^### (?:[\d.]+ )?`([^`]+)`([^\n]*)\n```[\w-]*\n(.*?)\n```", re.S | re.M)


def extract(doc: str, text: str) -> tuple[dict[str, str], list[str]]:
    """Return ({path: content}, [query blocks to append]) for one doc."""
    files: dict[str, str] = {}
    for path, tail, body in FILE_BLOCK.findall(text):
        if path.endswith("/") or " " in path:
            continue
        if doc == "SETUP" and path not in SETUP_ONLY:
            continue
        files[path] = body + "\n"
        if path == ".dockerignore" and "gcloudignore" in tail:
            files[".gcloudignore"] = body + "\n.gcloudignore\n"
    if doc == "SCN":                       # globex inputs share one section
        m = re.search(r"### `data/globex/` \(SCN-3\).*?```json\n(.*?)\n```\n```\n(.*?)\n```", text, re.S)
        if m:
            files["data/globex/alerts.json"] = m.group(1) + "\n"
            files["data/globex/logs.txt"] = m.group(2) + "\n"
    appends = []
    if doc in APPEND:
        m = re.search(re.escape(APPEND[doc]) + r".*?```python\n(.*?)\n```", text, re.S)
        if not m:
            raise SystemExit(f"{doc}.md: append block not found")
        appends.append(m.group(1) + "\n")
    return files, appends


def plan(docs_dir: Path, only: list[str] | None) -> tuple[dict[str, str], dict[str, list[str]]]:
    files, appends = {}, {}
    for doc in ORDER:
        if only and doc not in only:
            continue
        p = docs_dir / f"{doc}.md"
        if not p.exists():
            raise SystemExit(f"missing {p}")
        f, a = extract(doc, p.read_text())
        files.update(f)
        if a:
            appends[doc] = a
    return files, appends


def apply(docs_dir: Path, root: Path, only=None, write=False, force=False) -> dict:
    files, appends = plan(docs_dir, only)
    report = {"new": [], "same": [], "changed": [], "overwritten": [], "appended": [], "append_present": []}
    # queries.py counts as up to date if it is the base plus any of the appended blocks
    base_q = files.get("memledger/queries.py")
    for path, content in sorted(files.items()):
        target = root / path
        if not target.exists():
            report["new"].append(path)
        elif target.read_text() == content or (path == "memledger/queries.py"
                                               and _is_base_plus_blocks(target.read_text(), base_q, appends)):
            report["same"].append(path)
            continue
        elif force:
            report["overwritten"].append(path)
        else:
            report["changed"].append(path)
            continue
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            if path.endswith(".sh"):
                target.chmod(0o755)
    for pkg in ("memledger/__init__.py", "scripts/__init__.py"):
        if any(p.startswith(pkg.split("/")[0] + "/") and p.endswith(".py") for p in files):
            t = root / pkg
            if not t.exists():
                report["new"].append(pkg)
                if write:
                    t.parent.mkdir(parents=True, exist_ok=True)
                    t.write_text("")
    q = root / "memledger" / "queries.py"
    for doc, blocks in appends.items():
        for block in blocks:
            marker = block.splitlines()[0]
            current = q.read_text() if q.exists() else (files.get("memledger/queries.py", "") if write else "")
            if marker in current:
                report["append_present"].append(f"queries.py <- {doc}")
            else:
                report["appended"].append(f"queries.py <- {doc}")
                if write:
                    if not q.exists():
                        raise SystemExit("memledger/queries.py missing: apply Mem first")
                    q.write_text(q.read_text().rstrip("\n") + "\n\n" + block)
    return report


def _is_base_plus_blocks(current: str, base: str, appends: dict) -> bool:
    """True if current == base followed by some of the appended blocks, in order."""
    if not current.startswith(base.rstrip("\n")):
        return False
    rest = current[len(base.rstrip("\n")):]
    for blocks in appends.values():
        for block in blocks:
            piece = "\n\n" + block.rstrip("\n")
            if rest.startswith(piece):
                rest = rest[len(piece):]
    return rest.strip() == ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--root", default=".")
    ap.add_argument("--only", help="comma-separated doc names, e.g. Mem,EXT")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    only = [d.strip() for d in a.only.split(",")] if a.only else None
    if only and any(d not in ORDER for d in only):
        raise SystemExit(f"--only takes names from {ORDER}")
    r = apply(Path(a.docs), Path(a.root), only, a.write, a.force)
    verb = "" if a.write else "(dry run) "
    for k in ("new", "overwritten", "appended", "changed", "same", "append_present"):
        for p in r[k]:
            print(f"{verb}{k:<15} {p}")
    if r["changed"]:
        print(f"\n{len(r['changed'])} file(s) differ from the docs and were left alone. "
              "Compare them by hand; use --force only if nobody has edited them.")
    if not a.write:
        print("\nNothing written. Add --write to apply.")
    return 1 if r["changed"] else 0


if __name__ == "__main__":
    sys.exit(main())
```

### `tests/test_collab.py`
```python
"""Task board and doc extraction (INSTRUCTIONS.md)."""
import shutil
from pathlib import Path

import pytest

from scripts import apply_docs as A
from scripts import status as st

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def board(tmp_path):
    p = tmp_path / "SETUP-STATUS.md"
    shutil.copy(ROOT / "SETUP-STATUS.md", p)
    return p


def run(board, *args):
    return st.main(list(args), path=board)


def status_of(board, tid):
    return next(r for r in st.load(board)[1] if r["ID"] == tid)


def mark_done(board, *ids):
    lines, rows, s, e = st.load(board)
    for r in rows:
        if r["ID"] in ids:
            r.update({"Status": "done", "Owner": "test"})
    st.save(lines, rows, s, e, None, board)


def test_fresh_board_is_valid_and_starts_with_setup(board, capsys):
    assert run(board, "check") == 0
    capsys.readouterr()
    assert run(board, "next") == 0
    assert capsys.readouterr().out.split()[0] == "S1"


def test_claim_respects_dependencies(board, capsys):
    assert run(board, "claim", "D-MEM", "--owner", "ana") == 2
    assert "waits for S1" in capsys.readouterr().out
    assert run(board, "claim", "S1", "--owner", "ana") == 0
    r = status_of(board, "S1")
    assert (r["Status"], r["Owner"], r["Branch"]) == ("in-progress", "ana", "task/s1")
    assert "ana: claimed S1 on task/s1" in board.read_text().splitlines()[-1]
    assert run(board, "claim", "S1", "--owner", "bo") == 2       # already taken


def test_locks_prevent_overlap(board, capsys):
    upstream = ["S1", "D-MEM", "D-EXT", "D-TRU", "D-AGT", "D-SCN", "D-API", "D-VENDOR",
                "D-MCP", "D-TEN", "D-EVL", "D-DEP", "D-SUB"]
    mark_done(board, *upstream)
    assert run(board, "claim", "C1", "--owner", "ana") == 0
    capsys.readouterr()
    assert run(board, "claim", "C2a", "--owner", "bo") == 2       # both lock queries.py
    assert "C1 (ana) holds memledger/queries.py" in capsys.readouterr().out
    assert run(board, "claim", "C2b", "--owner", "bo") == 0       # memory.py only: fine in parallel
    run(board, "next")
    assert "C2a" not in capsys.readouterr().out
    assert run(board, "done", "C1") == 0
    assert run(board, "claim", "C2a", "--owner", "bo") == 0


def test_folder_locks_cover_files():
    assert st.overlaps("memledger/agents/", "memledger/agents/team.py")
    assert st.overlaps("data/", "data/acme/scenario.json")
    assert not st.overlaps("memledger/api.py", "memledger/api_v2.py")
    assert not st.overlaps("data/acme/", "data/globex/logs.txt")


def test_check_catches_a_hand_edited_clash(board, capsys):
    text = board.read_text()
    text = text.replace("| C2a | Apply the seed + as_of patch (SCN.md §12) and tests/test_patch.py; remove the SCN xfail | D-SUB | todo | - | - |",
                        "| C2a | Apply the seed + as_of patch (SCN.md §12) and tests/test_patch.py; remove the SCN xfail | D-SUB | in-progress | bo | b |")
    text = text.replace("| C2b | Apply the cross-process lock patch (TEN.md §5) | D-SUB | todo | - | - |",
                        "| C2b | Apply the cross-process lock patch (TEN.md §5) | D-SUB | in-progress | - | b |")
    board.write_text(text)
    assert run(board, "check") == 1
    out = capsys.readouterr().out
    assert "C2a is in-progress but dependency D-SUB is todo" in out
    assert "C2b is in-progress without an owner" in out


def test_review_done_block_release(board):
    run(board, "claim", "S1", "--owner", "ana")
    assert run(board, "review", "S1") == 0 and status_of(board, "S1")["Status"] == "review"
    assert run(board, "done", "S1") == 0 and status_of(board, "S1")["Status"] == "done"
    run(board, "claim", "D-MEM", "--owner", "ana")
    assert run(board, "block", "D-MEM") == 2                       # needs --note
    assert run(board, "block", "D-MEM", "--note", "docker won't start") == 0
    assert run(board, "release", "D-MEM") == 0
    r = status_of(board, "D-MEM")
    assert (r["Status"], r["Owner"]) == ("todo", "-")
    assert run(board, "check") == 0


DOCS = ROOT / "docs"


@pytest.mark.skipif(not (DOCS / "Mem.md").exists(), reason="docs/ not present")
def test_apply_docs_full_then_idempotent(tmp_path):
    r = A.apply(DOCS, tmp_path, write=True)
    assert len(r["new"]) > 55 and r["changed"] == [] and len(r["appended"]) == 3
    assert not (tmp_path / "scripts" / "seed.py").exists()          # SETUP v1 code not taken
    mem = A.extract("Mem", (DOCS / "Mem.md").read_text())[0]["memledger/queries.py"]
    q = (tmp_path / "memledger" / "queries.py").read_text()
    assert q.startswith(mem.rstrip("\n")) and "agents (AGT.md)" in q and "tenancy (TEN.md)" in q
    again = A.apply(DOCS, tmp_path, write=True)
    assert again["new"] == [] and again["changed"] == [] and again["appended"] == []
    assert (tmp_path / ".gcloudignore").read_text().endswith(".gcloudignore\n")


@pytest.mark.skipif(not (DOCS / "Mem.md").exists(), reason="docs/ not present")
def test_apply_docs_never_clobbers_edits(tmp_path):
    A.apply(DOCS, tmp_path, write=True)
    f = tmp_path / "memledger" / "agents" / "team.py"
    f.write_text(f.read_text() + "# my change\n")
    r = A.apply(DOCS, tmp_path, write=True)
    assert r["changed"] == ["memledger/agents/team.py"] and f.read_text().endswith("# my change\n")
    r = A.apply(DOCS, tmp_path, write=True, force=True)
    assert r["overwritten"] == ["memledger/agents/team.py"] and not f.read_text().endswith("# my change\n")


@pytest.mark.skipif(not (DOCS / "Mem.md").exists(), reason="docs/ not present")
def test_apply_docs_one_doc_at_a_time(tmp_path):
    for doc in A.ORDER:
        A.apply(DOCS, tmp_path, only=[doc], write=True)
    assert A.apply(DOCS, tmp_path)["changed"] == []
```

`SETUP-STATUS.md` and `DEBUG.md` are delivered as separate files.
