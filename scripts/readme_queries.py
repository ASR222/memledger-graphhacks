"""Render every Cypher query in memledger/queries.py into the README.

    python scripts/readme_queries.py README.md          # rewrite the block in place
    python scripts/readme_queries.py --print            # print the Markdown

The README must contain the markers
    <!-- QUERIES:START -->
    <!-- QUERIES:END -->
Everything between them is replaced, so the README always lists exactly the
queries the code runs (hackathon rule 10).
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- QUERIES:START -->", "<!-- QUERIES:END -->"


def queries() -> list[tuple[str, str, str]]:
    """(name, comment above it, Cypher) for every string or list constant, in file order."""
    src = (ROOT / "memledger" / "queries.py").read_text()
    lines = src.splitlines()
    out = []
    for node in ast.parse(src).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id.isupper()):
            continue
        value = ast.literal_eval(node.value)
        cypher = "\n".join(value) if isinstance(value, list) else value
        comment, i = [], node.lineno - 2
        while i >= 0 and lines[i].startswith("#") and not lines[i].startswith("# ---"):
            comment.insert(0, lines[i].lstrip("# ").rstrip())
            i -= 1
        out.append((node.targets[0].id, " ".join(comment), cypher.strip()))
    return out


def markdown() -> str:
    qs = queries()
    parts = [f"All {len(qs)} queries the product runs, generated from `memledger/queries.py`.\n"]
    for name, comment, cypher in qs:
        parts.append(f"#### `{name}`\n\n{comment or ''}\n\n```cypher\n{cypher}\n```\n")
    return "\n".join(parts)


def rewrite(readme: Path) -> int:
    text = readme.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"{readme} needs the markers {START} and {END}")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    readme.write_text(f"{head}{START}\n{markdown()}\n{END}{tail}")
    return len(queries())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "--print":
        print(f"wrote {rewrite(Path(sys.argv[1]))} queries into {sys.argv[1]}")
    else:
        print(markdown())
