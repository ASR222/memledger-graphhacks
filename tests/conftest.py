import os
import tempfile

import pytest
from redislite.falkordb_client import FalkorDB as LiteFalkorDB

from memledger import db, schema


@pytest.fixture(scope="session")
def lite_server():
    """One embedded FalkorDB for the whole run, shut down at the end.

    Starting a server per test and never closing it leaves stray processes
    that make pytest hang on exit.
    """
    lite = LiteFalkorDB(os.path.join(tempfile.mkdtemp(), "test.db"))
    yield lite
    lite.close()


@pytest.fixture(autouse=True)
def lite_db(lite_server, monkeypatch):
    """Empty graphs for every test, both tenants seeded."""
    for name in lite_server.list_graphs():
        lite_server.select_graph(name).delete()
    monkeypatch.setattr(db, "_db", lite_server)
    for t in ("acme", "globex"):
        schema.seed(t)
    yield lite_server
