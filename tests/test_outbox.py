"""Outbox: a push that fails at the network level is held and delivered late.
Runs against a real local HTTP server standing in for Pushover."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pharos  # noqa: E402
from pharos import outbox  # noqa: E402


class FakePushover:
    def __init__(self):
        self.requests = []
        self.code = 200
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
                server.requests.append({k: v[0] for k, v in urllib.parse.parse_qs(body).items()})
                payload = b'{"status":1,"request":"fake"}' if server.code == 200 else b'{"status":0}'
                self.send_response(server.code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/1/messages.json"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def dead_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()   # nothing listens here now: connection refused = a transport failure
    return f"http://127.0.0.1:{port}/1/messages.json"


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"pushover": {"user_key": "u-test", "app_token": "t-test"}}), encoding="utf-8")
    monkeypatch.setenv("PHAROS_CONFIG", str(cfg))
    monkeypatch.setenv("PHAROS_LOG", str(tmp_path / "pushes.jsonl"))
    monkeypatch.setenv("PHAROS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("PHAROS_POLICY", raising=False)
    fake = FakePushover()
    yield fake, monkeypatch, tmp_path
    fake.close()


def held_lines():
    p = outbox.path()
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def test_network_failure_is_held_then_delivered_late(env):
    fake, mp, _ = env
    mp.setenv("PHAROS_ENDPOINT", dead_url())
    r = pharos.send("Trader session down", "Last online 25m ago", source="trader", hold=True)
    assert r.status == "failed" and r.response.startswith("held for retry")
    assert len(held_lines()) == 1
    # network back: the next send delivers the held one first, with its original time
    mp.setenv("PHAROS_ENDPOINT", fake.url)
    held_at = held_lines()[0]["queued_at"]
    r2 = pharos.send("Trader session back", "Down for 3m", source="trader")
    assert r2.status == "sent"
    assert [q["title"] for q in fake.requests] == ["\U0001F6E0 Trader session down", "\U0001F6E0 Trader session back"]
    assert fake.requests[0]["message"].startswith("Last online 25m ago\nHeld ")
    assert fake.requests[0]["timestamp"] == str(int(held_at))
    assert held_lines() == []
    ledger = pharos.recent(10)
    assert any(e["status"] == "sent" and e["detail"].startswith("held") for e in ledger)


def test_without_hold_nothing_is_kept(env):
    _, mp, _ = env
    mp.setenv("PHAROS_ENDPOINT", dead_url())
    assert pharos.send("x", "y", hold=False).status == "failed"
    assert held_lines() == []


def test_rejected_4xx_is_not_held_but_5xx_is(env):
    fake, mp, _ = env
    mp.setenv("PHAROS_ENDPOINT", fake.url)
    fake.code = 400
    assert pharos.send("bad", "y", hold=True).response.startswith("HTTPError: 400")
    assert held_lines() == []
    fake.code = 503
    assert pharos.send("busy", "y", hold=True).response.startswith("held for retry")
    assert len(held_lines()) == 1


def test_stale_holds_expire(env):
    fake, mp, _ = env
    mp.setenv("PHAROS_ENDPOINT", dead_url())
    pharos.send("old news", "y", hold=True)
    counts = outbox.flush(now=time.time() + (outbox.MAX_AGE_HOURS + 1) * 3600)
    assert counts["expired"] == 1 and held_lines() == []
    assert any(e["status"] == "expired" for e in pharos.recent(5))


def test_still_down_keeps_it(env):
    _, mp, _ = env
    mp.setenv("PHAROS_ENDPOINT", dead_url())
    pharos.send("x", "y", hold=True)
    assert outbox.flush()["kept"] == 1
    assert len(held_lines()) == 1


PS = shutil.which("powershell.exe")


def ps(script):
    subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                    f"$ErrorActionPreference='Stop'; Import-Module '{ROOT / 'Pharos.psm1'}' -Force; {script}"],
                   check=True, capture_output=True, env=os.environ.copy(), timeout=90)


@pytest.mark.skipif(not PS, reason="Windows PowerShell not available")
def test_powershell_holds_python_delivers(env):
    fake, mp, _ = env
    mp.setenv("PHAROS_ENDPOINT", dead_url())
    ps("$null = Send-Pharos -Source vesper -Channel ops -Title 'Remote session down' -Message 'from ps' -Hold")
    lines = held_lines()
    assert len(lines) == 1 and lines[0]["title"] == "\U0001F6E0 Remote session down"
    mp.setenv("PHAROS_ENDPOINT", fake.url)
    assert outbox.flush()["sent"] == 1
    assert fake.requests[0]["message"].startswith("from ps\nHeld ")


@pytest.mark.skipif(not PS, reason="Windows PowerShell not available")
def test_python_holds_powershell_delivers(env):
    fake, mp, _ = env
    mp.setenv("PHAROS_ENDPOINT", dead_url())
    pharos.send("Update failed", "from py", source="trader", hold=True, priority=1)
    mp.setenv("PHAROS_ENDPOINT", fake.url)
    ps("$null = Invoke-PharosFlush")
    assert len(fake.requests) == 1
    q = fake.requests[0]
    assert q["title"] == "\U0001F6E0 Update failed" and q["priority"] == "1"
    assert q["message"].startswith("from py\nHeld ")
    assert held_lines() == []
