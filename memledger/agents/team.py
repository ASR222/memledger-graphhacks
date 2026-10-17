"""The team: routes inputs to agents, records handoffs, runs status updates.

The Team object holds configuration only. All state (facts, episodes,
handoffs) lives in the graph, so a new Team in a new session picks up
exactly where the last one left off.
"""
import time
import uuid

from .. import memory
from .. import queries as Q
from ..db import graph
from ..extract import Extractor
from ..ingest import ingest
from ..memory import _rows
from ..trust import RoleFilteredExtractor
from .roles import ROUTES
from .runner import run_agent
from .tools import REASONING, AgentContext, check_citations, ensure_reasoning_source, summarize


def _now_ms() -> int:
    return int(time.time() * 1000)


class Team:
    def __init__(self, tenant: str, subject: str, extractor: Extractor, llm, clock=_now_ms):
        self.tenant, self.subject = tenant, memory.canon(subject)
        self.extractor, self.llm, self.clock = extractor, llm, clock
        ensure_reasoning_source(tenant)

    def _ctx(self, agent: str, session: str) -> AgentContext:
        return AgentContext(self.tenant, agent, session, self.subject, self.extractor, self.clock)

    # ------------------------------------------------------------ observe

    def route(self, source: str) -> str:
        rows = _rows(graph(self.tenant).ro_query(Q.SOURCE_KIND, {"id": source}))
        if not rows:
            raise memory.UnknownReference(f"unknown source {source!r}")
        agent = ROUTES.get(rows[0]["kind"])
        if agent is None:
            raise ValueError(f"no agent handles source kind {rows[0]['kind']!r}")
        return agent

    def observe(self, session: str, source: str, text: str) -> dict:
        """An input arrives. The routed agent ingests it (role-filtered), then
        hands every new active or quarantined fact to Comms by id."""
        agent = self.route(source)
        report = ingest(self.tenant, extractor=RoleFilteredExtractor(self.extractor, agent),
                        agent=agent, source=source, session=session, subject=self.subject,
                        text=text, now=self.clock())
        new = [w["id"] for w in report["written"] if not w["corroborated"] and not w["ignored"]]
        changed = new + [w["id"] for w in report["written"] if w["promoted"]]
        handoff = self.handoff(agent, "comms", session, changed,
                               note=f"{len(changed)} update(s) from {source}") if changed else None
        return {"agent": agent, "episode": report["episode"], "handoff": handoff, **summarize(report)}

    # ------------------------------------------------------------ handoffs

    def handoff(self, sender: str, to: str, session: str, fact_ids: list, note: str = "") -> str:
        hid = f"h-{uuid.uuid4().hex[:8]}"
        graph(self.tenant).query(Q.HANDOFF, {"id": hid, "from": sender, "to": to, "session": session,
                                             "now": self.clock(), "note": note, "facts": fact_ids})
        return hid

    def pending(self, agent: str) -> list[dict]:
        rows = _rows(graph(self.tenant).ro_query(Q.PENDING_HANDOFFS, {"to": agent}))
        for r in rows:
            r["facts"] = [f for f in r["facts"] if f["id"] is not None]
        return rows

    def _deliver(self, ids: list) -> None:
        if ids:
            graph(self.tenant).query(Q.DELIVER_HANDOFFS, {"ids": ids, "now": self.clock()})

    # ------------------------------------------------------------ runs

    def ask(self, agent: str, session: str, question: str):
        """Any agent answers a question from shared memory."""
        run = run_agent(self._ctx(agent, session), self.llm, question)
        return run, check_citations(self.tenant, run.text)

    def investigate(self, session: str):
        """Investigator reviews memory (stale facts, disputes) and may conclude."""
        task = ("Review incident memory. Call stale and disputes. If a mitigation or owner "
                "depends on a root cause that is no longer believed, conclude what should "
                "change, citing the facts. Then summarise in two sentences.")
        return run_agent(self._ctx("investigator", session), self.llm, task)

    def status_update(self, session: str) -> dict:
        """Comms reads its handoffs, writes the update, and the update's status
        line is stored as a conclusion citing the facts it used."""
        handoffs = self.pending("comms")
        lines = [f"- from {h['sender']}: " + ", ".join(
            f"[{f['id']}] {f['predicate']}={f['object']} ({f['status']})" for f in h["facts"])
            for h in handoffs]
        task = "Write the status update for " + self.subject + "."
        if lines:
            task += ("\nHanded to you since the last update (status shown is current; anything not "
                     "active must not be stated as fact):\n" + "\n".join(lines))
        run = run_agent(self._ctx("comms", session), self.llm, task)
        cites = check_citations(self.tenant, run.text)
        stored = None
        if run.stopped == "answered" and cites["active"]:
            report = ingest(self.tenant, extractor=RoleFilteredExtractor(self.extractor, "comms"),
                            agent="comms", source=REASONING["id"], session=session,
                            subject=self.subject, text=run.text, now=self.clock(),
                            parents=cites["active"])
            stored = summarize(report)
        self._deliver([h["id"] for h in handoffs])
        return {"text": run.text, "citations": cites, "stored": stored,
                "handoffs_read": [h["id"] for h in handoffs], "run": run}
