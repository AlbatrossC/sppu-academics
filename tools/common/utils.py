"""Project path, configuration, and JSON helpers."""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.json"
MAPPING_PATH = PROJECT_ROOT / "mapping" / "sync_mapping.json"
LOCAL_MAPPING_DIR = PROJECT_ROOT / "mapping" / "local"
SYNC_PLAN_PATH = PROJECT_ROOT / "sync_plan" / "sync_plan.json"
CHANGELOG_PATH = PROJECT_ROOT / "changelog" / "sync.md"
PAPERS_DIR = PROJECT_ROOT / "papers"
INCOMING_DIR = PROJECT_ROOT / "incoming"
NEEDS_REVIEW_DIR = PROJECT_ROOT / "needs_review"
MANIFEST_DIR = PROJECT_ROOT / "manifest"
TRACKING_DIR = PROJECT_ROOT / "tracking"
TRACKING_DB_PATH = TRACKING_DIR / "manifest.db"

INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ConfigError(RuntimeError):
    """Raised when project configuration is missing or invalid."""


def utc_now_iso() -> str:
    """Return the current UTC timestamp in Google-compatible ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any | None = None) -> Any:
    """Read a JSON file, returning default when the file does not exist."""
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically enough for local CLI use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    last_error: OSError | None = None
    for attempt in range(8):
        try:
            temp_path.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.1 * (attempt + 1))
    try:
        temp_path.unlink()
    except OSError:
        pass
    if last_error:
        raise last_error


def ensure_project_dirs() -> None:
    """Create the expected project directories if they are missing."""
    for directory in (PAPERS_DIR, INCOMING_DIR, NEEDS_REVIEW_DIR, MAPPING_PATH.parent, TRACKING_DIR, SYNC_PLAN_PATH.parent, CHANGELOG_PATH.parent):
        directory.mkdir(parents=True, exist_ok=True)


def load_config(require_root: bool = True) -> dict[str, Any]:
    """Load config.json and optionally require a root Drive folder ID."""
    config = read_json(CONFIG_PATH, default={}) or {}
    root_folder_id = str(config.get("root_folder_id", "")).strip()
    if require_root and not root_folder_id:
        raise ConfigError(
            "config.json is missing root_folder_id. Add the public Google Drive root folder ID before running."
        )
    return {
        "root_folder_id": root_folder_id,
        "request_timeout": int(config.get("request_timeout", 30)),
        "max_retries": int(config.get("max_retries", 5)),
        "backoff_factor": float(config.get("backoff_factor", 1.5)),
    }


def sanitize_path_part(value: str) -> str:
    """Make a Drive name safe for use as a local path component."""
    cleaned = INVALID_PATH_CHARS.sub("_", value).strip().rstrip(".")
    return cleaned or "_"


def split_folder_path(folder_path: str) -> tuple[str, str, str, str]:
    """Split Branch/Year/Pattern/Subject paths and validate their depth."""
    parts = [part for part in folder_path.split("/") if part]
    if len(parts) != 4:
        raise ValueError(f"Expected subject folder path with 4 parts, got: {folder_path}")
    return parts[0], parts[1], parts[2], parts[3]


def local_pdf_path(folder_path: str, filename: str) -> Path:
    """Return the local papers path for a Drive PDF."""
    parts = [sanitize_path_part(part) for part in folder_path.split("/") if part]
    return PAPERS_DIR.joinpath(*parts, sanitize_path_part(filename))


def project_relative(path: Path) -> str:
    """Return a POSIX-style path relative to the project root."""
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()
