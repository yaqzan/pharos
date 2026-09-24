# Pharos

Machine-wide push notifications (Pushover). Every project on this box pages the owner through
here; no project keeps its own transport. Usage, channels, mutes, status contract:
[README.md](README.md).

## Layout

- `pharos/push.py` -- Python binding (stdlib only). `pharos/__main__.py` -- CLI.
- `pharos/incident.py` -- page-on-change for recurring checks; state in `state/` (gitignored).
  Trader's heartbeat uses it. Python only.
- `pharos/outbox.py` + `Invoke-PharosFlush` -- pushes held through a network outage (`hold=True` /
  `-Hold`), delivered late with `Held <span>`. Same `state/outbox.jsonl` format in both bindings;
  `tests/test_outbox.py` proves cross-language delivery against a local fake Pushover.
  Never for Trader (it re-sends itself).
- `icons/` -- 128x128 Pushover app icons per source, built from each project's own icon by
  `icons/build_icons.py`; `draw_pharos.py` / `draw_archivist.py` / `draw_vesper.py` / `draw_spore.py` / `draw_gleaner.py` / `draw_arbiter.py` draw the
  lighthouse, temple, moonlit mic, crystal mushrooms, Gleaner's transcript play button and Arbiter's laurelled reel
  (owner-approved designs, keep them).
  Per-source app tokens: `config.json` `pushover.apps`; the default `app_token` is the Pharos app.
- **Pushes are sourced by the project they are about**, not by the tool that noticed. claude-rc
  sends a Vesper session alert as `source="vesper"` so it wears the Vesper icon.
- `Pharos.psm1` / `pharos.ps1` -- PowerShell binding + CLI. **ASCII only** (PS 5.1 reads BOM-less
  UTF-8 as ANSI); glyphs are read from `policy.json`, never written into a `.ps1`/`.psm1`.
- `policy.json` -- channels (glyph, mutable) and mutes. Tracked. The single source of truth for
  both languages.
- `config.json` -- live Pushover credentials. Gitignored. The installer never overwrites it.
- `logs/pushes.jsonl` -- push ledger, every real attempt from both bindings.
- `install.ps1` -- writes `pharos.pth` into Python 3.11 site-packages. Dry-run unless `-Apply`.
- `.retired/` -- backup of the pre-Pharos `_ops\notify` package (2026-09-22). Gitignored.

## Commands

```bash
py -3.11 -m pytest tests -q          # includes the Python/PowerShell parity test
py -3.11 -m pharos --check           # masked config + active mutes
py -3.11 -m pharos --recent 20       # ledger tail
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 [-Apply]
```

## Invariants

- **Never raises / never throws.** Alerting must not break the job it watches. Missing
  credentials -> `disabled`, broken policy -> falls back to ops-only, ledger write errors are
  swallowed.
- **`sent` means it left the box.** Trader gates DB writes on it. Don't return `sent` for anything
  else; a new "settled but not sent" state goes in `delivered()` too.
- **`ops` is never mutable.** A dead pipeline must always reach the phone. `active_mute` ignores
  non-mutable channels even if a rule lists them.
- **Both bindings behave identically.** Any change to title shape, mute logic or statuses lands in
  `push.py` AND `Pharos.psm1` in the same edit; `test_powershell_binding_matches_python` fails
  otherwise.
- **Push wording follows README "Writing a push"** (owner's rules, 2026-09-22): no project name in
  the headline, one short body line, relative times via `ago()`/`span()`, never a command or
  instruction. Apply it to every caller you touch. Callers never hand-roll the channel glyph.
- Project-specific policy (like Trader's embargo) is a `mutes` entry in `policy.json`, not code in
  the caller.
- No real pushes from tests: they point `PHAROS_CONFIG` at a missing file.
- **Recurring checks use `incident()`, never bare `send()` per run.** Re-paging the same red check
  every 30 min is the 2026-09-22 spam this exists to prevent.
- Folder was `C:\Development\Tocsin` until 2026-09-22 (renamed; `install.ps1` retires `tocsin.pth`).
