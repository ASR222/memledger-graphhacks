"""Scenario runner: replays an incident story step by step and checks it.

A scenario is data/<tenant>/scenario.json plus the input files it names.
Each step runs one action with a fixed timestamp, then checks the graph
against the step's "expect" block. Hard checks must pass; soft checks depend
on what a live model wrote and only warn.
"""
import itertools
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import llm_retry, memory, schema, trust
from .agents.llm import Reply
from .agents.team import Team
from .db import get_db, graph

DATA = Path(__file__).resolve().parents[1] / "data"
AGENT_ACTIONS = {"investigate": "investigator", "status_update": "comms", "ask": None}
ACTIONS = {"observe", "investigate", "status_update", "ask", "preview", "revoke", "as_of", "isolation"}


class ScenarioError(Exception):
    pass


def iso_ms(s: str) -> int:
    return int(datetime.fromisoformat(s).timestamp() * 1000)


def load(tenant: str, data_dir: Path = DATA) -> dict:
    """Load and validate data/<tenant>/scenario.json."""
    path = Path(data_dir) / tenant / "scenario.json"
    sc = json.loads(path.read_text())
    sc["dir"] = path.parent
    last = None
    for i, st in enumerate(sc["steps"], 1):
        if st["n"] != i:
            raise ScenarioError(f"step numbers must run 1, 2, 3...; got {st['n']} at position {i}")
        if st["action"] not in ACTIONS:
            raise ScenarioError(f"step {i}: unknown action {st['action']!r}")
        t = iso_ms(st["at"])
        if last is not None and t <= last:
            raise ScenarioError(f"step {i}: time must be after step {i - 1}")
        last = t
        if "file" in st and not (path.parent / st["file"]).exists():
            raise ScenarioError(f"step {i}: missing file {st['file']}")
    return sc


# ---------------------------------------------------------------- offline stand-ins

class GoldenLLM:
    """Extraction from reference claims (data/<tenant>/golden_claims.json).

    Input files are matched by exact text. Agent-written text is read with
    three fixed patterns ("Status: x.", "Mitigation: x.", "Ruled out
    mitigation: x."). For tests and rehearsal only.
    """
    model = "golden"

    def __init__(self, scenario: dict):
        golden = json.loads((scenario["dir"] / "golden_claims.json").read_text())
        self.by_text = {(scenario["dir"] / name).read_text(): claims
                        for name, claims in golden.items() if not name.startswith("_")}

    def __call__(self, system, user):
        text = user.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        if text in self.by_text:
            return json.dumps({"claims": self.by_text[text]})
        claims = []
        for m in re.finditer(r"Ruled out mitigation: ([^.\[\]]+)\.", text):
            claims.append(_claim("mitigation", m.group(1), "ruled_out", m.group(0)))
        for m in re.finditer(r"(?<!out )Mitigation: ([^.\[\];]+)\.", text):
            claims.append(_claim("mitigation", m.group(1), "stated", m.group(0)))
        for m in re.finditer(r"Status: (investigating|identified|mitigating|monitoring|resolved)\.", text):
            claims.append(_claim("status", m.group(1), "stated", m.group(0)))
        return json.dumps({"claims": claims})


def _claim(p, v, c, e):
    return {"predicate": p, "value": v.strip(), "certainty": c, "evidence": e}


class OfflineChat:
    """A deterministic stand-in for the agent model, following each role's
    instructions with fixed rules. Same interface as GeminiChat. Set `hint`
    to give the investigator a conclusion to draw (from the scenario), and
    `parent` ("predicate=value") to cite that fact instead of the root cause."""

    def __init__(self):
        self.hint = None
        self.parent = None

    def start(self, system, tools):
        role = re.search(r"You are the (\w+) agent", system).group(1)
        return _OfflineSession(role, self.hint, self.parent)


class _OfflineSession:
    def __init__(self, role, hint, parent=None):
        self.role, self.hint, self.parent, self.phase, self.mem = role, hint, parent, 0, {}

    def send(self, task):
        self.task = task
        if self.role == "comms" and task.startswith("Write the status update"):
            return _calls("recall", "disputes")
        if self.role == "investigator":
            return _calls("recall", "stale", "disputes")
        return _calls("recall")

    def send_tool_results(self, results):
        r = dict(results)
        self.phase += 1
        facts = r.get("recall", {}).get("facts", self.mem.get("facts", []))
        self.mem.setdefault("facts", facts)
        rc = next((f for f in facts if f["predicate"] == "root_cause"), None)

        if self.role == "comms" and self.task.startswith("Write the status update"):
            return Reply(text=_status_text(facts, r.get("disputes", {}).get("disputes", [])))

        if self.role == "comms":                      # ask
            if self.phase == 1:
                if rc is None:
                    return Reply(text="No root cause is recorded yet.")
                self.mem["rc"] = rc
                return Reply(calls=[{"name": "why", "args": {"fact_id": rc["id"]}}])
            rc, w = self.mem["rc"], r["why"]
            text = (f"The root cause is {rc['object']} [{rc['id']}]. It was written by "
                    f"{', '.join(w['agents'])} from {', '.join(w['sources'])}")
            if w.get("replaced"):
                text += f", and it replaced {', '.join(w['replaced'])}"
            return Reply(text=text + ".")

        if self.role == "investigator":
            if self.phase == 1:
                stale = [s for s in r.get("stale", {}).get("stale", []) if s["predicate"] == "mitigation"]
                if stale and rc:
                    text = " ".join(f"Ruled out mitigation: {s['object']}." for s in stale)
                    return Reply(calls=[{"name": "conclude", "args": {"text": text, "parents": [rc["id"]]}}])
                cite = rc
                if self.parent:
                    cite = next((f for f in facts if f"{f['predicate']}={f['object']}" == self.parent), None)
                if self.hint and cite:
                    return Reply(calls=[{"name": "conclude", "args": {"text": self.hint, "parents": [cite["id"]]}}])
                return Reply(text="Nothing to change.")
            c = r.get("conclude", {})
            done = [f"stored {x['predicate']}={x['value']} ({x['status']})" for x in c.get("stored", [])]
            done += [f"ruled out {x['predicate']}={x['value']}" for x in c.get("retracted", [])]
            return Reply(text=("Done: " + "; ".join(done) + ".") if done else "Nothing changed.")

        return Reply(text="No change.")


def _calls(*names):
    return Reply(calls=[{"name": n, "args": {}} for n in names])


def _status_text(facts, disputes) -> str:
    by = {}
    for f in facts:
        by.setdefault(f["predicate"], []).append(f)

    def cite(pred):
        return "; ".join(f"{f['object']} [{f['id']}]" for f in by.get(pred, []))

    parts = []
    for label, pred in [("Impact", "affects_service"), ("Severity", "severity"),
                        ("Root cause", "root_cause"), ("Mitigation", "mitigation"), ("Owner", "owner")]:
        if pred in by:
            parts.append(f"{label}: {cite(pred)}.")
    if disputes:
        parts.append("Unconfirmed reports, not verified: " + ", ".join(d["claimed"] for d in disputes) + ".")
    status = "mitigating" if "mitigation" in by else "identified" if "root_cause" in by else "investigating"
    return " ".join(parts) + f"\nStatus: {status}."


# ---------------------------------------------------------------- state and checks

def facts_by_status(tenant: str, subject: str) -> dict[str, set]:
    """{status: {"predicate=value", ...}} for one subject."""
    subject = memory.canon(subject)
    out: dict[str, set] = {}
    for n in memory.snapshot(tenant)["nodes"]:
        p = n["props"]
        if n["label"] == "Fact" and p.get("subject") == subject:
            out.setdefault(p["status"], set()).add(f"{p['predicate']}={p['object']}")
    return out


def _has(items: set, want: str) -> bool:
    return want in items if "=" in want else any(i.startswith(want + "=") for i in items)


def check(tenant: str, subject: str, expect: dict, output: dict) -> list[dict]:
    soft = bool(expect.get("soft"))
    state = facts_by_status(tenant, subject)
    res = []

    def add(name, ok):
        res.append({"check": name, "ok": bool(ok), "soft": soft})

    for status in ("active", "closed", "quarantined", "revoked"):
        for want in expect.get(status, []):
            add(f"{status}: {want}", _has(state.get(status, set()), want))
    if "disputed" in expect:
        subj = memory.canon(subject)
        d = {f"{x['predicate']}={x['claimed']}" for x in memory.disputes(tenant) if x["subject"] == subj}
        for want in expect["disputed"]:
            add(f"disputed: {want}", want in d)
    if expect.get("stale_empty"):
        add("nothing stale", memory.stale(tenant) == [])
    if expect.get("citations_ok"):
        c = output.get("citations") or {}
        add("citations all active", c.get("active") and not c.get("inactive") and not c.get("unknown"))
    text = (output.get("text") or "").lower()
    for s in expect.get("text_includes", []):
        add(f"text mentions {s}", s.lower() in text)
    for s in expect.get("text_excludes", []):
        add(f"text omits {s}", s.lower() not in text)
    if "radius" in expect:
        got = {f"{f['predicate']}={f['object']}" for f in output.get("facts", [])}
        for want in expect["radius"]:
            add(f"in blast radius: {want}", want in got)
    for agent in expect.get("radius_agents", []):
        add(f"blast radius reaches {agent}", agent in (output.get("by_agent") or {}))
    if "as_of" in expect:
        got = {f"{f['predicate']}={f['object']}" for f in output.get("facts", [])}
        for want in expect["as_of"]:
            add(f"believed then: {want}", want in got)
    if expect.get("isolated"):
        add("no facts cross tenants", output.get("isolated"))
    return res


# ---------------------------------------------------------------- runner

@dataclass
class StepResult:
    n: int
    action: str
    session: str
    at: str
    say: str
    output: dict
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks if not c["soft"])

    @property
    def warnings(self) -> list:
        return [c for c in self.checks if c["soft"] and not c["ok"]]


def _short(e: BaseException, limit: int = 120) -> str:
    """First line of an error, without the JSON payload Gemini errors carry."""
    msg = str(e).splitlines()[0] if str(e) else type(e).__name__
    msg = msg.split(". {", 1)[0]
    return msg if len(msg) <= limit else msg[:limit - 3] + "..."


class Runner:
    """Runs a scenario against the tenant's graph, one step at a time.

    Progress is kept in a small JSON file so `--step N` can refuse to run out
    of order. Every step builds a new Team, so nothing carries over in code.
    """

    def __init__(self, scenario: dict, extractor, llm, state_path: Path | None = None):
        self.sc, self.extractor, self.llm = scenario, extractor, llm
        self.tenant, self.subject = scenario["tenant"], scenario["subject"]
        self.state_path = Path(state_path or (DATA / ".demo_state.json"))

    # progress
    def _state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def last_step(self) -> int:
        return self._state().get(self.tenant, 0)

    def _set_last(self, n: int) -> None:
        s = self._state()
        s[self.tenant] = n
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(s, indent=1))

    def reset(self) -> None:
        """Delete the tenant's graph and seed it fresh (safe: the graph is empty)."""
        name = f"memory_{self.tenant}"
        if name in get_db().list_graphs():
            graph(self.tenant).delete()
        schema.seed(self.tenant)
        self._set_last(0)

    # running
    def run_step(self, n: int, force: bool = False) -> StepResult:
        last = self.last_step()
        if not force and n != last + 1:
            raise ScenarioError(f"next step is {last + 1}; run that, or reset")
        st = self.sc["steps"][n - 1]
        ticks = itertools.count(iso_ms(st["at"]))
        clock = lambda: next(ticks)  # noqa: E731
        if hasattr(self.llm, "hint"):
            self.llm.hint = st.get("offline_conclusion")
            if hasattr(self.llm, "parent"):
                self.llm.parent = st.get("offline_parent")
        team = Team(self.tenant, self.subject, self.extractor, self.llm, clock)
        try:
            out = self._act(team, st, clock)
        except Exception as e:
            # The agent model ran out of rate limit (retries and any fallback
            # already spent): report this step as failed instead of crashing.
            if st["action"] not in AGENT_ACTIONS or not llm_retry.is_transient(e):
                raise
            out = {"agent": AGENT_ACTIONS[st["action"]] or st.get("agent"), "text": "",
                   "tools": [], "error": f"agent model unavailable: {_short(e)}"}
        checks = check(self.tenant, self.subject, st.get("expect", {}), out)
        if out.get("error"):
            checks.insert(0, {"check": out["error"], "ok": False, "soft": False})
        res = StepResult(n, st["action"], st["session"], st["at"], st.get("say", ""), out, checks)
        self._set_last(max(last, n))
        return res

    def run_until(self, n: int) -> list[StepResult]:
        return [self.run_step(i) for i in range(self.last_step() + 1, n + 1)]

    def _act(self, team: Team, st: dict, clock) -> dict:
        a, s = st["action"], st["session"]
        if a == "observe":
            text = (self.sc["dir"] / st["file"]).read_text()
            return team.observe(s, st["source"], text)
        if a == "investigate":
            run = team.investigate(s)
            return {"agent": "investigator", "text": run.text,
                    "tools": [t["tool"] for t in run.tool_calls]}
        if a == "status_update":
            u = team.status_update(s)
            return {"agent": "comms", "text": u["text"], "citations": u["citations"],
                    "stored": (u["stored"] or {}).get("stored", []),
                    "tools": [t["tool"] for t in u["run"].tool_calls]}
        if a == "ask":
            run, cites = team.ask(st["agent"], s, st["question"])
            return {"agent": st["agent"], "text": run.text, "citations": cites,
                    "tools": [t["tool"] for t in run.tool_calls]}
        if a == "preview":
            return trust.blast_radius(self.tenant, st["source"])
        if a == "revoke":
            return trust.revoke_source(self.tenant, st["source"], clock())
        if a == "as_of":
            subj = memory.canon(self.subject)
            return {"time": st["time"],
                    "facts": [f for f in memory.as_of(self.tenant, iso_ms(st["time"]))
                              if f["subject"] == subj]}
        if a == "isolation":
            other = st["other"]
            exists = f"memory_{other}" in get_db().list_graphs()
            mine = memory.read_active(other, self.subject) if exists else []
            try:
                theirs_subject = load(other, self.sc["dir"].parent)["subject"]
                theirs = memory.read_active(self.tenant, theirs_subject)
            except FileNotFoundError:
                theirs_subject, theirs = None, []
            return {"other": other, "other_subject": theirs_subject, "other_exists": exists,
                    "leaked_to_other": mine, "leaked_from_other": theirs,
                    "isolated": not mine and not theirs}
        raise ScenarioError(f"unknown action {a!r}")
