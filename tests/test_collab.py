"""Task board and doc extraction (INSTRUCTIONS.md)."""
import shutil
from pathlib import Path

import pytest

from scripts import apply_docs as A
from scripts import status as st

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def board(tmp_path):
    p = tmp_path / "SETUP-STATUS.md"
    shutil.copy(ROOT / "SETUP-STATUS.md", p)
    return p


def run(board, *args):
    return st.main(list(args), path=board)


def status_of(board, tid):
    return next(r for r in st.load(board)[1] if r["ID"] == tid)


def mark_done(board, *ids):
    lines, rows, s, e = st.load(board)
    for r in rows:
        if r["ID"] in ids:
            r.update({"Status": "done", "Owner": "test"})
    st.save(lines, rows, s, e, None, board)


def test_fresh_board_is_valid_and_starts_with_setup(board, capsys):
    assert run(board, "check") == 0
    capsys.readouterr()
    assert run(board, "next") == 0
    assert capsys.readouterr().out.split()[0] == "S1"


def test_claim_respects_dependencies(board, capsys):
    assert run(board, "claim", "D-MEM", "--owner", "ana") == 2
    assert "waits for S1" in capsys.readouterr().out
    assert run(board, "claim", "S1", "--owner", "ana") == 0
    r = status_of(board, "S1")
    assert (r["Status"], r["Owner"], r["Branch"]) == ("in-progress", "ana", "task/s1")
    assert "ana: claimed S1 on task/s1" in board.read_text().splitlines()[-1]
    assert run(board, "claim", "S1", "--owner", "bo") == 2       # already taken


def test_locks_prevent_overlap(board, capsys):
    upstream = ["S1", "D-MEM", "D-EXT", "D-TRU", "D-AGT", "D-SCN", "D-API", "D-VENDOR",
                "D-MCP", "D-TEN", "D-EVL", "D-DEP", "D-SUB"]
    mark_done(board, *upstream)
    assert run(board, "claim", "C1", "--owner", "ana") == 0
    capsys.readouterr()
    assert run(board, "claim", "C2a", "--owner", "bo") == 2       # both lock queries.py
    assert "C1 (ana) holds memledger/queries.py" in capsys.readouterr().out
    assert run(board, "claim", "C2b", "--owner", "bo") == 0       # memory.py only: fine in parallel
    run(board, "next")
    assert "C2a" not in capsys.readouterr().out
    assert run(board, "done", "C1") == 0
    assert run(board, "claim", "C2a", "--owner", "bo") == 0


def test_folder_locks_cover_files():
    assert st.overlaps("memledger/agents/", "memledger/agents/team.py")
    assert st.overlaps("data/", "data/acme/scenario.json")
    assert not st.overlaps("memledger/api.py", "memledger/api_v2.py")
    assert not st.overlaps("data/acme/", "data/globex/logs.txt")


def test_check_catches_a_hand_edited_clash(board, capsys):
    text = board.read_text()
    text = text.replace("| C2a | Apply the seed + as_of patch (SCN.md §12) and tests/test_patch.py; remove the SCN xfail | D-SUB | todo | - | - |",
                        "| C2a | Apply the seed + as_of patch (SCN.md §12) and tests/test_patch.py; remove the SCN xfail | D-SUB | in-progress | bo | b |")
    text = text.replace("| C2b | Apply the cross-process lock patch (TEN.md §5) | D-SUB | todo | - | - |",
                        "| C2b | Apply the cross-process lock patch (TEN.md §5) | D-SUB | in-progress | - | b |")
    board.write_text(text)
    assert run(board, "check") == 1
    out = capsys.readouterr().out
    assert "C2a is in-progress but dependency D-SUB is todo" in out
    assert "C2b is in-progress without an owner" in out


def test_review_done_block_release(board):
    run(board, "claim", "S1", "--owner", "ana")
    assert run(board, "review", "S1") == 0 and status_of(board, "S1")["Status"] == "review"
    assert run(board, "done", "S1") == 0 and status_of(board, "S1")["Status"] == "done"
    run(board, "claim", "D-MEM", "--owner", "ana")
    assert run(board, "block", "D-MEM") == 2                       # needs --note
    assert run(board, "block", "D-MEM", "--note", "docker won't start") == 0
    assert run(board, "release", "D-MEM") == 0
    r = status_of(board, "D-MEM")
    assert (r["Status"], r["Owner"]) == ("todo", "-")
    assert run(board, "check") == 0


DOCS = ROOT / "docs"


@pytest.mark.skipif(not (DOCS / "Mem.md").exists(), reason="docs/ not present")
def test_apply_docs_full_then_idempotent(tmp_path):
    r = A.apply(DOCS, tmp_path, write=True)
    assert len(r["new"]) > 55 and r["changed"] == [] and len(r["appended"]) == 3
    assert not (tmp_path / "scripts" / "seed.py").exists()          # SETUP v1 code not taken
    for f in ("docker-compose.yml", "pyproject.toml", ".env.example", ".gitignore"):
        assert (tmp_path / f).exists(), f                             # SETUP config files taken
    mem = A.extract("Mem", (DOCS / "Mem.md").read_text())[0]["memledger/queries.py"]
    q = (tmp_path / "memledger" / "queries.py").read_text()
    assert q.startswith(mem.rstrip("\n")) and "agents (AGT.md)" in q and "tenancy (TEN.md)" in q
    again = A.apply(DOCS, tmp_path, write=True)
    assert again["new"] == [] and again["changed"] == [] and again["appended"] == []
    assert (tmp_path / ".gcloudignore").read_text().endswith(".gcloudignore\n")


@pytest.mark.skipif(not (DOCS / "Mem.md").exists(), reason="docs/ not present")
def test_apply_docs_never_clobbers_edits(tmp_path):
    A.apply(DOCS, tmp_path, write=True)
    f = tmp_path / "memledger" / "agents" / "team.py"
    f.write_text(f.read_text() + "# my change\n")
    r = A.apply(DOCS, tmp_path, write=True)
    assert r["changed"] == ["memledger/agents/team.py"] and f.read_text().endswith("# my change\n")
    r = A.apply(DOCS, tmp_path, write=True, force=True)
    assert r["overwritten"] == ["memledger/agents/team.py"] and not f.read_text().endswith("# my change\n")


@pytest.mark.skipif(not (DOCS / "Mem.md").exists(), reason="docs/ not present")
def test_apply_docs_one_doc_at_a_time(tmp_path):
    for doc in A.ORDER:
        A.apply(DOCS, tmp_path, only=[doc], write=True)
    assert A.apply(DOCS, tmp_path)["changed"] == []
