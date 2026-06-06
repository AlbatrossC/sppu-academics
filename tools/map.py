"""Build or refresh Google Drive folder ID mapping."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from common.drive_client import GoogleDriveClient
from common.logger import setup_logging
from common.mapping import build_mapping, folder_count, refresh_mapping, refresh_selected_branches, save_mapping
from common.utils import ConfigError, ensure_project_dirs, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or refresh Google Drive folder mapping.")
    parser.add_argument("command", choices=["build", "refresh"], help="Mapping operation to run.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument("--save-every", type=int, default=25, help="Checkpoint sync_mapping.json after this many folders.")
    parser.add_argument(
        "--branch",
        action="append",
        default=[],
        help="Refresh only this top-level branch. Can be used multiple times.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.verbose)
    ensure_project_dirs()

    try:
        config = load_config()
        client = GoogleDriveClient(
            timeout=config["request_timeout"],
            max_retries=config["max_retries"],
            backoff_factor=config["backoff_factor"],
            logger=logger,
        )
        last_checkpoint = 0

        def checkpoint(mapping_data: dict[str, Any]) -> None:
            nonlocal last_checkpoint
            current_count = folder_count(mapping_data)
            if args.save_every > 0 and current_count - last_checkpoint >= args.save_every:
                save_mapping(mapping_data)
                last_checkpoint = current_count
                logger.info("Checkpoint saved to mapping/sync_mapping.json at %d folders.", current_count)

        if args.branch:
            logger.info("Running selected branch refresh for: %s", ", ".join(args.branch))
            mapping, new_paths = refresh_selected_branches(
                client,
                config["root_folder_id"],
                args.branch,
                logger=logger,
                on_progress=checkpoint,
            )
            logger.info("Selected branch refresh finished with %d folders; %d new.", folder_count(mapping), len(new_paths))
            for path in new_paths:
                logger.info("New folder: %s", path)
        elif args.command == "build":
            logger.info("Running map build. Progress will be printed as folders are scanned.")
            mapping = build_mapping(client, config["root_folder_id"], logger=logger, on_progress=checkpoint)
            save_mapping(mapping)
            logger.info("Mapping built with %d folders.", folder_count(mapping))
        else:
            logger.info("Running map refresh. Progress will be printed as folders are scanned.")
            mapping, new_paths = refresh_mapping(client, config["root_folder_id"], logger=logger, on_progress=checkpoint)
            logger.info("Mapping refreshed with %d folders; %d new.", folder_count(mapping), len(new_paths))
            for path in new_paths:
                logger.info("New folder: %s", path)
        return 0
    except (ConfigError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
