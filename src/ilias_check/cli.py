"""Command-line interface for ILIAS-Check."""

from __future__ import annotations

import argparse
import json
import sys

from ilias_check.collector import collect_inventory
from ilias_check.config import CollectorConfig, ConfigurationError

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ilias-check",
        description="Collect a bounded, read-only ILIAS repository inventory.",
    )
    subparsers = parser.add_subparsers(dest="command")
    collect = subparsers.add_parser(
        "collect", help="collect repository metadata as JSON"
    )
    collect.add_argument(
        "--env-file",
        metavar="PATH",
        help="explicit dotenv file (no automatic .env discovery)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        config = CollectorConfig.from_environment(env_file=args.env_file)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        inventory = collect_inventory(config)
    except Exception:
        # Do not print exception representations; transports and libraries can
        # include full URLs, response fragments, cookies, or credential values.
        print("Fatal collection error: the inventory could not be created.", file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    complete_roots = sum(1 for item in inventory["coverage"] if item["complete"])
    if complete_roots == len(inventory["coverage"]):
        return 0
    if complete_roots:
        print("Collection incomplete: one or more roots need verification.", file=sys.stderr)
        return 2
    print("Collection failed: no configured root was confirmed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
