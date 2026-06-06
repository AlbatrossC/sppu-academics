"""Mapping store for Drive folder IDs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from common.drive_client import GoogleDriveClient
from common.utils import MAPPING_PATH, read_json, utc_now_iso, write_json


SPECIAL_CASE_BRANCH_FILES = {
    "First Year": "first_year_mapping.json",
    "Honors Course": "honors_course_mapping.json",
    "M.B.A": "mba.json",
}
FIRST_YEAR_BRANCH = "First Year"
MBA_BRANCH = "M.B.A"
EXCLUDED_YEAR_LEVELS = {"ME"}


def empty_mapping(root_folder_id: str) -> dict[str, Any]:
    """Return an empty mapping document."""
    return {
        "schema_version": 2,
        "generated_at": utc_now_iso(),
        "root": {"folder_id": root_folder_id},
        "branches": {},
        "exceptions": {},
    }


def load_mapping() -> dict[str, Any]:
    """Load mapping/sync_mapping.json."""
    mapping = read_json(MAPPING_PATH, default=None)
    if not mapping:
        raise FileNotFoundError("mapping/sync_mapping.json does not exist. Run: python3 tools/map.py build")
    return mapping


def save_mapping(mapping: dict[str, Any]) -> None:
    """Persist mapping/sync_mapping.json."""
    write_special_case_mappings(mapping)
    organized = normalize_mapping(mapping)
    organized["generated_at"] = utc_now_iso()
    write_json(MAPPING_PATH, organized)


def folder_count(mapping: dict[str, Any]) -> int:
    """Count mapped folders in the organized mapping structure."""
    return len(_all_entries(mapping))


def _folder_record(folder_id: str, parent_id: str, path: str) -> dict[str, str]:
    return {"folder_id": folder_id, "parent_id": parent_id, "path": path}


def _all_entries(mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Flatten any supported mapping schema to path-indexed folder metadata."""
    if "folders" in mapping:
        return {
            path: {"folder_id": str(meta.get("folder_id", "")), "parent_id": str(meta.get("parent_id", "")), "path": path}
            for path, meta in (mapping.get("folders") or {}).items()
            if isinstance(meta, dict)
        }

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
                        entries[subject["path"]] = _folder_record(
                            subject.get("folder_id", ""),
                            subject.get("parent_id", ""),
                            subject["path"],
                        )
    for path, exception in (mapping.get("exceptions") or {}).items():
        if isinstance(exception, dict):
            entries[path] = _folder_record(exception.get("folder_id", ""), exception.get("parent_id", ""), path)
    return entries


def _has_child(path: str, paths: set[str]) -> bool:
    prefix = f"{path}/"
    return any(candidate.startswith(prefix) for candidate in paths)


def _add_exception(mapping: dict[str, Any], folder_path: str, folder_id: str, parent_id: str, reason: str) -> None:
    parts = [part for part in folder_path.split("/") if part]
    mapping.setdefault("exceptions", {})[folder_path] = {
        "folder_id": folder_id,
        "parent_id": parent_id,
        "path": folder_path,
        "depth": len(parts),
        "parts": parts,
        "reason": reason,
    }


def _source_group_for_standardized_path(parts: list[str]) -> str:
    """Return removed middle path parts when flattening to standard format."""
    return " / ".join(parts[2:-2])


def _standardize_parts(parts: list[str]) -> tuple[str, str, str, str, str | None]:
    """Return branch/year/pattern/subject plus removed source group if present."""
    branch_name = parts[0]
    year_name = parts[1]
    if len(parts) > 4 and parts[-2].lower().endswith("pattern"):
        return branch_name, year_name, parts[-2], parts[-1], _source_group_for_standardized_path(parts)
    return branch_name, year_name, parts[2], parts[-1], None


def _unique_subject_name(pattern: dict[str, Any], subject_name: str, source_group: str | None, folder_id: str) -> str:
    """Avoid losing duplicate subjects created by standardizing extra-depth paths."""
    subjects = pattern.setdefault("subjects", {})
    existing = subjects.get(subject_name)
    if not existing or existing.get("folder_id") == folder_id:
        return subject_name
    if source_group:
        candidate = f"{subject_name} ({source_group})"
        if candidate not in subjects or subjects[candidate].get("folder_id") == folder_id:
            return candidate
    index = 2
    while True:
        candidate = f"{subject_name} ({index})"
        if candidate not in subjects or subjects[candidate].get("folder_id") == folder_id:
            return candidate
        index += 1


def _add_subject(
    mapping: dict[str, Any],
    branch_name: str,
    year_name: str,
    pattern_name: str,
    subject_name: str,
    folder_path: str,
    folder_id: str,
    parent_id: str,
) -> None:
    branch = mapping.setdefault("branches", {}).setdefault(
        branch_name,
        {"folder_id": "", "parent_id": "", "path": branch_name, "years": {}},
    )
    year_path = f"{branch_name}/{year_name}"
    year = branch.setdefault("years", {}).setdefault(
        year_name,
        {"folder_id": "", "parent_id": "", "path": year_path, "patterns": {}},
    )
    pattern_path = f"{year_path}/{pattern_name}"
    pattern = year.setdefault("patterns", {}).setdefault(
        pattern_name,
        {"folder_id": "", "parent_id": "", "path": pattern_path, "subjects": {}},
    )
    subject_key = _unique_subject_name(pattern, subject_name, None, folder_id)
    pattern.setdefault("subjects", {})[subject_key] = _folder_record(folder_id, parent_id, folder_path)


def _add_standardized_subject(
    mapping: dict[str, Any],
    parts: list[str],
    folder_path: str,
    folder_id: str,
    parent_id: str,
) -> None:
    """Add a leaf folder as Branch/Year/Pattern/Subject, dropping extra middle levels."""
    branch_name, year_name, pattern_name, subject_name, source_group = _standardize_parts(parts)
    branch = mapping.setdefault("branches", {}).setdefault(
        branch_name,
        {"folder_id": "", "parent_id": "", "path": branch_name, "years": {}},
    )
    year_path = f"{branch_name}/{year_name}"
    year = branch.setdefault("years", {}).setdefault(
        year_name,
        {"folder_id": "", "parent_id": "", "path": year_path, "patterns": {}},
    )
    pattern_path = f"{year_path}/{pattern_name}"
    pattern = year.setdefault("patterns", {}).setdefault(
        pattern_name,
        {"folder_id": "", "parent_id": "", "path": pattern_path, "subjects": {}},
    )
    subject_key = _unique_subject_name(pattern, subject_name, source_group, folder_id)
    record = _folder_record(folder_id, parent_id, f"{branch_name}/{year_name}/{pattern_name}/{subject_key}")
    record["drive_path"] = folder_path
    if source_group:
        record["source_group"] = source_group
    pattern.setdefault("subjects", {})[subject_key] = record


def build_special_case_mapping(branch_name: str, entries: dict[str, dict[str, str]], root_folder_id: str) -> dict[str, Any]:
    """Build a standalone mapping document for a nonstandard top-level branch."""
    branch_entries = {
        path: metadata
        for path, metadata in sorted(entries.items())
        if path == branch_name or path.startswith(f"{branch_name}/")
    }
    return {
        "schema_version": 2,
        "generated_at": utc_now_iso(),
        "root": {"folder_id": root_folder_id},
        "branch": branch_name,
        "folders": branch_entries,
    }


def build_first_year_mapping(entries: dict[str, dict[str, str]], root_folder_id: str) -> dict[str, Any]:
    """Build the First Year mapping as First Year/Pattern/Subject."""
    branch_metadata = entries.get(FIRST_YEAR_BRANCH, {})
    first_year_mapping: dict[str, Any] = {
        "schema_version": 2,
        "generated_at": utc_now_iso(),
        "root": {"folder_id": root_folder_id},
        "branch": FIRST_YEAR_BRANCH,
        "folder_id": branch_metadata.get("folder_id", ""),
        "parent_id": branch_metadata.get("parent_id", root_folder_id),
        "path": FIRST_YEAR_BRANCH,
        "patterns": {},
        "exceptions": {},
    }

    first_year_paths = {
        path: metadata
        for path, metadata in sorted(entries.items())
        if path == FIRST_YEAR_BRANCH or path.startswith(f"{FIRST_YEAR_BRANCH}/")
    }
    paths = set(first_year_paths)

    for folder_path, metadata in first_year_paths.items():
        parts = [part for part in folder_path.split("/") if part]
        if len(parts) == 1:
            continue

        folder_id = metadata.get("folder_id", "")
        parent_id = metadata.get("parent_id", "")
        has_child = _has_child(folder_path, paths)

        if len(parts) == 2:
            pattern_name = parts[1]
            pattern = first_year_mapping["patterns"].setdefault(
                pattern_name,
                _folder_record(folder_id, parent_id, folder_path) | {"subjects": {}},
            )
            pattern.update(_folder_record(folder_id, parent_id, folder_path))
            pattern.setdefault("subjects", {})
            if not has_child:
                _add_exception(
                    first_year_mapping,
                    folder_path,
                    folder_id,
                    parent_id,
                    "leaf_pattern_without_subject",
                )
            continue

        if len(parts) == 3 and not has_child:
            pattern_name = parts[1]
            subject_name = parts[2]
            pattern_path = f"{FIRST_YEAR_BRANCH}/{pattern_name}"
            pattern_metadata = first_year_paths.get(pattern_path, {})
            pattern = first_year_mapping["patterns"].setdefault(
                pattern_name,
                _folder_record(
                    pattern_metadata.get("folder_id", ""),
                    pattern_metadata.get("parent_id", ""),
                    pattern_path,
                )
                | {"subjects": {}},
            )
            pattern.setdefault("subjects", {})[subject_name] = _folder_record(folder_id, parent_id, folder_path)
            continue

        _add_exception(
            first_year_mapping,
            folder_path,
            folder_id,
            parent_id,
            "nonstandard_first_year_depth",
        )

    return first_year_mapping


def _unique_mba_subject_name(pattern: dict[str, Any], subject_name: str, source_group: str | None, folder_id: str) -> str:
    subjects = pattern.setdefault("subjects", {})
    existing = subjects.get(subject_name)
    if not existing or existing.get("folder_id") == folder_id:
        return subject_name
    if source_group:
        candidate = f"{subject_name} ({source_group})"
        if candidate not in subjects or subjects[candidate].get("folder_id") == folder_id:
            return candidate
    index = 2
    while True:
        candidate = f"{subject_name} ({index})"
        if candidate not in subjects or subjects[candidate].get("folder_id") == folder_id:
            return candidate
        index += 1


def build_mba_mapping(entries: dict[str, dict[str, str]], root_folder_id: str) -> dict[str, Any]:
    """Build the MBA mapping as M.B.A/Semester/Pattern/Subject."""
    branch_metadata = entries.get(MBA_BRANCH, {})
    mba_mapping: dict[str, Any] = {
        "schema_version": 2,
        "generated_at": utc_now_iso(),
        "root": {"folder_id": root_folder_id},
        "branch": MBA_BRANCH,
        "folder_id": branch_metadata.get("folder_id", ""),
        "parent_id": branch_metadata.get("parent_id", root_folder_id),
        "path": MBA_BRANCH,
        "semesters": {},
    }

    mba_paths = {
        path: metadata
        for path, metadata in sorted(entries.items())
        if path == MBA_BRANCH or path.startswith(f"{MBA_BRANCH}/")
    }
    paths = set(mba_paths)

    for folder_path, metadata in mba_paths.items():
        parts = [part for part in folder_path.split("/") if part]
        if len(parts) == 1:
            continue

        folder_id = metadata.get("folder_id", "")
        parent_id = metadata.get("parent_id", "")
        has_child = _has_child(folder_path, paths)

        if len(parts) == 2:
            semester_name = parts[1]
            semester = mba_mapping["semesters"].setdefault(
                semester_name,
                _folder_record(folder_id, parent_id, folder_path) | {"patterns": {}},
            )
            semester.update(_folder_record(folder_id, parent_id, folder_path))
            semester.setdefault("patterns", {})
            continue

        if len(parts) == 3:
            semester_name = parts[1]
            pattern_name = parts[2]
            semester_path = f"{MBA_BRANCH}/{semester_name}"
            semester_metadata = mba_paths.get(semester_path, {})
            semester = mba_mapping["semesters"].setdefault(
                semester_name,
                _folder_record(
                    semester_metadata.get("folder_id", ""),
                    semester_metadata.get("parent_id", ""),
                    semester_path,
                )
                | {"patterns": {}},
            )
            pattern = semester.setdefault("patterns", {}).setdefault(
                pattern_name,
                _folder_record(folder_id, parent_id, folder_path) | {"subjects": {}},
            )
            pattern.update(_folder_record(folder_id, parent_id, folder_path))
            pattern.setdefault("subjects", {})
            continue

        if has_child:
            continue

        semester_name = parts[1]
        pattern_name = parts[2]
        subject_name = parts[-1]
        source_group = " / ".join(parts[3:-1]) or None
        semester_path = f"{MBA_BRANCH}/{semester_name}"
        pattern_path = f"{semester_path}/{pattern_name}"
        semester_metadata = mba_paths.get(semester_path, {})
        pattern_metadata = mba_paths.get(pattern_path, {})

        semester = mba_mapping["semesters"].setdefault(
            semester_name,
            _folder_record(
                semester_metadata.get("folder_id", ""),
                semester_metadata.get("parent_id", ""),
                semester_path,
            )
            | {"patterns": {}},
        )
        pattern = semester.setdefault("patterns", {}).setdefault(
            pattern_name,
            _folder_record(
                pattern_metadata.get("folder_id", ""),
                pattern_metadata.get("parent_id", ""),
                pattern_path,
            )
            | {"subjects": {}},
        )
        subject_key = _unique_mba_subject_name(pattern, subject_name, source_group, folder_id)
        record = _folder_record(folder_id, parent_id, f"{pattern_path}/{subject_key}")
        if folder_path != record["path"]:
            record["drive_path"] = folder_path
        if source_group:
            record["source_group"] = source_group
        pattern.setdefault("subjects", {})[subject_key] = record

    return mba_mapping


def write_special_case_mappings(mapping: dict[str, Any]) -> None:
    """Write standalone mapping files for branches intentionally kept as exceptions."""
    root_folder_id = str((mapping.get("root") or {}).get("folder_id", ""))
    entries = _all_entries(mapping)
    for branch_name, filename in SPECIAL_CASE_BRANCH_FILES.items():
        if branch_name not in entries:
            continue
        if branch_name == FIRST_YEAR_BRANCH:
            special_mapping = build_first_year_mapping(entries, root_folder_id)
        elif branch_name == MBA_BRANCH:
            special_mapping = build_mba_mapping(entries, root_folder_id)
        else:
            special_mapping = build_special_case_mapping(branch_name, entries, root_folder_id)
        write_json(MAPPING_PATH.parent / filename, special_mapping)


def normalize_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Rebuild mapping into branch/year/pattern/subject form and record exceptions."""
    root_folder_id = str((mapping.get("root") or {}).get("folder_id", ""))
    entries = _all_entries(mapping)
    paths = set(entries)
    organized = empty_mapping(root_folder_id)

    for folder_path, metadata in sorted(entries.items()):
        folder_id = metadata.get("folder_id", "")
        parent_id = metadata.get("parent_id", "")
        parts = [part for part in folder_path.split("/") if part]
        if not parts:
            continue

        if parts[0] in SPECIAL_CASE_BRANCH_FILES:
            continue

        if len(parts) >= 2 and parts[1].upper() in EXCLUDED_YEAR_LEVELS:
            continue

        has_child = _has_child(folder_path, paths)
        if len(parts) == 1:
            branch = organized["branches"].setdefault(parts[0], _folder_record(folder_id, parent_id, folder_path) | {"years": {}})
            branch.update(_folder_record(folder_id, parent_id, folder_path))
            branch.setdefault("years", {})
            continue

        if len(parts) == 2:
            branch = organized["branches"].setdefault(parts[0], {"folder_id": "", "parent_id": "", "path": parts[0], "years": {}})
            year = branch.setdefault("years", {}).setdefault(parts[1], _folder_record(folder_id, parent_id, folder_path) | {"patterns": {}})
            year.update(_folder_record(folder_id, parent_id, folder_path))
            year.setdefault("patterns", {})
            if not has_child:
                _add_exception(organized, folder_path, folder_id, parent_id, "leaf_folder_without_pattern_or_subject")
            continue

        if len(parts) == 3:
            branch = organized["branches"].setdefault(parts[0], {"folder_id": "", "parent_id": "", "path": parts[0], "years": {}})
            year = branch.setdefault("years", {}).setdefault(
                parts[1],
                {"folder_id": "", "parent_id": "", "path": "/".join(parts[:2]), "patterns": {}},
            )
            if has_child and not parts[2].lower().endswith("pattern"):
                _add_exception(organized, folder_path, folder_id, parent_id, "standardized_container_removed")
                continue
            if has_child:
                pattern = year.setdefault("patterns", {}).setdefault(parts[2], _folder_record(folder_id, parent_id, folder_path) | {"subjects": {}})
                pattern.update(_folder_record(folder_id, parent_id, folder_path))
                pattern.setdefault("subjects", {})
            else:
                _add_exception(organized, folder_path, folder_id, parent_id, "leaf_folder_without_pattern")
            continue

        if has_child:
            _add_exception(organized, folder_path, folder_id, parent_id, "nonstandard_container_depth")
            continue

        _add_standardized_subject(organized, parts, folder_path, folder_id, parent_id)
        if len(parts) != 4:
            _add_exception(organized, folder_path, folder_id, parent_id, "standardized_from_nonstandard_subject_depth")

    return organized


def add_folder(mapping: dict[str, Any], folder_path: str, folder_id: str, parent_id: str) -> None:
    """Add a Drive folder to the organized branch/year/pattern/subject mapping."""
    parts = [part for part in folder_path.split("/") if part]
    if not parts:
        return

    branches = mapping.setdefault("branches", {})
    exceptions = mapping.setdefault("exceptions", {})

    if len(parts) == 1:
        branch = branches.setdefault(parts[0], _folder_record(folder_id, parent_id, folder_path) | {"years": {}})
        branch.update(_folder_record(folder_id, parent_id, folder_path))
        branch.setdefault("years", {})
        return

    if len(parts) == 2:
        branch = branches.setdefault(parts[0], {"folder_id": "", "parent_id": "", "path": parts[0], "years": {}})
        year = branch.setdefault("years", {}).setdefault(
            parts[1],
            _folder_record(folder_id, parent_id, folder_path) | {"patterns": {}},
        )
        year.update(_folder_record(folder_id, parent_id, folder_path))
        year.setdefault("patterns", {})
        return

    if len(parts) == 3:
        branch = branches.setdefault(parts[0], {"folder_id": "", "parent_id": "", "path": parts[0], "years": {}})
        year = branch.setdefault("years", {}).setdefault(
            parts[1],
            {"folder_id": "", "parent_id": "", "path": "/".join(parts[:2]), "patterns": {}},
        )
        pattern = year.setdefault("patterns", {}).setdefault(
            parts[2],
            _folder_record(folder_id, parent_id, folder_path) | {"subjects": {}},
        )
        pattern.update(_folder_record(folder_id, parent_id, folder_path))
        pattern.setdefault("subjects", {})
        return

    if len(parts) == 4:
        branch = branches.setdefault(parts[0], {"folder_id": "", "parent_id": "", "path": parts[0], "years": {}})
        year = branch.setdefault("years", {}).setdefault(
            parts[1],
            {"folder_id": "", "parent_id": "", "path": "/".join(parts[:2]), "patterns": {}},
        )
        pattern = year.setdefault("patterns", {}).setdefault(
            parts[2],
            {"folder_id": "", "parent_id": "", "path": "/".join(parts[:3]), "subjects": {}},
        )
        pattern.setdefault("subjects", {})[parts[3]] = _folder_record(folder_id, parent_id, folder_path)
        return

    exceptions[folder_path] = {
        "folder_id": folder_id,
        "parent_id": parent_id,
        "path": folder_path,
        "depth": len(parts),
        "reason": "deeper_than_branch_year_pattern_subject",
    }


def convert_flat_mapping(flat_mapping: dict[str, Any]) -> dict[str, Any]:
    """Convert the original flat path mapping into the organized schema."""
    return normalize_mapping(flat_mapping)


def build_mapping(
    client: GoogleDriveClient,
    root_folder_id: str,
    logger: logging.Logger | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Traverse the full Drive folder tree and build a fresh mapping."""
    logger = logger or logging.getLogger(__name__)
    mapping = empty_mapping(root_folder_id)
    logger.info("Starting full mapping build from root folder: %s", root_folder_id)
    for folder_path, folder_id, parent_id in client.walk_folders(root_folder_id):
        add_folder(mapping, folder_path, folder_id, parent_id)
        logger.info("Mapped folder #%d: %s (%s)", folder_count(mapping), folder_path, folder_id)
        if on_progress:
            on_progress(mapping)
    logger.info("Finished mapping build. Total folders mapped: %d", folder_count(mapping))
    return mapping


def refresh_mapping(
    client: GoogleDriveClient,
    root_folder_id: str,
    logger: logging.Logger | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Refresh mapping and return the updated mapping plus newly discovered paths."""
    existing = read_json(MAPPING_PATH, default=empty_mapping(root_folder_id)) or empty_mapping(root_folder_id)
    if "folders" in existing:
        existing = convert_flat_mapping(existing)
    discovered = build_mapping(client, root_folder_id, logger=logger, on_progress=on_progress)
    old_paths = set(all_folder_paths(existing))
    new_paths = sorted(set(all_folder_paths(discovered)) - old_paths)
    save_mapping(discovered)
    return discovered, new_paths


def refresh_selected_branches(
    client: GoogleDriveClient,
    root_folder_id: str,
    branch_names: list[str],
    logger: logging.Logger | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Refresh only selected top-level branches and merge them into sync_mapping.json."""
    logger = logger or logging.getLogger(__name__)
    existing = read_json(MAPPING_PATH, default=empty_mapping(root_folder_id)) or empty_mapping(root_folder_id)
    entries = _all_entries(existing)
    target_names = set(branch_names)
    root_folders = {folder["name"]: folder for folder in client.list_folders(root_folder_id)}
    missing = sorted(target_names - set(root_folders))
    if missing:
        raise ValueError(f"Could not find top-level Drive folders: {', '.join(missing)}")

    for branch_name in sorted(target_names):
        logger.info("Refreshing selected branch: %s", branch_name)
        entries = {
            path: metadata
            for path, metadata in entries.items()
            if path != branch_name and not path.startswith(f"{branch_name}/")
        }

        branch = root_folders[branch_name]
        entries[branch_name] = _folder_record(branch["id"], root_folder_id, branch_name)
        working = {"root": {"folder_id": root_folder_id}, "folders": dict(entries)}
        if on_progress:
            on_progress(working)

        for child_path, folder_id, parent_id in client.walk_folders(branch["id"]):
            full_path = f"{branch_name}/{child_path}"
            entries[full_path] = _folder_record(folder_id, parent_id, full_path)
            logger.info("Mapped selected folder: %s (%s)", full_path, folder_id)
            if on_progress:
                on_progress({"root": {"folder_id": root_folder_id}, "folders": dict(entries)})

    discovered = normalize_mapping({"root": {"folder_id": root_folder_id}, "folders": entries})
    old_paths = set(all_folder_paths(existing))
    new_paths = sorted(set(all_folder_paths(discovered)) - old_paths)
    save_mapping(discovered)
    return discovered, new_paths


def iter_subject_folders(mapping: dict[str, Any]) -> list[dict[str, str]]:
    """Return mapped subject folders from the organized hierarchy."""
    if "folders" in mapping:
        mapping = convert_flat_mapping(mapping)

    subjects: list[dict[str, str]] = []
    for branch_name, branch in (mapping.get("branches") or {}).items():
        for year_name, year in (branch.get("years") or {}).items():
            for pattern_name, pattern in (year.get("patterns") or {}).items():
                for subject_name, subject in (pattern.get("subjects") or {}).items():
                    folder_path = subject.get("path") or f"{branch_name}/{year_name}/{pattern_name}/{subject_name}"
                    subjects.append(
                        {
                            "branch": branch_name,
                            "year": year_name,
                            "pattern": pattern_name,
                            "subject": subject_name,
                            "folder_path": folder_path,
                            "folder_id": subject["folder_id"],
                            "parent_id": subject["parent_id"],
                        }
                    )
    return sorted(subjects, key=lambda item: item["folder_path"])


def subject_folder_paths(mapping: dict[str, Any]) -> list[str]:
    """Return mapped subject folder paths at Branch/Year/Pattern/Subject depth."""
    return [item["folder_path"] for item in iter_subject_folders(mapping)]


def all_folder_paths(mapping: dict[str, Any]) -> list[str]:
    """Return every organized folder path, including exceptions."""
    if "folders" in mapping:
        return sorted((mapping.get("folders") or {}).keys())

    paths: list[str] = []
    for branch in (mapping.get("branches") or {}).values():
        if branch.get("path"):
            paths.append(branch["path"])
        for year in (branch.get("years") or {}).values():
            if year.get("path"):
                paths.append(year["path"])
            for pattern in (year.get("patterns") or {}).values():
                if pattern.get("path"):
                    paths.append(pattern["path"])
                for subject in (pattern.get("subjects") or {}).values():
                    if subject.get("path"):
                        paths.append(subject["path"])
    paths.extend((mapping.get("exceptions") or {}).keys())
    return sorted(set(paths))
