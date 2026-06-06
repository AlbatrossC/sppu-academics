"""Move VERIFIED tracked PDFs into papers/."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import tracking
from common.utils import PAPERS_DIR, PROJECT_ROOT


def repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def in_scope(path_value: str | None, scope: Path | None) -> bool:
    if scope is None:
        return True
    path = repo_path(path_value)
    if not path:
        return False
    return is_under(path, scope)


def move_verified(scope: Path | None = None, dry_run: bool = False) -> dict[str, int]:
    moved = 0
    reviewed = 0
    missing = 0
    skipped = 0
    for row in tracking.all_files():
        if row["current_stage"] != "VERIFIED":
            continue
        if not in_scope(row.get("current_path"), scope):
            continue
        source = repo_path(row.get("current_path"))
        target = repo_path(row.get("expected_path"))
        if not source or not source.exists():
            if dry_run:
                missing += 1
                continue
            tracking.update_stage(row["file_id"], "MISSING", review_reason="Verified source file is missing", reason="Verified source file is missing")
            missing += 1
            continue
        if not target or not is_under(target, PAPERS_DIR):
            if dry_run:
                reviewed += 1
                continue
            tracking.update_stage(
                row["file_id"],
                "NEEDS_REVIEW",
                current_path=row.get("current_path"),
                review_category="invalid_expected_path",
                review_reason="Expected path is missing or not under papers/",
                reason="Expected path is missing or not under papers/",
            )
            reviewed += 1
            continue
        if target.exists():
            if dry_run:
                reviewed += 1
                continue
            tracking.update_stage(
                row["file_id"],
                "NEEDS_REVIEW",
                current_path=row.get("current_path"),
                review_category="duplicate_filename",
                review_reason=f"Target already exists: {target.relative_to(PROJECT_ROOT)}",
                reason="Target already exists",
            )
            reviewed += 1
            continue
        if not (is_under(source, PROJECT_ROOT / "incoming") or is_under(source, PROJECT_ROOT / "needs_review")):
            skipped += 1
            continue
        if dry_run:
            moved += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        relative_target = target.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
        tracking.update_stage(
            row["file_id"],
            "MOVED",
            current_path=relative_target,
            expected_path=relative_target,
            final_path=relative_target,
            reason="Moved verified file to papers/",
        )
        moved += 1
    return {"moved": moved, "reviewed": reviewed, "missing": missing, "skipped": skipped}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move VERIFIED files from incoming/ or needs_review/ to papers/.")
    parser.add_argument("--path", help="Optional incoming/ or needs_review/ subtree to move. Defaults to all VERIFIED files.")
    parser.add_argument("--dry-run", action="store_true", help="Count what would move without changing files or SQLite.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        scope = repo_path(args.path) if args.path else None
        result = move_verified(scope=scope, dry_run=args.dry_run)
        prefix = "Would move" if args.dry_run else "Moved"
        print(
            f"{prefix} {result['moved']} verified file(s); "
            f"{result['reviewed']} need review; {result['missing']} missing; {result['skipped']} skipped."
        )
        return 0
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
