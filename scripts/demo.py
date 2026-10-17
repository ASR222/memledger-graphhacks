"""Scripted demo: replay the incident story one step at a time.

    python scripts/demo.py --list                       # show the steps
    python scripts/demo.py --reset                      # wipe and seed the tenant
    python scripts/demo.py --step 1                     # run the next step
    python scripts/demo.py --until 9                    # run up to step 9
    python scripts/demo.py --all                        # run everything left
    python scripts/demo.py --tenant globex --reset --all

Modes:
    --extract live | cache | golden    default: cache (EXTRACT_MODE=cache_only)
    --agents  live | offline           default: live (Gemini)

    Rehearsal without a key:  --extract golden --agents offline
    First real run:           --extract live --agents live      (fills the cache)
    Recording:                --extract cache --agents live
Exit code 1 if any hard check fails.
"""
import argparse
import json
import sys
from datetime import datetime

from memledger import config
from memledger.extract import Extractor, GeminiLLM
from memledger.scenario import GoldenLLM, OfflineChat, Runner, ScenarioError, load


def make(sc, extract, agents):
    if extract == "golden":
        ex = Extractor(GoldenLLM(sc), mode="live", model_name="golden")
    elif extract == "live":
        ex = Extractor(GeminiLLM(), cache_path=config.EXTRACT_CACHE, mode="live")
    else:
        ex = Extractor(None, cache_path=config.EXTRACT_CACHE, mode="cache_only",
                       model_name=config.GEMINI_MODEL)
    if agents == "offline":
        llm = OfflineChat()
    else:
        from memledger.agents.llm import GeminiChat
        llm = GeminiChat()
    return ex, llm


def hhmm(iso):
    return datetime.fromisoformat(iso).strftime("%H:%M")


def show(r):
    head = f"\n━━ Step {r.n} · {r.session} · {hhmm(r.at)} · {r.action}"
    o = r.output
    if r.action == "observe":
        head += f" ({o['agent']})"
    print(head)
    if r.say:
        print(f"   {r.say}")
    if r.action == "observe":
        for s in o["stored"]:
            extra = f", replaced {s['replaced']}" if s["replaced"] else ""
            extra += ", disputed" if s["disputes"] else ""
            print(f"   + {s['predicate']} = {s['value']}  [{s['status']}{extra}]")
        for t in o["retracted"]:
            print(f"   - ruled out {t['predicate']} = {t['value']}")
        for d in o["dropped"]:
            print(f"   · dropped {d['predicate']}: {d['reason']}")
    elif r.action in ("status_update", "ask", "investigate"):
        print("   tools: " + ", ".join(o.get("tools", [])))
        for line in (o.get("text") or "").splitlines():
            print(f"   │ {line}")
        if "citations" in o:
            print(f"   citations: {json.dumps(o['citations'])}")
    elif r.action in ("preview", "revoke"):
        print(f"   {len(o['facts'])} fact(s): {o['direct']} direct, {o['derived']} derived; {o['by_agent']}")
        for f in o["facts"]:
            print(f"   ✗ {f['predicate']} = {f['object']}  ({f['writer']}, {f['status']})")
    elif r.action == "as_of":
        print(f"   believed at {hhmm(o['time'])}:")
        for f in o["facts"]:
            print(f"   · {f['predicate']} = {f['object']}")
    elif r.action == "isolation":
        if not o["other_exists"]:
            print(f"   {o['other']} has no graph yet: run its scenario first to make this beat meaningful")
        print(f"   {o['other']} sees none of this incident; this tenant sees none of {o['other_subject']}")
    for c in r.checks:
        mark = "✓" if c["ok"] else ("~" if c["soft"] else "✗")
        print(f"   {mark} {c['check']}" + ("  (soft: depends on the live model)" if c["soft"] and not c["ok"] else ""))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="acme")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--step", type=int)
    ap.add_argument("--until", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="run --step out of order")
    ap.add_argument("--extract", choices=["live", "cache", "golden"], default="cache")
    ap.add_argument("--agents", choices=["live", "offline"], default="live")
    ap.add_argument("--state", help="progress file (default data/.demo_state.json)")
    a = ap.parse_args(argv)

    sc = load(a.tenant)
    if a.list:
        print(f"{sc['subject']}: {sc['title']} ({a.tenant})")
        for st in sc["steps"]:
            print(f"  {st['n']:>2}. {st['session']} {hhmm(st['at'])} {st['action']:<13} {st.get('say', '')}")
        return 0
    ex, llm = make(sc, a.extract, a.agents)
    runner = Runner(sc, ex, llm, state_path=a.state)
    if a.reset:
        runner.reset()
        print(f"Reset {a.tenant}: empty graph, sources and agents seeded.")
    try:
        if a.step:
            results = [runner.run_step(a.step, force=a.force)]
        elif a.until:
            results = runner.run_until(a.until)
        elif a.all:
            results = runner.run_until(len(sc["steps"]))
        else:
            results = []
    except ScenarioError as e:
        print(f"Error: {e}")
        return 2
    for r in results:
        show(r)
    failed = [r.n for r in results if not r.ok]
    if results:
        warn = sum(len(r.warnings) for r in results)
        print(f"\n{len(results)} step(s) run; hard checks {'FAILED at ' + str(failed) if failed else 'all passed'}"
              f"; {warn} soft warning(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
