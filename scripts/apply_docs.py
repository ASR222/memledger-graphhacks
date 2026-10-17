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
# A heading naming a file, optional blank lines, then its fenced block.
FILE_BLOCK = re.compile(r"^### (?:[\d.]+ )?`([^`]+)`([^\n]*)\n(?:[ \t]*\n)*```[\w-]*\n(.*?)\n```", re.S | re.M)


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
