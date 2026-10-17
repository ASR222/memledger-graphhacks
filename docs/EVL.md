# EVL.md — MemLedger Evaluation

Complete context for the evaluation: what it measures, the four memory designs compared, the 16 questions, the results, and how to read them honestly. Covers workstream EVL on the build board (EVL-1 to EVL-3).

**Status (17 Oct 2026):**
- Every file in section 10 was run. The full suite is **143 passed, 1 skipped, 2 expected failures**: the 136 from earlier docs plus 8 new tests (7 pass, 1 is the Q16 expected failure). The skip is the official FalkorDB MCP test, which needs Node.
- **The result:** MemLedger answers **15 of 16** questions correctly; the strongest baseline answers **8**. The one miss is the Mem.md time-travel bug, and **with the SCN.md §12 patch it's 16 of 16** (tested in a copy).
- **Not yet run:** with live Gemini (cache extraction + live agents). Run it after your first live scenario run (§6).

**This file is additive. It does not change any earlier doc.** It adds:

| File | Purpose |
|---|---|
| `data/acme/eval_questions.json` | 16 questions with expected answers and checkpoints |
| `memledger/evaluate.py` | records the claim stream, implements the baselines, runs the evaluation |
| `scripts/eval.py` | CLI; writes a JSON with every answer and a Markdown table |
| `tests/test_eval.py` | 8 tests; they detect whether the §12 patch is applied and expect 15 or 16 |

---

## 1. What this measures, and what it doesn't

**It measures memory policy:** given the same stream of extracted claims, which memory design hands an agent the right beliefs at each point in the INC-42 story?

- **Extraction is held constant.** All systems receive the identical claims, validated by EXT.md's pipeline, before any role filter.
- **Answers come from deterministic readers, not an LLM.** The score is what each memory would hand to an agent, not how well a model phrases an answer.

**It is not a benchmark.** I designed the scenario, the questions and the baselines, and the questions target the features MemLedger was built for. Read it as a **feature-by-feature demonstration with a reproducible scorecard**, not as evidence that MemLedger beats published memory systems. Say exactly that to judges; it's more credible than a big number.

What it can't tell you:
- how well the live Gemini extraction does (EXT.md's `try_extract.py` checks that);
- how well agents phrase answers;
- scale (TEN.md covers concurrency);
- performance on public benchmarks (LongMemEval, LoCoMo, MemoryAgentBench).

---

## 2. The four systems

| System | What it is | Single-valued fields | Multi-valued fields | Trust | "Ruled out" | Revoke | Time travel | Provenance |
|---|---|---|---|---|---|---|---|---|
| **A. No shared memory** | each session sees only its own claims | newest claim wins | every value claimed | none | ignored | none | within the session | source kept |
| **B. Shared log, last write wins** | one append-only log for all agents and sessions: the "shared blob" most multi-agent setups use | newest claim wins | every value ever claimed | none | ignored | none | claims up to *t* | source kept |
| **C. Shared log + trust filter + delete on revoke** | B plus the obvious quick fixes: drop claims from sources below 0.5 trust; delete everything from a revoked source | newest wins | every value | **filter at write** | ignored | **delete** | claims up to *t* (deleted ones gone) | source kept, until deleted |
| **D. MemLedger** | this project | supersession | accumulate | quarantine + disputes; hedges quarantined | retraction | taint revocation, history kept | validity windows | full graph |

All three baselines treat `stated` and `suspected` claims as assertions; they have no notion of hedging. C is a deliberately reasonable baseline: it is what a competent engineer would add to a vector or key-value store in an afternoon, and it wins some questions.

---

## 3. The questions (EVL-1)

Asked after the given step of the SCN.md story. Answers are compared as **exact sets of values**.

| Q | After step | Asks | Expected | Trap / what it tests |
|---|---|---|---|---|
| Q1 | 2 | root cause | db-pool-exhaustion | sanity: one uncontested belief |
| Q2 | 5 | root cause | bad-deploy-v2.3.1 | a correction replaces an older belief |
| Q3 | 5 | affected service | payments-api | persistence across sessions |
| Q4 | 5 | stale mitigations | raise-the-db-connection-pool-size | a conclusion whose basis was replaced is flagged |
| Q5 | 6 | mitigations | rollback-to-v2.3.0 | an explicit "ruled out" removes a belief |
| Q6 | 7 | root cause | bad-deploy-v2.3.1 | a **newer** claim from an untrusted source (DDoS) must not win |
| Q7 | 7 | status | mitigating | a prompt-injected "resolved" must not win |
| Q8 | 7 | unconfirmed root causes | ddos | contested claims surfaced, neither believed nor silently dropped |
| Q9 | 8 | root cause | bad-deploy-v2.3.1 | a **hedged** guess ("possibly the cause") from a **trusted** source must not win |
| Q10 | 8 | mitigations | rollback, flush-cache | no retracted, no untrusted values |
| Q11 | 11 | mitigations | rollback-to-v2.3.0 | revocation withdraws what the source said |
| Q12 | 11 | root cause | bad-deploy-v2.3.1 | root cause after revocation |
| Q13 | 11 | what did the webhook contribute? | flush-cache, redis-outage | audit **after** revocation |
| Q14 | 11 | mitigations at 13:55 | rollback, flush-cache | time travel |
| Q15 | 11 | root cause at 10:30 | db-pool-exhaustion | time travel to the previous session |
| Q16 | 11 | root cause at 13:55 | bad-deploy-v2.3.1 | time travel must not show claims that were **never believed** |

**Six questions depend on agent behavior** (Q4, Q5, Q7, Q10, Q11, Q14): their expected answers assume the Investigator concludes the pool-size mitigation in step 3, rules it out in step 6, and Comms writes "mitigating". The rehearsal stand-ins do; live Gemini may not (§6).

---

## 4. Results (EVL-2, EVL-3)

Rehearsal mode (reference extraction, offline agents), embedded FalkorDB 4.18.3:

| Q | Tests | No shared memory | Shared log, last write wins | Shared log + trust filter + delete on revoke | MemLedger |
|---|---|---|---|---|---|
| Q1 | baseline: a single, uncontested belief | ✅ db-pool-exhaustion | ✅ db-pool-exhaustion | ✅ db-pool-exhaustion | ✅ db-pool-exhaustion |
| Q2 | a correction replaces an older belief | ✅ bad-deploy-v2.3.1 | ✅ bad-deploy-v2.3.1 | ✅ bad-deploy-v2.3.1 | ✅ bad-deploy-v2.3.1 |
| Q3 | memory persists across sessions | ❌ ∅ | ✅ payments-api | ✅ payments-api | ✅ payments-api |
| Q4 | flags a conclusion whose basis was replaced | ❌ ∅ | ❌ ∅ | ❌ ∅ | ✅ raise-the-db-connection-pool-size |
| Q5 | an explicit 'ruled out' removes a belief | ✅ rollback-to-v2.3.0 | ❌ raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ❌ raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ✅ rollback-to-v2.3.0 |
| Q6 | a newer claim from an untrusted source does not win | ❌ ddos | ❌ ddos | ✅ bad-deploy-v2.3.1 | ✅ bad-deploy-v2.3.1 |
| Q7 | a prompt-injected 'resolved' does not win | ❌ resolved | ❌ resolved | ✅ mitigating | ✅ mitigating |
| Q8 | contested claims are surfaced as unconfirmed, not dropped or believed | ❌ ∅ | ❌ ∅ | ❌ ∅ | ✅ ddos |
| Q9 | a hedged guess from a trusted source does not overwrite a belief | ❌ redis-outage | ❌ redis-outage | ❌ redis-outage | ✅ bad-deploy-v2.3.1 |
| Q10 | current mitigations: no retracted, no untrusted | ❌ block-1.2.3.4-at-edge, flush-cache, rollback-to-v2.3.0 | ❌ block-1.2.3.4-at-edge, flush-cache, raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ❌ flush-cache, raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ✅ flush-cache, rollback-to-v2.3.0 |
| Q11 | revoking a source withdraws what it said | ❌ block-1.2.3.4-at-edge, flush-cache, rollback-to-v2.3.0 | ❌ block-1.2.3.4-at-edge, flush-cache, raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ❌ raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ✅ rollback-to-v2.3.0 |
| Q12 | root cause after revocation | ❌ redis-outage | ❌ redis-outage | ✅ bad-deploy-v2.3.1 | ✅ bad-deploy-v2.3.1 |
| Q13 | audit: what did the compromised source contribute, after revocation | ✅ flush-cache, redis-outage | ✅ flush-cache, redis-outage | ❌ ∅ | ✅ flush-cache, redis-outage |
| Q14 | time travel: mitigations believed at 13:55 | ❌ block-1.2.3.4-at-edge, flush-cache, rollback-to-v2.3.0 | ❌ block-1.2.3.4-at-edge, flush-cache, raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ❌ raise-the-db-connection-pool-size, rollback-to-v2.3.0 | ✅ flush-cache, rollback-to-v2.3.0 |
| Q15 | time travel: the morning's belief, from the afternoon | ❌ ∅ | ✅ db-pool-exhaustion | ✅ db-pool-exhaustion | ✅ db-pool-exhaustion |
| Q16 | time travel must not show claims that were never believed | ❌ redis-outage | ❌ redis-outage | ✅ bad-deploy-v2.3.1 | ❌ bad-deploy-v2.3.1, redis-outage |
| | **Score** | **4/16** | **5/16** | **8/16** | **15/16** |

| System | Score | Without the two capability questions (Q4, Q8)* |
|---|---|---|
| A. No shared memory | 4/16 | 4/14 |
| B. Shared log, last write wins | 5/16 | 5/14 |
| C. + trust filter + delete on revoke | 8/16 | 8/14 |
| **D. MemLedger** | **15/16** (16/16 with the SCN.md §12 patch) | **13/14** (14/14 patched) |

\*Q4 (stale reasoning) and Q8 (disputes) ask for something the baselines have no concept of, so they score zero by construction. The second column removes them, so the comparison is only on questions every design could in principle answer.

### What the table shows

- **Last-write-wins is dangerous, not just imprecise.** B reports **DDoS** as the root cause (Q6) and **"resolved"** as the status (Q7), both from the junk forwarded message with the prompt injection. Then it reports **redis-outage** (Q9, Q12), a hedged guess from a source later revoked.
- **The quick fixes help, and stop short.** C's trust filter fixes Q6, Q7 and Q12. But:
  - it still believes the hedged Redis guess (Q9), because the webhook is "trusted";
  - it keeps the ruled-out pool-size fix (Q5, Q10, Q11);
  - deleting on revoke **destroys the audit trail** (Q13: it can't say what the compromised source contributed) and corrupts history (Q14).
- **A loses everything at the session boundary** (Q3, Q15). It wins Q5 only by accident: session 2 never saw the session-1 mitigation.
- **MemLedger's miss is real.** Q16: at 13:55 its time travel returns `redis-outage`, which was only ever quarantined and was never believed. Revocation turned its status from `quarantined` into `revoked`, so the as-of filter stopped excluding it. C gets this one right. The fix is the SCN.md §12 patch, which gives **16/16** in a copy.

**Pitch line:** "Against a shared log with the obvious fixes, MemLedger answers 15 of 16 versus 8. The one we missed is a bug we found with this evaluation, and the fix is ready. Last-write-wins would have told stakeholders the incident was resolved because a forwarded email said so."

---

## 5. How it works

1. `evaluate.run` resets the tenant and replays the SCN.md scenario step by step with `scenario.Runner`.
2. **Recording.** While it runs, `ingest` (in both the team and the conclude tool) and `trust.revoke_source` are wrapped:
   - each ingest's text is extracted with the **inner** extractor (before the role filter), using the same known values ingest uses, so the cache key and the claims match exactly;
   - claims are recorded with time, session, source and agent; revocations with time and source.
   - The real functions run unchanged, and the originals are restored afterwards (tested).
3. **Checkpoints.** After each step, the questions for that step are asked of all four systems. Baselines answer from the claims recorded so far; MemLedger from the live graph through the memory API. "Now" for a checkpoint is the step's time plus 10 seconds.
4. The result holds every answer, the full claim stream and the revocations, so any row can be audited.

---

## 6. Running it

```bash
# rehearsal: no key, no Docker
python scripts/eval.py --embedded --extract golden --agents offline --out data/acme/eval_results

# real: after one live scenario run has filled the extraction cache (SCN.md §6)
python scripts/eval.py --extract cache --agents live --out data/acme/eval_results_live
```

It resets the tenant's graph (acme) first. Don't run it against the tenant you're about to record.

**Live runs.** Extraction from the cache is identical every time, but live agents differ. The six agent-dependent questions may then fail for every system, because the expected answer assumed a particular conclusion. Read those rows before judging. If Gemini consistently concludes something else, update that question's `expect` and say so. The other ten don't depend on agents.

**Put in the README:** the Markdown table from `--out`, the mode line above it, and the honest framing from §1. Don't drop Q16 to get a clean 16/16; either apply the patch or show the miss.

---

## 7. Tests

```bash
pytest -q        # 143 passed, 1 skipped, 2 xfailed  (unpatched)
```

| Test | Checks |
|---|---|
| `test_scores` | exact scores per system (MemLedger 15, or 16 if patched) |
| `test_memledger_misses_at_most_q16` | MemLedger's only miss is Q16, and only when unpatched |
| `test_q16_after_patch` | expected failure until the §12 patch; passes once it's applied |
| `test_traps_catch_the_baselines` | B believes DDoS and "resolved"; C believes the hedged Redis guess and loses the audit trail; every scenario step's hard checks passed during the eval |
| `test_stream_was_recorded_and_hooks_restored` | all sources recorded, a ruled-out claim present, revocation recorded, originals restored |
| `test_table` | Markdown table with the score row |
| `test_log_baseline_semantics` | newest wins, trust filter, delete on revoke, session-only, ruled-out ignored, time cutoff, provenance, no stale concept |
| `test_cli_writes_results` | `--out` writes JSON and Markdown |

**Checked in a copy with the §12 patch applied:** `tests/test_eval.py` passes 8/8 (the expected failure turns into a pass, and the scores read 16).

---

## 8. Known limits and threats to validity

- **Author-designed:** scenario, questions and baselines are mine, and the questions map to MemLedger features (§1).
- **One scenario, 16 questions.** Small; no variance estimate. The deterministic setup makes it reproducible, not general.
- **Baselines are my implementations.** They follow the descriptions in §2; a different "quick fix" could score differently. C was made deliberately reasonable.
- **Structured answers.** Real agents ask in natural language; this skips the retrieval-and-phrasing step on purpose.
- **Rehearsal stand-ins** produced the claim stream for the numbers above; see §6 for live.

---

## 9. Judge talking points

- "We compared four memory designs on the same claim stream. Extraction was held constant, so only the memory policy differs."
- "A shared log, the default in most multi-agent frameworks, said the incident was resolved because a forwarded email told it to."
- "Adding a trust filter and delete-on-revoke helps, but it believes a trusted source's guess and destroys the audit trail."
- "MemLedger: 15 of 16. The miss is a time-travel bug this evaluation found, and the fix makes it 16."
- "We designed these questions around our features. It's a scorecard, not a benchmark."

---

## 10. Source files (tested)

### `data/acme/eval_questions.json`
```json
{
  "_note": "Asked after the given scenario step. 'kind': current | at | stale | disputed | from_source. Answers are compared as exact sets of values.",
  "questions": [
    {"id": "Q1",  "after": 2,  "kind": "current", "predicate": "root_cause", "expect": ["db-pool-exhaustion"],
     "tests": "baseline: a single, uncontested belief"},
    {"id": "Q2",  "after": 5,  "kind": "current", "predicate": "root_cause", "expect": ["bad-deploy-v2.3.1"],
     "tests": "a correction replaces an older belief"},
    {"id": "Q3",  "after": 5,  "kind": "current", "predicate": "affects_service", "expect": ["payments-api"],
     "tests": "memory persists across sessions"},
    {"id": "Q4",  "after": 5,  "kind": "stale", "predicate": "mitigation", "expect": ["raise-the-db-connection-pool-size"],
     "tests": "flags a conclusion whose basis was replaced", "depends_on_agents": true},
    {"id": "Q5",  "after": 6,  "kind": "current", "predicate": "mitigation", "expect": ["rollback-to-v2.3.0"],
     "tests": "an explicit 'ruled out' removes a belief", "depends_on_agents": true},
    {"id": "Q6",  "after": 7,  "kind": "current", "predicate": "root_cause", "expect": ["bad-deploy-v2.3.1"],
     "tests": "a newer claim from an untrusted source does not win"},
    {"id": "Q7",  "after": 7,  "kind": "current", "predicate": "status", "expect": ["mitigating"],
     "tests": "a prompt-injected 'resolved' does not win", "depends_on_agents": true},
    {"id": "Q8",  "after": 7,  "kind": "disputed", "predicate": "root_cause", "expect": ["ddos"],
     "tests": "contested claims are surfaced as unconfirmed, not dropped or believed"},
    {"id": "Q9",  "after": 8,  "kind": "current", "predicate": "root_cause", "expect": ["bad-deploy-v2.3.1"],
     "tests": "a hedged guess from a trusted source does not overwrite a belief"},
    {"id": "Q10", "after": 8,  "kind": "current", "predicate": "mitigation", "expect": ["rollback-to-v2.3.0", "flush-cache"],
     "tests": "current mitigations: no retracted, no untrusted", "depends_on_agents": true},
    {"id": "Q11", "after": 11, "kind": "current", "predicate": "mitigation", "expect": ["rollback-to-v2.3.0"],
     "tests": "revoking a source withdraws what it said", "depends_on_agents": true},
    {"id": "Q12", "after": 11, "kind": "current", "predicate": "root_cause", "expect": ["bad-deploy-v2.3.1"],
     "tests": "root cause after revocation"},
    {"id": "Q13", "after": 11, "kind": "from_source", "source": "webhook", "expect": ["flush-cache", "redis-outage"],
     "tests": "audit: what did the compromised source contribute, after revocation"},
    {"id": "Q14", "after": 11, "kind": "at", "predicate": "mitigation", "time": "2026-10-17T13:55:00+05:30",
     "expect": ["rollback-to-v2.3.0", "flush-cache"], "tests": "time travel: mitigations believed at 13:55",
     "depends_on_agents": true},
    {"id": "Q15", "after": 11, "kind": "at", "predicate": "root_cause", "time": "2026-10-17T10:30:00+05:30",
     "expect": ["db-pool-exhaustion"], "tests": "time travel: the morning's belief, from the afternoon"},
    {"id": "Q16", "after": 11, "kind": "at", "predicate": "root_cause", "time": "2026-10-17T13:55:00+05:30",
     "expect": ["bad-deploy-v2.3.1"], "tests": "time travel must not show claims that were never believed"}
  ]
}
```

### `memledger/evaluate.py`
```python
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
```

### `scripts/eval.py`
```python
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
```

### `tests/test_eval.py`
```python
"""Scenario evaluation (EVL.md)."""
import json

import pytest

from memledger import evaluate as E
from memledger import scenario as S
from memledger import trust
from memledger.agents import team as team_mod
from memledger.agents import tools as tools_mod
from memledger.extract import Extractor
from memledger import queries as Q
from scripts import eval as cli

# The SCN.md §12 patch fixes time travel for claims that were never believed.
PATCHED = "revoked_from" in Q.REVOKE
LEDGER = 16 if PATCHED else 15


def rehearsal():
    sc = S.load("acme")
    return Extractor(S.GoldenLLM(sc), mode="live", model_name="golden"), S.OfflineChat()


@pytest.fixture(scope="module")
def result(tmp_path_factory, lite_server):
    from memledger import db
    db._db = lite_server
    for name in lite_server.list_graphs():
        lite_server.select_graph(name).delete()
    ex, llm = rehearsal()
    return E.run(ex, llm, "acme", state_path=tmp_path_factory.mktemp("e") / "s.json")


def by_id(res, qid):
    return next(r for r in res["rows"] if r["id"] == qid)


def test_scores(result):
    s = result["score"]
    assert result["questions"] == 16
    assert s == {"No shared memory (per-session log)": 4, "Shared log, last write wins": 5,
                 "Shared log + trust filter + delete on revoke": 8, "MemLedger": LEDGER}


def test_memledger_misses_at_most_q16(result):
    wrong = [r["id"] for r in result["rows"] if not r["correct"]["MemLedger"]]
    assert wrong == ([] if PATCHED else ["Q16"])
    if not PATCHED:
        assert by_id(result, "Q16")["answers"]["MemLedger"] == ["bad-deploy-v2.3.1", "redis-outage"]


@pytest.mark.xfail(not PATCHED, strict=True, reason="needs the as_of patch in SCN.md section 12")
def test_q16_after_patch(result):
    assert by_id(result, "Q16")["correct"]["MemLedger"]


def test_traps_catch_the_baselines(result):
    lww = "Shared log, last write wins"
    assert by_id(result, "Q6")["answers"][lww] == ["ddos"]                # untrusted poison wins
    assert by_id(result, "Q7")["answers"][lww] == ["resolved"]            # injection wins
    assert by_id(result, "Q9")["answers"]["Shared log + trust filter + delete on revoke"] == ["redis-outage"]
    assert by_id(result, "Q13")["answers"]["Shared log + trust filter + delete on revoke"] == []
    assert all(r["step_ok"] for r in result["rows"])


def test_stream_was_recorded_and_hooks_restored(result):
    assert result["revocations"] and result["revocations"][0][1] == "webhook"
    sources = {c["source"] for c in result["claims"]}
    assert {"alerts", "app-logs", "runbook", "fwd-logs", "webhook", "reasoning"} <= sources
    assert any(c["certainty"] == "ruled_out" for c in result["claims"])
    from memledger.ingest import ingest
    assert team_mod.ingest is ingest and tools_mod.ingest is ingest
    assert trust.revoke_source.__name__ == "revoke_source"


def test_table(result):
    md = E.table(result)
    assert md.splitlines()[0].startswith("| Q | Tests |") and f"**{LEDGER}/16**" in md


def claim(t, session, source, pred, value, cert="stated"):
    return E.Claim(t, session, source, "x", pred, value, cert)


def test_log_baseline_semantics():
    st = E.Stream(claims=[
        claim(1, "s1", "alerts", "root_cause", "a"),
        claim(2, "s2", "fwd-logs", "root_cause", "b"),
        claim(3, "s2", "webhook", "mitigation", "m1"),
        claim(4, "s2", "runbook", "mitigation", "m2"),
        claim(5, "s2", "runbook", "mitigation", "m1", "ruled_out"),
    ], revocations=[(6, "webhook")])
    tr = {"alerts": 0.9, "fwd-logs": 0.3, "webhook": 0.6, "runbook": 0.9}
    a, b, c = E.baselines(st, tr)
    cur = {"kind": "current", "predicate": "root_cause"}
    mit = {"kind": "current", "predicate": "mitigation"}
    assert b.answer(cur, 10, "s2") == {"b"}                 # newest wins
    assert c.answer(cur, 10, "s2") == {"a"}                 # untrusted filtered
    assert a.answer(cur, 10, "s1") == {"a"} and a.answer(cur, 10, "s2") == {"b"}
    assert b.answer(mit, 10, "s2") == {"m1", "m2"}          # ruled_out ignored, multi accumulates
    assert c.answer(mit, 10, "s2") == {"m2"}                # revoked source deleted
    assert c.answer(mit, 5, "s2") == {"m1", "m2"}           # before the revocation
    assert b.answer({"kind": "at", "predicate": "root_cause", "time": "1970-01-01T00:00:00.001+00:00"},
                    10, "s2") == {"a"}
    assert b.answer({"kind": "from_source", "source": "webhook"}, 10, "s2") == {"m1"}
    assert b.answer({"kind": "stale", "predicate": "mitigation"}, 10, "s2") == set()


def test_cli_writes_results(tmp_path, capsys):
    out = str(tmp_path / "res")
    assert cli.main(["--extract", "golden", "--agents", "offline", "--out", out]) == 0
    assert f"**{LEDGER}/16**" in capsys.readouterr().out
    data = json.loads(open(out + ".json").read())
    assert data["score"]["MemLedger"] == LEDGER and open(out + ".md").read().startswith("Mode:")
```
