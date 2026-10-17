"""The README lists every query the product runs (SUB.md, hackathon rule 10)."""
import re
from pathlib import Path

import pytest

from scripts import readme_queries as rq

ROOT = Path(__file__).resolve().parents[1]


def test_readme_lists_every_query():
    text = (ROOT / "README.md").read_text()
    block = text.split(rq.START, 1)[1].split(rq.END, 1)[0]
    names = [n for n, _, _ in rq.queries()]
    assert len(names) >= 30
    missing = [n for n in names if f"#### `{n}`" not in block]
    assert missing == [], f"run: python scripts/readme_queries.py README.md  (missing {missing})"
    assert block.strip() == rq.markdown().strip(), "README queries are stale; rerun the generator"


@pytest.mark.xfail(strict=True, reason="SUB.md task C1: move the inline query in agents/team.py to queries.py")
def test_no_cypher_outside_queries_py():
    found = []
    for path in (ROOT / "memledger").rglob("*.py"):
        if path.name == "queries.py":
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\b(MATCH|MERGE|CREATE)\s*\(", line):
                found.append(f"{path.relative_to(ROOT)}:{i}")
    assert found == []
