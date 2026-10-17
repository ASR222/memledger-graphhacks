# TEN.md — MemLedger Tenancy & Concurrency

Complete context for how MemLedger keeps customers apart and how it behaves under concurrent reads and writes: the tenancy model, tenant admin (create, stats, export, forget), a concurrency benchmark with invariant checks, the results, and a race that appears once writes come from more than one process. Covers workstream TEN on the build board (TEN-1 to TEN-4) and two Track 02 focus areas: *separate memory per user or tenant* and *high-concurrency reads and writes*.

**Status (17 Oct 2026):**
- Every file in section 10 was run. The full suite is **136 passed, 1 skipped, 1 expected failure**: the 130 from earlier docs plus 6 new tests. The skip is the official FalkorDB MCP test, which needs Node; the expected failure is the Mem.md bug from SCN.md §12.
- The benchmark was run several times (§4). **It found a real race when writers run in separate processes (§5).** A fix is tested but not applied.

**⚠ Engine version.** Every test and benchmark in these docs ran on **embedded FalkorDB 4.18.3** (the falkordblite package). `docker run falkordb/falkordb:latest` gives you **6.x**, which uses a different engine (MVCC: readers never block). The behavior tested here is ordinary Cypher and should carry over, but **rerun the benchmark against your Docker or Cloud instance before quoting any numbers.**

**This file is additive. It does not change any earlier doc.** It adds:

| File | Purpose |
|---|---|
| `memledger/queries.py` | **append** the block in §10.1 (3 read queries) |
| `memledger/tenancy.py` | tenant admin: names, exists, create, stats, i1_violations, export, forget |
| `scripts/bench.py` | concurrency benchmark with invariant and leak checks |
| `tests/test_tenants.py` | 6 tests |

---

## 1. Tenancy model (TEN-1)

**One tenant = one FalkorDB graph**, named `memory_<tenant>`. No query ever spans graphs, so isolation is physical rather than a `WHERE tenant = …` filter that one forgotten clause could break.

- **Tenant names** must match `^[a-z][a-z0-9_]{0,40}$`, checked in `db.graph()` before anything reaches FalkorDB. The graph name is the only part of any query built from a string; everything else is a parameter.
- **Fact ids are per tenant.** Two tenants can both have `f1`; they're different facts (`test_same_ids_in_two_tenants_are_independent`).
- **Every layer takes the tenant explicitly**: memory functions, ingest, agents (`AgentContext.tenant`), trust, the API path (`/api/{tenant}/…`) and every MCP tool argument.

### What is shared between tenants

| Shared | Why it's acceptable |
|---|---|
| The process, the Gemini client, the agent prompts | Code, not data |
| `data/.extract_cache.json` | Keyed by text + known values. A tenant only gets a cached extraction for text it submitted itself; it learns nothing about other tenants. Known values are per tenant and part of the key |
| `data/.demo_state.json` | One entry per tenant (step number only) |
| The per-tenant lock dictionary | One lock per tenant; tenants never wait for each other |

### Isolation is tested at every layer

| Layer | Test |
|---|---|
| Memory functions | `test_no_leak`, `test_revoke_is_tenant_scoped` (Mem.md) |
| Tenant names | `test_invalid_tenant` ×6 (Mem.md), `test_bad_tenants` (API.md) |
| Same ids, different tenants | `test_same_ids_in_two_tenants_are_independent` |
| Scenario | step 15 + `test_globex_story_and_isolation` (SCN.md) |
| API and MCP | `test_api_and_mcp_cannot_cross_tenants`: a fact id from acme gives 404 through `/api/globex/…` and an error through MCP |
| Under concurrent load | the benchmark's cross-tenant check (§4), every run |

---

## 2. Tenant admin (`memledger/tenancy.py`)

| Function | Returns | Notes |
|---|---|---|
| `names()` | tenant names | from the graph list |
| `exists(t)` | bool | validates the name |
| `create(t)` | `{tenant, created}` | **seeds only a new graph**, so it can't hit the seed bug (AGT.md §15) |
| `stats(t)` | `{nodes: {label: n}, facts: {status: n}}` | cheap count queries |
| `i1_violations(t)` | single-valued fields with more than one active value | must be `[]`; used by the benchmark |
| `export(t)` | every node and edge, JSON-able | data portability; raises `KeyError` if missing |
| `forget(t)` | `{deleted, ms, nodes}` | **deletes the whole graph, irreversibly** |

### Forgetting a tenant (TEN-4)

```python
from memledger import tenancy
tenancy.forget("globex")   # {'tenant': 'globex', 'deleted': True, 'ms': 2.1, 'nodes': 1279}
```

Measured: **about 2 ms to delete a tenant of ~1,270 nodes** (embedded 4.18.3; two runs: 2.1 ms and 1.6 ms). It's one `GRAPH.DELETE` because the tenant is its own graph. A shared-graph design would need to find and delete every node with that tenant's id, and could miss some. **Pitch:** "Right to be forgotten is one command, and it can't leave anything behind."

---

## 3. Concurrency model

| Layer | Behavior |
|---|---|
| FalkorDB | Writes to **one graph are serialized**; reads run concurrently (6.x: readers never block writers). Different graphs (tenants) are independent |
| `write_fact`, `retract`, `promote`, `revoke` | Several queries (check, then write). A **per-tenant `threading.Lock`** makes each sequence atomic **within one Python process** |
| Reads | No lock |
| API | One worker (API.md §5); FastAPI runs sync routes in a thread pool, so concurrent requests are threads in one process: covered by the lock |

**What to claim:** many concurrent readers; parallel writes across tenants; writes within a tenant serialized and race-free inside one process. **Don't claim** unlimited parallel writes to one tenant, or multi-process safety without the §5 patch.

---

## 4. Benchmark (TEN-3)

```bash
python scripts/bench.py                       # against FALKORDB_HOST/PORT (Docker, Cloud)
python scripts/bench.py --embedded            # no Docker: embedded FalkorDB on TCP
python scripts/bench.py --tenants 4 --readers 20 --writers 2 --seconds 10 --json
python scripts/bench.py --embedded --processes --same-tenant     # the race experiment (§5)
```

- **Writers** call `log_episode` + `write_fact` with a random source (one in four untrusted), predicate and value, so trust, quarantine, promotion, supersession and corroboration all run.
- **Readers** randomly call `read_active`, `all_active`, `as_of` or `disputes` on random tenants.
- **After each run** it checks invariant I1 (one active value per single-valued field) in every tenant and cross-tenant leakage (each tenant's incident looked up in every other tenant).
- Tenants `bench0…` are deleted and recreated at the start of every run. Exit code 1 on errors or leaks.

### Results (sandbox, embedded FalkorDB 4.18.3, client and server on one machine)

| Run | Writes/s | Write p50 / p95 / p99 | Reads/s | Read p50 / p95 / p99 | Errors | I1 | Leaks |
|---|---|---|---|---|---|---|---|
| 4 tenants, 20 reader threads, 2 writer threads per tenant | 214 | 35 / 59 / 73 ms | 3,264 | 5.2 / 13 / 19 ms | 0 | ok | none |
| 8 writer **processes** on **one** tenant (unpatched) | 392–405 | 14 / 33 / 52 ms | 3,400–3,600 | 3.6 / 11 / 23 ms | **81–82 (~2%)** | ok | none |
| same, **with the §5 patch** | 163–168 | 22 / 131–145 / 211–244 ms | 4,400 | 2.7 / 9 / 18 ms | **0** | ok | none |
| 4 tenants, threads, **with the §5 patch** | 152 | 47 / 95 / 124 ms | 3,130 | 5.1 / 15 / 24 ms | 0 | ok | none |

How to read these:
- **Latencies include the Python client.** 28 threads share one interpreter, so thread scheduling inflates the threaded numbers. The process runs show lower per-write latency for that reason, not because the database got faster.
- **Writes include the full rule pipeline** (3–5 queries each: source check, find-same, write, sometimes promote), not a single insert.
- **Reads stay fast while writes run.**
- **The patched multi-process run serializes eight writers on one tenant on purpose**, so its tail latency is waiting for the lock. That's the cost of correctness there.

FalkorDB's own blog (vendor figures, Oct 2026) reports sub-millisecond p99 reads at 1M edges with 20 concurrent agent writers on 6.x. Measure on your instance rather than quoting theirs.

---

## 5. The multi-process race

**What happens.** With writers in separate processes on the same tenant, about 2% of writes fail with `IndexError: list index out of range`. The per-tenant lock only exists inside one process. Two processes can both run `FIND_SAME`, both see the same quarantined claim, and both decide to promote it. The first `PROMOTE` succeeds; the second matches nothing, and `write_fact` indexes into an empty result.

**Reproducible:** two unpatched runs gave 82 and 81 errors. I1 held in every run (the duplicate-active case didn't occur), and no data leaked across tenants. But a failed write means a lost observation.

**When it matters.** Whenever more than one process writes to the same tenant:
- `uvicorn --workers 2` or more;
- **Cloud Run scaling to more than one instance** (it does under load unless capped);
- running `scripts/demo.py` while the API is also writing to the same tenant.

**For the hackathon:** keep one writer process. Run uvicorn with `--workers 1` and **set Cloud Run `--max-instances 1`** (note this for DEP). Then the in-process lock covers everything.

### The fix (tested in a copy, not applied)

Hold the lock on the FalkorDB server, which speaks the Redis protocol, using redis-py's `Lock` (`SET … NX PX`). It works across processes and machines, and expires after 30 s if a holder dies.

```diff
--- memledger/memory.py	2026-10-17 13:27:33.300803710 +0000
+++ memledger/memory.py	2026-10-17 13:29:35.059862460 +0000
@@ -7,10 +7,11 @@
 import threading
 import uuid
 from collections import defaultdict
+from contextlib import contextmanager
 
 from . import config
 from . import queries as Q
-from .db import graph
+from .db import get_db, graph
 
 # FalkorDB serializes writes per graph, but write_fact is several queries
 # (check, then write). This lock makes that sequence atomic per tenant within
@@ -18,6 +19,24 @@
 _locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
 
 
+LOCK_TTL_S = 30
+
+
+@contextmanager
+def _tenant_lock(tenant: str):
+    """Serialize check-then-write sequences for one tenant across threads AND
+    processes: a thread lock, plus a lock key on the FalkorDB server itself
+    (it speaks the Redis protocol). Expires after LOCK_TTL_S if a holder dies."""
+    conn = getattr(get_db(), "connection", None)
+    with _locks[tenant]:
+        if conn is None or not hasattr(conn, "lock"):
+            yield
+            return
+        with conn.lock(f"memledger:lock:{tenant}", timeout=LOCK_TTL_S, sleep=0.002,
+                       blocking_timeout=LOCK_TTL_S):
+            yield
+
+
 class MemoryError_(Exception):
     """Base error for memory-rule violations."""
 
@@ -91,7 +110,7 @@
     parents = list(parents)
     g = graph(tenant)
 
-    with _locks[tenant]:
+    with _tenant_lock(tenant):
         src = _rows(g.ro_query(Q.SOURCE_INFO, {"id": source}))
         if not src:
             raise UnknownReference(f"unknown source {source!r}")
@@ -153,7 +172,7 @@
     if predicate not in config.PREDICATES:
         raise ValueError(f"predicate {predicate!r} not in vocabulary")
     g = graph(tenant)
-    with _locks[tenant]:
+    with _tenant_lock(tenant):
         src = _rows(g.ro_query(Q.SOURCE_INFO, {"id": source}))
         if not src:
             raise UnknownReference(f"unknown source {source!r}")
@@ -168,7 +187,7 @@
 
 
 def promote(tenant, fact_id, now) -> dict:
-    with _locks[tenant]:
+    with _tenant_lock(tenant):
         rows = _rows(graph(tenant).query(Q.PROMOTE, {
             "id": fact_id, "now": now, "single_preds": sorted(config.SINGLE_VALUED)}))
     if not rows:
@@ -178,7 +197,7 @@
 
 def revoke(tenant, source, now) -> list[dict]:
     """Mark a source compromised and revoke everything that depends on it."""
-    with _locks[tenant]:
+    with _tenant_lock(tenant):
         g = graph(tenant)
         if not _rows(g.ro_query(Q.SOURCE_INFO, {"id": source})):
             raise UnknownReference(f"unknown source {source!r}")
```

Results with the patch: the multi-process race **dropped to 0 errors** in two runs, and the full current suite passed (136 passed, 1 skipped, 1 expected failure). The cost is **~30% lower single-process write throughput** (214 → 152 writes/s) from the extra round trips, plus lock-wait tail latency when many processes hit one tenant.

**Your call.** With one process, you don't need it. If you deploy with more than one instance or worker, apply it. Like the SCN.md §12 patch, it changes Mem.md's `memory.py`, so I haven't touched that file. Say the word and I'll fold both into Mem.md v3.

---

## 6. Deployment checklist (for DEP)

- [ ] `uvicorn memledger.api:app --workers 1`
- [ ] Cloud Run: `--max-instances 1` (or apply §5 and allow more)
- [ ] Create tenants with `tenancy.create` or the console's Reset, never by calling `schema.seed` on an existing graph
- [ ] Run `scripts/bench.py` against the deployed FalkorDB once; use those numbers in the README and video

---

## 7. Judge talking points

- "Every customer gets its own graph. Isolation isn't a filter we have to remember; it's a different graph, and we test it at every layer, including under load."
- "Forgetting a customer is one command: about 2 ms for a whole tenant, and nothing can be left behind."
- "Under 20 concurrent readers and parallel writers across four tenants we saw zero errors, zero leaks, and the one-belief-per-field invariant held. These are the numbers we measured, on our setup."
- "We also found where it breaks: separate processes writing to one tenant. We measured it, and we have a fix that holds the lock in FalkorDB itself."

---

## 8. Tests

```bash
pytest -q        # expect: 136 passed, 1 skipped, 1 xfailed
```

| Test | Checks |
|---|---|
| `test_create_is_idempotent_and_never_resets` | second create does nothing; a revoked source stays compromised |
| `test_stats_export_and_forget` | counts; export is JSON-able; forget removes the graph, leaves the other tenant, reports nodes and time; second forget is a no-op |
| `test_same_ids_in_two_tenants_are_independent` | same id, different facts; revoke in one tenant only |
| `test_i1_checker_catches_a_violation` | the checker finds a deliberately planted second active value |
| `test_api_and_mcp_cannot_cross_tenants` | acme's fact via globex: API 404, not in globex's graph view, MCP error |
| `test_concurrent_threads_keep_invariants` | a short benchmark run in-process: 0 errors, I1 holds, no leaks |

The multi-process race isn't a unit test, because it's probabilistic. `scripts/bench.py --processes --same-tenant` is the reproduction.

---

## 9. Known limits

- **Multi-process writes to one tenant** (§5) until the patch is applied.
- **No authentication per tenant.** Anyone who can reach the API can name any tenant (API.md §6).
- **Export has no import.** Restoring a tenant from an export isn't built.
- **`forget` has no confirmation step** in code. Don't expose it on a route without one.
- **Benchmark numbers are from embedded 4.18.3 in a sandbox.** Rerun on your setup.

---

## 10. Source files (tested)

### 10.1 Append to `memledger/queries.py`

Add at the end, after AGT.md's block.

```python
# ---------------------------------------------------------------- tenancy (TEN.md)

# Node counts by label.
LABEL_COUNTS = """
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY label
"""

# Fact counts by status.
FACT_STATUS_COUNTS = """
MATCH (f:Fact) RETURN f.status AS status, count(f) AS n ORDER BY status
"""

# Single-valued (subject, predicate) pairs with more than one active fact.
# Must always be empty (Mem.md invariant I1); used to check it under load.
I1_VIOLATIONS = """
MATCH (f:Fact {status:'active'})
WHERE f.predicate IN $single_preds
WITH f.subject AS subject, f.predicate AS predicate, collect(f.object) AS objects
WHERE size(objects) > 1
RETURN subject, predicate, objects
"""
```

### `memledger/tenancy.py`
```python
"""Tenant administration: one FalkorDB graph per tenant.

Isolation is physical: tenant `acme` lives in graph `memory_acme` and no
query ever spans graphs. This module creates, inspects, exports and forgets
tenants.
"""
import time

from . import config, schema
from . import queries as Q
from .db import get_db, graph
from .memory import _rows, snapshot


def names() -> list[str]:
    return sorted(g.removeprefix("memory_") for g in get_db().list_graphs() if g.startswith("memory_"))


def exists(tenant: str) -> bool:
    graph(tenant)                                       # validates the name
    return f"memory_{tenant}" in get_db().list_graphs()


def create(tenant: str) -> dict:
    """Create and seed a tenant. Does nothing if it already exists, so it can
    never reset an existing tenant's sources (see the seed bug in AGT.md §15)."""
    if exists(tenant):
        return {"tenant": tenant, "created": False}
    schema.seed(tenant)
    return {"tenant": tenant, "created": True}


def stats(tenant: str) -> dict:
    g = graph(tenant)
    return {"tenant": tenant,
            "nodes": {r["label"]: r["n"] for r in _rows(g.ro_query(Q.LABEL_COUNTS))},
            "facts": {r["status"]: r["n"] for r in _rows(g.ro_query(Q.FACT_STATUS_COUNTS))}}


def i1_violations(tenant: str) -> list[dict]:
    """Single-valued fields with more than one active value. Should be []."""
    return _rows(graph(tenant).ro_query(Q.I1_VIOLATIONS,
                                         {"single_preds": sorted(config.SINGLE_VALUED)}))


def export(tenant: str) -> dict:
    """Everything the tenant's memory holds, as JSON-able data."""
    if not exists(tenant):
        raise KeyError(tenant)
    return {"tenant": tenant, "exported_at": int(time.time() * 1000), **snapshot(tenant)}


def forget(tenant: str) -> dict:
    """Delete a tenant's whole memory. Irreversible. Returns how long it took."""
    if not exists(tenant):
        return {"tenant": tenant, "deleted": False, "ms": 0.0, "nodes": 0}
    n = sum(stats(tenant)["nodes"].values())
    t0 = time.perf_counter()
    graph(tenant).delete()
    return {"tenant": tenant, "deleted": True, "ms": round((time.perf_counter() - t0) * 1000, 3),
            "nodes": n}
```

### `scripts/bench.py`
```python
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
```

### `tests/test_tenants.py`
```python
"""Tenancy and concurrency (TEN.md)."""
import json

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.client.client import Client

from memledger import memory as m
from memledger import tenancy
from memledger.api import create_app
from memledger.mcp_server import mcp
from scripts import bench


def ep(t, i, now, src="alerts"):
    return m.log_episode(t, id=i, agent="triage", source=src, session="s1", text=i, now=now)


def test_create_is_idempotent_and_never_resets():
    assert tenancy.create("newco") == {"tenant": "newco", "created": True}
    m.revoke("newco", "webhook", 100)
    assert tenancy.create("newco") == {"tenant": "newco", "created": False}
    assert m.source_info("newco", "webhook")["compromised"] is True
    assert "newco" in tenancy.names()


def test_stats_export_and_forget():
    ep("acme", "e1", 100)
    m.write_fact("acme", id="f1", agent="triage", source="alerts", episode="e1",
                 subject="INC-42", predicate="severity", object="sev1", now=101)
    st = tenancy.stats("acme")
    assert st["nodes"]["Agent"] == 3 and st["nodes"]["Fact"] == 1 and st["facts"] == {"active": 1}
    dump = tenancy.export("acme")
    json.dumps(dump)
    assert any(n["label"] == "Fact" for n in dump["nodes"])
    gone = tenancy.forget("acme")
    assert gone["deleted"] and gone["nodes"] >= 10 and gone["ms"] >= 0
    assert not tenancy.exists("acme") and m.all_active("globex") == []
    assert tenancy.forget("acme") == {"tenant": "acme", "deleted": False, "ms": 0.0, "nodes": 0}
    with pytest.raises(KeyError):
        tenancy.export("acme")


def test_same_ids_in_two_tenants_are_independent():
    for t, v in (("acme", "sev1"), ("globex", "sev3")):
        ep(t, "e1", 100)
        m.write_fact(t, id="f1", agent="triage", source="alerts", episode="e1",
                     subject="INC-1", predicate="severity", object=v, now=101)
    assert m.why("acme", "f1")["object"] == "sev1" and m.why("globex", "f1")["object"] == "sev3"
    m.revoke("acme", "alerts", 200)
    assert m.why("acme", "f1")["status"] == "revoked" and m.why("globex", "f1")["status"] == "active"


def test_i1_checker_catches_a_violation():
    ep("acme", "e1", 100)
    m.write_fact("acme", id="f1", agent="triage", source="alerts", episode="e1",
                 subject="INC-1", predicate="severity", object="sev1", now=101)
    assert tenancy.i1_violations("acme") == []
    m.graph("acme").query("CREATE (:Fact {id:'fx', subject:'inc-1', predicate:'severity', "
                          "object:'sev2', status:'active', valid_from:102})")
    v = tenancy.i1_violations("acme")
    assert len(v) == 1 and sorted(v[0]["objects"]) == ["sev1", "sev2"]


def test_api_and_mcp_cannot_cross_tenants(tmp_path):
    ep("acme", "e1", 100)
    m.write_fact("acme", id="f-0000aaaa", agent="triage", source="alerts", episode="e1",
                 subject="INC-42", predicate="severity", object="sev1", now=101)
    c = TestClient(create_app("golden", "offline", state_path=tmp_path / "d.json"))
    assert c.get("/api/acme/facts/f-0000aaaa/why").status_code == 200
    assert c.get("/api/globex/facts/f-0000aaaa/why").status_code == 404
    assert "f-0000aaaa" not in json.dumps(c.get("/api/globex/graph").json())

    async def go():
        async with Client(mcp) as cl:
            r = await cl.call_tool("explain_fact", {"tenant": "globex", "fact_id": "f-0000aaaa"})
            return r.is_error
    assert anyio.run(go)


def test_concurrent_threads_keep_invariants():
    res = bench.run(tenants=3, readers=6, writers=2, seconds=1.5)
    assert res["errors"] == 0, res["error_samples"]
    assert res["i1_violations"] == {} and res["cross_tenant_leaks"] == []
    assert res["writes"]["n"] > 20 and res["reads"]["n"] > 100
    assert set(res["facts"]) == {"bench0", "bench1", "bench2"}
    for t in ("bench0", "bench1", "bench2"):
        tenancy.forget(t)
```
