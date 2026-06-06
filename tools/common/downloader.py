"""Execute sync plans by downloading files and updating manifests."""

from __future__ import annotations

import logging
from typing import Any

from common.drive_client import GoogleDriveClient
from common.manifest import upsert_entry
from common.utils import SYNC_PLAN_PATH, local_pdf_path, project_relative, read_json


class DownloadPlanError(RuntimeError):
    """Raised when sync_plan.json is missing or invalid."""


def load_sync_plan() -> dict[str, Any]:
    """Load sync_plan/sync_plan.json."""
    plan = read_json(SYNC_PLAN_PATH, default=None)
    if not plan:
        raise DownloadPlanError("sync_plan/sync_plan.json is missing. Run: python3 tools/sync.py")
    if not isinstance(plan.get("download"), list):
        raise DownloadPlanError("sync_plan/sync_plan.json is invalid: download must be a list.")
    return plan


def execute_sync_plan(client: GoogleDriveClient, logger: logging.Logger | None = None) -> int:
    """Download every file in the current sync plan and update the manifest."""
    logger = logger or logging.getLogger(__name__)
    plan = load_sync_plan()
    downloaded = 0

    for item in plan.get("download", []):
        file_id = item["file_id"]
        filename = item["filename"]
        folder_path = item["folder_path"]
        modified_time = item.get("modified_time", "")
        destination = local_pdf_path(folder_path, filename)

        logger.info("Downloading %s/%s", folder_path, filename)
        client.download_file(file_id, destination)
        upsert_entry(
            folder_path=folder_path,
            file_id=file_id,
            filename=filename,
            modified_time=modified_time,
            local_path=project_relative(destination),
        )
        downloaded += 1

    return downloaded
