"""FalkorDB connection and the graph-per-tenant rule."""
import re

from falkordb import FalkorDB

from . import config

_db = None  # tests replace this with an embedded falkordblite instance
_TENANT = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


def get_db():
    global _db
    if _db is None:
        _db = FalkorDB(host=config.HOST, port=config.PORT,
                       username=config.USERNAME, password=config.PASSWORD)
    return _db


def graph(tenant: str):
    """Return the tenant's graph. Each tenant is a separate FalkorDB graph."""
    if not isinstance(tenant, str) or not _TENANT.match(tenant):
        raise ValueError(f"invalid tenant: {tenant!r}")
    return get_db().select_graph(f"memory_{tenant}")
