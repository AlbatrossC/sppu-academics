"""Run the review-first workflow as a single orchestrated command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_step(command: list[str], dry_run: bool = False) -> int:
    display = " ".join(command)
    print(f"\n$ {display}")
    if dry_run:
        return 0
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return completed.returncode


def sync_scope_args(scope: str | None) -> list[str]:
    return [scope] if scope else []


def run_commands(commands: list[list[str]], dry_run: bool) -> int:
    for command in commands:
        code = run_step(command, dry_run=dry_run)
        if code != 0:
            print(f"Pipeline stopped after failed command: {' '.join(command)}", file=sys.stderr)
            return code
    return 0


def review_commands(scope: str | None) -> list[list[str]]:
    scope_args = sync_scope_args(scope)
    return [
        [PYTHON, "tools/sync.py", "--folders", *scope_args],
        [PYTHON, "tools/sync.py", "--files", *scope_args],
        [PYTHON, "tools/status.py", "--print"],
    ]


def apply_download_commands(args: argparse.Namespace) -> list[list[str]]:
    file_apply = [PYTHON, "tools/sync.py", "--files", "--apply"]
    if args.gdown:
        file_apply.append("--gdown")
    if args.rclone:
        file_apply.append("--rclone")
    if args.download_delay:
        file_apply.extend(["--download-delay", str(args.download_delay)])
    if args.workers:
        file_apply.extend(["--workers", str(args.workers)])

    folder_path = args.folder_path or "incoming"
    rename_path = args.incoming_path or "incoming"
    return [
        [PYTHON, "tools/sync.py", "--folders", "--apply"],
        file_apply,
        [PYTHON, "tools/rename_folders.py", "--create"],
        [PYTHON, "tools/rename_folders.py", "--path", folder_path, "--dry-run"],
        [PYTHON, "tools/rename_folders.py", "--path", folder_path],
        [PYTHON, "tools/rename_files.py", "--path", rename_path, "--ocr-workers", str(args.ocr_workers)],
        [PYTHON, "tools/status.py", "--print"],
    ]


def apply_rename_commands(args: argparse.Namespace) -> list[list[str]]:
    rename_path = args.incoming_path or "incoming"
    return [
        [PYTHON, "tools/rename_files.py", "--apply", "--path", rename_path],
        [PYTHON, "tools/verify.py"],
        [PYTHON, "tools/move.py", "--path", rename_path],
        [PYTHON, "tools/status.py", "--print"],
    ]


def full_commands(args: argparse.Namespace) -> list[list[str]]:
    commands = review_commands(args.scope)
    if args.apply:
        commands.extend(apply_download_commands(args))
        commands.extend(apply_rename_commands(args))
    return commands


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orchestrate the SPPU PYQ review/apply workflow using the existing tools.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 tools/pipeline.py --review --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
  python3 tools/pipeline.py --apply-reviewed --gdown --download-delay 5
  python3 tools/pipeline.py --apply-reviewed --rclone --workers 8
  python3 tools/pipeline.py --apply-renames --incoming-path incoming/artificial-intelligence-and-data-science/be/2019_pattern
  python3 tools/pipeline.py --full --apply --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"

Notes:
  --scope affects review commands only.
  --apply-reviewed applies all pending folder/file changelog entries.
""",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--review", action="store_true", help="Review Drive folder and file changes, then write status.md.")
    mode.add_argument("--apply-reviewed", action="store_true", help="Apply reviewed folder/file downloads, normalize incoming, and review PDF renames.")
    mode.add_argument("--apply-renames", action="store_true", help="Apply reviewed PDF renames.")
    mode.add_argument("--full", action="store_true", help="Run review. Add --apply to continue through all apply stages.")
    parser.add_argument("--apply", action="store_true", help="With --full, apply reviewed changes and final renames after review.")
    parser.add_argument("--scope", help='Drive scope for sync commands, for example "Artificial Intelligence and Data Science/BE/2019 Pattern".')
    parser.add_argument("--folder-path", help="Raw incoming folder path for folder normalization. Defaults to incoming/.")
    parser.add_argument("--incoming-path", help="Normalized incoming path for rename stages. Defaults to incoming/.")
    parser.add_argument("--ocr-workers", type=int, default=1, help="PaddleOCR worker count passed to tools/rename_files.py review. Defaults to 1 for 4 GB GPU VRAM.")
    parser.add_argument("--workers", type=int, default=2, help="Download worker count for sync.py. rename_files.py keeps --workers only as a compatibility alias.")
    parser.add_argument("--gdown", action="store_true", help="Use gdown when applying reviewed file downloads.")
    parser.add_argument("--rclone", action="store_true", help="Use rclone copyurl bulk mode when applying reviewed file downloads.")
    parser.add_argument("--download-delay", type=float, default=0, help="Seconds between downloads during file apply.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and not args.full:
        print("ERROR: --apply is only valid with --full.", file=sys.stderr)
        return 1
    if args.gdown and args.rclone:
        print("ERROR: Use only one downloader at a time: --gdown or --rclone.", file=sys.stderr)
        return 1

    if args.apply_reviewed:
        commands = apply_download_commands(args)
    elif args.apply_renames:
        commands = apply_rename_commands(args)
    elif args.full:
        commands = full_commands(args)
    else:
        commands = review_commands(args.scope)

    return run_commands(commands, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
