"""Operator CLI for trust and revocation.

    python scripts/trust.py sources   [--tenant acme]
    python scripts/trust.py quarantine
    python scripts/trust.py preview   webhook
    python scripts/trust.py revoke    webhook --yes
    python scripts/trust.py promote   f-1a2b3c4d
    python scripts/trust.py set-trust app-logs 0.4
"""
import argparse
import sys
import time

from memledger import trust


def now_ms() -> int:
    return int(time.time() * 1000)


def show_radius(r):
    print(f"{len(r['facts'])} fact(s) depend on {r['source']}: "
          f"{r['direct']} direct, {r['derived']} derived; by agent {r['by_agent']}")
    for f in r["facts"]:
        print(f"  {f['id']:12} hops={f['hops']} {f['status']:11} {f['writer'] or '-':13} "
              f"{f['predicate']} = {f['object']}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sources", "quarantine", "preview", "revoke", "promote", "set-trust"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("value", nargs="?", type=float)
    ap.add_argument("--tenant", default="acme")
    ap.add_argument("--yes", action="store_true", help="confirm revoke")
    a = ap.parse_args(argv)
    t = a.tenant

    if a.cmd == "sources":
        for s in trust.trust_table(t):
            flag = "COMPROMISED" if s["compromised"] else ("trusted" if s["trusted"] else "untrusted")
            print(f"{s['id']:10} {s['kind']:12} trust={s['trust']:.2f} {flag:11} "
                  f"active={s['active']} quarantined={s['quarantined']} revoked={s['revoked']}")
    elif a.cmd == "quarantine":
        for q in trust.quarantine(t):
            d = f" disputes {q['disputes']['believed']}" if q["disputes"] else ""
            print(f"{q['id']:12} {q['predicate']} = {q['object']} from {q['sources']}{d}")
    elif a.cmd == "preview":
        show_radius(trust.blast_radius(t, a.arg))
    elif a.cmd == "revoke":
        if not a.yes:
            show_radius(trust.blast_radius(t, a.arg))
            print("Dry run. Add --yes to revoke.")
            return 1
        r = trust.revoke_source(t, a.arg, now_ms())
        print(f"Revoked {len(r['revoked'])} fact(s) from {a.arg}: {r['revoked']}")
        for s in r["stale"]:
            print(f"  stale: {s['id']} {s['predicate']} = {s['object']} (based on {s['based_on_value']})")
    elif a.cmd == "promote":
        print(trust.promote(t, a.arg, now_ms()))
    elif a.cmd == "set-trust":
        print(trust.set_trust(t, a.arg, a.value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
