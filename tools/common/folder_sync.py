"""Folder mapping review, apply, and discard helpers."""

from __future__ import annotations

import json
from typing import Any

from common.drive_client import GoogleDriveClient
from common.mapping import (
    MBA_BRANCH,
    FIRST_YEAR_BRANCH,
    build_first_year_mapping,
    build_mapping,
    build_mba_mapping,
    build_special_case_mapping,
    empty_mapping,
    normalize_mapping,
)
from common.utils import PROJECT_ROOT, MAPPING_PATH, read_json, utc_now_iso, write_json


FOLDER_CHANGELOG_PATH = PROJECT_ROOT / "changelog" / "folder.md"
SYNC_MAPPING_FILE = "sync_mapping.json"
FIRST_YEAR_MAPPING_FILE = "first_year_mapping.json"
MBA_MAPPING_FILE = "mba.json"
HONORS_MAPPING_FILE = "honors_course_mapping.json"
HONORS_BRANCH = "Honors Course"
BEGIN_PENDING = "<!-- FOLDER_SYNC_PENDING_BEGIN -->"
END_PENDING = "<!-- FOLDER_SYNC_PENDING_END -->"


def _folder_record(folder_id: str, parent_id: str, path: str) -> dict[str, str]:
    return {"folder_id": folder_id, "parent_id": parent_id, "path": path}


def _all_entries(mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for branch in (mapping.get("branches") or {}).values():
        if branch.get("path"):
            entries[branch["path"]] = _folder_record(branch.get("folder_id", ""), branch.get("parent_id", ""), branch["path"])
        for year in (branch.get("years") or {}).values():
            if year.get("path"):
                entries[year["path"]] = _folder_record(year.get("folder_id", ""), year.get("parent_id", ""), year["path"])
            for pattern in (year.get("patterns") or {}).values():
                if pattern.get("path"):
                    entries[pattern["path"]] = _folder_record(pattern.get("folder_id", ""), pattern.get("parent_id", ""), pattern["path"])
                for subject in (pattern.get("subjects") or {}).values():
                    if subject.get("path"):
                        entries[subject["path"]] = _folder_record(subject.get("folder_id", ""), subject.get("parent_id", ""), subject["path"])
    for path, exception in (mapping.get("exceptions") or {}).items():
        if isinstance(exception, dict):
            entries[path] = _folder_record(exception.get("folder_id", ""), exception.get("parent_id", ""), path)
    return entries


def _raw_entries(mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        path: _folder_record(meta.get("folder_id", ""), meta.get("parent_id", ""), path)
        for path, meta in (mapping.get("folders") or {}).items()
        if isinstance(meta, dict)
    }


def _first_year_entries(mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    if mapping.get("path"):
        entries[mapping["path"]] = _folder_record(mapping.get("folder_id", ""), mapping.get("parent_id", ""), mapping["path"])
    for pattern in (mapping.get("patterns") or {}).values():
        if pattern.get("path"):
            entries[pattern["path"]] = _folder_record(pattern.get("folder_id", ""), pattern.get("parent_id", ""), pattern["path"])
        for subject in (pattern.get("subjects") or {}).values():
            if subject.get("path"):
                entries[subject["path"]] = _folder_record(subject.get("folder_id", ""), subject.get("parent_id", ""), subject["path"])
    for path, exception in (mapping.get("exceptions") or {}).items():
        if isinstance(exception, dict):
            entries[path] = _folder_record(exception.get("folder_id", ""), exception.get("parent_id", ""), path)
    return entries


def _mba_entries(mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    if mapping.get("path"):
        entries[mapping["path"]] = _folder_record(mapping.get("folder_id", ""), mapping.get("parent_id", ""), mapping["path"])
    for semester in (mapping.get("semesters") or {}).values():
        if semester.get("path"):
            entries[semester["path"]] = _folder_record(semester.get("folder_id", ""), semester.get("parent_id", ""), semester["path"])
        for pattern in (semester.get("patterns") or {}).values():
            if pattern.get("path"):
                entries[pattern["path"]] = _folder_record(pattern.get("folder_id", ""), pattern.get("parent_id", ""), pattern["path"])
            for subject in (pattern.get("subjects") or {}).values():
                folder_path = subject.get("drive_path") or subject.get("path")
                if folder_path:
                    entries[folder_path] = _folder_record(subject.get("folder_id", ""), subject.get("parent_id", ""), folder_path)
    return entries


def _entries_for_mapping_file(filename: str, mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    if filename == SYNC_MAPPING_FILE:
        return _all_entries(mapping)
    if filename == FIRST_YEAR_MAPPING_FILE:
        return _first_year_entries(mapping)
    if filename == MBA_MAPPING_FILE:
        return _mba_entries(mapping)
    if filename == HONORS_MAPPING_FILE:
        return _raw_entries(mapping)
    return {}


def _mapping_file_for_path(path: str) -> str:
    first_part = path.split("/", 1)[0]
    if first_part == FIRST_YEAR_BRANCH:
        return FIRST_YEAR_MAPPING_FILE
    if first_part == MBA_BRANCH:
        return MBA_MAPPING_FILE
    if first_part == HONORS_BRANCH:
        return HONORS_MAPPING_FILE
    return SYNC_MAPPING_FILE


def _project_mapping_files(mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    root_folder_id = str((mapping.get("root") or {}).get("folder_id", ""))
    entries = _all_entries(mapping)
    return {
        SYNC_MAPPING_FILE: normalize_mapping(mapping),
        FIRST_YEAR_MAPPING_FILE: build_first_year_mapping(entries, root_folder_id),
        MBA_MAPPING_FILE: build_mba_mapping(entries, root_folder_id),
        HONORS_MAPPING_FILE: build_special_case_mapping(HONORS_BRANCH, entries, root_folder_id),
    }


def _load_current_mapping_files(root_folder_id: str) -> dict[str, dict[str, Any]]:
    mapping_dir = MAPPING_PATH.parent
    files = {
        SYNC_MAPPING_FILE: read_json(mapping_dir / SYNC_MAPPING_FILE, default=empty_mapping(root_folder_id)),
        FIRST_YEAR_MAPPING_FILE: read_json(mapping_dir / FIRST_YEAR_MAPPING_FILE, default={}),
        MBA_MAPPING_FILE: read_json(mapping_dir / MBA_MAPPING_FILE, default={}),
        HONORS_MAPPING_FILE: read_json(mapping_dir / HONORS_MAPPING_FILE, default={}),
    }
    return {filename: data or {} for filename, data in files.items()}


def _path_in_scope(path: str, scope: str | None) -> bool:
    if not scope:
        return True
    return path == scope or path.startswith(f"{scope}/")


def _scan_drive_mapping(client: GoogleDriveClient, root_folder_id: str, scope: str | None) -> dict[str, Any]:
    if not scope:
        return build_mapping(client, root_folder_id)

    root_folders = {folder["name"]: folder for folder in client.list_folders(root_folder_id)}
    branch_name = scope.split("/", 1)[0]
    branch = root_folders.get(branch_name)
    if not branch:
        raise ValueError(f"Could not find top-level Drive folder: {branch_name}")

    mapping = empty_mapping(root_folder_id)
    mapping.setdefault("branches", {})[branch_name] = _folder_record(branch["id"], root_folder_id, branch_name) | {"years": {}}
    for child_path, folder_id, parent_id in client.walk_folders(branch["id"]):
        full_path = f"{branch_name}/{child_path}"
        if _path_in_scope(full_path, scope) or full_path.startswith(f"{scope}/") or scope.startswith(f"{full_path}/"):
            from common.mapping import add_folder

            add_folder(mapping, full_path, folder_id, parent_id)
    return mapping


def _build_changes(
    current_files: dict[str, dict[str, Any]],
    discovered_files: dict[str, dict[str, Any]],
    scope: str | None,
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for filename, discovered_mapping in discovered_files.items():
        current_entries = _entries_for_mapping_file(filename, current_files.get(filename, {}))
        discovered_entries = _entries_for_mapping_file(filename, discovered_mapping)
        current_paths = {path for path in current_entries if _path_in_scope(path, scope)}
        discovered_paths = {path for path in discovered_entries if _path_in_scope(path, scope)}

        for path in sorted(discovered_paths - current_paths):
            meta = discovered_entries[path]
            changes.append(
                {
                    "action": "add",
                    "mapping_file": filename,
                    "path": path,
                    "folder_id": meta.get("folder_id", ""),
                    "parent_id": meta.get("parent_id", ""),
                }
            )
        for path in sorted(current_paths - discovered_paths):
            meta = current_entries[path]
            changes.append(
                {
                    "action": "remove",
                    "mapping_file": filename,
                    "path": path,
                    "folder_id": meta.get("folder_id", ""),
                    "parent_id": meta.get("parent_id", ""),
                }
            )
    return changes


def _pending_payload(changes: list[dict[str, str]], scope: str | None = None) -> dict[str, Any]:
    return {"generated_at": utc_now_iso(), "scope": scope or "all", "changes": changes}


def _render_folder_changelog(payload: dict[str, Any]) -> str:
    changes = payload.get("changes", [])
    lines = [
        "# Folder Mapping Review",
        "",
        "This file is generated by `python3 tools/sync.py --folders`.",
        "Review the pending folder changes below, then use `--apply` or `--discard`.",
        "",
        f"- Generated at: `{payload.get('generated_at', '')}`",
        f"- Scope: `{payload.get('scope', 'all')}`",
        f"- Pending changes: `{len(changes)}`",
        "",
    ]
    if changes:
        lines.extend(["| Action | Mapping file | Folder path | Folder ID |", "| --- | --- | --- | --- |"])
        for change in changes:
            lines.append(
                f"| {change['action']} | `{change['mapping_file']}` | `{change['path']}` | `{change.get('folder_id', '')}` |"
            )
        lines.append("")
    else:
        lines.extend(["No folder changes are pending.", ""])

    lines.extend(
        [
            BEGIN_PENDING,
            "```json",
            json.dumps(payload, indent=2, ensure_ascii=False),
            "```",
            END_PENDING,
            "",
        ]
    )
    return "\n".join(lines)


def _change_key(change: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        change.get("action", ""),
        change.get("mapping_file", ""),
        change.get("path", ""),
        change.get("folder_id", ""),
    )


def _append_unique_changes(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = {_change_key(change) for change in existing}
    combined = list(existing)
    for change in incoming:
        key = _change_key(change)
        if key not in seen:
            combined.append(change)
            seen.add(key)
    return combined


def write_folder_changelog(changes: list[dict[str, str]], scope: str | None = None, append_pending: bool = False) -> dict[str, Any]:
    if append_pending and FOLDER_CHANGELOG_PATH.exists():
        try:
            existing_payload = read_folder_changelog()
            changes = _append_unique_changes(existing_payload.get("changes") or [], changes)
        except (json.JSONDecodeError, ValueError):
            pass
    payload = _pending_payload(changes, scope)
    FOLDER_CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    FOLDER_CHANGELOG_PATH.write_text(_render_folder_changelog(payload), encoding="utf-8")
    return payload


def read_folder_changelog() -> dict[str, Any]:
    if not FOLDER_CHANGELOG_PATH.exists():
        raise FileNotFoundError("changelog/folder.md does not exist. Run: python3 tools/sync.py --folders")
    text = FOLDER_CHANGELOG_PATH.read_text(encoding="utf-8")
    start = text.rfind(BEGIN_PENDING)
    end = text.rfind(END_PENDING)
    if start == -1 or end == -1 or end <= start:
        raise ValueError("changelog/folder.md is missing the pending JSON block.")
    block = text[start:end]
    json_start = block.find("```json")
    if json_start == -1:
        raise ValueError("changelog/folder.md is missing the pending JSON fence.")
    json_text = block[json_start + len("```json") :]
    json_end = json_text.find("```")
    if json_end == -1:
        raise ValueError("changelog/folder.md has an unterminated pending JSON fence.")
    return json.loads(json_text[:json_end].strip())


def review_folder_changes(client: GoogleDriveClient, root_folder_id: str, scope: str | None = None) -> dict[str, Any]:
    current_files = _load_current_mapping_files(root_folder_id)
    discovered_mapping = _scan_drive_mapping(client, root_folder_id, scope)
    discovered_files = _project_mapping_files(discovered_mapping)
    changes = _build_changes(current_files, discovered_files, scope)
    return write_folder_changelog(changes, scope, append_pending=True)


def _root_folder_id_from_file(mapping: dict[str, Any], fallback: str) -> str:
    return str((mapping.get("root") or {}).get("folder_id", "") or fallback)


def _write_entries_for_file(filename: str, entries: dict[str, dict[str, str]], root_folder_id: str) -> None:
    target = MAPPING_PATH.parent / filename
    source = {"root": {"folder_id": root_folder_id}, "folders": entries}
    if filename == SYNC_MAPPING_FILE:
        write_json(target, normalize_mapping(source))
    elif filename == FIRST_YEAR_MAPPING_FILE:
        write_json(target, build_first_year_mapping(entries, root_folder_id))
    elif filename == MBA_MAPPING_FILE:
        write_json(target, build_mba_mapping(entries, root_folder_id))
    elif filename == HONORS_MAPPING_FILE:
        write_json(target, build_special_case_mapping(HONORS_BRANCH, entries, root_folder_id))
    else:
        raise ValueError(f"Unknown mapping file: {filename}")


def apply_folder_changes(root_folder_id: str = "") -> dict[str, Any]:
    payload = read_folder_changelog()
    changes = payload.get("changes") or []
    if not changes:
        return {"applied": 0, "remaining": 0}

    grouped: dict[str, list[dict[str, str]]] = {}
    for change in changes:
        grouped.setdefault(change["mapping_file"], []).append(change)

    applied = 0
    for filename, file_changes in grouped.items():
        path = MAPPING_PATH.parent / filename
        current = read_json(path, default={}) or {}
        file_root_id = _root_folder_id_from_file(current, root_folder_id)
        entries = _entries_for_mapping_file(filename, current)
        for change in file_changes:
            folder_path = change["path"]
            if change["action"] == "add":
                entries[folder_path] = _folder_record(change.get("folder_id", ""), change.get("parent_id", ""), folder_path)
                applied += 1
            elif change["action"] == "remove":
                entries = {
                    path_key: meta
                    for path_key, meta in entries.items()
                    if path_key != folder_path and not path_key.startswith(f"{folder_path}/")
                }
                applied += 1
        _write_entries_for_file(filename, entries, file_root_id)

    write_folder_changelog([], payload.get("scope") if payload.get("scope") != "all" else None)
    return {"applied": applied, "remaining": 0}


def discard_folder_changes(identifiers: list[str] | None = None) -> dict[str, Any]:
    payload = read_folder_changelog()
    changes = payload.get("changes") or []
    if not changes:
        return {"discarded": 0, "remaining": 0}

    identifiers = identifiers or []
    if not identifiers:
        discarded = len(changes)
        remaining_changes: list[dict[str, str]] = []
    else:
        wanted = set(identifiers)
        remaining_changes = [
            change
            for change in changes
            if change.get("path") not in wanted and change.get("folder_id") not in wanted
        ]
        discarded = len(changes) - len(remaining_changes)

    payload["changes"] = remaining_changes
    payload["generated_at"] = utc_now_iso()
    FOLDER_CHANGELOG_PATH.write_text(_render_folder_changelog(payload), encoding="utf-8")
    return {"discarded": discarded, "remaining": len(remaining_changes)}
