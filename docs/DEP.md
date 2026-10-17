# DEP.md — MemLedger Deployment

Complete context for putting MemLedger on a public URL: the two ways to run the database, the container, the deploy script, how to verify a deployment, what happens on restarts, and a checklist for the judging period. Covers workstream DEP on the build board (DEP-1 to DEP-3).

**Status (17 Oct 2026):**
- Every file in section 11 was run, except the parts in "Not verified" below. The full suite is **149 passed, 1 skipped, 2 expected failures** (the 143 from earlier docs plus 6 new tests).
- **Tested for real:**
  - **The container's exact start command** (`python -m memledger.serve`), in both database modes. The full smoke test, which replays both scenarios over HTTP (19 steps), passed against each.
  - **An app restart** with the graph kept but the progress file lost.
  - **The database wiped while the app was running** (what a FalkorDB Cloud free instance does when it idles out). The app reported it clearly, Reset recovered, and the full smoke test passed again.
- **Not verified:**
  - **The Docker image build.** Docker Hub is blocked from my sandbox, so I couldn't pull `python:3.12-slim`. The Dockerfile was checked by hand and by a test (§10).
  - **The Cloud Run deploy.** I have no access to your project. The script's syntax is checked, and its flags follow the Cloud Run docs.

**This file is additive. It does not change any earlier doc.** It adds:

| File | Purpose |
|---|---|
| `Dockerfile`, `.dockerignore`, `.gcloudignore` | the container and what goes into it |
| `requirements.txt` | runtime dependencies pinned to the tested versions |
| `memledger/serve.py` | container entrypoint: one worker on `$PORT`, optional embedded FalkorDB, creates missing tenants |
| `scripts/deploy.sh` | Cloud Run deploy from source, with secrets |
| `scripts/smoke.py` | post-deploy check (standard library only); `--full` replays the story |
| `tests/test_deploy.py` | 6 tests |

---

## 1. The decision: where FalkorDB runs

| | **A. Embedded** (`MODE=embedded`) | **B. FalkorDB Cloud free tier** (`MODE=cloud`) |
|---|---|---|
| What | FalkorDB runs inside the app container (falkordblite) | managed FalkorDB instance; the app connects over the network |
| Version | **4.18.3** (the version all tests ran on) | current Cloud release (6.x) |
| Data survives an app restart | **no**: tenants are recreated empty, press Reset | yes, until the instance stops |
| Expires | **never** (as long as the Cloud Run service exists) | **stopped after 1 day unused, deleted after 7**; no persistence or backups (FalkorDB docs) |
| Size limit | container memory (1 GiB set) | 100 MB |
| TLS | n/a (in-process) | none on the free tier |
| Shows judges | "FalkorDB is the database" | "runs on FalkorDB Cloud", the sponsor's product |

**Recommendation:**
- **Submit the embedded deployment as the live URL.** Judging will likely happen after Sunday. A free cloud instance that sits unused for a day is stopped, and after 7 days it's deleted, so judges could open a dead demo. The embedded one can't expire. It loses data on restart, but recovery is one click (§6).
- **Optionally also run B while recording**, so the video can show the sponsor's cloud product. Say in the README which URL uses which.

**A third option, not tested:** run the official `falkordb/falkordb` image (6.x) as a **sidecar container in the same Cloud Run service**, with the app talking to `localhost:6379`. That gives 6.x with no expiry. It needs a multi-container service YAML instead of `--source`, so it's more setup. Only worth it if you have time after everything else.

---

## 2. Prerequisites

- A Google Cloud project **with billing enabled**, and `gcloud` logged in (`gcloud auth login`). You used Cloud Run for Cortex AI, so this should be familiar.
- Your Gemini API key.
- **The extraction cache committed:** `data/.extract_cache.json` from one live run (SCN.md §6). The deploy script refuses `EXTRACT=cache` without it; use `EXTRACT=live` if you'd rather extract on the server.
- For mode B: a FalkorDB Cloud free instance (§3).

---

## 3. DEP-1: FalkorDB Cloud (mode B only)

1. In the FalkorDB Cloud console, create a **Free** instance. Pick **GCP** and the region closest to your Cloud Run region.
2. Set the user (default `falkordb`) and a password.
3. Once it's **Running**, open **Deployments → Instances → your instance → Connectivity**. The **Endpoint** card shows `host:port`. Use that port; it's often not 6379.
4. **No TLS on the free tier,** so MemLedger's `db.py` connects as-is (host, port, username, password). Paid tiers with TLS would need `ssl=True` in `db.py`.
5. Nothing to create by hand: on first start the app creates the scenario tenants in the instance (§6).

**Free-tier facts** (FalkorDB docs): 100 MB RAM and graph size; "Free instances that aren't utilized for 1 day will be stopped, and deleted after 7 days"; "no persistence and no backups". MemLedger's demo graphs are tiny (a full story is a few hundred nodes), so 100 MB is plenty. **Don't run `scripts/bench.py` against it**: benchmark tenants grow fast and would compete for the 100 MB.

---

## 4. DEP-2: Deploy to Cloud Run

```bash
# A. embedded (recommended for the submission URL)
PROJECT=your-project GEMINI_API_KEY=... MODE=embedded scripts/deploy.sh

# B. FalkorDB Cloud
PROJECT=your-project GEMINI_API_KEY=... MODE=cloud \
  FALKORDB_HOST=r-xxxx.falkordb.cloud FALKORDB_PORT=12345 FALKORDB_PASSWORD=... \
  SERVICE=memledger-cloud scripts/deploy.sh
```

Optional variables: `REGION` (default `asia-south1`, Mumbai), `SERVICE` (`memledger`), `EXTRACT` (`cache`), `AGENTS` (`live`), `ALLOW_RESET` (`1`), `FALKORDB_USERNAME` (`falkordb`).

What the script does, in order:
1. Enables Cloud Run, Cloud Build, Artifact Registry and Secret Manager.
2. Grants **Cloud Run Builder** (`roles/run.builder`) to the Compute Engine default service account. Source deploys build with that account; Google's docs say the grant can take a couple of minutes to propagate.
3. Stores the Gemini key (and, for B, the FalkorDB password) in **Secret Manager** and lets the service account read them. No secret is ever in an env var or the image.
4. Deploys from source (Cloud Build uses the `Dockerfile`) with:

| Flag | Why |
|---|---|
| `--min-instances 1` | always warm: no cold start on camera; in mode A, keeps the data alive |
| `--max-instances 1` | **required**: the write lock is per process (TEN.md §5), and in mode A the data lives in one instance |
| `--cpu 1 --memory 1Gi` | room for the app plus embedded FalkorDB |
| `--timeout 300` | agent calls to Gemini can take a while |
| `--concurrency 40` | many requests per instance; they're threads in one process, which the lock covers |
| `--allow-unauthenticated` | judges open it without a Google login |
| `--set-secrets` | Gemini key and FalkorDB password from Secret Manager |

5. Prints the URL and the smoke-test command.

**What goes into the image:** `memledger/`, `scripts/`, `data/` (scenarios, golden claims, eval questions, **the extraction cache**). `.env`, tests, virtualenvs and local state files are excluded (`.dockerignore`, and `.gcloudignore` for the source upload). The vendored graph library must be in `memledger/static/vendor/` (API.md §9).

---

## 5. DEP-3: Verify

```bash
python scripts/smoke.py https://memledger-xxxx.a.run.app            # read-only
python scripts/smoke.py https://memledger-xxxx.a.run.app --full     # replays both stories
```

`--full` **resets globex and acme** and runs all 19 steps through the API, printing each step's time and any failed checks. Don't run it while someone is presenting. With `AGENTS=live`, soft-check warnings are normal (wording varies); hard-check failures are not.

Then open the URL, check the header chips say `extract: cache` and `agents: live`, and step through once by hand.

**Before recording:** in mode B, the instance may have idled. Open the console's FalkorDB instance page first; if it's stopped, start it, then press **Reset** in MemLedger (its data is gone, §6). Run `smoke.py --full` once to warm everything up, then **Reset** acme before you start recording.

---

## 6. Restarts, wipes and recovery (all tested locally)

| Event | What MemLedger does | What you do |
|---|---|---|
| Container starts with an empty database | creates every scenario tenant (seeded, empty) and sets its demo progress to 0 | nothing; **Next step** works |
| Container restarts, **mode A** | data is gone; tenants recreated empty; progress reset | nothing, or Reset |
| Container restarts, **mode B** (graph kept, progress file lost) | leaves existing graphs alone; progress starts at 0 | press **Reset** for a clean story (Next would otherwise replay over the existing graph) |
| FalkorDB wiped while the app runs (free instance stopped/restarted) | `/api/tenants` shows `has_graph: false`; Next says "reset the tenant first"; graph routes 404 with a clear message; the console says "No graph yet. Press Reset" | press **Reset** (tested: full story passes afterwards; the app reconnects on its own) |
| Gemini quota or outage (`AGENTS=live`) | agent steps fail; observe steps still work from the cache | redeploy with `AGENTS=offline` and say so (the header chip shows it) |

Startup never resets a graph that exists: `tenancy.create` only seeds empty graphs, so the seed bug (AGT.md §15) can't trigger on deploy.

---

## 7. Configuration reference (container)

| Variable | Default in image | Meaning |
|---|---|---|
| `PORT` | 8080 | set by Cloud Run |
| `MEMLEDGER_EXTRACT` | `cache` | `live`, `cache` or `golden` |
| `MEMLEDGER_AGENTS` | `live` | `live` or `offline` |
| `MEMLEDGER_ALLOW_RESET` | `1` | Reset button and route |
| `MEMLEDGER_DEMO_STATE` | `/tmp/memledger/demo_state.json` | demo progress |
| `MEMLEDGER_EMBEDDED_DB` | unset | `1` = embedded FalkorDB (mode A) |
| `MEMLEDGER_EMBEDDED_PATH` | `/tmp/memledger/falkordb.db` | embedded database file |
| `FALKORDB_HOST`, `_PORT`, `_USERNAME`, `_PASSWORD` | — | mode B |
| `GEMINI_API_KEY` | — (secret) | |
| `GEMINI_MODEL` | `gemini-2.5-flash` | set to the Flash model your key has |

---

## 8. Security and cost

- **Public, no login.** Anyone with the URL can step the demo, reset, revoke and promote (API.md §6). That's what lets judges replay the story. If you'd rather freeze it after recording, redeploy with `ALLOW_RESET=0`; revoke and promote stay possible.
- **Secrets** live only in Secret Manager. `.env` is excluded from the image and the upload.
- **The image runs as a non-root user** (`app`).
- **Cost:** `--min-instances 1` keeps one instance running, so it's billed continuously, not just per request. Small, but not zero. After judging, set `--min-instances 0` or delete the service. Gemini calls are billed to your key whenever someone steps through with `AGENTS=live`.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails with a permission error on the build service account | `roles/run.builder` not propagated yet, or an org policy | wait a few minutes and rerun; check the grant in IAM |
| Deploy fails: secret access denied | the service account can't read the secret | rerun the script (it grants `secretAccessor`) |
| Smoke: "unreachable" | wrong URL, or the service isn't up | `gcloud run services describe memledger --region …` |
| Smoke: "tenants reachable" fails | the app can't reach FalkorDB (mode B) | instance stopped, wrong port (use the Connectivity endpoint), wrong password |
| Every observe step drops claims as `extraction_failed` | `EXTRACT=cache` but the cache doesn't have these texts | commit the cache from a live run, or `EXTRACT=live` |
| Agent steps error out | Gemini quota or model name | check `GEMINI_MODEL`; fall back to `AGENTS=offline` |
| Next step replays step 1 on a full graph | progress lost on restart (mode B) | press Reset |
| The graph doesn't draw | vendored library missing | API.md §9 |

---

## 10. Tests

```bash
pytest -q        # 149 passed, 1 skipped, 2 xfailed
```

| Test | Checks |
|---|---|
| `test_startup_creates_missing_tenants_only` | startup creates only missing tenants; progress reset only for those; second call does nothing |
| `test_smoke_full_against_a_running_server` | a real uvicorn server in rehearsal mode; `smoke.py --full` passes all 19 steps |
| `test_smoke_reports_an_unreachable_server` | clean "unreachable … FAIL", exit 1 |
| `test_requirements_match_tested_versions` | every pin in `requirements.txt` equals the installed, tested version |
| `test_docker_files` | entrypoint and non-root user; every `COPY` source exists; `.env` and tests excluded; `.gcloudignore` matches |
| `test_deploy_script_parses` | `bash -n`; one instance, the builder grant and secrets are in the script |

Also run by hand (not in the suite, because they start long-lived processes): `python -m memledger.serve` in **embedded** mode and in **external-DB** mode against FalkorDB on TCP, each with `smoke.py --full` (PASS); an app restart with the progress file deleted (PASS); the database killed and replaced with an empty one under the running app, then Reset and `smoke.py --full` (PASS).

---

## 11. Source files (tested)

### `Dockerfile`
```dockerfile
# MemLedger: API + console in one container. Cloud Run sets $PORT.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# libstdc++/libgcc are needed by the embedded FalkorDB binary (MEMLEDGER_EMBEDDED_DB=1).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libstdc++6 libgcc-s1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY memledger ./memledger
COPY scripts ./scripts
COPY data ./data

RUN useradd --create-home app && chown -R app /app
USER app

ENV PORT=8080 \
    MEMLEDGER_EXTRACT=cache \
    MEMLEDGER_AGENTS=live \
    MEMLEDGER_DEMO_STATE=/tmp/memledger/demo_state.json
EXPOSE 8080
CMD ["python", "-m", "memledger.serve"]
```

### `.dockerignore` (copy it to `.gcloudignore` and add the line `.gcloudignore`)
```
.git
.venv
**/__pycache__
**/*.pyc
.env
.env.*
tests
node_modules
package
*.tgz
data/.demo_state.json
data/*/eval_results*
*.db
```

### `requirements.txt`
```
# Runtime dependencies for the deployed app, pinned to the versions tested (17 Oct 2026).
falkordb==1.8.0
redis==8.1.0
fastapi==0.143.3
uvicorn[standard]==0.53.0
google-genai==2.31.0
pydantic==2.13.5
python-dotenv==1.2.3
# Only needed for MEMLEDGER_EMBEDDED_DB=1 (FalkorDB inside the container)
falkordblite==0.10.0
```

### `memledger/serve.py`
```python
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
```

### `scripts/deploy.sh`
```bash
#!/usr/bin/env bash
# Deploy MemLedger to Cloud Run from source (Cloud Build uses the Dockerfile).
#
#   PROJECT=my-project GEMINI_API_KEY=... MODE=embedded scripts/deploy.sh
#   PROJECT=my-project GEMINI_API_KEY=... MODE=cloud \
#     FALKORDB_HOST=... FALKORDB_PORT=... FALKORDB_PASSWORD=... scripts/deploy.sh
#
# MODE=embedded : FalkorDB runs inside the container (data lost on restart; never expires)
# MODE=cloud    : FalkorDB Cloud (free tier: stops after 1 idle day, deleted after 7)
# Optional: REGION (asia-south1), SERVICE (memledger), EXTRACT (cache), AGENTS (live),
#           FALKORDB_USERNAME (falkordb), ALLOW_RESET (1)
set -euo pipefail

: "${PROJECT:?set PROJECT to your GCP project id}"
: "${GEMINI_API_KEY:?set GEMINI_API_KEY}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-memledger}"
MODE="${MODE:-embedded}"
EXTRACT="${EXTRACT:-cache}"
AGENTS="${AGENTS:-live}"
ALLOW_RESET="${ALLOW_RESET:-1}"

case "$MODE" in embedded|cloud) ;; *) echo "MODE must be embedded or cloud" >&2; exit 2 ;; esac
if [[ "$EXTRACT" == "cache" && ! -f data/.extract_cache.json ]]; then
  echo "EXTRACT=cache but data/.extract_cache.json is missing: do one live run first (SCN.md §6)," >&2
  echo "or deploy with EXTRACT=live." >&2
  exit 2
fi

gcloud config set project "$PROJECT" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

NUM="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA="${NUM}-compute@developer.gserviceaccount.com"

# Source deploys build with the Compute Engine default service account.
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role=roles/run.builder --condition=None >/dev/null

secret() {   # secret NAME VALUE: create or add a version, and let the service read it
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=- >/dev/null
  else
    printf '%s' "$2" | gcloud secrets create "$1" --data-file=- --replication-policy=automatic >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "$1" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
}

secret memledger-gemini-key "$GEMINI_API_KEY"
ENV_VARS="MEMLEDGER_EXTRACT=${EXTRACT},MEMLEDGER_AGENTS=${AGENTS},MEMLEDGER_ALLOW_RESET=${ALLOW_RESET}"
SECRETS="GEMINI_API_KEY=memledger-gemini-key:latest"

if [[ "$MODE" == "embedded" ]]; then
  ENV_VARS="${ENV_VARS},MEMLEDGER_EMBEDDED_DB=1"
else
  : "${FALKORDB_HOST:?set FALKORDB_HOST}" "${FALKORDB_PORT:?set FALKORDB_PORT}" "${FALKORDB_PASSWORD:?set FALKORDB_PASSWORD}"
  secret memledger-falkordb-password "$FALKORDB_PASSWORD"
  ENV_VARS="${ENV_VARS},FALKORDB_HOST=${FALKORDB_HOST},FALKORDB_PORT=${FALKORDB_PORT},FALKORDB_USERNAME=${FALKORDB_USERNAME:-falkordb}"
  SECRETS="${SECRETS},FALKORDB_PASSWORD=memledger-falkordb-password:latest"
fi

# One instance, always on: the per-tenant write lock is per process (TEN.md §5),
# and in embedded mode the data lives in that one instance.
gcloud run deploy "$SERVICE" --source . --region "$REGION" --allow-unauthenticated \
  --min-instances 1 --max-instances 1 --cpu 1 --memory 1Gi --timeout 300 --concurrency 40 \
  --set-env-vars "$ENV_VARS" --set-secrets "$SECRETS"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Deployed: $URL"
echo "Check it:  python scripts/smoke.py $URL --full"
```

### `scripts/smoke.py`
```python
"""Check a running MemLedger deployment. Standard library only.

    python scripts/smoke.py https://memledger-xxxx.a.run.app            # read-only checks
    python scripts/smoke.py https://memledger-xxxx.a.run.app --full     # also replays the story

--full RESETS the globex and acme tenants and runs both scenarios through
the API, step by step. Don't run it while someone is presenting.
Exit code 1 if anything fails.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def req(base, path, method="GET", timeout=120):
    t0 = time.perf_counter()
    r = urllib.request.Request(base.rstrip("/") + path, method=method,
                               data=b"{}" if method == "POST" else None,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            body, code = resp.read(), resp.status
    except urllib.error.HTTPError as e:
        body, code = e.read(), e.code
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, f"unreachable: {getattr(e, 'reason', e)}", (time.perf_counter() - t0) * 1000
    ms = (time.perf_counter() - t0) * 1000
    try:
        return code, json.loads(body), ms
    except ValueError:
        return code, body.decode(errors="replace"), ms


def check(label, ok, detail=""):
    ok = bool(ok)
    print(f"  {'✓' if ok else '✗'} {label}{('  ' + detail) if detail else ''}")
    return ok


def run_story(base, tenant, timeout):
    code, _, _ = req(base, f"/api/{tenant}/demo/reset", "POST", timeout)
    if not check(f"{tenant}: reset", code == 200, f"HTTP {code}"):
        return False
    code, demo, _ = req(base, f"/api/{tenant}/demo", timeout=timeout)
    ok = True
    for st in demo["steps"]:
        code, r, ms = req(base, f"/api/{tenant}/demo/next", "POST", timeout)
        good = bool(code == 200 and r.get("ok"))
        bad = [c["check"] for c in (r.get("checks") or []) if not c["ok"] and not c["soft"]] if code == 200 else [r]
        warn = [c["check"] for c in (r.get("checks") or []) if not c["ok"] and c["soft"]] if code == 200 else []
        ok &= check(f"{tenant} step {st['n']:>2} {st['action']:<13} {ms:7.0f} ms", good,
                    (f"FAILED {bad}" if not good else "") + (f" soft warnings {warn}" if warn else ""))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--timeout", type=float, default=120)
    a = ap.parse_args(argv)
    base, ok = a.url, True
    print(f"Smoke test: {base}")
    code, page, ms = req(base, "/", timeout=a.timeout)
    ok &= check("console page", code == 200 and "MemLedger" in str(page),
                f"{ms:.0f} ms" if code else str(page))
    if not code:
        print("FAIL")
        return 1
    code, _, _ = req(base, "/static/vendor/force-graph.min.js", timeout=a.timeout)
    ok &= check("graph library served", code == 200)
    code, h, ms = req(base, "/api/health", timeout=a.timeout)
    ok &= check("health", code == 200 and h.get("ok"), f"{h}  {ms:.0f} ms")
    code, ts, ms = req(base, "/api/tenants", timeout=a.timeout)
    names = {t["tenant"]: t for t in ts} if code == 200 else {}
    ok &= check("tenants reachable (database connected)", code == 200, f"{ms:.0f} ms")
    for t in ("acme", "globex"):
        ok &= check(f"tenant {t} has a scenario", t in names and names[t]["subject"])
    if a.full and ok:
        ok &= run_story(base, "globex", a.timeout)
        ok &= run_story(base, "acme", a.timeout)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

### `tests/test_deploy.py`
```python
"""Deployment files and entrypoint (DEP.md)."""
import json
import re
import socket
import subprocess
import threading
import time
from importlib import metadata
from pathlib import Path

import uvicorn

from memledger import serve, tenancy
from memledger.api import create_app
from scripts import smoke

ROOT = Path(__file__).resolve().parents[1]


def test_startup_creates_missing_tenants_only(tmp_path, monkeypatch, lite_db):
    lite_db.select_graph("memory_globex").delete()
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"acme": 9, "globex": 4}))
    monkeypatch.setenv("MEMLEDGER_DEMO_STATE", str(state))
    made = serve.create_scenario_tenants()
    serve.reset_progress(made)
    assert made == ["globex"] and tenancy.exists("globex")
    assert json.loads(state.read_text()) == {"acme": 9, "globex": 0}   # acme untouched
    assert serve.create_scenario_tenants() == []


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_smoke_full_against_a_running_server(tmp_path, capsys):
    port = free_port()
    app = create_app("golden", "offline", state_path=tmp_path / "d.json", allow_reset=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        assert smoke.main([f"http://127.0.0.1:{port}", "--full"]) == 0
        out = capsys.readouterr().out
        assert "acme step 15 isolation" in out and out.strip().endswith("PASS")
    finally:
        server.should_exit = True
        t.join(5)


def test_smoke_reports_an_unreachable_server(capsys):
    port = free_port()
    assert smoke.main([f"http://127.0.0.1:{port}", "--timeout", "2"]) == 1
    out = capsys.readouterr().out
    assert "unreachable" in out and out.strip().endswith("FAIL")


def test_requirements_match_tested_versions():
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?==(\S+)", line.strip())
        if m:
            pins[m.group(1).lower()] = m.group(3)
    assert {"falkordb", "fastapi", "uvicorn", "google-genai", "pydantic", "falkordblite"} <= set(pins)
    for name, ver in pins.items():
        assert metadata.version(name) == ver, f"{name}: pinned {ver}, installed {metadata.version(name)}"


def test_docker_files():
    df = (ROOT / "Dockerfile").read_text()
    assert 'CMD ["python", "-m", "memledger.serve"]' in df and "USER app" in df
    for path in re.findall(r"^COPY (\S+)", df, re.M):
        assert (ROOT / path).exists(), path
    ignore = (ROOT / ".dockerignore").read_text().split()
    assert ".env" in ignore and "tests" in ignore
    assert (ROOT / ".gcloudignore").read_text().split()[:len(ignore)] == ignore


def test_deploy_script_parses():
    r = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "deploy.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = (ROOT / "scripts" / "deploy.sh").read_text()
    assert "--max-instances 1" in text and "roles/run.builder" in text and "--set-secrets" in text
```

---

Sources: [FalkorDB Cloud free tier](https://docs.falkordb.com/cloud/tiers/free.md), [FalkorDB Cloud: connect to your instance](https://docs.falkordb.com/cloud/console/connect), [FalkorDB Cloud quickstart](https://docs.falkordb.com/cloud/quickstart.md), [Cloud Run: deploying from source](https://docs.cloud.google.com/run/docs/deploying-source-code).
