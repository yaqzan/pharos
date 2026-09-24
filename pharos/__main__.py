"""CLI: `py -3.11 -m pharos --source x --title y --message z`.

For scheduled tasks, .bat files, hooks, or a language with no binding.
Exit codes: 0 sent / muted / dry_run, 1 failed, 2 disabled.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .push import config_summary, enabled, recent, send

_EXIT_CODES = {"sent": 0, "muted": 0, "dry_run": 0, "disabled": 2, "failed": 1}


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="pharos", description="Send one push notification.")
    parser.add_argument("--title", default="")
    parser.add_argument("--message", default="")
    parser.add_argument(
        "--message-file",
        help="Read the body from this file. Use it for anything multi-line or "
        "quote-heavy: long inline arguments are how quoting bugs get shipped.",
    )
    parser.add_argument("--source", help="Project name. Prefixed to the title.")
    parser.add_argument("--channel", help="policy.json channel (default ops).")
    parser.add_argument("--priority", type=int, default=0, choices=[-2, -1, 0, 1, 2])
    parser.add_argument("--url")
    parser.add_argument("--url-title")
    parser.add_argument("--sound")
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true", help="Print masked config, send nothing.")
    parser.add_argument("--recent", type=int, metavar="N", help="Print the last N ledger entries.")
    parser.add_argument("--flush", action="store_true", help="Deliver pushes held through a network outage.")
    parser.add_argument("--hold", action="store_true", help="On a network failure, hold the push and deliver it late.")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.check:
        print(json.dumps(config_summary(), indent=2, ensure_ascii=False))
        return 0 if enabled() else 2
    if args.flush:
        from .outbox import flush, pending
        print(json.dumps({**flush(), "still_held": pending()}))
        return 0
    if args.recent:
        for entry in recent(args.recent):
            print(json.dumps(entry, ensure_ascii=False))
        return 0
    if not args.title:
        parser.error("--title is required unless --check or --recent is given")

    message = args.message
    if args.message_file:
        with open(args.message_file, "r", encoding="utf-8-sig") as handle:
            message = handle.read()

    result = send(
        args.title,
        message,
        source=args.source,
        channel=args.channel,
        priority=args.priority,
        url=args.url,
        url_title=args.url_title,
        html=args.html,
        sound=args.sound,
        dry_run=args.dry_run,
        hold=args.hold,
    )
    print(f"[{result.status}] {result.response}")
    return _EXIT_CODES.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
