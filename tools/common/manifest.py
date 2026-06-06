"""Manifest helpers keyed by Google Drive file ID."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.utils import MANIFEST_DIR, PROJECT_ROOT, read_json, split_folder_path, write_json


def manifest_path_for(folder_path: str) -> Path:
    """Return manifest path for a subject folder."""
    branch, year, pattern, _subject = split_folder_path(folder_path)
    return MANIFEST_DIR / branch / year / f"{pattern}.json"


def load_pattern_manifest(folder_path: str) -> dict[str, Any]:
    """Load the manifest JSON containing a subject folder."""
    return read_json(manifest_path_for(folder_path), default={}) or {}


def save_pattern_manifest(folder_path: str, manifest: dict[str, Any]) -> None:
    """Save the manifest JSON containing a subject folder."""
    write_json(manifest_path_for(folder_path), manifest)


def load_all_manifest_entries() -> dict[str, dict[str, Any]]:
    """Load every manifest entry indexed by file ID."""
    entries: dict[str, dict[str, Any]] = {}
    if not MANIFEST_DIR.exists():
        return entries

    for path in MANIFEST_DIR.rglob("*.json"):
        manifest = read_json(path, default={}) or {}
        for subject, files in manifest.items():
            if not isinstance(files, dict):
                continue
            for file_id, metadata in files.items():
                if isinstance(metadata, dict):
                    record = dict(metadata)
                    record["subject"] = subject
                    record["manifest_path"] = path
                    entries[file_id] = record
    return entries


def get_entry(folder_path: str, subject: str, file_id: str) -> dict[str, Any] | None:
    """Return a manifest entry for a file ID in a subject, if present."""
    manifest = load_pattern_manifest(folder_path)
    subject_entries = manifest.get(subject, {})
    if not isinstance(subject_entries, dict):
        return None
    entry = subject_entries.get(file_id)
    return entry if isinstance(entry, dict) else None


def upsert_entry(folder_path: str, file_id: str, filename: str, modified_time: str, local_path: str) -> None:
    """Insert or update a manifest entry keyed by Drive file ID."""
    _branch, _year, _pattern, subject = split_folder_path(folder_path)
    manifest = load_pattern_manifest(folder_path)
    subject_entries = manifest.setdefault(subject, {})
    subject_entries[file_id] = {
        "filename": filename,
        "modified_time": modified_time,
        "local_path": local_path,
    }
    save_pattern_manifest(folder_path, manifest)


def local_file_exists(entry: dict[str, Any]) -> bool:
    """Return whether a manifest entry's local file exists."""
    local_path = entry.get("local_path")
    if not local_path:
        return False
    return (PROJECT_ROOT / local_path).exists()
