# SUB.md — MemLedger Submission

Everything needed to submit: the rules checklist, **what you need to do yourself so the project isn't rejected under rule 13**, the README and AI-disclosure drafts, a 3-minute video script, judge Q&A prep, and a Sunday timeline. Covers workstream SUB on the build board (SUB-1 to SUB-7).

**Status (17 Oct 2026):**
- `README.md` and `AI_DISCLOSURE.md` drafts are delivered alongside this file. The README's Cypher section is generated from `queries.py` (all 35 queries) and both Mermaid diagrams were rendered with the official Mermaid CLI to check they draw correctly.
- The suite is **150 passed, 1 skipped, 3 expected failures** (2 new README tests, one an expected failure that's your task C1).
- The rules below were re-read from the official page on 17 Oct.

**This file is additive.** It adds `scripts/readme_queries.py`, `tests/test_readme.py`, and the two drafts. No earlier doc or code changes.

**Deadline: Sun 18 Oct, 11:59 PM IST.** Aim to submit by 10 PM.

---

## 0. Read this first: rules 11–13

From the official rules page (17 Oct):

> **11.** "AI coding assistants are allowed, but their use must be disclosed."
> **12.** "Participants must understand the submitted code and be able to explain the graph model, the queries, the project architecture, and the technical decisions behind them."
> **13.** "Projects that are entirely generated using AI without meaningful participant contribution, verification, or technical understanding may be rejected."

**Straight assessment.** Almost all of the code and every design doc in this project was written by me (Claude) in this conversation. Your contributions so far are real but thin in code terms: choosing the track and scope, directing each workstream, and the decisions you've made along the way. As things stand, a strict judge could read rule 13 against you. Here's how to fix that honestly between now and submission:

1. **Contribute.** Do the tasks in §2 yourself. They're real engineering, not busywork: verifying with live models, applying fixes, a scenario change, deployment.
2. **Verify.** Run everything yourself with live Gemini and real FalkorDB, and fix what breaks. That's the "verification" rule 13 names, and live runs will surface things my sandbox couldn't.
3. **Understand.** Work through §3 until you can answer without notes.
4. **Disclose accurately** (§5). Don't understate what the AI did. A judge who asks two questions and finds the disclosure was misleading is a much worse outcome than an honest "AI wrote most of it; here's what I did and verified, and I can explain all of it."
5. **Commit as you go.** Small commits with honest messages show the progression. Don't squash everything into one commit, and don't backdate anything.

---

## 1. Submission requirements (rule 10) → where they are

| Requirement (verbatim) | Where | Status |
|---|---|---|
| "A public source-code repository" | GitHub, public | TODO: create, push, make public |
| "A README with setup instructions and your graph data model" | `README.md` (draft) | fill the TODO(you) lines |
| "The Cypher queries or graph algorithms the product depends on" | README → Cypher queries (generated) | done; rerun the generator after any query change |
| "A demo video showing the working project" | §6 script | TODO: record, upload, link |
| "A live deployment, or complete local setup instructions if it cannot be deployed" | DEP.md; README → Run it locally | TODO: deploy, link |
| "The track you are entering" | submission form + README header | **Track 02: Agent Memory and Coordination** |

Also from the rules:
- **Team:** solo is fine; one team per person.
- **FalkorDB** must be primary and central. ✓ "A visualisation drawn on top of ordinary storage does not qualify" doesn't apply: the console draws the actual graph.
- **Data:** public, synthetic or your own. ✓ All scenario data is synthetic. Don't load anything else.
- **Timing:** "main coding and design work must begin after the hackathon starts". ✓ Everything here was written on 16–17 Oct, after the 15 Oct start. Cortex AI code was not reused.

---

## 2. Your contribution plan

Do these yourself, in this order. Commit after each one.

| # | Task | Time | Why it counts |
|---|---|---|---|
| **C1** | Move the inline Cypher in `memledger/agents/team.py` (`Team.route`: `MATCH (s:Source {id:$id}) RETURN s.kind`) into `queries.py` as `SOURCE_KIND`. Then rerun `python scripts/readme_queries.py README.md` and delete the `xfail` line on `test_no_cypher_outside_queries_py` (strict mode makes it fail until you do). | 15 min | a real violation of the project's own rule; you fix it |
| **C2** | Decide on the three Mem.md patches and apply them yourself: **seed reset + time travel** (SCN.md §12, three query edits) and **cross-process lock** (TEN.md §5 diff). Read each diff, apply, run `pytest -q`, explain the change in your commit message. The eval and time-travel tests detect the patch and flip on their own. | 30–45 min | your technical decision, verified by you |
| **C3** | **Live run.** `scripts/try_extract.py` with your key; fix any value spellings with `config.ALIASES` or the scenario expectations; then `scripts/demo.py --extract live --agents live --reset --all` for globex and acme. Note every ✗ and ~, fix what's yours to fix, commit `data/.extract_cache.json`. | 1–2 h | rule 13's "verification"; nothing in my sandbox touched live Gemini |
| **C4** | **Make the revoke cascade cross-agent** (SCN.md §9). Add a scenario step between 8 and 9 where the Investigator concludes a new owner from the flush-cache mitigation (`investigate` with an `offline_conclusion` like `"Owner: cache team."` citing it), update expectations, and confirm the blast radius now spans two agents. You'll need a small `OfflineChat` change to cite the mitigation instead of the root cause; that's the interesting part. | 45–60 min | a feature change you design and test |
| **C5** | **Deploy** (DEP.md) and run `scripts/smoke.py <url> --full`. Fix whatever the real image build or Cloud Run throws at you. | 1 h | real-world verification |
| **C6** | **Benchmark on real FalkorDB** (Docker 6.x or Cloud): `scripts/bench.py`. Put your numbers in the README with the setup line. | 15 min | replaces my sandbox numbers with yours |
| **C7** | **Write in your own words:** the README intro paragraph, the "What I did" and "Verification" sections of `AI_DISCLOSURE.md`, and the video voice-over. | 45 min | the parts judges read first |
| **C8** | **Rehearse §3** out loud until you don't need notes. | 45 min | rule 12 |

If you're short on time: C1, C2, C3, C5, C7 and C8 are the minimum. C4 and C6 are what make it clearly yours.

---

## 3. Explain it yourself (rule 12)

### 3.1 Five queries to know by heart

For each, say what it matches, what it changes, and why it needs a graph. The full text is in the README.

1. **`WRITE_FACT`:** creates the fact and its provenance edges. For single-valued predicates, an active write closes the current belief and links `SUPERSEDES`; a quarantined one only adds `CONFLICTS_WITH`. Why `OPTIONAL MATCH` + `FOREACH` (Mem.md §8.1).
2. **`REVOKE`:** walks back from the source along `FROM_SOURCE|DERIVED_FROM*1..6`, revokes every active or quarantined fact found, and marks the source compromised. Why 6 hops; why episodes are on the path.
3. **`AS_OF`:** validity-window filter. Know what the patch adds (`promoted_at`, `revoked_from`) and why.
4. **`STALE`:** active facts derived from a closed one. Why closing doesn't cascade but revoking does.
5. **`BLAST_RADIUS`:** the same traversal as `REVOKE`, read-only, plus `direct` = "the source itself asserted it".

**Self-quiz (answer without looking):**
1. What does `$single` change in `WRITE_FACT`?
2. A conclusion was written from the `reasoning` source, not the webhook. Why is it still revoked when the webhook is?
3. Why does a quarantined write never close an active fact?
4. Which index makes the contradiction check fast?
5. What would break if `READ_ACTIVE` didn't filter on status?

### 3.2 Questions judges are likely to ask

| Question | Short answer |
|---|---|
| Why a graph and not a vector store? | Revocation, provenance, supersession and disputes are traversals and edges. A vector store can find similar text; it can't tell you everything concluded from a source, or what replaced what. The eval shows a log-based memory believing an injected "resolved". |
| Isn't this Graphiti or Zep? | Graphiti has temporal invalidation, and we borrowed that idea. It doesn't track which agent wrote a fact, trust-based quarantine, disputes, cross-agent revocation through derivations, or role permissions. We wrote our own model so the graph and queries are ours to explain. |
| How does revocation work? | The `REVOKE` traversal (§3.1). Facts reach the source directly, through the episode they were extracted from, or through parent facts. |
| What if a trusted source said the same thing? | Taint semantics: anything touched by a compromised source is withdrawn, and the trusted source can re-assert it as a fresh fact. Untrusted echoes are ignored, so junk can't be used to delete true facts. |
| How do you stop hallucinated facts? | Every claim must quote its evidence verbatim; code checks it against the text and drops the claim otherwise. |
| Prompt injection? | We tested with a model that obeys the injection. Trust decides what becomes a belief: the claim from an untrusted source is quarantined, and "mark resolved" is dropped by role permissions. |
| How are conflicts resolved? | Structurally: same incident, same single-valued field, different value. The newest trusted, non-hedged write wins; otherwise it becomes a dispute. No LLM judge. |
| Is it bi-temporal? | No. Validity windows on one timeline. We don't separate record time from real-world time. |
| Concurrency? | FalkorDB serializes writes per graph; we serialize the check-then-write sequence per tenant. We found a race with multiple processes, measured it (~2% failed writes), and fixed it with a lock held in FalkorDB itself [if C2 applied]. The deployment runs one instance. |
| Does it scale? | Demo graphs are hundreds of nodes. Each tenant is its own graph. Benchmark: [your C6 numbers]. Not tested at millions of edges. |
| Is the evaluation fair? | It's a scorecard we designed around our features, not a benchmark. Extraction is held constant; baseline C is deliberately reasonable and beats MemLedger on one question before the fix. |
| Procedural memory? | Not built. Episodic (logged turns) and semantic (facts) are. |
| Which FalkorDB version? | Tests ran on embedded 4.18.3; the live URL uses [embedded / Cloud]; benchmark numbers from [C6]. |
| What did you build versus the AI? | [Your honest answer, matching AI_DISCLOSURE.md.] |
| What's next? | Support counting for revocation, procedural memory, auth, separating record time from real time. |

---

## 4. README (SUB-1, SUB-2, SUB-3)

`README.md` (delivered alongside) has:
- **Header** (track, links), the problem, what MemLedger does, **why the graph is necessary** (SUB-3);
- **Architecture** and **graph data model** as Mermaid diagrams, both checked by rendering;
- **Run it locally**: no-key embedded mode, Docker mode, demo CLI, tests, eval;
- the demo story, **evaluation** (rehearsal scores, honestly framed), concurrency and tenancy;
- **Cypher queries** (SUB-2): all 35, generated between `<!-- QUERIES:START -->` and `<!-- QUERIES:END -->`;
- deployment, limitations, credits.

**Your TODOs in it** (search `TODO(you)` and `YOU:`):
- live URL and which DB mode it uses;
- video link;
- your intro paragraph;
- repo URL in the clone command;
- live or final eval table (after C2/C3);
- your benchmark numbers (C6).

**Keep the query list in sync:** `python scripts/readme_queries.py README.md` after any change to `queries.py`. `tests/test_readme.py` fails if the README is stale.

---

## 5. AI_DISCLOSURE.md

`AI_DISCLOSURE.md` (delivered alongside) states plainly what the assistant did: research, all design docs, most of the code, tests and bug reports. It leaves **"What I did"** and **"Verification"** for you to fill truthfully. The commented examples are prompts, not claims. Delete anything that isn't true.

The README links it from the header, so judges see it immediately. **Keep the "Understanding" line only once it's true.**

---

## 6. Demo video (SUB-4): 3:00 script

**Setup:** console full screen at 1440p, browser zoom 110–125%; deployed URL (or local) with `extract: cache`, `agents: live` visible in the header; globex already run; acme Reset. Optional: Claude Desktop window ready. Record the voice-over separately if you can; it's easier to keep timing.

| Time | Screen | Say (adapt in your words) |
|---|---|---|
| 0:00–0:15 | eval table, the "resolved" row | "Most multi-agent memory is a shared log where the last write wins. In our test it told stakeholders the incident was resolved, because a forwarded email said so. MemLedger is a memory where every belief has a writer, a source, a validity window and a path." |
| 0:15–0:30 | console overview, legend | "Three agents share one memory graph in FalkorDB. Everything you see is a node in the database." |
| 0:30–0:55 | Next ×4 (steps 1–4) | "An alert, then logs blaming the DB pool. The investigator concludes a fix from that. Comms writes an update, and every claim cites a fact id." Click a citation chip. |
| 0:55–1:20 | steps 5–6 | "Session two: a new process with empty chats. The runbook corrects the root cause. The old one is closed, not overwritten, and the fix based on it is flagged as stale and ruled out." |
| 1:20–1:45 | steps 7–8 | "A forwarded message claims a DDoS and tries a prompt injection. Untrusted, so it's quarantined as a dispute, and 'mark resolved' is dropped because that agent can't set status. Then a trusted cache integration guesses Redis, 'possibly', so even that stays in quarantine. Its recommended cache flush is accepted." |
| 1:45–2:15 | steps 9–12 (preview ringed, revoke, update) | "The cache integration turns out to be compromised. Preview the blast radius, revoke, and one Cypher traversal withdraws everything it said. The next update drops the flush." |
| 2:15–2:35 | step 13 why panel; step 14 slider | "Why do we believe the root cause? Written by the investigator, from the runbook, replacing the DB pool. And at 13:55, this is what the team believed. History is kept." |
| 2:35–2:50 | Claude Desktop over MCP, *or* step 15 isolation | "Claude Desktop reads the same memory over MCP, with the same rules." *or* "A second customer's graph is completely separate." |
| 2:50–3:00 | scorecard / repo | "Fifteen of sixteen against eight for a log with the obvious fixes [or sixteen after C2]. MemLedger: memory you can audit and retract." |

**Rules for the take:**
- Rehearse twice.
- Don't narrate features the take doesn't show.
- If a live agent writes something unexpected, keep going or re-record that step; don't edit the text.
- Upload as unlisted or public, and **check the link works in a private window.**

---

## 7. Sunday timeline (IST)

| By | Do |
|---|---|
| Sat night | C1, C2, start C3 (live extraction check) |
| Sun 11:00 | C3 done, cache committed; C4 if time |
| Sun 14:00 | C5 deployed, smoke `--full` PASS; C6 benchmark. **Feature freeze** |
| Sun 17:00 | README and AI_DISCLOSURE filled (C7) |
| Sun 20:00 | video recorded and uploaded (§6); C8 rehearsed |
| Sun 21:30 | final checklist (§8) |
| **Sun 22:00** | **submit** (Track 02) |
| Sun 23:59 | hard deadline |

---

## 8. Final checklist

- [ ] Repo **public**; README renders on GitHub (diagrams draw)
- [ ] **No secrets in git history:** `git log -p | grep -i "GEMINI_API_KEY="` finds no real key; `.env` never committed
- [ ] `pytest -q` passes locally (and you know why each skip or expected failure is there)
- [ ] `python scripts/readme_queries.py README.md` run after the last query change
- [ ] Live URL opens; `smoke.py <url> --full` PASS; then **Reset** acme so judges start at step 0
- [ ] Video link opens in a private window
- [ ] `AI_DISCLOSURE.md` filled in truthfully
- [ ] No `TODO(you)` left: `grep -rn "TODO(you)" README.md AI_DISCLOSURE.md`
- [ ] Optionally add a `LICENSE` (MIT is common); the vendored force-graph is MIT
- [ ] Submission form: repo URL, video URL, live URL, **Track 02: Agent Memory and Coordination**

---

## 9. Blog post (SUB-7, stretch, after submitting)

The rules page doesn't mention the blog prize; check the event page for its rules before writing. Outline if you do:
1. The failure: a shared log believing an injected "resolved" (the eval row).
2. Memory as a ledger: writer, source, validity, path (the data model diagram).
3. Three queries: supersede, revoke, as-of, each in a few lines.
4. What surprised you during the build (your own experience: live-model issues, the races and bugs found).
5. The honest scorecard and what's next.

Write it yourself.

---

## 10. Tests

```bash
pytest -q        # 150 passed, 1 skipped, 3 xfailed  (before C1/C2)
```

| Test | Checks |
|---|---|
| `test_readme_lists_every_query` | every constant in `queries.py` is in the README block, and the block is exactly what the generator produces |
| `test_no_cypher_outside_queries_py` | **expected failure until C1**: no Cypher outside `queries.py`. Strict, so once you fix it the test fails until you remove the marker |

---

## 11. Source files (tested)

### `scripts/readme_queries.py`
```python
"""Render every Cypher query in memledger/queries.py into the README.

    python scripts/readme_queries.py README.md          # rewrite the block in place
    python scripts/readme_queries.py --print            # print the Markdown

The README must contain the markers
    <!-- QUERIES:START -->
    <!-- QUERIES:END -->
Everything between them is replaced, so the README always lists exactly the
queries the code runs (hackathon rule 10).
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- QUERIES:START -->", "<!-- QUERIES:END -->"


def queries() -> list[tuple[str, str, str]]:
    """(name, comment above it, Cypher) for every string or list constant, in file order."""
    src = (ROOT / "memledger" / "queries.py").read_text()
    lines = src.splitlines()
    out = []
    for node in ast.parse(src).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id.isupper()):
            continue
        value = ast.literal_eval(node.value)
        cypher = "\n".join(value) if isinstance(value, list) else value
        comment, i = [], node.lineno - 2
        while i >= 0 and lines[i].startswith("#") and not lines[i].startswith("# ---"):
            comment.insert(0, lines[i].lstrip("# ").rstrip())
            i -= 1
        out.append((node.targets[0].id, " ".join(comment), cypher.strip()))
    return out


def markdown() -> str:
    qs = queries()
    parts = [f"All {len(qs)} queries the product runs, generated from `memledger/queries.py`.\n"]
    for name, comment, cypher in qs:
        parts.append(f"#### `{name}`\n\n{comment or ''}\n\n```cypher\n{cypher}\n```\n")
    return "\n".join(parts)


def rewrite(readme: Path) -> int:
    text = readme.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"{readme} needs the markers {START} and {END}")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    readme.write_text(f"{head}{START}\n{markdown()}\n{END}{tail}")
    return len(queries())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "--print":
        print(f"wrote {rewrite(Path(sys.argv[1]))} queries into {sys.argv[1]}")
    else:
        print(markdown())
```

### `tests/test_readme.py`
```python
"""The README lists every query the product runs (SUB.md, hackathon rule 10)."""
import re
from pathlib import Path

import pytest

from scripts import readme_queries as rq

ROOT = Path(__file__).resolve().parents[1]


def test_readme_lists_every_query():
    text = (ROOT / "README.md").read_text()
    block = text.split(rq.START, 1)[1].split(rq.END, 1)[0]
    names = [n for n, _, _ in rq.queries()]
    assert len(names) >= 30
    missing = [n for n in names if f"#### `{n}`" not in block]
    assert missing == [], f"run: python scripts/readme_queries.py README.md  (missing {missing})"
    assert block.strip() == rq.markdown().strip(), "README queries are stale; rerun the generator"


@pytest.mark.xfail(strict=True, reason="SUB.md task C1: move the inline query in agents/team.py to queries.py")
def test_no_cypher_outside_queries_py():
    found = []
    for path in (ROOT / "memledger").rglob("*.py"):
        if path.name == "queries.py":
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\b(MATCH|MERGE|CREATE)\s*\(", line):
                found.append(f"{path.relative_to(ROOT)}:{i}")
    assert found == []
```

`README.md` and `AI_DISCLOSURE.md` are delivered as separate files.
