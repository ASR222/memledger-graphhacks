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
