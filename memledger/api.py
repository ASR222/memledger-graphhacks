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

    @app.middleware("http")
    async def revalidate_ui(request, call_next):
        # pages and their CSS/JS must never be served stale after a deploy
        resp = await call_next(request)
        path = request.url.path
        if path in ("/", "/demo") or (path.startswith("/static/") and path.endswith((".css", ".js", ".html"))):
            resp.headers["Cache-Control"] = "no-cache"
        return resp
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

        @app.get("/demo", include_in_schema=False)
        def demo_page():
            return FileResponse(STATIC / "demo.html")

    return app


app = create_app()
