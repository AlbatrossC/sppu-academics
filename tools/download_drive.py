"""Download files from sync_plan.json and update manifests."""

from __future__ import annotations

import argparse
import sys

from common.downloader import DownloadPlanError, execute_sync_plan
from common.drive_client import GoogleDriveClient
from common.logger import setup_logging
from common.utils import ConfigError, ensure_project_dirs, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download files listed in sync_plan.json.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.verbose)
    ensure_project_dirs()

    try:
        config = load_config(require_root=False)
        client = GoogleDriveClient(
            timeout=config["request_timeout"],
            max_retries=config["max_retries"],
            backoff_factor=config["backoff_factor"],
            logger=logger,
        )
        downloaded = execute_sync_plan(client, logger)
        logger.info("Downloaded %d files and updated manifest.", downloaded)
        return 0
    except (ConfigError, DownloadPlanError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
