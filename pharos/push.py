"""Pharos: the one push channel for every project on bookmaker.

Stdlib only, zero imports from any project, so anything can page the owner
without dragging a project's database along. Pushover is the transport.

    import pharos
    pharos.send("Import stalled", "no new rows in 6h", source="archivist")

TITLE SHAPE -- every push, both languages:  "<glyph> <title>"
  glyph   the channel's glyph from policy.json (ops by default). Callers never
          hand-roll it; a title that already leads with a known glyph is not
          double-stamped.
  No project label. `source` is for mutes and the ledger only -- the owner
  infers the project from the content. A caller-supplied "<source>: " prefix
  is stripped. Writing rules for titles and bodies: README "Writing a push".

STATUS CONTRACT -- send() returns Result(status, response), never raises:
    sent      delivered, response is Pushover's JSON body
    muted     a policy.json mute swallowed it on purpose, nothing sent
    dry_run   nothing sent, response is the payload minus the token
    disabled  no credentials configured, nothing sent
    failed    transport error, response is "ExcType: message"
"sent" must only ever mean the push left the box: Trader gates database writes
on it. delivered() is true for sent and muted -- latch on that, so a mute window
does not queue months of retries that all fire the day it lifts.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import NamedTuple, Optional

PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"
DEFAULT_TIMEOUT = 15

# Pushover rejects priority 2 unless told how hard to retry. Supplying defaults
# means an emergency page cannot silently no-op.
EMERGENCY_RETRY_SECONDS = 60
EMERGENCY_EXPIRE_SECONDS = 3600

LOG_ROTATE_BYTES = 5 * 1024 * 1024

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FALLBACK_POLICY = {
    "default_channel": "ops",
    "channels": {"ops": {"glyph": "\U0001F6E0", "mutable": False}},
    "mutes": [],
}
_FALSY = ("", "0", "false", "no", "off")


class Result(NamedTuple):
    """(status, response). A tuple so `status, body = send(...)` unpacks."""

    status: str
    response: str


class Channel(NamedTuple):
    key: str
    glyph: str
    mutable: bool


# ---- config & policy ----------------------------------------------------------

def _config_path() -> str:
    return os.environ.get("PHAROS_CONFIG") or os.path.join(ROOT, "config.json")


def _policy_path() -> str:
    return os.environ.get("PHAROS_POLICY") or os.path.join(ROOT, "policy.json")


def _log_path() -> str:
    return os.environ.get("PHAROS_LOG") or os.path.join(ROOT, "logs", "pushes.jsonl")


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Missing or malformed is a degraded condition, never a crash.
        return {}


def load_policy() -> dict:
    policy = _read_json(_policy_path())
    if not policy.get("channels"):
        return _FALLBACK_POLICY
    return policy


def channels() -> dict:
    policy = load_policy()
    return {
        key: Channel(key, spec.get("glyph", ""), bool(spec.get("mutable", False)))
        for key, spec in policy["channels"].items()
    }


def resolve_channel(channel: Optional[str], policy: Optional[dict] = None) -> Channel:
    """Unknown or missing channel degrades to the default (ops, never muted)."""
    policy = policy or load_policy()
    specs = policy["channels"]
    key = channel if channel in specs else policy.get("default_channel", "ops")
    if key not in specs:
        key = next(iter(specs))
    spec = specs[key]
    return Channel(key, spec.get("glyph", ""), bool(spec.get("mutable", False)))


def _app_tokens(pushover: dict) -> dict:
    apps = pushover.get("apps") or {}
    return {str(k).lower(): v for k, v in apps.items() if v} if isinstance(apps, dict) else {}


def _credentials(source: Optional[str] = None) -> tuple:
    """(user, token). Each project can have its own Pushover app -- that is
    what gives its pushes their own icon -- in config.json `pushover.apps`,
    keyed by source. Sources without one fall back to the default app."""
    config = _read_json(_config_path())
    pushover = config.get("pushover") or {}
    user = os.environ.get("PHAROS_PUSHOVER_USER_KEY") or pushover.get("user_key")
    token = (
        _app_tokens(pushover).get((source or "").lower())
        or os.environ.get("PHAROS_PUSHOVER_APP_TOKEN")
        or pushover.get("app_token")
    )
    return user, token


def enabled() -> bool:
    """True when a push would actually be attempted."""
    user, token = _credentials()
    return bool(user and token)


def config_summary() -> dict:
    """Masked view of what would be used. Safe to print and paste into logs."""
    user, token = _credentials()

    def mask(value: Optional[str]) -> str:
        return "..." + value[-4:] if value else "(unset)"

    policy = load_policy()
    return {
        "config_file": _config_path(),
        "config_file_exists": os.path.exists(_config_path()),
        "policy_file": _policy_path(),
        "log_file": _log_path(),
        "user_key": mask(user),
        "app_token": mask(token),
        "project_apps": {k: mask(v) for k, v in _app_tokens(_read_json(_config_path()).get("pushover") or {}).items()},
        "enabled": bool(user and token),
        "channels": {k: c.glyph for k, c in channels().items()},
        "active_mutes": [m for m in policy.get("mutes", []) if _mute_live(m)],
    }


# ---- mutes --------------------------------------------------------------------

def _mute_live(mute: dict, today: Optional[date] = None) -> bool:
    until = mute.get("until")
    if until:
        try:
            if (today or date.today()) >= date.fromisoformat(until):
                return False
        except ValueError:
            pass
    override = mute.get("override_env")
    if override and os.environ.get(override, "").strip().lower() not in _FALSY:
        return False
    return True


def active_mute(source: Optional[str], channel: Channel, policy: Optional[dict] = None) -> Optional[dict]:
    """The mute rule swallowing this push, or None. Never applies to a channel
    that is not mutable -- a dead pipeline must always reach the phone."""
    if not channel.mutable:
        return None
    policy = policy or load_policy()
    for mute in policy.get("mutes", []):
        rule_source = (mute.get("source") or "").lower()
        if rule_source and rule_source != (source or "").lower():
            continue
        if channel.key not in (mute.get("channels") or []):
            continue
        if _mute_live(mute):
            return mute
    return None


# ---- title --------------------------------------------------------------------

def compose_title(title: str, source: Optional[str], channel: Channel, policy: Optional[dict] = None) -> str:
    """"<glyph> <title>". Idempotent: a title that already carries a known
    glyph is not stamped twice. A leading "<source>: " label is removed --
    projects are never named in the headline."""
    policy = policy or load_policy()
    body = title.strip()
    for spec in policy["channels"].values():
        glyph = spec.get("glyph")
        if glyph and body.startswith(glyph):
            body = body[len(glyph):].lstrip("️").lstrip()
            break
    if source:
        body = re.sub(r"^" + re.escape(source) + r"\s*:\s*", "", body, flags=re.IGNORECASE)
    return f"{channel.glyph} {body}" if channel.glyph else body


# ---- time phrases --------------------------------------------------------------

def span(seconds: float) -> str:
    """Compact duration: "40s", "25m", "2h 15m", "3 days"."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m = s // 60
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m" if m else f"{h}h"
    d = h // 24
    return "1 day" if d == 1 else f"{d} days"


def ago(when, now: Optional[datetime] = None) -> str:
    """Smart relative time for a push body: "just now", "25m ago", "3h ago",
    "yesterday", "4 days ago", then a date ("Dec 26", "Dec 26 2025").
    Accepts a datetime or an ISO string; naive and aware are both fine."""
    if isinstance(when, str):
        when = datetime.fromisoformat(when.strip().replace("Z", "+00:00"))
    now = now or (datetime.now(when.tzinfo) if when.tzinfo else datetime.now())
    secs = (now - when).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 6 * 3600 or when.date() == now.date():
        return f"{int(secs // 3600)}h ago"
    days = (now.date() - when.date()).days
    if days <= 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    label = f"{when:%b} {when.day}"
    return label if when.year == now.year else f"{label} {when.year}"


def delivered(status: str) -> bool:
    """Settled: really sent, or muted on purpose. Latch callers use this."""
    return status in ("sent", "muted")


# ---- log ----------------------------------------------------------------------

def _log(entry: dict) -> None:
    """Append one line to the push ledger. Never raises."""
    try:
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > LOG_ROTATE_BYTES:
            os.replace(path, path + ".1")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def recent(limit: int = 20) -> list:
    """Last `limit` ledger entries, oldest first."""
    try:
        with open(_log_path(), "r", encoding="utf-8-sig") as handle:
            lines = handle.readlines()[-limit:]
    except Exception:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ---- send ---------------------------------------------------------------------

def _endpoint() -> str:
    """PHAROS_ENDPOINT overrides the Pushover URL (tests point it at a local server)."""
    return os.environ.get("PHAROS_ENDPOINT") or PUSHOVER_ENDPOINT


def _post(payload: dict, timeout: int = DEFAULT_TIMEOUT) -> tuple:
    """POST one payload. Returns (Result, transport_failure). A transport failure
    (DNS, refused, timeout, 5xx) is worth retrying later; a 4xx is not."""
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(_endpoint(), data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Result("sent", response.read().decode("utf-8", errors="replace")), False
    except urllib.error.HTTPError as exc:
        return Result("failed", f"HTTPError: {exc.code} {exc.reason}"), exc.code >= 500
    except Exception as exc:
        return Result("failed", f"{type(exc).__name__}: {exc}"), True


def send(
    title: str,
    message: str,
    *,
    source: Optional[str] = None,
    channel: Optional[str] = None,
    priority: int = 0,
    url: Optional[str] = None,
    url_title: Optional[str] = None,
    html: bool = False,
    sound: Optional[str] = None,
    retry: Optional[int] = None,
    expire: Optional[int] = None,
    dry_run: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    hold: bool = False,
) -> Result:
    """Send one push. Never raises -- see the STATUS CONTRACT above.

    hold=True: if the push fails at the network level, keep it in the outbox and
    deliver it late (see outbox.py). The status is still "failed" -- it did not
    leave the box. Only for callers with no retry of their own."""
    if not dry_run:
        try:
            from . import outbox
            if outbox.pending():
                outbox.flush()
        except Exception:
            pass
    try:
        policy = load_policy()
        ch = resolve_channel(channel, policy)
        full_title = compose_title(title, source, ch, policy)
    except Exception:  # a broken policy must not stop the page
        policy = _FALLBACK_POLICY
        ch = resolve_channel("ops", policy)
        full_title = title

    user, token = _credentials(source)
    payload = {
        "token": token or "",
        "user": user or "",
        "title": full_title,
        "message": message,
        "priority": str(priority),
    }
    if url:
        payload["url"] = url
        if url_title:
            payload["url_title"] = url_title
    if html:
        payload["html"] = "1"
    if sound:
        payload["sound"] = sound
    if priority == 2:
        payload["retry"] = str(retry or EMERGENCY_RETRY_SECONDS)
        payload["expire"] = str(expire or EMERGENCY_EXPIRE_SECONDS)

    if dry_run:
        redacted = {k: v for k, v in payload.items() if k not in ("token", "user")}
        return Result("dry_run", json.dumps(redacted, ensure_ascii=False))

    mute = active_mute(source, ch, policy)
    if mute:
        hint = f" ({mute['override_env']}=1 to re-enable)" if mute.get("override_env") else ""
        result = Result("muted", f"{ch.key} pushes from {source} muted: {mute.get('reason', '')}{hint}")
    elif not token or not user:
        result = Result("disabled", f"No Pushover credentials (PHAROS_PUSHOVER_* env or {_config_path()})")
    else:
        result, transport = _post(payload, timeout)
        if result.status == "failed" and transport and hold:
            from . import outbox
            fields = {k: v for k, v in payload.items() if k not in ("token", "user", "title", "message")}
            if outbox.hold({"queued_at": time.time(), "source": source, "channel": ch.key,
                            "priority": priority, "title": full_title, "message": message,
                            "fields": fields}):
                result = Result("failed", f"held for retry: {result.response}")

    _log({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "lang": "py",
        "source": source,
        "channel": ch.key,
        "priority": priority,
        "status": result.status,
        "title": full_title,
        "message": message[:500],
        "detail": result.response[:300] if result.status != "sent" else "",
    })
    return result
