"""Per-project Pushover apps (the icon): both bindings pick the same token."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pharos import push  # noqa: E402

CONFIG = {"pushover": {"user_key": "u-1234", "app_token": "default-tok",
                       "apps": {"trader": "trader-tok", "Claude-RC": "rc-tok", "empty": ""}}}
# source -> expected token
CASES = [("trader", "trader-tok"), ("TRADER", "trader-tok"), ("claude-rc", "rc-tok"),
         ("archivist", "default-tok"), ("empty", "default-tok"), (None, "default-tok")]


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG), encoding="utf-8")
    monkeypatch.setenv("PHAROS_CONFIG", str(path))
    monkeypatch.delenv("PHAROS_PUSHOVER_APP_TOKEN", raising=False)
    monkeypatch.delenv("PHAROS_PUSHOVER_USER_KEY", raising=False)
    return path


@pytest.mark.parametrize("source,token", CASES)
def test_python_picks_project_app(config, source, token):
    assert push._credentials(source) == ("u-1234", token)


def test_summary_masks_project_apps(config):
    apps = push.config_summary()["project_apps"]
    assert apps == {"trader": "...-tok", "claude-rc": "...-tok"}


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="Windows PowerShell not available")
def test_powershell_picks_same_token(config, tmp_path):
    out = tmp_path / "out.json"
    sources = [s or "" for s, _ in CASES]
    script = f"""
$ErrorActionPreference = 'Stop'
$m = Import-Module '{ROOT / "Pharos.psm1"}' -Force -PassThru
$sources = '{json.dumps(sources)}' | ConvertFrom-Json
$tokens = @($sources | ForEach-Object {{ $s = $_; (& $m {{ param($x) Get-PharosCredentials $x }} $s).Token }})
[System.IO.File]::WriteAllText('{out}', (ConvertTo-Json -InputObject $tokens -Compress))
"""
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                   check=True, capture_output=True, env=os.environ.copy(), timeout=60)
    assert json.loads(out.read_text(encoding="utf-8")) == [t for _, t in CASES]
