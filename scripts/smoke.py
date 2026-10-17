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
