"""Command-line interface for ILIAS-Check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ilias_check.collector import collect_inventory
from ilias_check.cache_config import CacheError
from ilias_check.telegram import TelegramConfig
from ilias_check.monitor import run_monitor
from ilias_check.bot import run_bot
from ilias_check.config import CollectorConfig, ConfigurationError, load_environment
from ilias_check.policy import ClassificationPolicy, PolicyError
from ilias_check.progress import Progress
from ilias_check.results import SELECTIONS, classify_inventory, select_activities

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
    collect.add_argument("--select", choices=SELECTIONS, default="all", help="activity category (full coverage and counts are retained)")
    collect.add_argument(
        "--progress",
        action="store_true",
        help="write low-noise extraction progress to stderr",
    )
    classify = subparsers.add_parser("classify", help="classify a saved inventory without network access")
    classify.add_argument("--input", required=True, type=Path, help="saved inventory JSON")
    classify.add_argument("--env-file", metavar="PATH", help="optional explicit file with classification settings")
    classify.add_argument("--select", choices=SELECTIONS, default="all", help="activity category")
    monitor = subparsers.add_parser("monitor", help="one-shot check with durable opt-in notifications")
    monitor.add_argument("--env-file", metavar="PATH")
    monitor.add_argument("--dry-run", action="store_true", help="preview without sending or acknowledging events")
    monitor.add_argument(
        "--progress",
        action="store_true",
        help="write low-noise extraction progress to stderr",
    )
    bot = subparsers.add_parser("bot", help="authorized private-chat long-poll worker")
    bot.add_argument("--env-file", metavar="PATH")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command in {"collect", "monitor", "bot"}:
            config = CollectorConfig.from_environment(env_file=args.env_file)
            if args.command in {"monitor", "bot"}:
                telegram = TelegramConfig.from_mapping(load_environment(args.env_file), worker=args.command == "bot")
        else:
            policy = ClassificationPolicy.from_mapping(load_environment(args.env_file))
    except (ConfigurationError, PolicyError, CacheError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "bot":
            run_bot(config, telegram)
            return 0
        progress = Progress() if getattr(args, "progress", False) else None
        if args.command == "monitor":
            if progress is None:
                report = run_monitor(config, telegram, args.dry_run)
            else:
                report = run_monitor(
                    config,
                    telegram,
                    args.dry_run,
                    collector=lambda run_config: collect_inventory(
                        run_config, progress=progress
                    ),
                )
            sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            return 1 if report["fatal"] else 0 if report["complete"] else 2
        if args.command == "collect":
            inventory = collect_inventory(config, progress=progress)
        else:
            inventory = classify_inventory(json.loads(args.input.read_text(encoding="utf-8")), policy)
        inventory = select_activities(inventory, args.select)
    except KeyboardInterrupt:
        return 130
    except CacheError as exc:
        print(f"Runtime state error: {exc}", file=sys.stderr)
        return 3 if "Another process" in str(exc) else 1
    except Exception:
        # Do not print exception representations; transports and libraries can
        # include full URLs, response fragments, cookies, or credential values.
        print("Fatal inventory error: the inventory could not be read or created.", file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    complete_roots = sum(1 for item in inventory["coverage"] if item["complete"])
    if complete_roots == len(inventory["coverage"]) and inventory["classification"]["complete"]:
        return 0
    if complete_roots == len(inventory["coverage"]):
        print("Classification incomplete: one or more activities need verification.", file=sys.stderr)
        return 2
    if complete_roots or not all(root.get("error") for root in inventory["coverage"]):
        print("Collection incomplete: one or more roots need verification.", file=sys.stderr)
        return 2
    print("Collection failed: no configured root was confirmed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
