"""Indexes and seed data for a tenant graph."""
from . import queries as Q
from .db import graph

AGENTS = [
    {"id": "triage", "role": "triage"},
    {"id": "investigator", "role": "investigator"},
    {"id": "comms", "role": "comms"},
]

SOURCES = [
    {"id": "alerts",   "kind": "alert_feed",  "trust": 0.9},
    {"id": "runbook",  "kind": "runbook",     "trust": 0.9},
    {"id": "app-logs", "kind": "log",         "trust": 0.7},
    {"id": "webhook",  "kind": "integration", "trust": 0.6},  # passes quarantine; revoked in the demo
    {"id": "fwd-logs", "kind": "tool_output", "trust": 0.3},  # always quarantined
]


def seed(tenant: str) -> None:
    g = graph(tenant)
    for q in Q.INDEXES:
        try:
            g.query(q)
        except Exception as e:  # re-running is fine
            if "already indexed" not in str(e).lower():
                raise
    g.query(Q.SEED, {"agents": AGENTS, "sources": SOURCES})
