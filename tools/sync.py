"""Create sync plans and review folder mapping changes."""

from __future__ import annotations

import argparse
import sys

from common.drive_client import GoogleDriveClient
from common.file_sync import RateLimitDetected, apply_file_changes, discard_file_changes, review_file_changes
from common.folder_sync import apply_folder_changes, discard_folder_changes, review_folder_changes
from common.logger import setup_logging
from common.mapping import load_mapping
from common.planner import create_sync_plan
from common.utils import ConfigError, ensure_project_dirs, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review-first sync CLI for folder mappings and Drive PDF downloads.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Common commands:
  python3 tools/sync.py
      Create the legacy read-only PDF sync plan at sync_plan/sync_plan.json.

  python3 tools/sync.py --folders
      Review all Drive folder additions/removals into changelog/folder.md.

  python3 tools/sync.py --folders "Computer Engineering/TE"
      Review only one folder scope and its descendants.

  python3 tools/sync.py --folders --apply
      Apply reviewed folder changes from changelog/folder.md. Does not call Drive.

  python3 tools/sync.py --folders --discard
      Clear pending folder changes without editing mapping JSON files.

  python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
      Review new PDF files for one scope into changelog/files.md.

  python3 tools/sync.py --files "Artificial Intelligence and Data Science" --workers 4
      Review new PDF files with parallel subject scans.

  python3 tools/sync.py --files --apply
      Download reviewed pending files into incoming/ and update tracking/manifest.db.

  python3 tools/sync.py --files --apply --gdown --download-delay 5
      Use gdown instead of the official Drive API for reviewed downloads, with throttling.

  python3 tools/sync.py --files --apply --rclone --workers 8
      Use rclone copyurl bulk mode for reviewed downloads.

  python3 tools/sync.py --files --apply --max-downloads 100 --workers 1 --download-delay 3
      Download a smaller batch and leave the rest pending.

Mapping families:
  Standard branches: Branch / Year / Pattern / Subject
      mapping/sync_mapping.json
      tracking/manifest.db

  First Year: First Year / Pattern / Subject
      mapping/first_year_mapping.json
      tracking/manifest.db

  MBA: M.B.A / Semester / Pattern / Subject
      mapping/mba.json
      tracking/manifest.db

  Honors Course: Honors Course / Year / Subject
      mapping/honors_course_mapping.json
      tracking/manifest.db

Review files:
  changelog/folder.md and changelog/files.md contain human tables plus machine-readable JSON blocks.
  Apply/discard commands read those JSON blocks. Do not delete the marker comments.
""",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument(
        "--folders",
        "--folder",
        dest="folders",
        action="store_true",
        help="Review folder mapping changes instead of creating the PDF sync plan.",
    )
    parser.add_argument(
        "--files",
        "--file",
        dest="files",
        action="store_true",
        help="Review Drive PDF file changes against tracking/manifest.db.",
    )
    parser.add_argument(
        "scope",
        nargs="?",
        help='Optional path scope for --folders or --files, for example "Computer Engineering".',
    )
    parser.add_argument("--apply", action="store_true", help="Apply pending changes from the relevant changelog review file.")
    parser.add_argument(
        "--discard",
        nargs="*",
        metavar="PATH_OR_ID",
        help="Discard pending changes from the relevant changelog review file. Omit values to discard all.",
    )
    parser.add_argument(
        "--gdown",
        action="store_true",
        help="Use gdown for --files --apply downloads instead of the official Drive API.",
    )
    parser.add_argument(
        "--rclone",
        action="store_true",
        help="Use rclone copyurl bulk mode for --files --apply downloads.",
    )
    parser.add_argument(
        "--download-delay",
        type=float,
        default=0,
        help="Seconds to wait between file downloads during --files --apply.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent workers for --files review scans and --files --apply downloads.",
    )
    parser.add_argument(
        "--max-downloads",
        type=int,
        default=0,
        help="Maximum pending files to download in this apply run. 0 means no limit.",
    )
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    folder_actions = sum(bool(value) for value in (args.apply, args.discard is not None))
    if args.folders and args.files:
        raise ValueError("Use only one review mode at a time: --folders or --files")
    if folder_actions and not (args.folders or args.files):
        raise ValueError("--apply and --discard are only valid with --folders or --files")
    if folder_actions > 1:
        raise ValueError("Use only one review action at a time: --apply or --discard")
    if args.scope and not (args.folders or args.files):
        raise ValueError("A path scope is only valid with --folders or --files")
    if args.gdown and not (args.files and args.apply):
        raise ValueError("--gdown is only valid with --files --apply")
    if args.rclone and not (args.files and args.apply):
        raise ValueError("--rclone is only valid with --files --apply")
    if args.gdown and args.rclone:
        raise ValueError("Use only one downloader at a time: --gdown or --rclone")
    if args.download_delay < 0:
        raise ValueError("--download-delay must be zero or greater")
    if args.max_downloads < 0:
        raise ValueError("--max-downloads must be zero or greater")


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.verbose)
    ensure_project_dirs()

    try:
        _validate_args(args)
        config = load_config(require_root=False)
        if args.folders and args.apply:
            result = apply_folder_changes(config["root_folder_id"])
            logger.info("Applied %d folder changes.", result["applied"])
            return 0

        if args.files and args.apply:
            client = None
            if not args.gdown and not args.rclone:
                client = GoogleDriveClient(
                    timeout=config["request_timeout"],
                    max_retries=config["max_retries"],
                    backoff_factor=config["backoff_factor"],
                    logger=logger,
                )
            downloader = "rclone" if args.rclone else "gdown" if args.gdown else "drive"
            result = apply_file_changes(
                client, 
                logger, 
                downloader=downloader, 
                download_delay=args.download_delay,
                workers=args.workers,
                max_downloads=args.max_downloads or None,
            )
            logger.info("Downloaded %d files; %d pending remain.", result["downloaded"], result["remaining"])
            return 0

        if args.folders and args.discard is not None:
            result = discard_folder_changes(args.discard)
            logger.info("Discarded %d folder changes; %d remaining.", result["discarded"], result["remaining"])
            return 0

        if args.files and args.discard is not None:
            result = discard_file_changes(args.discard)
            logger.info("Discarded %d file changes; %d remaining.", result["discarded"], result["remaining"])
            return 0

        if args.folders:
            if not config["root_folder_id"]:
                raise ConfigError("config.json is missing root_folder_id. Folder review needs the Drive root folder ID.")
            client = GoogleDriveClient(
                timeout=config["request_timeout"],
                max_retries=config["max_retries"],
                backoff_factor=config["backoff_factor"],
                logger=logger,
            )
            payload = review_folder_changes(client, config["root_folder_id"], args.scope)
            logger.info("Folder review generated with %d pending changes.", len(payload.get("changes", [])))
            return 0

        if args.files:
            client = GoogleDriveClient(
                timeout=config["request_timeout"],
                max_retries=config["max_retries"],
                backoff_factor=config["backoff_factor"],
                logger=logger,
            )
            payload = review_file_changes(client, args.scope, logger=logger, workers=args.workers)
            logger.info("File review generated with %d pending files.", len(payload.get("changes", [])))
            return 0

        mapping = load_mapping()
        client = GoogleDriveClient(
            timeout=config["request_timeout"],
            max_retries=config["max_retries"],
            backoff_factor=config["backoff_factor"],
            logger=logger,
        )
        plan = create_sync_plan(client, mapping)
        logger.info("Sync plan generated with %d downloads.", len(plan.get("download", [])))
        return 0
    except RateLimitDetected as exc:
        logger.error("%s", exc)
        return 2
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
