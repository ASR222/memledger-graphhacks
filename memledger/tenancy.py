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
