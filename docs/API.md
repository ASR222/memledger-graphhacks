# API.md — MemLedger API & Interface

Complete context for the HTTP API and the operator console: every route, the graph format the UI draws, the console's layout and controls, how to run it, and the decisions behind it. Covers workstream API on the build board (API-1 to API-5, including the time slider).

**Status (17 Oct 2026):**
- Every file in section 11 was run. The full suite is **125 passed, 1 expected failure**: the 113 from earlier docs plus 12 new API tests through FastAPI's test client. The expected failure is the Mem.md bug from SCN.md §12.
- **The console was driven in a real browser.** Headless Chromium on embedded FalkorDB in rehearsal mode clicked Reset, Next ×14, Preview revoke, the quarantine tab, a citation (why panel) and time travel, with **no console errors**. The screenshots were sent alongside this file.
- **Not yet verified:** the console with live Gemini, and on a deployed server.

**This file is additive. It does not change any earlier doc.** It adds:

| File | Purpose |
|---|---|
| `memledger/api.py` | FastAPI app: routes, error mapping, graph shaping, static UI |
| `memledger/static/index.html`, `style.css`, `app.js` | the console (plain JS, no build step) |
| `memledger/static/vendor/force-graph.min.js` | vendored graph library (MIT, v1.47.4); download step in §9 |
| `tests/test_api.py` | 12 tests |

Dependencies: `fastapi` and `uvicorn[standard]` (already in SETUP.md's pyproject); add `httpx` to the `dev` extras for the test client.

---

## 1. Run it

```bash
docker compose up -d                                   # FalkorDB
export GEMINI_API_KEY=...                              # for live modes
uvicorn memledger.api:app --port 8000 --workers 1      # one worker, see §5
open http://localhost:8000
```

**Modes** (environment variables, read at startup):

| Variable | Values | Default | Meaning |
|---|---|---|---|
| `MEMLEDGER_EXTRACT` | `live`, `cache`, `golden` | `cache` | same as `demo.py --extract` (SCN.md §6) |
| `MEMLEDGER_AGENTS` | `live`, `offline` | `live` | same as `demo.py --agents` |
| `MEMLEDGER_ALLOW_RESET` | `1`, `0` | `1` | allow `POST /api/{tenant}/demo/reset` |
| `MEMLEDGER_DEMO_STATE` | path | `data/.demo_state.json` | demo progress file |

Rehearsal without a key: `MEMLEDGER_EXTRACT=golden MEMLEDGER_AGENTS=offline uvicorn memledger.api:app`. The header shows both modes as chips, so a viewer can tell rehearsal from live.

Swagger docs are at `/docs`.

---

## 2. Routes (API-1)

All tenant routes are under `/api/{tenant}`. The incident (`subject`) defaults to the tenant's scenario (`data/{tenant}/scenario.json`); pass `?subject=` for tenants without one.

### Meta
| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{ok, extract, agents, allow_reset}` |
| GET | `/api/tenants` | `[{tenant, has_graph, subject, title}]` from graphs and scenarios |

### Reading memory
| Method | Path | Returns |
|---|---|---|
| GET | `/{t}/graph?at=&episodes=` | force-graph data (§3) |
| GET | `/{t}/facts` | `{subject, active, known_values}` |
| GET | `/{t}/facts/{id}/why` | `memory.why` + `versions` of that predicate |
| GET | `/{t}/as_of?t=` | facts believed at `t` (epoch ms) |
| GET | `/{t}/history/{session}` | logged turns |
| GET | `/{t}/disputes` | quarantined claims contradicting a belief |
| GET | `/{t}/stale` | active facts based on a belief no longer held |
| GET | `/{t}/handoffs/{agent}` | pending handoffs with current fact status |

### Trust (TRU.md §8.1)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/{t}/sources` | — | trust table |
| GET | `/{t}/quarantine` | — | quarantined facts + what they dispute |
| GET | `/{t}/sources/{id}/blast-radius` | — | preview |
| POST | `/{t}/sources/{id}/revoke` | — | preview + `revoked` + `stale` |
| PUT | `/{t}/sources/{id}/trust` | `{trust}` | `{id, trust}` |
| POST | `/{t}/facts/{id}/promote` | — | `{id, closed}` |

### Agents (AGT.md §12)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/{t}/observe` | `{session, source, text}` | routed agent, stored/dropped, handoff |
| POST | `/{t}/status-update` | `{session}` | text, citations, stored, handoffs_read, tools |
| POST | `/{t}/investigate` | `{session}` | text, tools, stopped |
| POST | `/{t}/ask` | `{agent, session, question}` | text, citations, tools, stopped |

### Scripted demo (SCN.md)
| Method | Path | Returns |
|---|---|---|
| GET | `/{t}/demo` | steps (n, session, at, action, say), `last_step`, `allow_reset` |
| POST | `/{t}/demo/next` | the next step's result: output, checks, `ok` |
| POST | `/{t}/demo/reset` | wipes and seeds the tenant (403 if disabled) |

### Errors
| Status | When |
|---|---|
| 404 | unknown source or fact; tenant has no graph yet; no scenario for the demo routes |
| 409 | compromised source; demo finished; demo run before reset; step out of order |
| 422 | invalid tenant name; trust outside 0–1; unknown agent; body validation |
| 403 | reset disabled |

Every error body is `{"detail": "..."}`.

---

## 3. Graph format (`GET /{t}/graph`)

```json
{"nodes": [
   {"id": "agent:investigator", "kind": "agent", "name": "investigator"},
   {"id": "source:webhook", "kind": "source", "name": "webhook", "trust": 0.6, "compromised": false},
   {"id": "f-1a2b3c4d", "kind": "fact", "name": "mitigation = flush-cache", "predicate": "mitigation",
    "object": "flush-cache", "status": "active", "valid_from": 1792143300000, "valid_to": null},
   {"id": "h-9f8e7d6c", "kind": "handoff", "name": "2 update(s) from runbook", "session": "s2"}],
 "links": [{"source": "agent:investigator", "target": "f-1a2b3c4d", "type": "WROTE"}]}
```

- Facts are limited to the tenant's incident. Entities are left out (they add a hub node and no information). Episodes are included only with `?episodes=true`.
- Every link's endpoints are nodes in the response (tested).
- With `?at=<ms>`: facts created after `at` are omitted and every fact gets `believed_at: true|false`, computed with `memory.as_of`.

---

## 4. The console (API-2 to API-5)

```
┌ MemLedger · Tenant [acme ▾] · INC-42 · payments-api latency spike        extract: cache  agents: live ┐
├──────────────────────────┬─────────────────────────────────────────────────────┬──────────────────────┤
│ SCRIPTED DEMO            │ legend: active · quarantined · closed · revoked …   │ Sources | Quarantine │
│ Step 9 of 15  [Reset][Next step]                                               │ alerts   trusted     │
│ Next: <narration>        │                                                     │ ███████▌  0.90       │
│ ▬▬▬▬▬▬▬▬▬▭▭▭▭▭▭          │             live memory graph                       │ [Preview revoke]     │
├──────────────────────────┤        (click a fact → why panel)                   │ webhook  trusted     │
│ feed (newest first):     │                                                     │ 2 facts: 2 direct …  │
│  9. status_update·comms  │                                                     │ [Revoke webhook]     │
│   text with [f-…] chips  │                                                     │                      │
│   ✓ checks               │  LIVE ───────────────────────────────●  [Live]      │                      │
├──────────────────────────┤                                                     │                      │
│ ASK AN AGENT [Comms▾][s2]│                                                     │                      │
│ [question………] [Ask]      │                                                     │                      │
└──────────────────────────┴─────────────────────────────────────────────────────┴──────────────────────┘
```

| Part | What it does |
|---|---|
| **Demo card** | Step counter, the next step's narration, progress bar (red segment = a hard check failed). **Next step** runs `/demo/next`. **Reset** needs a second click within 3 s to confirm. |
| **Feed** | One card per step or action, newest first: stored (+), ruled out (−), dropped (·) facts with status pills; agent text with clickable citation chips (struck through if no longer active); blast radius lists; ✓ / ~ / ✗ checks. |
| **Ask** | Ask any agent a question in a session; the answer's citations are chips. |
| **Graph** (API-3) | force-graph, polled every 2.5 s, redrawn only when the data changes, existing nodes keep their positions. Shapes: agents violet circles, sources blue squares (red when compromised), facts small circles colored by status (quarantined = dashed ring), handoffs small diamonds. Links: SUPERSEDES orange arrows, CONFLICTS_WITH red dashed, DERIVED_FROM blue arrows, the rest faint. |
| **Why panel** (API-4) | Click a fact node or a citation chip: predicate = value, status, written by, sources, based on (clickable), replaced, and every version of that predicate with its time window. The fact's provenance is ringed in the graph and everything else dims. |
| **Sources tab** | Trust bar with the 0.5 threshold tick, counts (active/quarantined/revoked), **Preview revoke** rings the blast radius in the graph and shows **Revoke** / **Cancel**. Periodic refresh pauses while a preview is open. |
| **Quarantine tab** | Pending claims, their source, what they dispute, **Promote**. |
| **Time slider** (API-5) | Drag to view memory as of any moment: facts not yet created disappear, facts not believed at that time fade. The label turns amber ("Memory as of 13:55"). **Live** returns to now. The demo's `as_of` step moves the slider automatically. |

### Driving the video from the console

1. Reset globex and run its 4 steps (switch tenant, Reset, Next ×4), then switch back to acme. Otherwise step 15's isolation beat has nothing to compare against.
2. On acme: Reset, then **Next step** through the story, reading each narration.
3. At step 10 (preview), the blast radius is ringed automatically. You can also do the revoke by hand from the Sources tab for a more visual beat. If you do, steps 10–11 still run but find nothing; their checks will show ✗ because the facts are already revoked. Pick one way and rehearse it.
4. After step 12, click the root-cause chip to open the why panel.
5. Step 14 moves the time slider back to 13:55.

---

## 5. Decisions

- **One process, one worker.** `write_fact`'s check-then-write runs under a per-process lock (Mem.md §13). Several workers could interleave writes to one tenant. `uvicorn --workers 1`.
- **No seeding on startup.** Because of the seed bug (AGT.md §15, SCN.md §12), the app never calls `schema.seed` itself. Graphs are created by **Reset** (which seeds an empty graph, so it's safe) or by `scripts/demo.py --reset`.
- **Stateless request handling.** A `Team` and a `Runner` are built per request; the graph and the demo progress file are the only state. Extractors and the agent model are created once per process (lazily) and reused.
- **Same modes as the CLI.** The API and `demo.py` read the same scenario and progress file, so you can mix them (for example advance from the terminal and watch in the browser). Don't do both at the same moment.
- **Plain JS, no build.** One HTML, one CSS, one JS file and a vendored library, served by FastAPI. Nothing to compile on the deploy box.
- **Vendored graph library with CDN fallback.** The stage Wi-Fi can't break the demo; if the local copy is missing, the page loads the same version from jsDelivr.
- **Graph limited to the incident.** Entities hidden, episodes optional, so the picture stays readable at demo scale.

---

## 6. Security (say it before a judge asks)

- **No authentication.** Anyone who can reach the server can revoke sources, promote facts and reset tenants. That's acceptable for a hackathon demo, not for production.
- On a public URL, judges clicking **Reset** or **Revoke** change what the next judge sees. If you'd rather lock it, set `MEMLEDGER_ALLOW_RESET=0` after setting the tenant up, and say the console is read-mostly.
- Input sizes are capped (text 20 000 characters, question 2 000) and every tenant name is validated before it reaches FalkorDB.
- All text from memory is HTML-escaped before rendering, so injected text in a source can't run script in the console.

---

## 7. Tests

```bash
pytest -q        # expect: 125 passed, 1 xfailed
```

| Test | Checks |
|---|---|
| `test_health_and_tenants` | modes reported; both tenants listed with subjects |
| `test_full_demo_over_http` | globex then all 15 acme steps over HTTP, every step ok; finished → 409 |
| `test_demo_needs_reset_first` | no graph → 409 |
| `test_graph_shape` | links reference real nodes; node kinds; fact statuses; link types; episodes flag |
| `test_graph_at_time` | `believed_at` at 13:55; facts from later hidden at 10:05 |
| `test_why_and_facts` | provenance and versions over HTTP; unknown fact 404 |
| `test_trust_routes` | trust table, quarantine + disputes, preview = revoke, 409/422/404 cases, promote clears the dispute |
| `test_agent_routes` | observe → handoff → status update (handoffs read) → ask → investigate → history; bad agent 422; unknown source 404 |
| `test_as_of_route` | as_of over HTTP |
| `test_bad_tenants` | invalid name 422; missing graph 404; no scenario 404 |
| `test_reset_can_be_disabled` | 403 |
| `test_ui_is_served` | index references the vendored library and app; static files served |

**Browser check (manual, done once):** start the server on embedded FalkorDB in rehearsal mode and click through with headless Chromium. Repeat it yourself after any UI change by opening the page and stepping through.

---

## 8. Known limits

- **Labels can overlap** where facts cluster (for example `affects_service` and `severity` right after the alert). Zoom with the mouse wheel; force-graph supports drag and zoom.
- **Polling, not push.** 2.5 s refresh; fine for one presenter.
- **Time travel shows the Mem.md as_of bug** until patched: at 13:55 the quarantined-then-revoked `redis-outage` appears as believed (green). See SCN.md §12.
- **The why panel's "Based on" lists episode ids** as plain text (only fact ids are clickable).
- **Phone layout** stacks the feed above the graph and hides the sources panel; the console is built for a laptop screen.
- **No episode toggle in the UI** (`?episodes=true` exists in the API).

---

## 9. Vendored graph library

Not included as a code block (165 KB minified). Get it once:

```bash
mkdir -p memledger/static/vendor
npm pack force-graph@1.47.4 && tar xzf force-graph-1.47.4.tgz \
  && cp package/dist/force-graph.min.js memledger/static/vendor/ && rm -rf package force-graph-1.47.4.tgz
# or: curl -L https://cdn.jsdelivr.net/npm/force-graph@1.47.4/dist/force-graph.min.js \
#       -o memledger/static/vendor/force-graph.min.js
```

MIT-licensed (vasturiano/force-graph). Commit it, and mention it in the README's credits.

---

## 10. Judge talking points

- "Every node on screen is a node in FalkorDB. What you see is the memory, not a visualization of logs."
- "Click any claim in a status update and you get its provenance: who wrote it, from which source, what it replaced, and every version over time."
- "Preview a source's blast radius, then revoke it, and watch it ripple through the graph."
- "Drag the slider back and you see exactly what the team believed at that moment."

---

## 11. Source files (tested)

### `memledger/api.py`
```python
"""HTTP API and the operator UI.

    uvicorn memledger.api:app --port 8000          # one worker (see API.md)

Modes come from the environment:
    MEMLEDGER_EXTRACT = live | cache | golden      (default: cache)
    MEMLEDGER_AGENTS  = live | offline             (default: live)
    MEMLEDGER_ALLOW_RESET = 1 | 0                  (default: 1)
"""
import dataclasses
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, memory, trust
from . import scenario as S
from .agents.team import Team
from .db import get_db, graph as tenant_graph
from .extract import Extractor

STATIC = Path(__file__).resolve().parent / "static"
AGENT_NAMES = {"triage", "investigator", "comms"}


# ---------------------------------------------------------------- bodies

class ObserveIn(BaseModel):
    session: str = Field(min_length=1, max_length=40)
    source: str
    text: str = Field(min_length=1, max_length=20000)


class SessionIn(BaseModel):
    session: str = Field(min_length=1, max_length=40)


class AskIn(BaseModel):
    agent: str
    session: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=1, max_length=2000)


class TrustIn(BaseModel):
    trust: float


# ---------------------------------------------------------------- helpers

def now_ms() -> int:
    return int(time.time() * 1000)


def plain(x):
    """Make dataclasses, sets and tuples JSON-friendly."""
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return plain(dataclasses.asdict(x))
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [plain(v) for v in x]
    return x


def graph_view(tenant: str, subject: str, at: int | None = None, episodes: bool = False) -> dict:
    """Nodes and links shaped for force-graph.

    Facts are limited to the subject. Entities are left out. Episodes and
    their edges are included only when asked. With `at`, facts created after
    `at` are hidden and each fact gets believed_at = true/false.
    """
    snap = memory.snapshot(tenant)
    subj = memory.canon(subject)
    believed = {f["id"] for f in memory.as_of(tenant, at)} if at is not None else None
    ids, nodes = {}, []
    for n in snap["nodes"]:
        p, label = n["props"], n["label"]
        if label == "Agent":
            node = {"id": f"agent:{p['id']}", "kind": "agent", "name": p["id"]}
        elif label == "Source":
            node = {"id": f"source:{p['id']}", "kind": "source", "name": p["id"],
                    "trust": p.get("trust"), "compromised": bool(p.get("compromised"))}
        elif label == "Fact":
            if p.get("subject") != subj or (at is not None and p["valid_from"] > at):
                continue
            node = {"id": p["id"], "kind": "fact", "name": f"{p['predicate']} = {p['object']}",
                    "predicate": p["predicate"], "object": p["object"], "status": p["status"],
                    "valid_from": p["valid_from"], "valid_to": p.get("valid_to")}
            if believed is not None:
                node["believed_at"] = p["id"] in believed
        elif label == "Handoff":
            node = {"id": p["id"], "kind": "handoff", "name": p.get("note") or "handoff",
                    "session": p.get("session")}
        elif label == "Episode" and episodes:
            node = {"id": p["id"], "kind": "episode", "name": p["text"][:80], "session": p["session"]}
        else:
            continue
        ids[n["nid"]] = node["id"]
        nodes.append(node)
    links = [{"source": ids[e["src"]], "target": ids[e["dst"]], "type": e["type"]}
             for e in snap["edges"] if e["src"] in ids and e["dst"] in ids]
    return {"nodes": nodes, "links": links}


# ---------------------------------------------------------------- app

def create_app(extract: str | None = None, agents: str | None = None, *, extractor=None,
               llm=None, clock=now_ms, data_dir: Path | None = None,
               state_path: Path | None = None, allow_reset: bool | None = None) -> FastAPI:
    extract = extract or os.getenv("MEMLEDGER_EXTRACT", "cache")
    agents = agents or os.getenv("MEMLEDGER_AGENTS", "live")
    data_dir = Path(data_dir or S.DATA)
    state_path = Path(state_path or os.getenv("MEMLEDGER_DEMO_STATE", data_dir / ".demo_state.json"))
    if allow_reset is None:
        allow_reset = os.getenv("MEMLEDGER_ALLOW_RESET", "1") == "1"

    app = FastAPI(title="MemLedger", version="1.0")
    cache: dict = {"extractors": {}, "llm": llm}

    def scenario(tenant: str) -> dict | None:
        try:
            return S.load(tenant, data_dir)
        except FileNotFoundError:
            return None

    def get_extractor(tenant: str):
        if extractor is not None:
            return extractor
        if tenant not in cache["extractors"]:
            if extract == "golden":
                sc = scenario(tenant)
                if sc is None:
                    raise HTTPException(409, f"golden extraction needs data/{tenant}/scenario.json")
                ex = Extractor(S.GoldenLLM(sc), mode="live", model_name="golden")
            elif extract == "live":
                from .extract import GeminiLLM
                ex = Extractor(GeminiLLM(), cache_path=config.EXTRACT_CACHE, mode="live")
            else:
                ex = Extractor(None, cache_path=config.EXTRACT_CACHE, mode="cache_only",
                               model_name=config.GEMINI_MODEL)
            cache["extractors"][tenant] = ex
        return cache["extractors"][tenant]

    def get_llm():
        if cache["llm"] is None:
            if agents == "offline":
                cache["llm"] = S.OfflineChat()
            else:
                from .agents.llm import GeminiChat
                cache["llm"] = GeminiChat()
        return cache["llm"]

    def subject_of(tenant: str, subject: str | None) -> str:
        if subject:
            return subject
        sc = scenario(tenant)
        if sc is None:
            raise HTTPException(422, "pass ?subject= (no scenario for this tenant)")
        return sc["subject"]

    def team(tenant: str, subject: str | None) -> Team:
        return Team(tenant, subject_of(tenant, subject), get_extractor(tenant), get_llm(), clock)

    def runner(tenant: str) -> S.Runner:
        sc = scenario(tenant)
        if sc is None:
            raise HTTPException(404, f"no scenario for {tenant}")
        return S.Runner(sc, get_extractor(tenant), get_llm(), state_path=state_path)

    def require_graph(tenant: str):
        tenant_graph(tenant)                                      # validates the name
        if f"memory_{tenant}" not in get_db().list_graphs():
            raise HTTPException(404, f"tenant {tenant} has no graph yet; reset it or run its scenario")

    # errors
    @app.exception_handler(memory.UnknownReference)
    async def _404(_: Request, e):
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.exception_handler(memory.CompromisedSource)
    async def _409(_: Request, e):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(S.ScenarioError)
    async def _409s(_: Request, e):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(ValueError)
    async def _422(_: Request, e):
        return JSONResponse({"detail": str(e)}, status_code=422)

    # ------------------------------------------------------------ meta
    @app.get("/api/health")
    def health():
        return {"ok": True, "extract": extract, "agents": agents, "allow_reset": allow_reset}

    @app.get("/api/tenants")
    def tenants():
        graphs = {g.removeprefix("memory_") for g in get_db().list_graphs() if g.startswith("memory_")}
        scen = {p.name for p in data_dir.iterdir() if (p / "scenario.json").exists()} if data_dir.exists() else set()
        out = []
        for t in sorted(graphs | scen):
            sc = scenario(t) if t in scen else None
            out.append({"tenant": t, "has_graph": t in graphs,
                        "subject": sc["subject"] if sc else None, "title": sc["title"] if sc else None})
        return out

    # ------------------------------------------------------------ reads
    @app.get("/api/{tenant}/graph")
    def graph(tenant: str, subject: str | None = None, at: int | None = None, episodes: bool = False):
        require_graph(tenant)
        return graph_view(tenant, subject_of(tenant, subject), at, episodes)

    @app.get("/api/{tenant}/facts")
    def facts(tenant: str, subject: str | None = None):
        require_graph(tenant)
        subj = subject_of(tenant, subject)
        return {"subject": memory.canon(subj), "active": memory.read_active(tenant, subj),
                "known_values": memory.known_values(tenant, subj)}

    @app.get("/api/{tenant}/facts/{fact_id}/why")
    def why(tenant: str, fact_id: str):
        require_graph(tenant)
        w = memory.why(tenant, fact_id)
        if w is None:
            raise HTTPException(404, f"no fact {fact_id}")
        w["versions"] = memory.versions(tenant, w["subject"], w["predicate"])
        return w

    @app.get("/api/{tenant}/as_of")
    def as_of(tenant: str, t: int, subject: str | None = None):
        require_graph(tenant)
        subj = memory.canon(subject_of(tenant, subject))
        return {"t": t, "facts": [f for f in memory.as_of(tenant, t) if f["subject"] == subj]}

    @app.get("/api/{tenant}/history/{session}")
    def history(tenant: str, session: str):
        require_graph(tenant)
        return memory.history(tenant, session)

    @app.get("/api/{tenant}/disputes")
    def disputes(tenant: str):
        require_graph(tenant)
        return memory.disputes(tenant)

    @app.get("/api/{tenant}/stale")
    def stale(tenant: str):
        require_graph(tenant)
        return memory.stale(tenant)

    @app.get("/api/{tenant}/handoffs/{agent}")
    def handoffs(tenant: str, agent: str, subject: str | None = None):
        require_graph(tenant)
        return team(tenant, subject).pending(agent)

    # ------------------------------------------------------------ trust
    @app.get("/api/{tenant}/sources")
    def sources(tenant: str):
        require_graph(tenant)
        return trust.trust_table(tenant)

    @app.get("/api/{tenant}/quarantine")
    def quarantine(tenant: str):
        require_graph(tenant)
        return trust.quarantine(tenant)

    @app.get("/api/{tenant}/sources/{source}/blast-radius")
    def blast_radius(tenant: str, source: str):
        require_graph(tenant)
        return trust.blast_radius(tenant, source)

    @app.post("/api/{tenant}/sources/{source}/revoke")
    def revoke(tenant: str, source: str):
        require_graph(tenant)
        return trust.revoke_source(tenant, source, clock())

    @app.put("/api/{tenant}/sources/{source}/trust")
    def set_trust(tenant: str, source: str, body: TrustIn):
        require_graph(tenant)
        return trust.set_trust(tenant, source, body.trust)

    @app.post("/api/{tenant}/facts/{fact_id}/promote")
    def promote(tenant: str, fact_id: str):
        require_graph(tenant)
        return trust.promote(tenant, fact_id, clock())

    # ------------------------------------------------------------ agents
    @app.post("/api/{tenant}/observe")
    def observe(tenant: str, body: ObserveIn, subject: str | None = None):
        require_graph(tenant)
        return team(tenant, subject).observe(body.session, body.source, body.text)

    @app.post("/api/{tenant}/status-update")
    def status_update(tenant: str, body: SessionIn, subject: str | None = None):
        require_graph(tenant)
        u = team(tenant, subject).status_update(body.session)
        run = u.pop("run")
        u["tools"] = [t["tool"] for t in run.tool_calls]
        return plain(u)

    @app.post("/api/{tenant}/investigate")
    def investigate(tenant: str, body: SessionIn, subject: str | None = None):
        require_graph(tenant)
        run = team(tenant, subject).investigate(body.session)
        return {"text": run.text, "tools": [t["tool"] for t in run.tool_calls], "stopped": run.stopped}

    @app.post("/api/{tenant}/ask")
    def ask(tenant: str, body: AskIn, subject: str | None = None):
        require_graph(tenant)
        if body.agent not in AGENT_NAMES:
            raise HTTPException(422, f"agent must be one of {sorted(AGENT_NAMES)}")
        run, cites = team(tenant, subject).ask(body.agent, body.session, body.question)
        return {"text": run.text, "citations": cites,
                "tools": [t["tool"] for t in run.tool_calls], "stopped": run.stopped}

    # ------------------------------------------------------------ scripted demo
    @app.get("/api/{tenant}/demo")
    def demo(tenant: str):
        r = runner(tenant)
        return {"tenant": tenant, "subject": r.subject, "title": r.sc["title"],
                "last_step": r.last_step(), "allow_reset": allow_reset,
                "steps": [{k: st.get(k) for k in ("n", "session", "at", "action", "say")}
                          for st in r.sc["steps"]]}

    @app.post("/api/{tenant}/demo/next")
    def demo_next(tenant: str):
        r = runner(tenant)
        if f"memory_{tenant}" not in get_db().list_graphs():
            raise HTTPException(409, "reset the tenant first")
        n = r.last_step() + 1
        if n > len(r.sc["steps"]):
            raise HTTPException(409, "the scenario is finished; reset to replay")
        res = r.run_step(n)
        return plain({**dataclasses.asdict(res), "ok": res.ok})

    @app.post("/api/{tenant}/demo/reset")
    def demo_reset(tenant: str):
        if not allow_reset:
            raise HTTPException(403, "reset is disabled (MEMLEDGER_ALLOW_RESET=0)")
        runner(tenant).reset()
        return {"tenant": tenant, "last_step": 0}

    # ------------------------------------------------------------ UI
    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(STATIC / "index.html")

    return app


app = create_app()
```

### `memledger/static/index.html`
```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MemLedger</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header class="top">
  <div class="brand"><span class="mark" aria-hidden="true"></span>MemLedger</div>
  <label class="field">Tenant
    <select id="tenant"></select>
  </label>
  <div class="incident" id="incident">—</div>
  <div class="modes" id="modes"></div>
</header>

<main class="layout">
  <section class="left" aria-label="Story and agents">
    <div class="card demo">
      <div class="demo-head">
        <div>
          <div class="eyebrow">Scripted demo</div>
          <div class="step-count" id="stepCount">Step 0 of 0</div>
        </div>
        <div class="demo-buttons">
          <button id="reset" class="ghost" type="button">Reset</button>
          <button id="next" class="primary" type="button">Next step</button>
        </div>
      </div>
      <p class="say" id="say">Reset the tenant, then step through the story.</p>
      <ol class="dots" id="dots" aria-label="Steps"></ol>
    </div>

    <div class="feed" id="feed" aria-live="polite"></div>

    <form class="card ask" id="askForm">
      <div class="eyebrow">Ask an agent</div>
      <div class="ask-row">
        <select id="askAgent" aria-label="Agent">
          <option value="comms">Comms</option>
          <option value="investigator">Investigator</option>
          <option value="triage">Triage</option>
        </select>
        <input id="askSession" aria-label="Session" value="s2" size="3">
      </div>
      <div class="ask-row">
        <input id="askQ" aria-label="Question" placeholder="Why do we believe the root cause?" required>
        <button class="primary" type="submit">Ask</button>
      </div>
    </form>
  </section>

  <section class="right" aria-label="Memory graph">
    <div id="graph"></div>

    <div class="legend" id="legend">
      <span><i class="dot active"></i>active</span>
      <span><i class="dot quarantined"></i>quarantined</span>
      <span><i class="dot closed"></i>closed</span>
      <span><i class="dot revoked"></i>revoked</span>
      <span><i class="sq agent"></i>agent</span>
      <span><i class="sq source"></i>source</span>
    </div>

    <div class="timebar">
      <span class="eyebrow" id="timeLabel">Live</span>
      <input type="range" id="time" min="0" max="1000" value="1000" aria-label="Time travel">
      <button id="live" class="ghost small" type="button">Live</button>
    </div>

    <aside class="panel" id="sourcesPanel" aria-label="Sources and quarantine">
      <div class="tabs">
        <button class="tab on" data-tab="sources" type="button">Sources</button>
        <button class="tab" data-tab="quarantine" type="button">Quarantine</button>
      </div>
      <div id="sources" class="tabbody"></div>
      <div id="quarantine" class="tabbody" hidden></div>
    </aside>

    <aside class="drawer" id="why" hidden aria-label="Why panel">
      <button class="close" id="whyClose" type="button" aria-label="Close">×</button>
      <div id="whyBody"></div>
    </aside>
  </section>
</main>

<script src="/static/vendor/force-graph.min.js"></script>
<script>
  if (!window.ForceGraph) {
    document.write('<script src="https://cdn.jsdelivr.net/npm/force-graph@1.47.4/dist/force-graph.min.js"><\/script>');
  }
</script>
<script src="/static/app.js"></script>
</body>
</html>
```

### `memledger/static/style.css`
```css
/* MemLedger operator console. Dark ops palette; status colors carry meaning. */
:root {
  --bg: #0d1016;
  --panel: #151a22;
  --panel-2: #1b212b;
  --line: #262e3a;
  --ink: #e6e9ef;
  --muted: #8b95a5;
  --accent: #8f7cff;
  --active: #3ecf8e;
  --quarantined: #9aa3b2;
  --closed: #4a5464;
  --revoked: #ff5d5d;
  --dispute: #ffb547;
  --source: #5ab0ff;
  --mono: ui-monospace, "SFMono-Regular", "JetBrains Mono", Menlo, Consolas, monospace;
  --sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color-scheme: dark;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { height: 100%; margin: 0; }
body { background: var(--bg); color: var(--ink); font: 14px/1.45 var(--sans); }
button, input, select { font: inherit; color: inherit; }
button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.top { height: 52px; display: flex; align-items: center; gap: 18px; padding: 0 16px; border-bottom: 1px solid var(--line); background: var(--panel); }
.brand { font-weight: 700; letter-spacing: .02em; display: flex; align-items: center; gap: 8px; }
.mark { width: 14px; height: 14px; border-radius: 3px; background: linear-gradient(135deg, var(--accent), var(--active)); }
.field { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; }
select, input { background: var(--panel-2); border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; }
.incident { font-family: var(--mono); font-size: 13px; }
.modes { margin-left: auto; display: flex; gap: 6px; }
.chip { font-family: var(--mono); font-size: 11px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; padding: 2px 8px; }

.layout { display: grid; grid-template-columns: minmax(340px, 430px) 1fr; height: calc(100% - 52px); }
.left { display: flex; flex-direction: column; gap: 10px; padding: 12px; border-right: 1px solid var(--line); min-height: 0; }
.right { position: relative; min-width: 0; overflow: hidden; }
#graph { position: absolute; top: 0; left: 0; bottom: 0; right: 300px; }

.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px; }
.eyebrow { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
.demo-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.step-count { font-weight: 650; font-size: 16px; }
.demo-buttons { display: flex; gap: 6px; }
.say { margin: 8px 0 10px; color: #c9cfd9; min-height: 2.9em; }
.dots { list-style: none; display: flex; gap: 4px; padding: 0; margin: 0; flex-wrap: wrap; }
.dots li { width: 18px; height: 6px; border-radius: 3px; background: var(--line); }
.dots li.done { background: var(--accent); }
.dots li.fail { background: var(--revoked); }

button.primary { background: var(--accent); color: #0d0a1f; border: 0; border-radius: 7px; padding: 6px 12px; font-weight: 650; cursor: pointer; }
button.ghost { background: transparent; border: 1px solid var(--line); border-radius: 7px; padding: 6px 10px; cursor: pointer; color: var(--muted); }
button.danger { background: var(--revoked); color: #1a0505; border: 0; border-radius: 7px; padding: 5px 10px; font-weight: 650; cursor: pointer; }
button.small { padding: 3px 8px; font-size: 12px; }
button:disabled { opacity: .5; cursor: progress; }

.feed { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.entry { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.entry.ok { border-left-color: var(--accent); }
.entry.bad { border-left-color: var(--revoked); }
.entry h4 { margin: 0 0 4px; font-size: 13px; display: flex; gap: 8px; align-items: baseline; }
.entry h4 .meta { font-family: var(--mono); font-size: 11px; color: var(--muted); font-weight: 400; }
.entry .text { white-space: pre-wrap; margin: 6px 0; }
.entry ul { list-style: none; margin: 4px 0; padding: 0; font-family: var(--mono); font-size: 12px; }
.entry li { padding: 1px 0; }
.plus { color: var(--active); } .minus { color: var(--revoked); } .drop { color: var(--muted); } .q { color: var(--quarantined); }
.checks { font-size: 12px; color: var(--muted); margin-top: 4px; }
.checks .pass { color: var(--active); } .checks .fail { color: var(--revoked); } .checks .warn { color: var(--dispute); }
.cite { font-family: var(--mono); font-size: 11px; background: #232a36; border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; cursor: pointer; color: var(--source); }
.cite.inactive { color: var(--revoked); text-decoration: line-through; }
.pill { font-family: var(--mono); font-size: 11px; border-radius: 4px; padding: 0 5px; }
.pill.active { background: rgba(62,207,142,.15); color: var(--active); }
.pill.quarantined { background: rgba(154,163,178,.15); color: var(--quarantined); }
.pill.closed { background: rgba(74,84,100,.3); color: #a3acba; }
.pill.revoked { background: rgba(255,93,93,.15); color: var(--revoked); }

.ask .ask-row { display: flex; gap: 6px; margin-top: 8px; }
.ask #askQ { flex: 1; min-width: 0; }

.legend { position: absolute; top: 10px; left: 12px; display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--muted); background: rgba(13,16,22,.8); padding: 6px 10px; border-radius: 8px; border: 1px solid var(--line); }
.legend span { display: flex; align-items: center; gap: 5px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot.active { background: var(--active); } .dot.quarantined { border: 2px dashed var(--quarantined); }
.dot.closed { background: var(--closed); } .dot.revoked { background: var(--revoked); }
.sq { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.sq.agent { background: var(--accent); } .sq.source { background: var(--source); }

.timebar { position: absolute; left: 12px; right: 312px; bottom: 12px; display: flex; align-items: center; gap: 10px; background: rgba(13,16,22,.85); border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px; }
.timebar input { flex: 1; accent-color: var(--accent); }
#timeLabel { min-width: 150px; }
#timeLabel.past { color: var(--dispute); }

.panel { position: absolute; top: 10px; right: 10px; bottom: 10px; width: 290px; background: rgba(21,26,34,.95); border: 1px solid var(--line); border-radius: 10px; overflow-y: auto; }
.tabs { display: flex; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--panel); }
.tab { flex: 1; background: none; border: 0; padding: 8px; color: var(--muted); cursor: pointer; }
.tab.on { color: var(--ink); box-shadow: inset 0 -2px var(--accent); }
.tabbody { padding: 8px 10px; display: flex; flex-direction: column; gap: 8px; }
.src { border: 1px solid var(--line); border-radius: 8px; padding: 8px; }
.src.comp { border-color: rgba(255,93,93,.5); }
.src-head { display: flex; justify-content: space-between; align-items: center; font-family: var(--mono); font-size: 12px; }
.trust { height: 4px; border-radius: 2px; background: var(--line); margin: 6px 0; position: relative; }
.trust i { position: absolute; inset: 0 auto 0 0; border-radius: 2px; background: var(--source); }
.trust b { position: absolute; top: -3px; width: 1px; height: 10px; background: var(--muted); }
.src-meta { font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.radius { margin-top: 6px; font-size: 12px; }
.radius ul { margin: 4px 0; padding-left: 14px; font-family: var(--mono); font-size: 11px; }

.drawer { position: absolute; top: 10px; right: 310px; width: 340px; max-height: calc(100% - 70px); overflow-y: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; box-shadow: 0 10px 40px rgba(0,0,0,.5); }
.drawer .close { position: absolute; top: 6px; right: 8px; background: none; border: 0; font-size: 20px; color: var(--muted); cursor: pointer; }
.drawer h3 { margin: 0 0 6px; font-family: var(--mono); font-size: 14px; padding-right: 20px; }
.drawer dl { display: grid; grid-template-columns: 90px 1fr; gap: 4px 8px; font-size: 12px; margin: 8px 0; }
.drawer dt { color: var(--muted); } .drawer dd { margin: 0; font-family: var(--mono); overflow-wrap: anywhere; }
.versions { list-style: none; padding: 0; margin: 6px 0 0; font-family: var(--mono); font-size: 11px; }
.versions li { padding: 2px 0; }

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; grid-template-rows: auto 60vh; height: auto; }
  .left { border-right: 0; }
  .panel { display: none; }
  .timebar { right: 12px; }
  #graph { right: 0; }
  .drawer { right: 10px; width: auto; left: 10px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
```

### `memledger/static/app.js`
```javascript
// MemLedger operator console. Plain JS, no build step.
(() => {
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const C = {
    active: css("--active"), quarantined: css("--quarantined"), closed: css("--closed"),
    revoked: css("--revoked"), agent: css("--accent"), source: css("--source"),
    dispute: css("--dispute"), ink: css("--ink"), muted: css("--muted"), line: css("--line"),
  };
  const LINK = {
    SUPERSEDES: C.dispute, CONFLICTS_WITH: C.revoked, DERIVED_FROM: C.source,
    FROM_SOURCE: "#3a4454", WROTE: "#2c3442", CARRIES: "#4b3f8a", SENT: "#4b3f8a", TO: "#4b3f8a",
    RETRACTED: C.revoked, RETRACTS: C.revoked, LOGGED: "#2c3442",
  };

  const S = {
    tenant: null, demo: null, at: null, live: true, nodes: new Map(), sig: "",
    highlight: new Set(), timeMin: 0, timeMax: 0, busy: false, previewing: null, fit: true, hasGraph: {}, failed: new Set(),
  };

  // ------------------------------------------------------------- utils
  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || r.statusText);
    return body;
  }
  const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const hhmm = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const T = () => `/api/${encodeURIComponent(S.tenant)}`;

  function withCites(text, cites) {
    const inactive = new Set([...(cites?.inactive || []), ...(cites?.unknown || [])]);
    return esc(text).replace(/\[(f-[0-9a-f]{8})\]/g, (_, id) =>
      `<span class="cite${inactive.has(id) ? " inactive" : ""}" data-fact="${id}" role="button" tabindex="0">${id}</span>`);
  }

  function entry(title, meta, html, ok = true) {
    const div = document.createElement("div");
    div.className = `entry ${ok ? "ok" : "bad"}`;
    div.innerHTML = `<h4>${esc(title)} <span class="meta">${esc(meta || "")}</span></h4>${html}`;
    $("feed").prepend(div);
  }

  function checksHtml(checks) {
    if (!checks?.length) return "";
    return `<div class="checks">${checks.map((c) =>
      `<span class="${c.ok ? "pass" : c.soft ? "warn" : "fail"}">${c.ok ? "✓" : c.soft ? "~" : "✗"} ${esc(c.check)}</span>`).join(" · ")}</div>`;
  }

  function factsList(o) {
    const li = [];
    (o.stored || []).forEach((s) => li.push(`<li class="${s.status === "active" ? "plus" : "q"}">+ ${esc(s.predicate)} = ${esc(s.value)} <span class="pill ${s.status}">${s.status}</span>${s.replaced ? " replaced " + s.replaced : ""}${s.disputes ? " · disputed" : ""}</li>`));
    (o.retracted || []).forEach((r) => li.push(`<li class="minus">− ruled out ${esc(r.predicate)} = ${esc(r.value)}</li>`));
    (o.dropped || []).forEach((d) => li.push(`<li class="drop">· dropped ${esc(d.predicate || "")}: ${esc(d.reason)}</li>`));
    return li.length ? `<ul>${li.join("")}</ul>` : "";
  }

  function radiusList(o) {
    return `<div>${o.facts.length} fact(s): ${o.direct} direct, ${o.derived} derived</div><ul>${o.facts.map((f) =>
      `<li class="minus">✗ ${esc(f.predicate)} = ${esc(f.object)} <span class="meta">(${esc(f.writer)}, ${esc(f.status)})</span></li>`).join("")}</ul>`;
  }

  // ------------------------------------------------------------- graph
  const fg = ForceGraph()($("graph"))
    .backgroundColor(css("--bg"))
    .nodeId("id")
    .linkColor((l) => LINK[l.type] || C.line)
    .linkWidth((l) => (["SUPERSEDES", "CONFLICTS_WITH", "DERIVED_FROM"].includes(l.type) ? 1.6 : 0.6))
    .linkLineDash((l) => (l.type === "CONFLICTS_WITH" ? [3, 3] : null))
    .linkDirectionalArrowLength((l) => (["SUPERSEDES", "DERIVED_FROM", "CONFLICTS_WITH"].includes(l.type) ? 4 : 0))
    .linkDirectionalArrowRelPos(1)
    .nodeLabel((n) => esc(n.kind === "fact" ? `${n.name} (${n.status})` : `${n.kind}: ${n.name}`))
    .nodeCanvasObject(drawNode)
    .nodePointerAreaPaint((n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, 9, 0, 2 * Math.PI); ctx.fill(); })
    .onNodeClick((n) => { if (n.kind === "fact") openWhy(n.id); })
    .cooldownTicks(150)
    .onEngineStop(() => { if (S.fit) { fg.zoomToFit(500, 80); S.fit = false; } });
  fg.d3Force("charge").strength(-260);
  fg.d3Force("link").distance((l) => (["SUPERSEDES", "CONFLICTS_WITH", "DERIVED_FROM"].includes(l.type) ? 45 : 75));
  const sizeGraph = () => { const el = $("graph"); fg.width(el.clientWidth).height(el.clientHeight); };
  sizeGraph();
  window.addEventListener("resize", () => { sizeGraph(); S.fit = true; });

  function factColor(n) {
    if (S.at !== null) return n.believed_at ? C.active : C.closed;
    return C[n.status] || C.muted;
  }

  function drawNode(n, ctx, scale) {
    const dim = S.highlight.size && !S.highlight.has(n.id);
    ctx.globalAlpha = dim ? 0.18 : (S.at !== null && n.kind === "fact" && !n.believed_at ? 0.35 : 1);
    let r = 5;
    if (n.kind === "agent") {
      r = 8; ctx.fillStyle = C.agent; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI); ctx.fill();
    } else if (n.kind === "source") {
      r = 7; ctx.fillStyle = n.compromised ? C.revoked : C.source;
      ctx.fillRect(n.x - r, n.y - r, 2 * r, 2 * r);
    } else if (n.kind === "handoff") {
      r = 3; ctx.fillStyle = "#4b3f8a"; ctx.beginPath();
      ctx.moveTo(n.x, n.y - r); ctx.lineTo(n.x + r, n.y); ctx.lineTo(n.x, n.y + r); ctx.lineTo(n.x - r, n.y); ctx.fill();
    } else if (n.kind === "fact") {
      const col = factColor(n);
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      if (n.status === "quarantined" && S.at === null) {
        ctx.setLineDash([2, 2]); ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]);
      } else { ctx.fillStyle = col; ctx.fill(); }
    } else {
      ctx.fillStyle = C.muted; ctx.beginPath(); ctx.arc(n.x, n.y, 3, 0, 2 * Math.PI); ctx.fill();
    }
    if (S.highlight.has(n.id)) {
      ctx.strokeStyle = C.dispute; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(n.x, n.y, r + 4, 0, 2 * Math.PI); ctx.stroke();
    }
    if (n.kind !== "handoff" && scale > 0.45) {
      const label = n.name;
      ctx.font = `${(n.kind === "fact" ? 10 : 11) / scale}px ${css("--mono")}`;
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      ctx.fillStyle = n.kind === "fact" && n.status !== "active" ? C.muted : C.ink;
      ctx.fillText(label.length > 34 ? label.slice(0, 33) + "…" : label, n.x, n.y + r + 3 / scale);
    }
    ctx.globalAlpha = 1;
  }

  async function refreshGraph() {
    if (!S.tenant) return;
    if (!S.hasGraph[S.tenant]) { fg.graphData({ nodes: [], links: [] }); S.nodes.clear(); S.sig = ""; return; }
    let data;
    try {
      data = await api(`${T()}/graph${S.at !== null ? `?at=${S.at}` : ""}`);
    } catch (e) { fg.graphData({ nodes: [], links: [] }); S.nodes.clear(); S.sig = ""; return; }
    const sig = JSON.stringify(data);
    if (sig === S.sig) return;
    S.sig = sig;
    if (data.nodes.length !== S.nodes.size) S.fit = true;
    const nodes = data.nodes.map((n) => Object.assign(S.nodes.get(n.id) || {}, n));
    S.nodes = new Map(nodes.map((n) => [n.id, n]));
    fg.graphData({ nodes, links: data.links });
    const times = data.nodes.filter((n) => n.kind === "fact").flatMap((n) => [n.valid_from, n.valid_to].filter(Boolean));
    if (S.at === null && times.length) {
      S.timeMin = Math.min(...times) - 60000;
      S.timeMax = Math.max(...times) + 60000;
    }
  }

  // ------------------------------------------------------------- time travel
  function setTime(ms) {
    S.at = ms;
    if (ms !== null && S.timeMax > S.timeMin) $("time").value = Math.round(1000 * (ms - S.timeMin) / (S.timeMax - S.timeMin));
    $("timeLabel").textContent = ms === null ? "Live" : `Memory as of ${hhmm(ms)}`;
    $("timeLabel").classList.toggle("past", ms !== null);
    if (ms === null) $("time").value = 1000;
    S.sig = ""; refreshGraph();
  }
  $("time").addEventListener("input", (e) => {
    const v = Number(e.target.value);
    if (v >= 1000 || !S.timeMax) return setTime(null);
    setTime(Math.round(S.timeMin + (S.timeMax - S.timeMin) * (v / 1000)));
  });
  $("live").addEventListener("click", () => setTime(null));

  // ------------------------------------------------------------- why panel
  async function openWhy(id) {
    let w;
    try { w = await api(`${T()}/facts/${encodeURIComponent(id)}/why`); }
    catch (e) { return entry("Why", id, `<div class="text">${esc(e.message)}</div>`, false); }
    S.highlight = new Set([id, ...w.upstream, ...w.sources.map((s) => `source:${s}`), ...w.agents.map((a) => `agent:${a}`)]);
    fg.nodeCanvasObject(drawNode);
    $("whyBody").innerHTML = `
      <div class="eyebrow">Why do we believe this?</div>
      <h3>${esc(w.predicate)} = ${esc(w.object)}</h3>
      <span class="pill ${w.status}">${w.status}</span>
      <dl>
        <dt>Written by</dt><dd>${esc(w.agents.join(", ") || "—")}</dd>
        <dt>Sources</dt><dd>${esc(w.sources.join(", ") || "—")}</dd>
        <dt>Based on</dt><dd>${w.upstream.map((u) => u.startsWith("f-") ? `<span class="cite" data-fact="${esc(u)}" role="button" tabindex="0">${esc(u)}</span>` : esc(u)).join(" ") || "—"}</dd>
        <dt>Replaced</dt><dd>${esc(w.replaced.join(", ") || "—")}</dd>
        <dt>Fact id</dt><dd>${esc(w.id)}</dd>
      </dl>
      <div class="eyebrow">Versions of ${esc(w.predicate)}</div>
      <ul class="versions">${w.versions.map((v) => `<li>${hhmm(v.valid_from)}${v.valid_to ? "–" + hhmm(v.valid_to) : "–now"} <span class="pill ${v.status}">${v.status}</span> ${esc(v.object)}</li>`).join("")}</ul>`;
    $("why").hidden = false;
  }
  $("whyClose").addEventListener("click", () => { $("why").hidden = true; S.highlight = new Set(); fg.nodeCanvasObject(drawNode); });
  document.addEventListener("click", (e) => { const c = e.target.closest(".cite"); if (c) openWhy(c.dataset.fact); });
  document.addEventListener("keydown", (e) => { const c = e.target.closest?.(".cite"); if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openWhy(c.dataset.fact); } });

  // ------------------------------------------------------------- sources & quarantine
  async function refreshSources() {
    if (!S.tenant) return;
    if (!S.hasGraph[S.tenant]) { $("sources").innerHTML = `<div class="drop">No graph yet. Press Reset to start the story.</div>`; $("quarantine").innerHTML = ""; return; }
    let rows = [], q = [];
    try { [rows, q] = await Promise.all([api(`${T()}/sources`), api(`${T()}/quarantine`)]); } catch (e) { /* no graph yet */ }
    $("sources").innerHTML = rows.map((s) => `
      <div class="src ${s.compromised ? "comp" : ""}" data-src="${esc(s.id)}">
        <div class="src-head"><span>${esc(s.id)}</span><span class="pill ${s.compromised ? "revoked" : s.trusted ? "active" : "quarantined"}">${s.compromised ? "compromised" : s.trusted ? "trusted" : "untrusted"}</span></div>
        <div class="trust" title="trust ${s.trust}"><i style="width:${s.trust * 100}%"></i><b style="left:50%"></b></div>
        <div class="src-meta"><span>${esc(s.kind)} · ${s.trust.toFixed(2)} · ${s.active}a ${s.quarantined}q ${s.revoked}r</span>
          ${s.compromised ? "" : `<button class="ghost small" data-preview="${esc(s.id)}" type="button">Preview revoke</button>`}</div>
        <div class="radius"></div>
      </div>`).join("") || `<div class="drop">No sources yet. Reset the tenant.</div>`;
    $("quarantine").innerHTML = q.map((f) => `
      <div class="src">
        <div class="src-head"><span>${esc(f.predicate)} = ${esc(f.object)}</span></div>
        <div class="src-meta"><span>from ${esc(f.sources.join(", "))}${f.disputes ? ` · disputes ${esc(f.disputes.believed)}` : ""}</span>
          <button class="ghost small" data-promote="${esc(f.id)}" type="button">Promote</button></div>
      </div>`).join("") || `<div class="drop">Nothing in quarantine.</div>`;
  }

  document.addEventListener("click", async (e) => {
    const p = e.target.closest("[data-preview]");
    if (p) {
      const src = p.dataset.preview, box = p.closest(".src").querySelector(".radius");
      const r = await api(`${T()}/sources/${encodeURIComponent(src)}/blast-radius`);
      S.highlight = new Set([`source:${src}`, ...r.facts.map((f) => f.id)]);
      fg.nodeCanvasObject(drawNode);
      S.previewing = src;
      box.innerHTML = radiusList(r) + `<button class="danger small" data-revoke="${esc(src)}" type="button">Revoke ${esc(src)}</button> <button class="ghost small" data-cancel type="button">Cancel</button>`;
      return;
    }
    if (e.target.closest("[data-cancel]")) { S.previewing = null; S.highlight = new Set(); fg.nodeCanvasObject(drawNode); refreshSources(); return; }
    const rv = e.target.closest("[data-revoke]");
    if (rv) {
      S.previewing = null;
      const r = await post(`${T()}/sources/${encodeURIComponent(rv.dataset.revoke)}/revoke`);
      entry(`Revoked ${rv.dataset.revoke}`, `${r.revoked.length} fact(s)`, radiusList(r));
      S.highlight = new Set(r.revoked); fg.nodeCanvasObject(drawNode);
      setTimeout(() => { S.highlight = new Set(); fg.nodeCanvasObject(drawNode); }, 4000);
      refreshAll(); return;
    }
    const pr = e.target.closest("[data-promote]");
    if (pr) {
      await post(`${T()}/facts/${encodeURIComponent(pr.dataset.promote)}/promote`);
      entry("Promoted", pr.dataset.promote, ""); refreshAll();
    }
  });

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === t));
    $("sources").hidden = t.dataset.tab !== "sources";
    $("quarantine").hidden = t.dataset.tab !== "quarantine";
  }));

  // ------------------------------------------------------------- demo
  async function loadDemo() {
    try { S.demo = await api(`${T()}/demo`); } catch (e) { S.demo = null; }
    const d = S.demo;
    $("incident").textContent = d ? `${d.subject} · ${d.title}` : S.tenant;
    $("next").disabled = !d; $("reset").disabled = !d || !d.allow_reset;
    if (!d) { $("stepCount").textContent = "No scenario"; $("dots").innerHTML = ""; return; }
    $("stepCount").textContent = `Step ${d.last_step} of ${d.steps.length}`;
    const next = d.steps[d.last_step];
    $("say").textContent = next ? `Next: ${next.say}` : "Story complete. Reset to replay.";
    $("dots").innerHTML = d.steps.map((s) => `<li class="${S.failed.has(s.n) ? "fail" : s.n <= d.last_step ? "done" : ""}" title="${s.n}. ${esc(s.action)}"></li>`).join("");
  }

  function showStep(r) {
    const o = r.output, title = `${r.n}. ${r.action}${o.agent ? " · " + o.agent : ""}`;
    let html = `<div class="text">${esc(r.say)}</div>`;
    if (r.action === "observe") html += factsList(o);
    if (["status_update", "ask", "investigate"].includes(r.action)) html += `<div class="text">${withCites(o.text, o.citations)}</div>`;
    if (["preview", "revoke"].includes(r.action)) html += radiusList(o);
    if (r.action === "as_of") { html += `<ul>${o.facts.map((f) => `<li>· ${esc(f.predicate)} = ${esc(f.object)}</li>`).join("")}</ul>`; setTime(Date.parse(o.time)); }
    if (r.action === "isolation") html += `<div class="text">${esc(o.other)} sees none of this incident; this tenant sees none of ${esc(o.other_subject || "—")}.</div>`;
    if (!r.ok) S.failed.add(r.n);
    entry(title, `${r.session} · ${hhmm(Date.parse(r.at))}`, html + checksHtml(r.checks), r.ok);
    if (r.action === "preview") { S.highlight = new Set(o.facts.map((f) => f.id)); fg.nodeCanvasObject(drawNode); }
    else if (r.action !== "as_of") { S.highlight = new Set(); }
  }

  $("next").addEventListener("click", async () => {
    if (S.busy) return; S.busy = true; $("next").disabled = true;
    try {
      if (S.at !== null && S.demo?.steps[S.demo.last_step]?.action !== "as_of") setTime(null);
      showStep(await post(`${T()}/demo/next`));
    } catch (e) { entry("Step failed", "", `<div class="text">${esc(e.message)}</div>`, false); }
    S.busy = false; await refreshAll();
  });

  $("reset").addEventListener("click", async () => {
    if (S.busy) return;
    if ($("reset").dataset.armed !== "1") {
      $("reset").dataset.armed = "1"; $("reset").textContent = "Confirm reset";
      setTimeout(() => { $("reset").dataset.armed = ""; $("reset").textContent = "Reset"; }, 3000);
      return;
    }
    $("reset").dataset.armed = ""; $("reset").textContent = "Reset";
    S.busy = true;
    try { await post(`${T()}/demo/reset`); S.hasGraph[S.tenant] = true; S.failed = new Set(); $("feed").innerHTML = ""; S.nodes.clear(); S.sig = ""; setTime(null); }
    catch (e) { entry("Reset failed", "", `<div class="text">${esc(e.message)}</div>`, false); }
    S.busy = false; refreshAll();
  });

  // ------------------------------------------------------------- ask
  $("askForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const agent = $("askAgent").value, q = $("askQ").value.trim();
    if (!q) return;
    const btn = e.target.querySelector("button"); btn.disabled = true;
    try {
      const r = await post(`${T()}/ask`, { agent, session: $("askSession").value || "s1", question: q });
      entry(`Ask · ${agent}`, r.tools.join(", "), `<div class="text">${esc(q)}</div><div class="text">${withCites(r.text, r.citations)}</div>`);
    } catch (err) { entry(`Ask · ${agent}`, "", `<div class="text">${esc(err.message)}</div>`, false); }
    btn.disabled = false;
  });

  // ------------------------------------------------------------- boot
  async function refreshAll() { await Promise.all([loadDemo(), refreshGraph(), refreshSources()]); }

  async function boot() {
    const [health, tenants] = await Promise.all([api("/api/health"), api("/api/tenants")]);
    $("modes").innerHTML = `<span class="chip">extract: ${esc(health.extract)}</span><span class="chip">agents: ${esc(health.agents)}</span>`;
    tenants.forEach((t) => { S.hasGraph[t.tenant] = t.has_graph; });
    $("tenant").innerHTML = tenants.map((t) => `<option value="${esc(t.tenant)}">${esc(t.tenant)}</option>`).join("");
    S.tenant = tenants.find((t) => t.tenant === "acme")?.tenant || tenants[0]?.tenant || null;
    if (S.tenant) $("tenant").value = S.tenant;
    $("tenant").addEventListener("change", () => {
      S.tenant = $("tenant").value; S.failed = new Set(); S.nodes.clear(); S.sig = ""; S.highlight = new Set();
      $("feed").innerHTML = ""; $("why").hidden = true; setTime(null); refreshAll();
    });
    await refreshAll();
    setInterval(() => { if (!S.busy) { refreshGraph(); if (!S.previewing) refreshSources(); } }, 2500);
  }
  boot().catch((e) => entry("Could not load", "", `<div class="text">${esc(e.message)}</div>`, false));
})();
```

### `tests/test_api.py`
```python
"""HTTP API (API.md). Rehearsal mode: golden extraction, offline agents."""
import pytest
from fastapi.testclient import TestClient

from memledger.api import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app("golden", "offline", state_path=tmp_path / "demo.json", allow_reset=True)
    return TestClient(app)


def run_demo(client, tenant="acme", upto=None):
    assert client.post(f"/api/{tenant}/demo/reset").status_code == 200
    n = upto or len(client.get(f"/api/{tenant}/demo").json()["steps"])
    out = []
    for _ in range(n):
        r = client.post(f"/api/{tenant}/demo/next")
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


def test_health_and_tenants(client):
    assert client.get("/api/health").json() == {"ok": True, "extract": "golden", "agents": "offline",
                                                 "allow_reset": True}
    t = {x["tenant"]: x for x in client.get("/api/tenants").json()}
    assert t["acme"]["subject"] == "INC-42" and t["globex"]["subject"] == "INC-7"


def test_full_demo_over_http(client):
    run_demo(client, "globex")
    steps = run_demo(client, "acme")
    assert len(steps) == 15 and all(s["ok"] for s in steps)
    assert steps[10]["action"] == "revoke" and len(steps[10]["output"]["revoked"]) == 2
    assert client.get("/api/acme/demo").json()["last_step"] == 15
    r = client.post("/api/acme/demo/next")
    assert r.status_code == 409 and "finished" in r.json()["detail"]


def test_demo_needs_reset_first(client, lite_db):
    lite_db.select_graph("memory_acme").delete()
    assert client.post("/api/acme/demo/next").status_code == 409


def test_graph_shape(client):
    run_demo(client, upto=8)
    g = client.get("/api/acme/graph").json()
    ids = {n["id"] for n in g["nodes"]}
    assert all(l["source"] in ids and l["target"] in ids for l in g["links"])
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"agent", "source", "fact", "handoff"} <= kinds and "episode" not in kinds
    facts = [n for n in g["nodes"] if n["kind"] == "fact"]
    assert {n["status"] for n in facts} >= {"active", "closed", "quarantined"}
    types = {l["type"] for l in g["links"]}
    assert {"SUPERSEDES", "CONFLICTS_WITH", "DERIVED_FROM", "FROM_SOURCE", "WROTE", "CARRIES"} <= types
    with_eps = client.get("/api/acme/graph?episodes=true").json()
    assert any(n["kind"] == "episode" for n in with_eps["nodes"])


def test_graph_at_time(client):
    run_demo(client, upto=11)
    from memledger.scenario import iso_ms
    g = client.get(f"/api/acme/graph?at={iso_ms('2026-10-17T13:55:00+05:30')}").json()
    facts = {n["name"]: n for n in g["nodes"] if n["kind"] == "fact"}
    assert facts["mitigation = flush-cache"]["believed_at"] is True
    assert facts["root_cause = db-pool-exhaustion"]["believed_at"] is False
    early = client.get(f"/api/acme/graph?at={iso_ms('2026-10-17T10:05:00+05:30')}").json()
    assert "root_cause = bad-deploy-v2.3.1" not in {n["name"] for n in early["nodes"]}


def test_why_and_facts(client):
    run_demo(client, upto=5)
    active = client.get("/api/acme/facts").json()["active"]
    rc = next(f for f in active if f["predicate"] == "root_cause")
    w = client.get(f"/api/acme/facts/{rc['id']}/why").json()
    assert w["sources"] == ["runbook"] and w["replaced"] == ["db-pool-exhaustion"]
    assert [v["status"] for v in w["versions"]] == ["closed", "active"]
    assert client.get("/api/acme/facts/f-00000000/why").status_code == 404


def test_trust_routes(client):
    run_demo(client, upto=9)
    src = {s["id"]: s for s in client.get("/api/acme/sources").json()}
    assert src["webhook"]["trusted"] and not src["fwd-logs"]["trusted"]
    q = client.get("/api/acme/quarantine").json()
    assert any(x["object"] == "ddos" and x["disputes"] for x in q)
    radius = client.get("/api/acme/sources/webhook/blast-radius").json()
    rv = client.post("/api/acme/sources/webhook/revoke").json()
    assert sorted(f["id"] for f in radius["facts"]) == rv["revoked"]
    assert client.put("/api/acme/sources/webhook/trust", json={"trust": 0.9}).status_code == 409
    assert client.put("/api/acme/sources/app-logs/trust", json={"trust": 2}).status_code == 422
    assert client.get("/api/acme/sources/nowhere/blast-radius").status_code == 404
    ddos = next(x for x in q if x["object"] == "ddos")
    assert client.post(f"/api/acme/facts/{ddos['id']}/promote").json()["closed"] == 1
    assert client.get("/api/acme/disputes").json() == []


def test_agent_routes(client):
    client.post("/api/acme/demo/reset")
    r = client.post("/api/acme/observe", json={"session": "s1", "source": "alerts",
                                                "text": open("data/acme/alerts.json").read()})
    assert r.status_code == 200 and r.json()["agent"] == "triage"
    assert len(client.get("/api/acme/handoffs/comms").json()) == 1
    u = client.post("/api/acme/status-update", json={"session": "s1"}).json()
    assert u["citations"]["active"] and u["stored"]["stored"][0]["predicate"] == "status"
    assert client.get("/api/acme/handoffs/comms").json() == []
    a = client.post("/api/acme/ask", json={"agent": "comms", "session": "s1", "question": "Root cause?"})
    assert a.status_code == 200 and a.json()["tools"] == ["recall"]
    assert client.post("/api/acme/ask", json={"agent": "boss", "session": "s1", "question": "x"}).status_code == 422
    i = client.post("/api/acme/investigate", json={"session": "s1"}).json()
    assert i["stopped"] == "answered"
    assert client.get("/api/acme/history/s1").json()[0]["agent"] == "triage"
    assert client.post("/api/acme/observe", json={"session": "s1", "source": "nowhere",
                                                   "text": "x"}).status_code == 404


def test_as_of_route(client):
    run_demo(client, upto=11)
    from memledger.scenario import iso_ms
    r = client.get(f"/api/acme/as_of?t={iso_ms('2026-10-17T13:55:00+05:30')}").json()
    assert "flush-cache" in {f["object"] for f in r["facts"]}


def test_bad_tenants(client):
    assert client.get("/api/Bad;Name/graph").status_code == 422
    assert client.get("/api/nobody/graph?subject=x").status_code == 404
    assert client.get("/api/nobody/demo").status_code == 404


def test_reset_can_be_disabled(tmp_path):
    c = TestClient(create_app("golden", "offline", state_path=tmp_path / "d.json", allow_reset=False))
    assert c.post("/api/acme/demo/reset").status_code == 403


def test_ui_is_served(client):
    html = client.get("/").text
    assert "/static/vendor/force-graph.min.js" in html and "/static/app.js" in html
    for f in ("app.js", "style.css", "vendor/force-graph.min.js"):
        assert client.get(f"/static/{f}").status_code == 200
```
