"""Read-only sync plan generation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from common.drive_client import GoogleDriveClient
from common.manifest import get_entry, local_file_exists
from common.mapping import iter_subject_folders
from common.utils import CHANGELOG_PATH, SYNC_PLAN_PATH, local_pdf_path, project_relative, split_folder_path, utc_now_iso, write_json


def create_sync_plan(client: GoogleDriveClient, mapping: dict[str, Any]) -> dict[str, Any]:
    """Create a read-only plan of PDFs that need downloading."""
    plan: dict[str, Any] = {"generated_at": utc_now_iso(), "download": []}

    for subject_folder in iter_subject_folders(mapping):
        folder_path = subject_folder["folder_path"]
        folder_id = subject_folder["folder_id"]
        subject = subject_folder["subject"]
        for drive_file in client.list_pdfs(folder_id):
            file_id = drive_file["id"]
            filename = drive_file["name"]
            modified_time = drive_file.get("modifiedTime", "")
            entry = get_entry(folder_path, subject, file_id)

            action: str | None = None
            if entry is None:
                action = "new"
            elif entry.get("modified_time") != modified_time:
                action = "updated"
            elif not local_file_exists(entry):
                action = "missing_local"

            if action:
                plan["download"].append(
                    {
                        "action": action,
                        "file_id": file_id,
                        "filename": filename,
                        "modified_time": modified_time,
                        "folder_path": folder_path,
                        "local_path": project_relative(local_pdf_path(folder_path, filename)),
                    }
                )

    write_json(SYNC_PLAN_PATH, plan)
    append_changelog(plan)
    return plan


def append_changelog(plan: dict[str, Any]) -> None:
    """Append a markdown summary for a generated sync plan."""
    CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CHANGELOG_PATH.exists():
        CHANGELOG_PATH.write_text("# Sync Changelog\n\n", encoding="utf-8")

    grouped: dict[str, list[str]] = defaultdict(list)
    for item in plan.get("download", []):
        grouped[item["action"]].append(f"{item['folder_path']}/{item['filename']}")

    title_map = {
        "new": "New Files",
        "updated": "Updated Files",
        "missing_local": "Missing Local Files",
    }
    date = str(plan.get("generated_at", ""))[:10]
    lines = [f"## {date}", ""]
    if not grouped:
        lines.extend(["No changes detected.", ""])
    else:
        for action in ("new", "updated", "missing_local"):
            paths = grouped.get(action, [])
            if not paths:
                continue
            lines.extend([f"### {title_map[action]}", ""])
            lines.extend(f"- {path}" for path in sorted(paths))
            lines.append("")

    with CHANGELOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")
