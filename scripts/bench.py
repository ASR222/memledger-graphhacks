"""Concurrency benchmark: many readers, parallel writers across tenants.

    python scripts/bench.py                                  # against FALKORDB_HOST/PORT
    python scripts/bench.py --embedded                       # no Docker: embedded FalkorDB on TCP
    python scripts/bench.py --tenants 4 --readers 20 --writers 2 --seconds 10
    python scripts/bench.py --processes --same-tenant        # the multi-process experiment (TEN.md §5)

Writes go through memory.write_fact (the real rules: trust, quarantine,
supersession), reads through the same functions agents and the API use.
After the run it checks invariant I1 (one active value per single-valued
field) and cross-tenant leakage. Tenants are named bench0, bench1, ... and
are deleted and recreated at the start of every run.
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memledger import db, memory, tenancy  # noqa: E402

VALUES = {
    "severity": ["sev1", "sev2", "sev3", "sev4"],
    "status": ["investigating", "identified", "mitigating", "monitoring"],
    "root_cause": ["bad-deploy", "db-pool", "cache-miss", "dns"],
    "mitigation": ["rollback", "scale-up", "flush-cache", "failover", "rate-limit"],
}
SOURCES = ["alerts", "runbook", "app-logs", "fwd-logs"]       # last one is untrusted


def subject(i: int) -> str:
    return f"inc-{i}"


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def write_once(tenant: str, subj: str, rnd: random.Random) -> None:
    src = rnd.choice(SOURCES)
    pred = rnd.choice(list(VALUES))
    ep = memory.log_episode(tenant, agent="investigator", source=src, session="bench",
                            text=f"{pred} {src}", now=now_ms())
    memory.write_fact(tenant, agent="investigator", source=src, episode=ep, subject=subj,
                      predicate=pred, object=rnd.choice(VALUES[pred]), now=now_ms())


def read_once(tenants: list[str], rnd: random.Random) -> str:
    i = rnd.randrange(len(tenants))
    op = rnd.choice(["read_active", "all_active", "as_of", "disputes"])
    t = tenants[i]
    if op == "read_active":
        memory.read_active(t, subject(i))
    elif op == "all_active":
        memory.all_active(t)
    elif op == "as_of":
        memory.as_of(t, now_ms())
    else:
        memory.disputes(t)
    return op


def _writer_loop(tenant, subj, seconds, seed, out, errors):
    rnd = random.Random(seed)
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        try:
            write_once(tenant, subj, rnd)
            out.append((time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001 - recorded and reported
            errors.append(f"write {tenant}: {e}")


def _writer_process(tenant, subj, seconds, seed, q):
    lat, err = [], []
    _writer_loop(tenant, subj, seconds, seed, lat, err)
    q.put((lat, err))


def _reader_loop(tenants, seconds, seed, out, errors):
    rnd = random.Random(seed)
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        try:
            read_once(tenants, rnd)
            out.append((time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            errors.append(f"read: {e}")


def pct(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    xs = sorted(xs)
    q = statistics.quantiles(xs, n=100, method="inclusive") if len(xs) > 1 else [xs[0]] * 99
    return {"n": len(xs), "p50": round(q[49], 2), "p95": round(q[94], 2),
            "p99": round(q[98], 2), "max": round(xs[-1], 2)}


def server_version() -> str:
    try:
        for m in db.get_db().connection.execute_command("MODULE", "LIST"):
            d = m if isinstance(m, dict) else dict(zip(m[::2], m[1::2]))
            d = {(k.decode() if isinstance(k, bytes) else k): v for k, v in d.items()}
            name = d.get("name")
            if name in (b"graph", "graph"):
                v = int(d["ver"])
                return f"FalkorDB module {v // 10000}.{v // 100 % 100}.{v % 100}"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def run(tenants=4, readers=20, writers=2, seconds=10.0, processes=False, same_tenant=False,
        seed=7) -> dict:
    names = [f"bench{i}" for i in range(tenants)]
    for t in names:
        tenancy.forget(t)
        tenancy.create(t)

    w_lat, r_lat, errors = [], [], []
    threads, procs = [], []
    q = mp.get_context("spawn").Queue() if processes else None
    for i, t in enumerate(names):
        if same_tenant and i > 0:
            break
        for w in range(writers * (tenants if same_tenant else 1)):
            args = (t, subject(i), seconds, seed * 1000 + i * 10 + w)
            if processes:
                p = mp.get_context("spawn").Process(target=_writer_process, args=(*args, q))
                procs.append(p)
            else:
                threads.append(threading.Thread(target=_writer_loop, args=(*args, w_lat, errors)))
    for r in range(readers):
        threads.append(threading.Thread(target=_reader_loop,
                                        args=(names, seconds, seed + r, r_lat, errors)))
    t0 = time.perf_counter()
    for p in procs:
        p.start()
    for th in threads:
        th.start()
    for _ in procs:
        lat, err = q.get()
        w_lat += lat
        errors += err
    for p in procs:
        p.join()
    for th in threads:
        th.join()
    wall = time.perf_counter() - t0

    i1 = {t: tenancy.i1_violations(t) for t in names}
    leaks = [(a, b) for i, a in enumerate(names) for j, b in enumerate(names)
             if i != j and memory.read_active(b, subject(i))]
    return {
        "server": server_version(),
        "config": {"tenants": tenants, "readers": readers, "writers_per_tenant": writers,
                   "seconds": seconds, "writers_as": "processes" if processes else "threads",
                   "same_tenant": same_tenant},
        "wall_s": round(wall, 2),
        "writes": {**pct(w_lat), "per_s": round(len(w_lat) / wall, 1)},
        "reads": {**pct(r_lat), "per_s": round(len(r_lat) / wall, 1)},
        "errors": len(errors), "error_samples": errors[:5],
        "i1_violations": {t: v for t, v in i1.items() if v},
        "cross_tenant_leaks": leaks,
        "facts": {t: tenancy.stats(t)["facts"] for t in names},
    }


def start_embedded() -> object:
    """Embedded FalkorDB on a free TCP port; sets FALKORDB_HOST/PORT for child processes."""
    import socket

    from redislite.falkordb_client import FalkorDB as Lite

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    lite = Lite(os.path.join(tempfile.mkdtemp(), "bench.db"), serverconfig={"port": str(port)})
    os.environ["FALKORDB_HOST"], os.environ["FALKORDB_PORT"] = "127.0.0.1", str(port)
    from memledger import config
    config.HOST, config.PORT = "127.0.0.1", port
    db._db = lite
    return lite


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenants", type=int, default=4)
    ap.add_argument("--readers", type=int, default=20)
    ap.add_argument("--writers", type=int, default=2, help="writers per tenant")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--processes", action="store_true", help="writers as separate processes")
    ap.add_argument("--same-tenant", action="store_true", help="all writers on one tenant")
    ap.add_argument("--embedded", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    lite = start_embedded() if a.embedded else None
    try:
        res = run(a.tenants, a.readers, a.writers, a.seconds, a.processes, a.same_tenant)
    finally:
        if lite is not None:
            lite.close()
    if a.json:
        print(json.dumps(res, indent=1))
        return 0
    c = res["config"]
    print(f"{res['server']} · {c['tenants']} tenants · {c['readers']} readers · "
          f"{c['writers_per_tenant']} writer(s)/tenant as {c['writers_as']}"
          f"{' on ONE tenant' if c['same_tenant'] else ''} · {res['wall_s']} s")
    for k in ("writes", "reads"):
        r = res[k]
        print(f"  {k:6} n={r.get('n', 0):>6}  {r.get('per_s', 0):>8}/s   p50 {r.get('p50', '-')} ms"
              f"   p95 {r.get('p95', '-')} ms   p99 {r.get('p99', '-')} ms   max {r.get('max', '-')} ms")
    print(f"  errors: {res['errors']}  {res['error_samples'][:2]}")
    print(f"  I1 violations: {res['i1_violations'] or 'none'}")
    print(f"  cross-tenant leaks: {res['cross_tenant_leaks'] or 'none'}")
    return 0 if not res["errors"] and not res["cross_tenant_leaks"] else 1


if __name__ == "__main__":
    sys.exit(main())
