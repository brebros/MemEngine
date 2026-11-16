"""Test suite for MemEngine core: quality gate, dedup, recall, links, backup.

Uses an isolated temp DB via MEMENGINE_DB so the production memory is never touched.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memengine.db import connect
from memengine.dedup import similar_exists
from memengine.quality import quality_gate


@pytest.fixture()
def tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "mem.db")
        monkeypatch.setenv("MEMENGINE_DB", db)
        yield db


# ---------- quality gate ----------

def test_gate_rejects_short_content():
    ok, reason = quality_gate("pendek")
    assert not ok and "too short" in reason


def test_gate_rejects_transcript():
    ok, reason = quality_gate("x" * 4500)
    assert not ok and "too long" in reason


def test_gate_rejects_api_key():
    ok, reason = quality_gate("configuration uses api_key=sk-abcdefghij1234567890abcd here")
    assert not ok and "secret" in reason


def test_gate_rejects_bot_token():
    ok, reason = quality_gate("telegram token 1234567890:AAEhBOweik6ad9r_QXMENQjcrGbqCr4K-1s")
    assert not ok and "secret" in reason


def test_gate_accepts_normal_memory():
    ok, reason = quality_gate("Deployed the monitoring stack and verified all dashboards render correctly")
    assert ok, reason


def test_gate_rejects_private_key_block():
    content = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\ndef\n-----END OPENSSH PRIVATE KEY-----"
    ok, reason = quality_gate(content)
    assert not ok and "secret" in reason


# ---------- dedup ----------

def test_dedup_flags_near_duplicate(tmp_db):
    con = connect()
    con.execute("INSERT INTO memories (bank, type, content, created_at) VALUES ('op','fact','deploy monitoring stack grafana', 1)")
    con.commit()
    _dup_id, score = similar_exists(con, "op", "deploy the monitoring stack with grafana today")
    assert score >= 0.6


def test_dedup_ignores_different_content(tmp_db):
    con = connect()
    con.execute("INSERT INTO memories (bank, type, content, created_at) VALUES ('op','fact','deploy monitoring stack grafana', 1)")
    con.commit()
    _dup_id, score = similar_exists(con, "op", "configure nginx rate limiting rules")
    assert score < 0.3


# ---------- CLI end-to-end (subprocess, isolated DB) ----------

def _run_cli(tmp_db, *args):
    env = dict(os.environ, MEMENGINE_DB=tmp_db)
    root = os.path.join(os.path.dirname(__file__), "..", "src")
    code = f"import sys; sys.path.insert(0, {root!r}); from memengine.cli import main; main()"
    r = subprocess.run(
        [sys.executable, "-c", code, *args], capture_output=True, text=True, env=env, check=False)
    assert r.returncode in (0, 1), r.stderr
    return r.returncode, json.loads(r.stdout)


def test_cli_add_recall_roundtrip(tmp_db):
    rc, res = _run_cli(tmp_db, "add", "op", "fact",
                       "Set up Prometheus monitoring for the trading bot on the VPS",
                       "--source", "test")
    assert rc == 0 and res["ok"]
    rc, res = _run_cli(tmp_db, "recall", "all", "prometheus", "monitoring")
    assert rc == 0 and res["count"] >= 1
    assert "Prometheus" in res["results"][0]["content"]


def test_cli_duplicate_guard(tmp_db):
    text = "Wrote the incident report for the outage last Tuesday at midnight"
    rc1, _res1 = _run_cli(tmp_db, "add", "op", "fact", text, "--source", "test")
    assert rc1 == 0
    rc2, res2 = _run_cli(tmp_db, "add", "op", "fact", text, "--source", "test")
    assert rc2 == 1 and res2.get("duplicate") is True


def test_cli_secret_blocked(tmp_db):
    rc, res = _run_cli(tmp_db, "add", "op", "fact", "the api_key=ghp_Abcdef12345678901234 secret here", "--source", "test")
    assert rc == 1 and "secret" in res.get("rejected", "")


def test_cli_link_and_backlinks(tmp_db):
    _run_cli(tmp_db, "add", "op", "fact", "first memory about the trading bot deployment", "--source", "t")
    _run_cli(tmp_db, "add", "op", "fact", "second memory about monitoring dashboards setup", "--source", "t")
    rc, lst = _run_cli(tmp_db, "list", "op")
    ids = [m["id"] for m in lst["memories"]]
    rc, _res = _run_cli(tmp_db, "link", "op", str(ids[0]), str(ids[1]))
    assert rc == 0
    rc, bl = _run_cli(tmp_db, "backlinks", "op", str(ids[1]))
    assert bl["count"] == 1


def test_cli_backup_rotation(tmp_db):
    _run_cli(tmp_db, "add", "op", "fact", "a memory worth backing up for later recall", "--source", "t")
    rc, res = _run_cli(tmp_db, "backup")
    assert rc == 0 and res["memories"] >= 1 and os.path.exists(res["path"])
