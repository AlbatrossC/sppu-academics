"""Validate SQLite tracking state and promote valid files to VERIFIED."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from common import tracking
from common.utils import INCOMING_DIR, PAPERS_DIR, PROJECT_ROOT


NEEDS_REVIEW_DIR = PROJECT_ROOT / "needs_review"
FILENAME_RE = re.compile(r"^(insem|endsem|other)_[a-z]{3}(?:_[a-z]{3})?_\d{4}_[A-Za-z0-9_]+_[A-Za-z0-9_]+_[A-Za-z0-9_]+\.pdf$")


def repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def project_path(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def path_root(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).parts[0] if Path(path).parts else ""


def folder_shape_valid(row: dict[str, Any]) -> bool:
    current_path = row.get("current_path") or row.get("expected_path") or ""
    parts = Path(current_path).parts
    if not parts:
        return False
    if parts[0] in {"incoming", "needs_review", "papers"}:
        parts = parts[1:]
    if row["branch_type"] == "first_year":
        return len(parts) >= 3
    if row["branch_type"] == "mba":
        return len(parts) >= 4
    if row["branch_type"] == "honors":
        return len(parts) >= 3
    return len(parts) >= 4


def expected_from_current(current_path: str) -> str | None:
    path = Path(current_path)
    if not path.name.lower().endswith(".pdf"):
        return None
    if not FILENAME_RE.fullmatch(path.name):
        return None
    parts = path.parts
    if not parts or parts[0] not in {"incoming", "needs_review"}:
        return None
    return Path("papers", *parts[1:]).as_posix()


def duplicate_expected_paths(rows: list[dict[str, Any]]) -> set[str]:
    counts: Counter[str] = Counter(row["expected_path"] for row in rows if row.get("expected_path"))
    return {path for path, count in counts.items() if count > 1}


def verify_rows(apply: bool = True) -> dict[str, Any]:
    rows = tracking.all_files()
    duplicate_expected = duplicate_expected_paths(rows)
    issues: Counter[str] = Counter()
    promoted = 0

    for row in rows:
        stage = row["current_stage"]
        current_path = row.get("current_path")
        current = repo_path(current_path)

        if stage == "DISCOVERED" and not current_path:
            continue

        if stage == "MOVED":
            if not current or not current.exists() or path_root(current_path) != "papers":
                issues["moved_missing"] += 1
                if apply:
                    tracking.update_stage(row["file_id"], "MISSING", review_reason="Moved file missing from papers/", reason="Moved file missing from papers/")
            continue

        if stage == "MISSING":
            issues["missing"] += 1
            continue

        if current_path and (not current or not current.exists()):
            issues["missing_current_path"] += 1
            if apply:
                tracking.update_stage(row["file_id"], "MISSING", review_reason="Current path is missing", reason="Current path is missing")
            continue

        if current_path and path_root(current_path) not in {"incoming", "needs_review", "papers"}:
            issues["invalid_current_root"] += 1
            continue

        if not folder_shape_valid(row):
            issues["invalid_folder_structure"] += 1
            continue

        if row.get("expected_path") in duplicate_expected:
            issues["duplicate_expected_path"] += 1
            continue

        if stage in {"DOWNLOADED", "FOLDER_RENAMED", "FILE_RENAMED", "NEEDS_REVIEW"} and current_path:
            filename = Path(current_path).name
            if not FILENAME_RE.fullmatch(filename):
                if stage == "NEEDS_REVIEW":
                    issues["needs_review_unfixed"] += 1
                elif stage in {"DOWNLOADED", "FOLDER_RENAMED"}:
                    issues["not_renamed_yet"] += 1
                else:
                    issues["invalid_filename"] += 1
                continue
            expected_path = row.get("expected_path") or expected_from_current(current_path)
            if not expected_path:
                issues["missing_expected_path"] += 1
                continue
            if apply:
                tracking.update_stage(
                    row["file_id"],
                    "VERIFIED",
                    current_path=current_path,
                    expected_path=expected_path,
                    renamed_filename=filename,
                    reason="Verified filename, folder structure, DB state, and file existence",
                )
            promoted += 1

    return {"promoted": promoted, "issues": issues, "counts": tracking.counts_by_stage()}


def render_report(result: dict[str, Any]) -> str:
    counts = result["counts"]
    lines = [
        f"Discovered: {counts['DISCOVERED']}",
        f"Downloaded: {counts['DOWNLOADED']}",
        f"Folder Renamed: {counts['FOLDER_RENAMED']}",
        f"File Renamed: {counts['FILE_RENAMED']}",
        f"Verified: {counts['VERIFIED']}",
        f"Moved: {counts['MOVED']}",
        "",
        f"Needs Review: {counts['NEEDS_REVIEW']}",
        f"Missing: {counts['MISSING']}",
        "",
        "Needs Review Reasons",
    ]
    reasons = tracking.needs_review_reasons()
    if reasons:
        lines.extend(f"{name.replace('_', ' ').title()}: {count}" for name, count in sorted(reasons.items()))
    else:
        lines.append("None: 0")
    lines.extend(["", "Retry Counts"])
    retries = tracking.retry_summary()
    if retries:
        lines.extend(f"{name}: {count}" for name, count in sorted(retries.items()))
    else:
        lines.append("None: 0")
    lines.extend(["", f"Promoted To Verified: {result['promoted']}"])
    issues = result["issues"]
    if issues:
        lines.extend(["", "Validation Issues"])
        lines.extend(f"{name.replace('_', ' ').title()}: {count}" for name, count in sorted(issues.items()))
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate tracking/manifest.db and promote valid files to VERIFIED.")
    parser.add_argument("--dry-run", action="store_true", help="Report issues without updating stages.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        print(render_report(verify_rows(apply=not args.dry_run)))
        return 0
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
