"""Pharos tests. No real pushes: credentials point at a file that does not exist.

    py -3.11 -m pytest tests -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pharos  # noqa: E402
from pharos import push  # noqa: E402

OPS = "\U0001F6E0"
SIGNAL = "\U0001F4C8"
TRADE = "\U0001F4BC"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PHAROS_CONFIG", str(tmp_path / "no-config.json"))
    monkeypatch.setenv("PHAROS_LOG", str(tmp_path / "pushes.jsonl"))
    monkeypatch.setenv("PHAROS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("PHAROS_POLICY", raising=False)
    monkeypatch.delenv("PHAROS_PUSHOVER_USER_KEY", raising=False)
    monkeypatch.delenv("PHAROS_PUSHOVER_APP_TOKEN", raising=False)
    monkeypatch.delenv("TRADER_SIGNAL_PUSH", raising=False)
    yield tmp_path


def _title(title, source=None, channel=None):
    return pharos.compose_title(title, source, pharos.resolve_channel(channel))


# ---- title shape --------------------------------------------------------------

TITLE_CASES = [
    # (title, source, channel, expected) -- no project label, ever
    ("Trader session down", "claude-rc", None, f"{OPS} Trader session down"),
    ("claude-rc: Trader is down", "claude-rc", "ops", f"{OPS} Trader is down"),
    ("Claude-RC:Trader is down", "claude-rc", "ops", f"{OPS} Trader is down"),
    ("\u274c Update failed", "trader", "ops", f"{OPS} \u274c Update failed"),
    ("AAPL \U0001F7E2 92", "trader", "signal", f"{SIGNAL} AAPL \U0001F7E2 92"),
    ("\U0001F7E2 Opened AAPL", "trader", "trade", f"{TRADE} \U0001F7E2 Opened AAPL"),
    (f"{OPS} Trader is down", "claude-rc", "ops", f"{OPS} Trader is down"),
    (f"{OPS}\ufe0f already stamped", None, "ops", f"{OPS} already stamped"),
    ("Backup done", None, None, f"{OPS} Backup done"),
    ("trader update ran", "trader", "ops", f"{OPS} trader update ran"),
    ("anything", "x", "no-such-channel", f"{OPS} anything"),
]

NOW = datetime(2026, 9, 22, 14, 0, 0)
AGO_CASES = [
    # (when, expected) relative to NOW
    ("2026-09-22T13:59:30", "just now"),
    ("2026-09-22T13:35:00", "25m ago"),
    ("2026-09-22T09:10:00", "4h ago"),
    ("2026-09-22T00:30:00", "13h ago"),
    ("2026-09-21T22:00:00", "yesterday"),
    ("2026-09-22T10:30:00", "3h ago"),
    ("2026-09-21T07:00:00", "yesterday"),
    ("2026-09-18T12:00:00", "4 days ago"),
    ("2026-09-01T12:00:00", "Sep 1"),
    ("2025-12-26T12:00:00", "Dec 26 2025"),
]
SPAN_CASES = [(40, "40s"), (1500, "25m"), (3600, "1h"), (8100, "2h 15m"), (90000, "1 day"), (260000, "3 days")]


@pytest.mark.parametrize("title,source,channel,expected", TITLE_CASES)
def test_compose_title(title, source, channel, expected):
    assert _title(title, source, channel) == expected


@pytest.mark.parametrize("when,expected", AGO_CASES)
def test_ago(when, expected):
    assert pharos.ago(when, now=NOW) == expected


@pytest.mark.parametrize("seconds,expected", SPAN_CASES)
def test_span(seconds, expected):
    assert pharos.span(seconds) == expected


def test_unknown_channel_degrades_to_ops():
    assert pharos.resolve_channel("typo").key == "ops"
    assert pharos.resolve_channel(None).key == "ops"


# ---- mutes --------------------------------------------------------------------

def test_trader_signal_and_trade_are_muted():
    for channel in ("signal", "trade"):
        r = pharos.send("AAPL", "x", source="trader", channel=channel)
        assert r.status == "muted", r
        assert "TRADER_SIGNAL_PUSH=1" in r.response
        assert pharos.delivered(r.status)


def test_ops_is_never_muted():
    # No credentials in the test env, so an un-muted push reads "disabled".
    assert pharos.send("x", "y", source="trader", channel="ops").status == "disabled"


def test_mute_is_scoped_to_its_source():
    assert pharos.send("x", "y", source="archivist", channel="signal").status == "disabled"


def test_override_env_lifts_the_mute(monkeypatch):
    monkeypatch.setenv("TRADER_SIGNAL_PUSH", "1")
    assert pharos.send("x", "y", source="trader", channel="signal").status == "disabled"
    monkeypatch.setenv("TRADER_SIGNAL_PUSH", "0")
    assert pharos.send("x", "y", source="trader", channel="signal").status == "muted"


def test_until_expires_the_mute():
    today = date.today()
    assert push._mute_live({"until": (today + timedelta(days=1)).isoformat()})
    assert not push._mute_live({"until": today.isoformat()})


def test_dry_run_bypasses_mute_and_hides_secrets():
    r = pharos.send("AAPL", "x", source="trader", channel="signal", dry_run=True)
    assert r.status == "dry_run"
    payload = json.loads(r.response)
    assert "token" not in payload and "user" not in payload
    assert payload["title"].startswith(SIGNAL)


def test_emergency_priority_carries_retry_and_expire():
    payload = json.loads(pharos.send("x", "y", priority=2, dry_run=True).response)
    assert payload["retry"] == "60" and payload["expire"] == "3600"


# ---- contract -----------------------------------------------------------------

def test_delivered():
    assert pharos.delivered("sent") and pharos.delivered("muted")
    for status in ("failed", "disabled", "dry_run"):
        assert not pharos.delivered(status)


def test_broken_policy_still_pages(isolated, monkeypatch):
    bad = isolated / "bad-policy.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("PHAROS_POLICY", str(bad))
    r = pharos.send("x", "y", source="trader", channel="signal", dry_run=True)
    assert r.status == "dry_run"
    assert json.loads(r.response)["title"] == f"{OPS} x"


def test_ledger_records_every_real_attempt():
    pharos.send("one", "m", source="a")
    pharos.send("two", "m", source="trader", channel="trade")
    pharos.send("three", "m", dry_run=True)  # dry runs are not logged
    entries = pharos.recent(10)
    assert [e["status"] for e in entries] == ["disabled", "muted"]
    assert entries[1]["title"] == f"{TRADE} two"


# ---- cross-language parity ----------------------------------------------------

@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="Windows PowerShell not available")
def test_powershell_binding_matches_python(isolated):
    cases = [{"title": t, "source": s, "channel": c} for t, s, c, _ in TITLE_CASES]
    cases_file = isolated / "cases.json"
    out_file = isolated / "out.json"
    cases_file.write_text(json.dumps({
        "titles": cases,
        "ago": [w for w, _ in AGO_CASES],
        "span": [n for n, _ in SPAN_CASES],
    }, ensure_ascii=False), encoding="utf-8")
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ROOT / "Pharos.psm1"}' -Force
$policy = Get-PharosPolicy
$cases = [System.IO.File]::ReadAllText('{cases_file}', [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$now = [datetime]::Parse('{NOW.isoformat()}', [Globalization.CultureInfo]::InvariantCulture)
$agos = @($cases.ago | ForEach-Object {{ Format-PharosAgo -When $_ -Now $now }})
$spans = @($cases.span | ForEach-Object {{ Format-PharosSpan -Seconds $_ }})
$titles = @($cases.titles | ForEach-Object {{
  $ch = Resolve-PharosChannel $_.channel $policy
  Format-PharosTitle -Title $_.title -Source $_.source -Channel $ch -Policy $policy
}})
$muted = @(
  (Send-Pharos -Title a -Message b -Source trader -Channel signal).Status,
  (Send-Pharos -Title a -Message b -Source trader -Channel ops).Status,
  (Send-Pharos -Title a -Message b -Source archivist -Channel trade).Status
)
$json = ConvertTo-Json -InputObject @{{ titles = $titles; statuses = $muted; ago = $agos; span = $spans }} -Compress
[System.IO.File]::WriteAllText('{out_file}', $json, (New-Object System.Text.UTF8Encoding $false))
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True, capture_output=True, env=os.environ.copy(), timeout=60,
    )
    got = json.loads(out_file.read_text(encoding="utf-8"))
    assert got["titles"] == [expected for *_, expected in TITLE_CASES]
    assert got["statuses"] == ["muted", "disabled", "disabled"]
    assert got["ago"] == [expected for _, expected in AGO_CASES]
    assert got["span"] == [expected for _, expected in SPAN_CASES]
    ledger = pharos.recent(10)
    assert [e["lang"] for e in ledger] == ["ps", "ps", "ps"]
    assert ledger[0]["title"] == f"{SIGNAL} a"
