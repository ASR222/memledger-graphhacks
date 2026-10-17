"""Deployment files and entrypoint (DEP.md)."""
import json
import re
import socket
import subprocess
import threading
import time
from importlib import metadata
from pathlib import Path

import uvicorn

from memledger import serve, tenancy
from memledger.api import create_app
from scripts import smoke

ROOT = Path(__file__).resolve().parents[1]


def test_startup_creates_missing_tenants_only(tmp_path, monkeypatch, lite_db):
    lite_db.select_graph("memory_globex").delete()
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"acme": 9, "globex": 4}))
    monkeypatch.setenv("MEMLEDGER_DEMO_STATE", str(state))
    made = serve.create_scenario_tenants()
    serve.reset_progress(made)
    assert made == ["globex"] and tenancy.exists("globex")
    assert json.loads(state.read_text()) == {"acme": 9, "globex": 0}   # acme untouched
    assert serve.create_scenario_tenants() == []


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_smoke_full_against_a_running_server(tmp_path, capsys):
    port = free_port()
    app = create_app("golden", "offline", state_path=tmp_path / "d.json", allow_reset=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        assert smoke.main([f"http://127.0.0.1:{port}", "--full"]) == 0
        out = capsys.readouterr().out
        assert "acme step 15 isolation" in out and out.strip().endswith("PASS")
    finally:
        server.should_exit = True
        t.join(5)


def test_smoke_reports_an_unreachable_server(capsys):
    port = free_port()
    assert smoke.main([f"http://127.0.0.1:{port}", "--timeout", "2"]) == 1
    out = capsys.readouterr().out
    assert "unreachable" in out and out.strip().endswith("FAIL")


def test_requirements_match_tested_versions():
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?==(\S+)", line.strip())
        if m:
            pins[m.group(1).lower()] = m.group(3)
    assert {"falkordb", "fastapi", "uvicorn", "google-genai", "pydantic", "falkordblite"} <= set(pins)
    for name, ver in pins.items():
        assert metadata.version(name) == ver, f"{name}: pinned {ver}, installed {metadata.version(name)}"


def test_docker_files():
    df = (ROOT / "Dockerfile").read_text()
    assert 'CMD ["python", "-m", "memledger.serve"]' in df and "USER app" in df
    for path in re.findall(r"^COPY (\S+)", df, re.M):
        assert (ROOT / path).exists(), path
    ignore = (ROOT / ".dockerignore").read_text().split()
    assert ".env" in ignore and "tests" in ignore
    assert (ROOT / ".gcloudignore").read_text().split()[:len(ignore)] == ignore


def test_deploy_script_parses():
    r = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "deploy.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = (ROOT / "scripts" / "deploy.sh").read_text()
    assert "--max-instances 1" in text and "roles/run.builder" in text and "--set-secrets" in text
