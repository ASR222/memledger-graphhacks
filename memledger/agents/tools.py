"""The tools agents use. Shared memory is their only memory.

Each tool is a plain function taking an AgentContext plus the model's
arguments and returning a small JSON-able dict. Errors are returned to the
model as {"error": ...}, never raised into the loop.
"""
import re
from dataclasses import dataclass, field
from typing import Callable

from .. import memory
from .. import queries as Q
from ..db import graph
from ..extract import Extractor
from ..ingest import ingest
from ..memory import _rows
from ..trust import RoleFilteredExtractor

# Conclusions agents draw from memory get their own source. Trusted (0.8), so a
# conclusion can become a belief, but every conclusion must cite active parent
# facts, so revoking the evidence revokes the conclusion.
REASONING = {"id": "reasoning", "kind": "agent_reasoning", "trust": 0.8}

CITATION = re.compile(r"\[(f-[0-9a-f]{8})\]")


@dataclass
class AgentContext:
    tenant: str
    agent: str
    session: str
    subject: str
    extractor: Extractor
    clock: Callable[[], int]
    log: list = field(default_factory=list)   # tool calls made during this run


def ensure_reasoning_source(tenant: str) -> None:
    graph(tenant).query(Q.ENSURE_SOURCE, REASONING)


# ---------------------------------------------------------------- tools

def recall(ctx: AgentContext) -> dict:
    """Current beliefs about the incident."""
    facts = memory.read_active(ctx.tenant, ctx.subject)
    return {"subject": ctx.subject, "facts": facts}


def disputes(ctx: AgentContext) -> dict:
    """Unconfirmed claims that contradict a current belief."""
    subject = memory.canon(ctx.subject)
    return {"disputes": [d for d in memory.disputes(ctx.tenant) if d["subject"] == subject]}


def stale(ctx: AgentContext) -> dict:
    """Active facts that were concluded from a belief no longer held."""
    return {"stale": memory.stale(ctx.tenant)}


def why(ctx: AgentContext, fact_id: str) -> dict:
    """Who wrote a fact, its sources, what it was based on, what it replaced."""
    w = memory.why(ctx.tenant, fact_id)
    if w is None:
        return {"error": f"no fact {fact_id}"}
    w.pop("paths", None)
    return w


def history(ctx: AgentContext, session: str) -> dict:
    """The turns logged in a session, oldest first."""
    return {"session": session, "turns": [
        {"agent": h["agent"], "at": h["at"], "text": h["text"][:300]}
        for h in memory.history(ctx.tenant, session)]}


def conclude(ctx: AgentContext, text: str, parents: list) -> dict:
    """Store a conclusion drawn from facts already in memory.

    `parents` must include at least one active fact id. The text is run through
    extraction like any other input, filtered by the agent's role.
    """
    parents = [p for p in (parents or []) if isinstance(p, str)]
    live = [p["id"] for p in memory.fact_info(ctx.tenant, parents) if p["status"] == "active"]
    if not live:
        return {"error": "a conclusion must cite at least one active fact id in parents"}
    report = ingest(ctx.tenant, extractor=RoleFilteredExtractor(ctx.extractor, ctx.agent),
                    agent=ctx.agent, source=REASONING["id"], session=ctx.session,
                    subject=ctx.subject, text=text, now=ctx.clock(), parents=live)
    return summarize(report)


def summarize(report: dict) -> dict:
    """Compact view of an ingest report for the model and the UI."""
    return {
        "stored": [{"id": w["id"], "predicate": w["predicate"], "value": w["value"],
                    "status": w["status"], "replaced": w["closed"], "disputes": w["conflicts"],
                    "ignored": w["ignored"]} for w in report["written"]],
        "retracted": [{"predicate": r["predicate"], "value": r["value"], "closed": r["closed"]}
                      for r in report["retracted"]],
        "dropped": [{"reason": d["reason"], "predicate": (d.get("item") or {}).get("predicate")}
                    for d in report["dropped"]],
    }


# ---------------------------------------------------------------- registry

TOOLS = {
    "recall": (recall, "Get the current beliefs about the incident, with fact ids.", {}),
    "disputes": (disputes, "List unconfirmed claims that contradict a current belief.", {}),
    "stale": (stale, "List active facts concluded from a belief that is no longer held.", {}),
    "why": (why, "Explain one fact: who wrote it, its sources, what it was based on, what it replaced.",
            {"fact_id": {"type": "string", "description": "Fact id, e.g. f-1a2b3c4d"}}),
    "history": (history, "Read the turns logged in a session.",
                {"session": {"type": "string", "description": "Session id, e.g. s1"}}),
    "conclude": (conclude, "Store a conclusion drawn from facts in memory. Cite the fact ids it is based on.",
                 {"text": {"type": "string", "description": "One or two plain sentences stating the conclusion."},
                  "parents": {"type": "array", "items": {"type": "string"},
                              "description": "Ids of the active facts this conclusion is based on."}}),
}


def tool_schemas(names) -> list[dict]:
    """JSON-schema declarations for the given tools."""
    out = []
    for n in names:
        _, desc, props = TOOLS[n]
        out.append({"name": n, "description": desc,
                    "parameters": {"type": "object", "properties": props, "required": list(props)}})
    return out


def call_tool(ctx: AgentContext, name: str, args: dict) -> dict:
    """Run one tool call from the model. Never raises."""
    if name not in TOOLS:
        result = {"error": f"unknown tool {name}"}
    else:
        fn, _, props = TOOLS[name]
        args = dict(args or {})
        missing = [p for p in props if p not in args]
        extra = [a for a in args if a not in props]
        if missing or extra:
            result = {"error": f"bad arguments; expected {sorted(props)}"}
        else:
            try:
                result = fn(ctx, **args)
            except memory.MemoryError_ as e:
                result = {"error": str(e)}
            except ValueError as e:
                result = {"error": str(e)}
    ctx.log.append({"tool": name, "args": args, "result": result})
    return result


def check_citations(tenant: str, text: str) -> dict:
    """Fact ids cited in text, split by whether they are still active."""
    ids = list(dict.fromkeys(CITATION.findall(text)))
    info = {f["id"]: f["status"] for f in memory.fact_info(tenant, ids)}
    return {"active": [i for i in ids if info.get(i) == "active"],
            "inactive": [i for i in ids if info.get(i) not in (None, "active")],
            "unknown": [i for i in ids if info.get(i) is None]}
