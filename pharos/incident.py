"""Incidents: page on change, not on every check.

A health checker that runs every 30 minutes and calls send() each time it sees
a red check pages the owner 48 times a day for one problem. incident() keeps a
small state file per (source, key) and only pushes when something changed:

    problem appears / a new one joins   -> page, priority 1
    one of several clears               -> quiet update, priority -1
    nothing changed                     -> nothing, until remind_hours pass,
                                           then one reminder at priority 0
    everything clears                   -> quiet "passing" push with how long
                                           it was broken, state removed

    import pharos
    pharos.incident("heartbeat", {"backup age": "last good backup 13 days ago"},
                    source="trader", noun="health check")

Call it on EVERY run, including all-clear runs (pass an empty dict), or it
cannot send the recovery push. Python only for now.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Mapping, Optional

from .push import ROOT, Result, delivered, send, span

DETAIL_CHARS = 60
DEFAULT_REMIND_HOURS = 12


def _state_path(source: Optional[str], key: str) -> str:
    base = os.environ.get("PHAROS_STATE_DIR") or os.path.join(ROOT, "state")
    safe = re.sub(r"[^\w.-]+", "_", f"{source or 'none'}-{key}")
    return os.path.join(base, safe + ".json")


def _load(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) and data.get("names") else None
    except Exception:
        return None


def _save(path: str, state: Optional[dict]) -> None:
    try:
        if state is None:
            if os.path.exists(path):
                os.remove(path)
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _lines(problems: Mapping[str, str]) -> str:
    out = []
    for name in sorted(problems):
        detail = " ".join(str(problems[name] or "").split())
        if len(detail) > DETAIL_CHARS:
            detail = detail[: DETAIL_CHARS - 1].rstrip() + "…"
        out.append(f"{name} · {detail}" if detail else name)
    return "\n".join(out)


def incident(
    key: str,
    problems: Mapping[str, str],
    *,
    source: Optional[str] = None,
    noun: str = "check",
    channel: str = "ops",
    remind_hours: float = DEFAULT_REMIND_HOURS,
    now: Optional[datetime] = None,
) -> Optional[Result]:
    """Push only when the set of failing problems changes (see module doc).
    Returns the send Result, or None when it deliberately stayed quiet.
    Never raises."""
    try:
        now = now or datetime.now()
        path = _state_path(source, key)
        state = _load(path)
        names = sorted(problems)
        before = set(state["names"]) if state else set()

        if not names:
            if not state:
                return None
            failing_for = span((now - datetime.fromisoformat(state["since"])).total_seconds())
            result = send(f"✅ All {noun}s passing", f"Failing for {failing_for}",
                          source=source, channel=channel, priority=-1)
            if delivered(result.status):
                _save(path, None)
            return result

        since = state["since"] if state else now.isoformat(timespec="seconds")
        new, fixed = set(names) - before, before - set(names)
        body = _lines(problems)
        if new:
            title, priority = f"⚠ {_plural(len(names), noun)} failing", 1
        elif fixed:
            title, priority = f"⚠ {_plural(len(names), noun)} failing", -1
            body += "\n✅ " + ", ".join(sorted(fixed)) + " fixed"
        else:
            last = datetime.fromisoformat(state["last_sent"])
            if (now - last).total_seconds() < remind_hours * 3600:
                return None
            title, priority = f"⚠ {_plural(len(names), noun)} still failing", 0
            body += f"\nFailing for {span((now - datetime.fromisoformat(since)).total_seconds())}"

        result = send(title, body, source=source, channel=channel, priority=priority)
        if delivered(result.status):
            _save(path, {"since": since, "names": names, "last_sent": now.isoformat(timespec="seconds")})
        return result
    except Exception as exc:  # alerting must never break the checker
        return Result("failed", f"{type(exc).__name__}: {exc}")
