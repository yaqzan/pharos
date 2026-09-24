"""incident(): page on change, stay quiet on repeats. Replays 2026-09-22, when
the Trader heartbeat paged every 30 minutes for the same two red checks."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib  # noqa: E402

incident_mod = importlib.import_module("pharos.incident")
from pharos.push import Result  # noqa: E402

T0 = datetime(2026, 9, 22, 14, 30)
UPDATE = {"update age": "last score write 1179 min ago"}
BACKUP = {"backup age": "last successful backup 329 h ago"}
POST = {"post market": "no successful run for today"}


@pytest.fixture
def sent(tmp_path, monkeypatch):
    monkeypatch.setenv("PHAROS_STATE_DIR", str(tmp_path))
    calls = []

    def fake_send(title, message, **kw):
        calls.append({"title": title, "message": message, "priority": kw.get("priority")})
        return Result("sent", "{}")

    monkeypatch.setattr(incident_mod, "send", fake_send)
    return calls


def run(problems, minutes):
    return incident_mod.incident("heartbeat", problems, source="trader", noun="health check",
                                 now=T0 + timedelta(minutes=minutes))


def test_replay_of_2026_09_22(sent):
    run({**UPDATE, **BACKUP}, 0)          # 14:30 two red -> page
    for m in (30, 60, 90):                # 15:00-16:00 same two -> quiet
        assert run({**UPDATE, **BACKUP}, m) is None
    run(BACKUP, 120)                      # 16:30 update age cleared -> quiet update
    run({**BACKUP, **POST}, 150)          # 17:00 post market joins -> page
    for m in range(180, 420, 30):         # 17:30-20:30 unchanged -> quiet
        assert run({**BACKUP, **POST}, m) is None

    assert [c["priority"] for c in sent] == [1, -1, 1]
    assert sent[0]["title"] == "⚠ 2 health checks failing"
    assert sent[1]["title"] == "⚠ 1 health check failing"
    assert "✅ update age fixed" in sent[1]["message"]
    assert sent[2]["message"].splitlines() == [
        "backup age · last successful backup 329 h ago",
        "post market · no successful run for today",
    ]


def test_reminder_after_quiet_period(sent):
    run(BACKUP, 0)
    assert run(BACKUP, 11 * 60) is None
    run(BACKUP, 12 * 60)
    assert [c["priority"] for c in sent] == [1, 0]
    assert sent[1]["title"] == "⚠ 1 health check still failing"
    assert sent[1]["message"].endswith("Failing for 12h")
    assert run(BACKUP, 13 * 60) is None   # reminder clock restarted


def test_recovery_push_then_silence(sent):
    run(BACKUP, 0)
    run({}, 150)
    assert sent[-1] == {"title": "✅ All health checks passing", "message": "Failing for 2h 30m", "priority": -1}
    assert run({}, 180) is None           # state cleared, nothing more to say


def test_nothing_ever_failing_is_silent(sent):
    assert run({}, 0) is None
    assert sent == []


def test_failed_send_retries_next_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PHAROS_STATE_DIR", str(tmp_path))
    statuses = iter(["failed", "sent"])
    monkeypatch.setattr(incident_mod, "send", lambda *a, **k: Result(next(statuses), ""))
    assert run(BACKUP, 0).status == "failed"
    assert run(BACKUP, 30).status == "sent"   # not suppressed: the first page never left
    assert run(BACKUP, 60) is None


def test_long_detail_is_trimmed(sent):
    run({"disk free": "x" * 200}, 0)
    line = sent[0]["message"]
    assert line.endswith("…") and len(line) <= len("disk free · ") + incident_mod.DETAIL_CHARS
