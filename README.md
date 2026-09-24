# Pharos

The one push channel for every project on this machine. Named after the
Pharos of Alexandria, the lighthouse that signalled ships from miles out.

Pushover is the transport. Python and PowerShell bindings share one config, one
policy file, one title shape and one status contract. Nothing to register: a
new project imports the binding and passes its name.

## Setup

You need a [Pushover](https://pushover.net) account (the phone app has a free trial, then a
one-time purchase) and Python 3.11. The PowerShell binding is for Windows (PowerShell 5.1 or 7).

1. Clone this repo anywhere, say `C:\path\to\Pharos`.
2. On pushover.net, copy your **user key**, then create an application
   (pushover.net/apps/build) and copy its **API token**. That app is your default channel.
3. Copy `config.example.json` to `config.json` and paste both in. `config.json` is gitignored.
   Or set `PHAROS_PUSHOVER_USER_KEY` and `PHAROS_PUSHOVER_APP_TOKEN` instead.
4. Run `powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1` to see what it would
   do, then again with `-Apply`. It puts a `pharos.pth` in Python 3.11's site-packages so any
   script can `import pharos`, and sends nothing.
5. Check it: `py -3.11 -m pharos --check`, then send yourself one:
   `py -3.11 -m pharos --source test --title "Hello" --message "it works"`.

Not on Windows? The Python binding is standard library only. Skip `install.ps1` and put the
repo on `PYTHONPATH`.

Optional: give each project its own Pushover app (and icon) and list the tokens under
`pushover.apps`, keyed by the `source` name you pass. See "Project icons" below.
`policy.json` ships with the channels and a mute this author uses; edit it to taste.

## Plug in

**Python** (any Python 3.11 process; `install.ps1` put `pharos.pth` in site-packages)

```python
import pharos

status, body = pharos.send("Import stalled", "no new rows in 6h", source="archivist", priority=1)
```

**PowerShell** (no Python needed, so a watchdog can page about a broken Python)

```powershell
Import-Module C:\path\to\Pharos\Pharos.psm1
$r = Send-Pharos -Source claude-rc -Title 'Spice is down' -Message $detail -Priority 1
```

**Command line** (scheduled tasks, `.bat`, hooks)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\Pharos\pharos.ps1 -Source archivist -Title 'Import stalled' -MessageFile C:\temp\body.txt
```

```bash
py -3.11 -m pharos --source spore --title "Migration done" --message-file C:\temp\summary.txt
```

Use a message file for anything multi-line or with quotes. Exit codes: `0` sent,
muted or dry run, `1` failed, `2` no credentials.

A venv built without `--system-site-packages` won't see the `.pth`. Add
`C:\path\to\Pharos` to that venv's `PYTHONPATH`, or use the command line.

## What a push looks like

```
🛠 ❌ Trader session down
   Last online 25m ago · no session showing in the app
📈 MTSI 🟢 87
   $379.53 (8.7%)
```

- The **channel glyph** comes first. Callers never type it. Default channel is `ops`.
- **No project name in the headline.** `source` is only used for mutes and the
  ledger. If a caller passes `"<source>: ..."`, Pharos strips the label.
- Passing an already-stamped title doesn't double the glyph.

## Writing a push

The owner reads these on a phone and deals with them later at a computer.

1. **Headline says what happened, in a few words.** `Update failed`, `Trader session down`.
   Don't name the project; the content makes it obvious.
2. **One short body line.** The key fact and maybe a reason, joined with ` · `.
   Full detail goes in the project's own log, not the push.
3. **Times are relative.** Use `pharos.ago(ts)` / `Format-PharosAgo` ("25m ago",
   "yesterday", "Dec 26") and `pharos.span(secs)` / `Format-PharosSpan`
   ("2h 15m", "3 days"). Never a raw timestamp.
4. **No instructions or commands.** No "run X", no script names, no flags. The
   push flags a problem; fixing it happens at the computer.
5. **Event markers** go after the channel glyph: ❌ broken/failed, ⚠ degraded or
   skipped, ✅ recovered/done. Domain markers (🟢 🔻 💰 🛑) are the caller's own.
6. **Recoveries get a push too**, saying how long it was broken ("Down for 2h 15m").

## Channels

Defined in `policy.json`, shared by both languages.

| channel | glyph | mutable | for |
|---|---|---|---|
| `ops` | 🛠 | no | health, watchdogs, heartbeats, failures, recoveries |
| `signal` | 📈 | yes | Trader score crossings, TP/SL exits |
| `trade` | 💼 | yes | Trader portfolio opens, closes, sprint alerts |

An unknown channel falls back to `ops`. Adding a channel is one entry in
`policy.json`; the parity test checks that both bindings still agree.

## Project icons

Pushover shows an icon per **app**, not per message. So every project has its
own Pushover app with its own icon, and a push about a project goes out under
that project's app, whoever sends it. claude-rc's "Vesper session down" is sent
with `source="vesper"`, so it shows the Vesper icon.

```json
{ "pushover": { "user_key": "...", "app_token": "<Pharos app: the default>",
                "apps": { "trader": "<Trader Alerts>", "vesper": "<Vesper>", "...": "..." } } }
```

Keys are the `source` name. A source with no app (or a machine-wide alert, such
as claude-rc's "logged out") uses the **Pharos** app and its lighthouse icon.

Registered 2026-09-23: arbiter (was curator), archivist, fantasy, gamenight,
gleaner (was scribe), spice, spore, trader (the older "Trader Alerts" app),
vesper, wayfinder.

Icons (128×128, Pushover's size) are in `icons/`: `py -3.11 icons\build_icons.py`
renders each project's own icon (PNG, or SVG via headless Edge), and
`draw_pharos.py` draws the lighthouse. `draw_archivist.py` draws
Archivist's brass temple, `draw_vesper.py` Vesper's moonlit mic, `draw_spore.py` Spore's crystal mushrooms, `draw_gleaner.py` Gleaner's play-button-into-transcript and `draw_arbiter.py` Arbiter's laurelled film reel (all owner-approved;
Vesper keeps its alternate glow levels as presets: `py -3.11 icons\draw_vesper.py faint`). To add a project: create an app at pushover.net/apps/build,
upload `icons/<source>.png`, put its token under `apps`.

## Incidents: page on change, not on every check

For anything that re-checks the same problems on a timer (heartbeats,
watchdogs), use `incident` instead of `send`. It keeps state per (source, key):

| situation | push |
|---|---|
| a problem appears, or a new one joins | ⚠ page, priority 1 |
| one of several clears | quiet update, priority -1 |
| nothing changed | nothing; one reminder after 12h, priority 0 |
| all clear | ✅ quiet "passing · Failing for 2h 30m", priority -1 |

```python
pharos.incident("heartbeat", {"backup age": "last good backup 13 days ago"},
                source="trader", noun="health check")
```

Call it on every run, passing `{}` when everything is fine, or it can't tell
you when things recover. State lives in `state/`. Python only for now.

## Held pushes: surviving a network outage

On 2026-09-22 `api.pushover.net` didn't resolve for eight hours and 16 alerts
were lost. A caller with no retry of its own passes `hold=True` (PowerShell:
`-Hold`, CLI: `--hold`). If the push fails at the network level (DNS, refused,
timeout, a 5xx), it waits in `state/outbox.jsonl` and goes out on the next send
from either language, or on claude-rc's 5-minute tick (`Invoke-PharosFlush`,
`pharos.flush()`, `py -3.11 -m pharos --flush`).

- It arrives with its original time and one extra line: `Held 2h 15m`.
- A 4xx is never held: Pushover rejected the message, and it would fail forever.
- Held longer than 12 hours, it's dropped and logged as `expired`.
- The status is still `failed` (it didn't leave the box). **Don't use it for
  Trader**, which re-sends on its own and would double up.

## Mutes

`policy.json` → `mutes`: silence one source's mutable channels without touching
its code.

```json
{ "source": "trader", "channels": ["signal", "trade"], "until": null,
  "override_env": "TRADER_SIGNAL_PUSH", "reason": "holdout embargo ..." }
```

Muted pushes return `muted` and nothing is sent. `until` (a `YYYY-MM-DD` date)
ends it automatically; setting the `override_env` variable to `1` lifts it early.
**`ops` can never be muted.**

## Status contract

`send` returns `(status, response)` and never raises.

| status | meaning |
|---|---|
| `sent` | left the box; response is Pushover's JSON |
| `muted` | a policy mute swallowed it on purpose |
| `dry_run` | nothing sent; response is the payload minus secrets |
| `disabled` | no credentials; nothing sent |
| `failed` | transport error; response is `ExcType: message` |

`sent` must only ever mean delivered, because Trader gates database writes on
it. Retry latches use `pharos.delivered(status)` (sent or muted), so a mute
window doesn't queue months of retries that all fire on the day it lifts.

## Ledger

Every real attempt (not dry runs) from either language is appended to
`logs/pushes.jsonl`: time, source, channel, priority, status, final title and
message. It rotates at 5 MB.

```bash
py -3.11 -m pharos --recent 20
```

## Config

Credentials: `PHAROS_PUSHOVER_USER_KEY` / `PHAROS_PUSHOVER_APP_TOKEN`, else
`config.json` (gitignored, live credentials, never overwritten by the
installer). `PHAROS_CONFIG`, `PHAROS_POLICY`, `PHAROS_LOG` override the file
paths (the tests use them).

```powershell
powershell -File C:\path\to\Pharos\pharos.ps1 -Check   # masked config + active mutes
```

## Priority

Pushover's scale: `-2` silent, `-1` quiet, `0` normal, `1` bypasses quiet hours,
`2` emergency (repeats until acknowledged). Priority 2 gets `retry=60` and
`expire=3600` by default, because Pushover rejects priority 2 without them.

## Callers

| project | how |
|---|---|
| Trader | `notifications.send_pushover` → `pharos.send(source="trader", channel=...)` |
| claude-rc | `Send-Alert` → `Send-Pharos -Source <project> -Channel ops -Hold` (machine-wide alerts: `claude-rc`, default app); each tick runs `Invoke-PharosFlush` |
