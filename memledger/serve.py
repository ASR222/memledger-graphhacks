"""Container entrypoint:  python -m memledger.serve

Runs the API and console with one worker on $PORT (default 8080).

MEMLEDGER_EMBEDDED_DB=1 starts FalkorDB inside the process (falkordblite)
instead of connecting to FALKORDB_HOST. Data then lives in the container
and is lost when it restarts.

In both modes, every tenant with a scenario that has no graph yet is created
(empty, seeded) at startup, so the console's Next step works straight away.
Existing graphs are never touched.
"""
import os
from pathlib import Path


def start_embedded_db():
    from redislite.falkordb_client import FalkorDB as Lite

    from . import db
    path = Path(os.getenv("MEMLEDGER_EMBEDDED_PATH", "/tmp/memledger/falkordb.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    lite = Lite(str(path))
    db._db = lite
    return lite


def create_scenario_tenants() -> list[str]:
    """Create (never reset) every tenant that has data/<tenant>/scenario.json."""
    from . import tenancy
    from .scenario import DATA
    made = []
    for d in sorted(DATA.iterdir()) if DATA.exists() else []:
        if (d / "scenario.json").exists() and tenancy.create(d.name)["created"]:
            made.append(d.name)
    return made


def reset_progress(tenants: list[str]) -> None:
    """A tenant created just now is empty, so its demo progress starts at 0."""
    import json
    path = Path(os.getenv("MEMLEDGER_DEMO_STATE") or Path(__file__).resolve().parents[1] / "data" / ".demo_state.json")
    try:
        state = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        state = {}
    for t in tenants:
        state[t] = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1))


def main():
    import uvicorn
    lite = None
    if os.getenv("MEMLEDGER_EMBEDDED_DB") == "1":
        lite = start_embedded_db()
        print("embedded FalkorDB ready", flush=True)
    made = create_scenario_tenants()
    reset_progress(made)
    print(f"created tenants: {made or 'none (all exist)'}", flush=True)
    state = os.getenv("MEMLEDGER_DEMO_STATE")
    if state:
        Path(state).parent.mkdir(parents=True, exist_ok=True)
    from .api import create_app
    try:
        uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")),
                    workers=1, proxy_headers=True, forwarded_allow_ips="*")
    finally:
        if lite is not None:
            lite.close()


if __name__ == "__main__":
    main()
