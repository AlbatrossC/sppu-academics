"""Migrate mapping/local JSON metadata into tracking/manifest.db."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from common import tracking
from common.utils import INCOMING_DIR, LOCAL_MAPPING_DIR, PAPERS_DIR, PROJECT_ROOT, utc_now_iso


NEEDS_REVIEW_DIR = PROJECT_ROOT / "needs_review"
FOLDER_NAMES_PATH = PROJECT_ROOT / "mapping" / "folder_names.yml"
RENAMED_RE = re.compile(r"^(insem|endsem|other)_[a-z]{3}(?:_[a-z]{3})?_\d{4}_.+\.pdf$")
MONTH_ALIASES = {
    "jan": "jan",
    "january": "jan",
    "feb": "feb",
    "february": "feb",
    "mar": "mar",
    "march": "mar",
    "apr": "apr",
    "april": "apr",
    "may": "may",
    "jun": "jun",
    "june": "jun",
    "jul": "jul",
    "july": "jul",
    "aug": "aug",
    "august": "aug",
    "sep": "sep",
    "sept": "sep",
    "september": "sep",
    "oct": "oct",
    "october": "oct",
    "nov": "nov",
    "november": "nov",
    "dec": "dec",
    "december": "dec",
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def folder_registry() -> dict[str, Any]:
    if not FOLDER_NAMES_PATH.exists():
        return {}
    with FOLDER_NAMES_PATH.open("r", encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("name_registry") or {}


def fallback_normalized(value: str, index: int) -> str:
    separator = "-" if index == 0 else "_"
    cleaned = value.strip().replace("&", " and ")
    cleaned = "".join(char if char.isalnum() else " " for char in cleaned)
    return separator.join(token.lower() for token in cleaned.split())


def normalized_parts(folder_path: str, registry: dict[str, Any]) -> list[str]:
    parts = [part for part in folder_path.split("/") if part]
    result: list[str] = []
    for index, part in enumerate(parts):
        entry = registry.get(part)
        if isinstance(entry, dict) and entry.get("normalized"):
            result.append(str(entry["normalized"]))
        else:
            result.append(fallback_normalized(part, index))
    return result


def month_year(filename: str) -> str:
    stem = Path(filename).stem.lower()
    year_match = re.search(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", stem)
    tokens = [token for token in re.split(r"[^a-z]+", stem) if token]
    months = [MONTH_ALIASES[token] for token in tokens if token in MONTH_ALIASES][:2]
    return f"{'_'.join(months)}_{year_match.group(1)}" if months and year_match else ""


def project_path(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def unique_papers_match(folder: Path, drive_filename: str) -> Path | None:
    if not folder.exists():
        return None
    signal = month_year(drive_filename)
    if not signal:
        return None
    matches = [path for path in folder.glob("*.pdf") if signal in path.name.lower()]
    return matches[0] if len(matches) == 1 else None


def locate_file(folder_path: str, drive_filename: str, registry: dict[str, Any]) -> tuple[str, str | None, str | None]:
    parts = normalized_parts(folder_path, registry)
    incoming_original = INCOMING_DIR.joinpath(*parts, drive_filename)
    review_original = NEEDS_REVIEW_DIR.joinpath(*parts, drive_filename)
    papers_folder = PAPERS_DIR.joinpath(*parts)
    papers_original = papers_folder / drive_filename

    if papers_original.exists():
        return "MOVED", project_path(papers_original), project_path(papers_original)
    papers_match = unique_papers_match(papers_folder, drive_filename)
    if papers_match:
        return "MOVED", project_path(papers_match), project_path(papers_match)
    if incoming_original.exists():
        stage = "FILE_RENAMED" if RENAMED_RE.fullmatch(incoming_original.name) else "DOWNLOADED"
        expected = project_path(PAPERS_DIR.joinpath(*parts, incoming_original.name)) if stage == "FILE_RENAMED" else None
        return stage, project_path(incoming_original), expected
    incoming_matches = list(INCOMING_DIR.joinpath(*parts).glob("*.pdf")) if INCOMING_DIR.joinpath(*parts).exists() else []
    signal = month_year(drive_filename)
    renamed_matches = [path for path in incoming_matches if signal and signal in path.name.lower() and RENAMED_RE.fullmatch(path.name)]
    if len(renamed_matches) == 1:
        expected = project_path(PAPERS_DIR.joinpath(*parts, renamed_matches[0].name))
        return "FILE_RENAMED", project_path(renamed_matches[0]), expected
    if review_original.exists():
        return "NEEDS_REVIEW", project_path(review_original), None
    return "MISSING", None, None


def iter_legacy_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not LOCAL_MAPPING_DIR.exists():
        return entries
    for path in LOCAL_MAPPING_DIR.rglob("*.json"):
        data = read_json(path)
        for subject_name, subject in (data.get("subjects") or {}).items():
            for file_id, metadata in (subject.get("files") or {}).items():
                if not isinstance(metadata, dict):
                    continue
                entry = dict(metadata)
                entry.setdefault("file_id", file_id)
                entry.setdefault("subject", subject_name)
                entries.append(entry)
    return entries


def migrate() -> dict[str, int]:
    tracking.ensure_schema()
    registry = folder_registry()
    counts = {"inserted": 0, "updated": 0, "missing": 0}
    for entry in iter_legacy_entries():
        file_id = str(entry.get("file_id") or "")
        folder_path = str(entry.get("folder_path") or "")
        filename = str(entry.get("filename") or "")
        if not file_id or not folder_path or not filename:
            continue
        existed = tracking.file_exists(file_id)
        stage, current_path, expected_path = locate_file(folder_path, filename, registry)
        change = {
            "file_id": file_id,
            "filename": filename,
            "modified_time": str(entry.get("modified_time") or ""),
            "folder_path": folder_path,
            "folder_id": str(entry.get("folder_id") or ""),
        }
        tracking.upsert_discovered_file(change)
        kwargs: dict[str, Any] = {"current_path": current_path}
        if expected_path:
            kwargs["expected_path"] = expected_path
        if stage == "MOVED":
            kwargs["final_path"] = current_path
        if stage == "FILE_RENAMED" and current_path:
            kwargs["renamed_filename"] = Path(current_path).name
        if stage == "NEEDS_REVIEW":
            kwargs["review_category"] = "manual_check"
            kwargs["review_reason"] = "Migrated from needs_review/"
        tracking.update_stage(file_id, stage, **kwargs, reason="Migrated from mapping/local")
        counts["updated" if existed else "inserted"] += 1
        if stage == "MISSING":
            counts["missing"] += 1
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate mapping/local JSON metadata to tracking/manifest.db.")
    parser.add_argument("--print", action="store_true", dest="print_summary", help="Print migration summary.")
    return parser.parse_args()


def main() -> int:
    try:
        result = migrate()
        if parse_args().print_summary:
            print(f"Inserted: {result['inserted']}")
            print(f"Updated: {result['updated']}")
            print(f"Missing: {result['missing']}")
        else:
            print(f"Migrated {result['inserted'] + result['updated']} tracked file(s) into tracking/manifest.db.")
        return 0
    except (OSError, json.JSONDecodeError, yaml.YAMLError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
