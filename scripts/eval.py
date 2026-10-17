"""Run the scenario evaluation and print the results table.

    python scripts/eval.py --extract golden --agents offline     # rehearsal, no key
    python scripts/eval.py --extract cache  --agents live        # after one live run
    python scripts/eval.py --embedded --extract golden --agents offline --out data/acme/eval_results

Writes <out>.json (every answer, the claim stream) and <out>.md (the table).
Uses the tenant's graph: it is reset first.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memledger import evaluate  # noqa: E402
from memledger import scenario as S  # noqa: E402
from scripts.demo import make  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="acme")
    ap.add_argument("--extract", choices=["live", "cache", "golden"], default="cache")
    ap.add_argument("--agents", choices=["live", "offline"], default="live")
    ap.add_argument("--embedded", action="store_true", help="embedded FalkorDB (no Docker)")
    ap.add_argument("--out", help="write <out>.json and <out>.md")
    a = ap.parse_args(argv)
    lite = None
    if a.embedded:
        from scripts.bench import start_embedded
        lite = start_embedded()
    try:
        sc = S.load(a.tenant)
        ex, llm = make(sc, a.extract, a.agents)
        res = evaluate.run(ex, llm, a.tenant, state_path=Path(tempfile.mkdtemp()) / "eval_state.json")
    finally:
        if lite is not None:
            lite.close()
    md = evaluate.table(res)
    print(f"Mode: extract={a.extract}, agents={a.agents}\n")
    print(md)
    dep = [r["id"] for r in res["rows"] if r["depends_on_agents"]]
    print(f"\nQuestions whose expected answer depends on agent behaviour: {', '.join(dep)}")
    if a.out:
        Path(a.out + ".json").write_text(json.dumps({**res, "mode": vars(a)}, indent=1))
        Path(a.out + ".md").write_text(f"Mode: extract={a.extract}, agents={a.agents}\n\n{md}\n")
        print(f"\nWrote {a.out}.json and {a.out}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
