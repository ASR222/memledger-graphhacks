"""Scenario evaluation: MemLedger vs three simpler memory designs.

All four systems receive the same stream of events from one run of the
scenario: the validated claims extracted from every input and agent
conclusion (before any role filter), and every source revocation. Extraction
is held constant, so only the memory policy differs. Questions are answered
by deterministic readers, not an LLM, so the score measures what each memory
would hand an agent, not how well a model phrases an answer.
"""
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import memory, trust
from . import scenario as S
from .agents import team as team_mod
from .agents import tools as tools_mod
from .config import SINGLE_VALUED, TRUST_THRESHOLD


@dataclass
class Claim:
    t: int
    session: str
    source: str
    agent: str
    predicate: str
    value: str
    certainty: str


@dataclass
class Stream:
    claims: list = field(default_factory=list)
    revocations: list = field(default_factory=list)   # (t, source)


# ---------------------------------------------------------------- recording

@contextmanager
def recording(stream: Stream, tenant: str):
    """Record every ingest's claims and every revocation while the scenario runs."""
    real_team, real_tools, real_revoke = team_mod.ingest, tools_mod.ingest, trust.revoke_source

    def rec_ingest(t, *, extractor, agent, source, session, subject, text, now, **kw):
        inner = getattr(extractor, "inner", extractor)          # before the role filter
        known = memory.known_values(t, memory.canon(subject))
        kept, _ = inner.extract(text, memory.canon(subject), known)
        if t == tenant:
            stream.claims += [Claim(now, session, source, agent, c.predicate, c.value, c.certainty)
                              for c in kept]
        return real_team(t, extractor=extractor, agent=agent, source=source, session=session,
                         subject=subject, text=text, now=now, **kw)

    def rec_revoke(t, source, now):
        if t == tenant:
            stream.revocations.append((now, source))
        return real_revoke(t, source, now)

    team_mod.ingest = tools_mod.ingest = rec_ingest
    trust.revoke_source = rec_revoke
    try:
        yield stream
    finally:
        team_mod.ingest, tools_mod.ingest, trust.revoke_source = real_team, real_tools, real_revoke


# ---------------------------------------------------------------- baselines

class LogMemory:
    """A shared append-only log of claims.

    Single-valued fields: the newest claim wins. Multi-valued fields: every
    value ever claimed. Hedges and 'ruled out' are not understood (ruled-out
    claims are skipped, everything else is an assertion). No revocation.
    Options turn it into the other baselines.
    """
    name = "Shared log, last write wins"

    def __init__(self, stream: Stream, trust_by_source: dict, *, session_only=False,
                 trust_filter=False, delete_on_revoke=False):
        self.stream, self.trust_by_source = stream, trust_by_source
        self.session_only, self.trust_filter, self.delete_on_revoke = session_only, trust_filter, delete_on_revoke

    def _visible(self, now: int, session: str, until: int | None = None):
        revoked = {s for t, s in self.stream.revocations if t <= now} if self.delete_on_revoke else set()
        out = []
        for c in self.stream.claims:
            if c.t > now or (until is not None and c.t > until):
                continue
            if c.certainty == "ruled_out":
                continue
            if self.session_only and c.session != session:
                continue
            if self.trust_filter and self.trust_by_source.get(c.source, 0) < TRUST_THRESHOLD:
                continue
            if c.source in revoked:
                continue
            out.append(c)
        return out

    def _values(self, claims, predicate):
        cs = sorted((c for c in claims if c.predicate == predicate), key=lambda c: c.t)
        if not cs:
            return set()
        if predicate in SINGLE_VALUED:
            return {cs[-1].value}
        return {c.value for c in cs}

    def answer(self, q: dict, now: int, session: str) -> set:
        k = q["kind"]
        if k == "current":
            return self._values(self._visible(now, session), q["predicate"])
        if k == "at":
            return self._values(self._visible(now, session, until=S.iso_ms(q["time"])), q["predicate"])
        if k == "from_source":
            return {c.value for c in self._visible(now, session) if c.source == q["source"]}
        return set()                      # stale, disputed: no such concept


def baselines(stream: Stream, trust_by_source: dict) -> list:
    a = LogMemory(stream, trust_by_source, session_only=True)
    a.name = "No shared memory (per-session log)"
    b = LogMemory(stream, trust_by_source)
    c = LogMemory(stream, trust_by_source, trust_filter=True, delete_on_revoke=True)
    c.name = "Shared log + trust filter + delete on revoke"
    return [a, b, c]


class LedgerMemory:
    """MemLedger itself, read through the memory API."""
    name = "MemLedger"

    def __init__(self, tenant: str, subject: str):
        self.tenant, self.subject = tenant, memory.canon(subject)

    def answer(self, q: dict, now: int, session: str) -> set:
        k, t = q["kind"], self.tenant
        if k == "current":
            return {f["object"] for f in memory.read_active(t, self.subject) if f["predicate"] == q["predicate"]}
        if k == "at":
            return {f["object"] for f in memory.as_of(t, S.iso_ms(q["time"]))
                    if f["subject"] == self.subject and f["predicate"] == q["predicate"]}
        if k == "stale":
            return {s["object"] for s in memory.stale(t) if s["predicate"] == q["predicate"]}
        if k == "disputed":
            return {d["claimed"] for d in memory.disputes(t)
                    if d["subject"] == self.subject and d["predicate"] == q["predicate"]}
        if k == "from_source":
            snap = memory.snapshot(t)
            src = {n["nid"] for n in snap["nodes"] if n["label"] == "Source" and n["props"]["id"] == q["source"]}
            facts = {n["nid"]: n["props"] for n in snap["nodes"] if n["label"] == "Fact"}
            return {facts[e["src"]]["object"] for e in snap["edges"]
                    if e["type"] == "FROM_SOURCE" and e["dst"] in src and e["src"] in facts}
        raise ValueError(k)


# ---------------------------------------------------------------- run

def load_questions(tenant: str = "acme", data_dir: Path = S.DATA) -> list[dict]:
    return json.loads((Path(data_dir) / tenant / "eval_questions.json").read_text())["questions"]


def run(extractor, llm, tenant: str = "acme", state_path=None, questions=None) -> dict:
    """Replay the scenario once, asking every system each question at its checkpoint."""
    sc = S.load(tenant)
    qs = questions or load_questions(tenant)
    runner = S.Runner(sc, extractor, llm, state_path=state_path)
    runner.reset()
    trust_by_source = {s["id"]: s["trust"] for s in trust.trust_table(tenant)}
    trust_by_source.setdefault("reasoning", 0.8)
    stream = Stream()
    ledger = LedgerMemory(tenant, sc["subject"])
    rows = []
    last = max(q["after"] for q in qs)
    with recording(stream, tenant):
        for n in range(1, last + 1):
            res = runner.run_step(n)
            step = sc["steps"][n - 1]
            now = S.iso_ms(step["at"]) + 10_000
            systems = baselines(stream, trust_by_source) + [ledger]
            for q in (q for q in qs if q["after"] == n):
                expect = set(q["expect"])
                got = {s.name: sorted(s.answer(q, now, step["session"])) for s in systems}
                rows.append({**{k: q.get(k) for k in ("id", "kind", "tests", "depends_on_agents")},
                             "after": n, "expect": sorted(expect), "answers": got,
                             "correct": {name: set(v) == expect for name, v in got.items()},
                             "step_ok": res.ok})
    names = [s.name for s in baselines(stream, trust_by_source)] + [ledger.name]
    score = {nm: sum(r["correct"][nm] for r in rows) for nm in names}
    return {"tenant": tenant, "questions": len(rows), "systems": names, "score": score,
            "rows": rows, "claims": [asdict(c) for c in stream.claims],
            "revocations": stream.revocations}


def table(result: dict) -> str:
    """Markdown results table."""
    names = result["systems"]
    short = {n: n.split(" (")[0] for n in names}
    head = "| Q | Tests | " + " | ".join(short[n] for n in names) + " |"
    sep = "|---|---|" + "---|" * len(names)
    lines = [head, sep]
    for r in result["rows"]:
        cells = []
        for n in names:
            v = ", ".join(r["answers"][n]) or "∅"
            cells.append(("✅ " if r["correct"][n] else "❌ ") + v)
        lines.append(f"| {r['id']} | {r['tests']} | " + " | ".join(cells) + " |")
    lines.append("| | **Score** | " + " | ".join(f"**{result['score'][n]}/{result['questions']}**" for n in names) + " |")
    return "\n".join(lines)
