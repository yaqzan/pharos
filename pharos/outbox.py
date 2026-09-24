"""Outbox: pushes held through a network outage, delivered late instead of lost.

On 2026-09-22 api.pushover.net did not resolve for eight hours and 16 claude-rc
alerts were dropped on the floor. A caller that has no retry of its own passes
`hold=True` to send(); if the push fails at the network level (DNS, refused,
timeout, a 5xx from Pushover) it is appended here. Every later send, from
either binding, first tries to deliver what is waiting, and claude-rc's
5-minute watchdog tick flushes too.

- Only transport failures are held. A 4xx means Pushover rejected the message
  itself; resending it would fail the same way forever.
- Held pushes keep their original time (Pushover's `timestamp`), and the body
  gets one line saying how late it is, e.g. "Held 2h 15m".
- Anything older than MAX_AGE_HOURS is dropped (and logged as expired): a page
  about a half-day-old problem is noise, not an alert.
- NOT for callers that retry on their own (Trader gates DB writes on "sent" and
  re-sends): holding those would deliver twice.

File: state/outbox.jsonl, one JSON object per line, written by BOTH bindings
(Pharos.psm1 speaks the same format). A flush claims the file by renaming it,
so two flushes at once can't deliver the same push twice.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Optional

MAX_AGE_HOURS = 12


def path() -> str:
    from .push import ROOT
    base = os.environ.get("PHAROS_STATE_DIR") or os.path.join(ROOT, "state")
    return os.path.join(base, "outbox.jsonl")


def hold(entry: dict) -> bool:
    """Append one held push. Never raises; False if it could not be written."""
    try:
        p = path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def pending() -> int:
    try:
        with open(path(), "r", encoding="utf-8-sig") as handle:
            return sum(1 for line in handle if line.strip())
    except Exception:
        return 0


def flush(now: Optional[float] = None) -> dict:
    """Try to deliver every held push. Returns counts. Never raises."""
    from .push import _post, _credentials, _log, span

    counts = {"sent": 0, "kept": 0, "expired": 0, "dropped": 0}
    p = path()
    if not os.path.exists(p):
        return counts
    claimed = f"{p}.flushing-{os.getpid()}-{int(time.time() * 1000)}"
    try:
        os.replace(p, claimed)
    except Exception:
        return counts  # another flush holds it right now
    try:
        with open(claimed, "r", encoding="utf-8-sig") as handle:
            lines = [line for line in handle if line.strip()]
    except Exception:
        lines = []
    keep = []
    now = now or time.time()
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            counts["dropped"] += 1
            continue
        age = now - float(e.get("queued_at", now))
        base_log = {"ts": datetime.now().isoformat(timespec="seconds"), "lang": "py",
                    "source": e.get("source"), "channel": e.get("channel"),
                    "priority": e.get("priority", 0), "title": e.get("title", ""),
                    "message": (e.get("message") or "")[:500]}
        if age > MAX_AGE_HOURS * 3600:
            counts["expired"] += 1
            _log({**base_log, "status": "expired", "detail": f"held {span(age)}, older than {MAX_AGE_HOURS}h"})
            continue
        user, token = _credentials(e.get("source"))
        if not user or not token:
            keep.append(line)
            counts["kept"] += 1
            continue
        payload = {k: v for k, v in (e.get("fields") or {}).items()}
        payload.update({"token": token, "user": user, "title": e.get("title", ""),
                        "message": f"{e.get('message', '')}\nHeld {span(age)}",
                        "timestamp": str(int(float(e.get("queued_at", now))))})
        result, transport = _post(payload)
        if result.status == "sent":
            counts["sent"] += 1
            _log({**base_log, "status": "sent", "detail": f"held {span(age)}"})
        elif transport:
            keep.append(line)
            counts["kept"] += 1
        else:
            counts["dropped"] += 1
            _log({**base_log, "status": "failed", "detail": f"held push rejected: {result.response[:200]}"})
    if keep:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a", encoding="utf-8") as handle:
                handle.writelines(k if k.endswith("\n") else k + "\n" for k in keep)
        except Exception:
            pass
    try:
        os.remove(claimed)
    except Exception:
        pass
    return counts
