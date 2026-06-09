"""File review, download, and local mapping helpers."""

from __future__ import annotations

import json
import logging
import inspect
import csv
import shutil
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

from common.drive_client import GoogleDriveClient
from common.mapping import iter_subject_folders
from common import tracking
from common.utils import INCOMING_DIR, MAPPING_PATH, PROJECT_ROOT, read_json, sanitize_path_part, utc_now_iso


FILES_CHANGELOG_PATH = PROJECT_ROOT / "changelog" / "files.md"
FOLDER_NAMES_PATH = PROJECT_ROOT / "mapping" / "folder_names.yml"
BEGIN_PENDING = "<!-- FILE_SYNC_PENDING_BEGIN -->"
END_PENDING = "<!-- FILE_SYNC_PENDING_END -->"

_state_lock = threading.RLock()
_folder_registry_cache: dict[str, Any] | None = None


class RateLimitDetected(RuntimeError):
    """Raised when Google blocks automated download requests."""


def _incoming_path(folder_path: str, filename: str) -> Path:
    parts = _normalized_folder_parts(folder_path)
    return INCOMING_DIR.joinpath(*parts, sanitize_path_part(filename))


def _fallback_normalized_name(value: str, level: str) -> str:
    separator = "-" if level == "branch" else "_"
    cleaned = value.strip().replace("&", " and ")
    cleaned = "".join(char if char.isalnum() else " " for char in cleaned)
    return separator.join(token.lower() for token in cleaned.split())


def _folder_name_registry() -> dict[str, Any]:
    global _folder_registry_cache
    if _folder_registry_cache is not None:
        return _folder_registry_cache
    if not FOLDER_NAMES_PATH.exists():
        _folder_registry_cache = {}
        return _folder_registry_cache
    with FOLDER_NAMES_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    _folder_registry_cache = data.get("name_registry") or {}
    return _folder_registry_cache


def _normalized_path_part(value: str, index: int) -> str:
    registry = _folder_name_registry()
    entry = registry.get(value)
    if isinstance(entry, dict) and entry.get("normalized"):
        return sanitize_path_part(str(entry["normalized"]))
    return sanitize_path_part(_fallback_normalized_name(value, "branch" if index == 0 else "folder"))


def _code_for_normalized(normalized: str) -> str:
    tokens = [token for token in normalized.replace("-", "_").split("_") if token]
    skip = {"and", "of", "the", "for", "in"}
    prefix: list[str] = []
    suffix: list[str] = []
    romans = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in {"ele", "elective"} and next_token in romans:
            suffix.append(f"e{next_token}")
            index += 2
            continue
        if token in romans or token.isdigit():
            prefix.append(token)
        elif token not in skip:
            prefix.append(token[0])
        index += 1
    base = "".join(prefix)
    return f"{base}_{'_'.join(suffix)}" if suffix else base


def _branch_code(branch_normalized: str) -> str:
    registry = _folder_name_registry()
    for entry in registry.values():
        if isinstance(entry, dict) and entry.get("normalized") == branch_normalized and entry.get("code"):
            return str(entry["code"])
    special = {"first-year": "fy", "m-b-a": "mba", "honors-course": "hc"}
    return special.get(branch_normalized, _code_for_normalized(branch_normalized))


def _normalized_folder_parts(folder_path: str) -> list[str]:
    raw_parts = [part for part in folder_path.split("/") if part]
    parts = [_normalized_path_part(part, index) for index, part in enumerate(raw_parts)]
    subject_indexes = {
        3,  # Standard: Branch / Year / Pattern / Subject
    }
    if parts[:1] == ["first-year"]:
        subject_indexes = {2}
    elif parts[:1] == ["m-b-a"]:
        subject_indexes = {3}
    elif parts[:1] == ["honors-course"]:
        subject_indexes = {2}
    if parts and len(parts) - 1 in subject_indexes:
        branch_code = _branch_code(parts[0])
        subject = parts[-1]
        suffix = f"_{branch_code}"
        if not subject.endswith(suffix):
            parts[-1] = f"{subject}{suffix}"
    return [sanitize_path_part(part) for part in parts]


def _known_file_ids() -> set[str]:
    return tracking.known_file_ids()


def _get_exception_file_ids() -> set[str]:
    exception_file = PROJECT_ROOT / "mapping" / "file-exception.yml"
    if not exception_file.exists():
        return set()
    try:
        with exception_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            exceptions = data.get("exceptions") or {}
            return set(exceptions.keys())
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to load file-exception.yml: %s", e)
        return set()


def _local_file_id_exists(file_id: str) -> bool:
    return tracking.file_has_local_copy(file_id)


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    signals = (
        "anti-automation",
        "automated queries",
        "rate limit",
        "rate-limit",
        "too many requests",
        "drive api error 403",
        "drive api error 429",
        "quota exceeded",
        "user rate limit exceeded",
    )
    return any(signal in text for signal in signals)


def _path_in_scope(path: str, scope: str | None) -> bool:
    if not scope:
        return True
    return path == scope or path.startswith(f"{scope}/")


def _standard_subjects(mapping: dict[str, Any]) -> list[dict[str, str]]:
    return iter_subject_folders(mapping)


def _first_year_subjects(mapping: dict[str, Any]) -> list[dict[str, str]]:
    subjects: list[dict[str, str]] = []
    for pattern_name, pattern in (mapping.get("patterns") or {}).items():
        for subject_name, subject in (pattern.get("subjects") or {}).items():
            folder_path = subject.get("path") or f"First Year/{pattern_name}/{subject_name}"
            subjects.append(
                {
                    "branch": "First Year",
                    "year": "",
                    "pattern": pattern_name,
                    "subject": subject_name,
                    "folder_path": folder_path,
                    "folder_id": subject["folder_id"],
                    "parent_id": subject["parent_id"],
                }
            )
    return sorted(subjects, key=lambda item: item["folder_path"])


def _mba_subjects(mapping: dict[str, Any]) -> list[dict[str, str]]:
    subjects: list[dict[str, str]] = []
    for semester_name, semester in (mapping.get("semesters") or {}).items():
        for pattern_name, pattern in (semester.get("patterns") or {}).items():
            for subject_name, subject in (pattern.get("subjects") or {}).items():
                folder_path = subject.get("drive_path") or subject.get("path") or f"M.B.A/{semester_name}/{pattern_name}/{subject_name}"
                subjects.append(
                    {
                        "branch": "M.B.A",
                        "year": semester_name,
                        "pattern": pattern_name,
                        "subject": subject_name,
                        "folder_path": folder_path,
                        "folder_id": subject["folder_id"],
                        "parent_id": subject["parent_id"],
                    }
                )
    return sorted(subjects, key=lambda item: item["folder_path"])


def _honors_subjects(mapping: dict[str, Any]) -> list[dict[str, str]]:
    subjects: list[dict[str, str]] = []
    for folder_path, meta in (mapping.get("folders") or {}).items():
        parts = [part for part in folder_path.split("/") if part]
        if len(parts) != 3:
            continue
        subjects.append(
            {
                "branch": "Honors Course",
                "year": parts[1],
                "pattern": "",
                "subject": parts[2],
                "folder_path": folder_path,
                "folder_id": meta["folder_id"],
                "parent_id": meta["parent_id"],
            }
        )
    return sorted(subjects, key=lambda item: item["folder_path"])


def load_all_subject_folders(scope: str | None = None) -> list[dict[str, str]]:
    mapping_dir = MAPPING_PATH.parent
    sources = [
        _standard_subjects(read_json(mapping_dir / "sync_mapping.json", default={}) or {}),
        _first_year_subjects(read_json(mapping_dir / "first_year_mapping.json", default={}) or {}),
        _mba_subjects(read_json(mapping_dir / "mba.json", default={}) or {}),
        _honors_subjects(read_json(mapping_dir / "honors_course_mapping.json", default={}) or {}),
    ]
    subjects = [item for source in sources for item in source]
    return [item for item in subjects if _path_in_scope(item["folder_path"], scope)]


def _change_key(change: dict[str, str]) -> tuple[str, str]:
    return change.get("file_id", ""), change.get("folder_path", "")


def _append_unique_changes(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = {_change_key(change) for change in existing}
    combined = list(existing)
    for change in incoming:
        key = _change_key(change)
        if key not in seen:
            combined.append(change)
            seen.add(key)
    return combined


def _pending_payload(changes: list[dict[str, str]], scope: str | None = None) -> dict[str, Any]:
    return {"generated_at": utc_now_iso(), "scope": scope or "all", "changes": changes}


def _render_files_changelog(payload: dict[str, Any]) -> str:
    changes = payload.get("changes", [])
    lines = [
        "# File Download Review",
        "",
        "This file is generated by `python3 tools/sync.py --files`.",
        "Review the pending files below, then use `--files --apply` to download them into `incoming/`.",
        "",
        f"- Generated at: `{payload.get('generated_at', '')}`",
        f"- Scope: `{payload.get('scope', 'all')}`",
        f"- Pending files: `{len(changes)}`",
        "",
    ]
    if changes:
        lines.extend(["| Action | Folder path | Filename | File ID |", "| --- | --- | --- | --- |"])
        for change in changes:
            lines.append(f"| {change['action']} | `{change['folder_path']}` | `{change['filename']}` | `{change['file_id']}` |")
        lines.append("")
    else:
        lines.extend(["No file changes are pending.", ""])

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


def read_files_changelog() -> dict[str, Any]:
    if not FILES_CHANGELOG_PATH.exists():
        raise FileNotFoundError("changelog/files.md does not exist. Run: python3 tools/sync.py --files")
    text = FILES_CHANGELOG_PATH.read_text(encoding="utf-8")
    start = text.rfind(BEGIN_PENDING)
    end = text.rfind(END_PENDING)
    if start == -1 or end == -1 or end <= start:
        raise ValueError("changelog/files.md is missing the pending JSON block.")
    block = text[start:end]
    json_start = block.find("```json")
    if json_start == -1:
        raise ValueError("changelog/files.md is missing the pending JSON fence.")
    json_text = block[json_start + len("```json") :]
    json_end = json_text.find("```")
    if json_end == -1:
        raise ValueError("changelog/files.md has an unterminated pending JSON fence.")
    return json.loads(json_text[:json_end].strip())


def write_files_changelog(changes: list[dict[str, str]], scope: str | None = None, append_pending: bool = False) -> dict[str, Any]:
    if append_pending and FILES_CHANGELOG_PATH.exists():
        try:
            existing_payload = read_files_changelog()
            changes = _append_unique_changes(existing_payload.get("changes") or [], changes)
        except (json.JSONDecodeError, ValueError):
            pass
    payload = _pending_payload(changes, scope)
    FILES_CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    FILES_CHANGELOG_PATH.write_text(_render_files_changelog(payload), encoding="utf-8")
    return payload


def _log_pending_files(logger: logging.Logger, changes: list[dict[str, str]], limit: int = 10) -> None:
    if not changes:
        return
    logger.info("Pending file list (showing %d of %d):", min(limit, len(changes)), len(changes))
    for index, change in enumerate(changes[:limit], start=1):
        logger.info(
            "  %d. %s/%s",
            index,
            change.get("folder_path", ""),
            change.get("filename", ""),
        )
    remaining = len(changes) - limit
    if remaining > 0:
        logger.info("  ... and %d more pending file(s).", remaining)


def review_file_changes(
    client: GoogleDriveClient,
    scope: str | None = None,
    logger: logging.Logger | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    logger = logger or logging.getLogger(__name__)
    workers = max(1, workers)
    known_ids = _known_file_ids()
    logger.info("Loaded %d known file IDs from tracking/manifest.db.", len(known_ids))
    exception_ids = _get_exception_file_ids()
    if exception_ids:
        logger.info("Loaded %d exception file IDs from mapping/file-exception.yml.", len(exception_ids))

    subject_folders = load_all_subject_folders(scope)
    logger.info(
        "Scanning %d mapped subject folders%s with %d worker%s.",
        len(subject_folders),
        f" under scope: {scope}" if scope else "",
        workers,
        "" if workers == 1 else "s",
    )

    def scan_subject(index: int, subject_folder: dict[str, str]) -> tuple[int, list[dict[str, str]], int, float]:
        started = time.monotonic()
        folder_path = subject_folder["folder_path"]
        subject = subject_folder["subject"]
        logger.info(
            "Scanning subject %d/%d: %s",
            index,
            len(subject_folders),
            folder_path,
        )
        drive_files = client.list_pdfs(subject_folder["folder_id"])
        subject_changes: list[dict[str, str]] = []
        for drive_file in drive_files:
            file_id = drive_file["id"]
            if file_id in known_ids:
                continue
            if file_id in exception_ids:
                logger.info("File '%s' (%s) appeared in Drive but was skipped due to file-exception.yml", drive_file["name"], file_id)
                continue
            filename = drive_file["name"]
            subject_changes.append(
                {
                    "action": "download",
                    "file_id": file_id,
                    "filename": filename,
                    "modified_time": drive_file.get("modifiedTime", ""),
                    "folder_path": folder_path,
                    "folder_id": subject_folder["folder_id"],
                    "subject": subject,
                    "incoming_path": _incoming_path(folder_path, filename).relative_to(PROJECT_ROOT).as_posix(),
                }
            )
            tracking.upsert_discovered_file(subject_changes[-1])
        elapsed = time.monotonic() - started
        logger.info(
            "Finished subject %d/%d in %.1fs: found %d PDFs, %d new.",
            index,
            len(subject_folders),
            elapsed,
            len(drive_files),
            len(subject_changes),
        )
        return index, subject_changes, len(drive_files), elapsed

    changes: list[dict[str, str]] = []
    completed = 0
    if workers > 1 and len(subject_folders) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(scan_subject, index, subject_folder)
                for index, subject_folder in enumerate(subject_folders, start=1)
            ]
            for future in as_completed(futures):
                index, subject_changes, _pdf_count, _elapsed = future.result()
                changes.extend(subject_changes)
                completed += 1
                logger.info(
                    "Progress: completed %d/%d subjects; total pending %d.",
                    completed,
                    len(subject_folders),
                    len(changes),
                )
    else:
        for index, subject_folder in enumerate(subject_folders, start=1):
            _index, subject_changes, _pdf_count, _elapsed = scan_subject(index, subject_folder)
            changes.extend(subject_changes)
            logger.info(
                "Progress: completed %d/%d subjects; total pending %d.",
                index,
                len(subject_folders),
                len(changes),
            )

    changes.sort(key=lambda change: (change["folder_path"], change["filename"]))
    logger.info("File review complete. Pending downloads found: %d.", len(changes))
    payload = write_files_changelog(changes, scope, append_pending=True)
    _log_pending_files(logger, payload.get("changes") or [])
    return payload


def _mark_downloaded(change: dict[str, str]) -> None:
    tracking.upsert_discovered_file(change)
    tracking.update_stage(
        change["file_id"],
        "DOWNLOADED",
        current_path=change["incoming_path"],
        reason="Downloaded into incoming/",
    )


def _write_payload(payload: dict[str, Any]) -> None:
    FILES_CHANGELOG_PATH.write_text(_render_files_changelog(payload), encoding="utf-8")


def _complete_change(payload: dict[str, Any], completed: dict[str, str]) -> None:
    payload["changes"] = [
        change
        for change in (payload.get("changes") or [])
        if _change_key(change) != _change_key(completed)
    ]
    payload["generated_at"] = utc_now_iso()
    _write_payload(payload)


def _download_with_gdown(file_id: str, destination: Path, logger: logging.Logger | None = None) -> None:
    logger = logger or logging.getLogger(__name__)
    try:
        import gdown  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("gdown is not installed. Install it with: python3 -m pip install gdown") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".part")
    url = f"https://drive.google.com/uc?id={file_id}"
    parameters = inspect.signature(gdown.download).parameters
    
    success = False
    try:
        if "id" in parameters:
            logger.info("gdown method: download(id=...) -> %s", temp_path)
            result = gdown.download(id=file_id, output=str(temp_path), quiet=True)
        elif "fuzzy" in parameters:
            logger.info("gdown method: download(url=..., fuzzy=True) -> %s", temp_path)
            result = gdown.download(url=url, output=str(temp_path), quiet=True, fuzzy=True)
        else:
            logger.info("gdown method: download(url=...) -> %s", temp_path)
            result = gdown.download(url=url, output=str(temp_path), quiet=True)
        if result:
            success = True
    except Exception as exc:
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        logger.warning("gdown did not complete for %s; trying fallback. Reason: %s", file_id, first_line)

    if not success:
        fallback_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        _download_with_fallback_request(fallback_url, temp_path, file_id, logger)

    try:
        _validate_downloaded_pdf(temp_path, file_id)
        with open(temp_path, "rb") as f:
            header = f.read(32).lower()
        if b"%pdf" not in header:
            logger.warning("Downloaded file for %s does not start with a PDF header; keeping it after HTML check.", file_id)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    temp_path.replace(destination)


def _download_with_fallback_request(url: str, temp_path: Path, file_id: str, logger: logging.Logger) -> None:
    curl_path = shutil.which("curl")
    if curl_path:
        logger.info("fallback method: curl -> %s", url)
        result = subprocess.run(
            [
                curl_path,
                "-L",
                "--fail",
                "--silent",
                "--show-error",
                "--connect-timeout",
                "30",
                "--max-time",
                "180",
                "-A",
                "Mozilla/5.0",
                "-o",
                str(temp_path),
                url,
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0 and temp_path.exists() and temp_path.stat().st_size > 0:
            return
        logger.warning(
            "curl fallback failed for %s: %s",
            file_id,
            (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
        )
        if temp_path.exists():
            temp_path.unlink()

    import urllib.request

    logger.info("fallback method: python HTTP request -> %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as response, open(temp_path, "wb") as out_file:
            out_file.write(response.read())
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"gdown, curl, and HTTP fallback failed for file ID: {file_id}. Error: {exc}")


def _validate_downloaded_pdf(path: Path, file_id: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Download did not create destination for ID: {file_id}")
    if path.stat().st_size < 1024:
        raise RuntimeError(f"Downloaded response was too small to be a PDF for ID: {file_id}")
    with path.open("rb") as handle:
        header = handle.read(4096).lower()
    if b"<!doctype html" in header or b"<html" in header:
        raise RuntimeError(f"Google Drive returned an HTML page instead of a PDF for ID: {file_id}")
    if b"%pdf" not in header:
        if not header.strip(b"\x00\r\n\t "):
            raise RuntimeError(f"Downloaded response was all zero bytes instead of a PDF for ID: {file_id}")
        raise RuntimeError(f"Downloaded response did not contain a PDF header for ID: {file_id}")


def _drive_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _apply_file_changes_with_rclone(
    payload: dict[str, Any],
    changes: list[dict[str, str]],
    logger: logging.Logger,
    transfers: int,
    max_downloads: int | None = None,
) -> dict[str, int]:
    rclone_path = shutil.which("rclone")
    if not rclone_path:
        raise RuntimeError("rclone is not installed or not on PATH. Install it from https://rclone.org/install/")

    download_changes = [change for change in changes if change.get("action") == "download"]
    if max_downloads is not None and max_downloads > 0:
        download_changes = download_changes[:max_downloads]
    if not download_changes:
        return {"downloaded": 0, "remaining": len(payload.get("changes") or [])}

    for change in download_changes:
        normalized_incoming = _incoming_path(change["folder_path"], change["filename"]).relative_to(PROJECT_ROOT).as_posix()
        if change.get("incoming_path") != normalized_incoming:
            change["incoming_path"] = normalized_incoming

    batch_dir = PROJECT_ROOT / "sync_plan" / "rclone"
    batch_dir.mkdir(parents=True, exist_ok=True)
    csv_path = batch_dir / f"download_urls_{int(time.time())}_{threading.get_ident()}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for change in download_changes:
            writer.writerow([_drive_download_url(change["file_id"]), change["incoming_path"]])

    transfer_count = max(1, transfers)
    logger.info("rclone bulk: preparing %d file(s) with %d transfer(s).", len(download_changes), transfer_count)
    command = [
        rclone_path,
        "copyurl",
        "--urls",
        str(csv_path),
        str(PROJECT_ROOT),
        "--transfers",
        str(transfer_count),
        "--checkers",
        str(max(4, transfer_count * 2)),
        "--retries",
        "3",
        "--low-level-retries",
        "5",
        "--disable-http2",
        "--user-agent",
        "curl",
        "--stats",
        "5s",
        "--stats-one-line",
        "--progress",
    ]
    logger.info("rclone bulk: starting copyurl batch.")
    result = subprocess.run(command, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
    for output in (result.stdout, result.stderr):
        for line in (output or "").splitlines():
            if line.strip():
                logger.info("rclone: %s", line.strip())

    downloaded = 0
    failed = 0
    for index, change in enumerate(download_changes, start=1):
        destination = PROJECT_ROOT / change["incoming_path"]
        try:
            _validate_downloaded_pdf(destination, change["file_id"])
        except Exception as exc:
            failed += 1
            logger.warning(
                "rclone invalid/missing file %d/%d: %s (%s)",
                index,
                len(download_changes),
                change["incoming_path"],
                exc,
            )
            continue
        _mark_downloaded(change)
        _complete_change(payload, change)
        downloaded += 1
        logger.info(
            "Downloaded file %d/%d with rclone: %s -> %s; remaining %d.",
            index,
            len(download_changes),
            change["filename"],
            change["incoming_path"],
            len(payload.get("changes") or []),
        )

    try:
        csv_path.unlink()
    except OSError:
        pass

    if result.returncode != 0 and downloaded == 0:
        raise RuntimeError(f"rclone failed with exit code {result.returncode}; {len(payload.get('changes') or [])} pending remain.")
    if failed:
        logger.warning("rclone finished with %d invalid or missing file(s); those remain pending.", failed)
    return {"downloaded": downloaded, "remaining": len(payload.get("changes") or [])}


def apply_file_changes(
    client: GoogleDriveClient | None,
    logger: logging.Logger | None = None,
    downloader: str = "drive",
    download_delay: float = 0,
    workers: int = 1,
    max_downloads: int | None = None,
) -> dict[str, int]:
    logger = logger or logging.getLogger(__name__)
    if downloader not in {"drive", "gdown", "rclone"}:
        raise ValueError(f"Unsupported downloader: {downloader}")
    if downloader == "drive" and client is None:
        raise ValueError("Official Drive downloader requires a GoogleDriveClient.")

    payload = read_files_changelog()
    changes = payload.get("changes") or []
    if not changes:
        return {"downloaded": 0, "remaining": 0}

    if downloader == "rclone":
        return _apply_file_changes_with_rclone(payload, changes, logger, workers, max_downloads)

    downloaded = 0
    initial_count = len(changes)
    rate_limit_event = threading.Event()
    
    shared_payload = payload

    def process_change(change: dict[str, str], index: int) -> bool:
        if rate_limit_event.is_set():
            return False
        with _state_lock:
            remaining_before = len(shared_payload.get("changes") or [])
            if _local_file_id_exists(change["file_id"]):
                logger.info(
                    "Skipping already recorded file %d/%d: %s/%s; remaining %d.",
                    index,
                    initial_count,
                    change["folder_path"],
                    change["filename"],
                    max(remaining_before - 1, 0),
                )
                _complete_change(shared_payload, change)
                return False

        normalized_incoming = _incoming_path(change["folder_path"], change["filename"]).relative_to(PROJECT_ROOT).as_posix()
        if change.get("incoming_path") != normalized_incoming:
            logger.info(
                "Using normalized incoming path for %s: %s",
                change["filename"],
                normalized_incoming,
            )
            change["incoming_path"] = normalized_incoming
            with _state_lock:
                _write_payload(shared_payload)
        destination = PROJECT_ROOT / change["incoming_path"]
        logger.info(
            "Downloading file %d/%d with %s: %s/%s -> %s",
            index,
            initial_count,
            downloader,
            change["folder_path"],
            change["filename"],
            change["incoming_path"],
        )
        
        try:
            if downloader == "gdown":
                logger.info("gdown source URL: https://drive.google.com/uc?id=%s", change["file_id"])
                _download_with_gdown(change["file_id"], destination, logger)
            else:
                assert client is not None
                client.download_file(change["file_id"], destination)
                _validate_downloaded_pdf(destination, change["file_id"])
        except Exception as e:
            if destination.exists():
                destination.unlink()
            if _is_rate_limit_error(e):
                rate_limit_event.set()
                logger.error(
                    "Rate limit detected while downloading %s. Stopping this batch; remaining files stay pending.",
                    change["filename"],
                )
            else:
                logger.error("Failed to download %s: %s", change["filename"], e)
            return False

        with _state_lock:
            _mark_downloaded(change)
            _complete_change(shared_payload, change)
            remaining_after = max(len(shared_payload.get("changes") or []), 0)
            logger.info(
                "Downloaded file %d/%d; remaining %d.",
                index,
                initial_count,
                remaining_after,
            )

        if download_delay > 0 and remaining_after > 0:
            logger.info("Waiting %.1f seconds before next download.", download_delay)
            time.sleep(download_delay)

        return True

    download_changes = [c for c in changes if c.get("action") == "download"]
    if max_downloads is not None and max_downloads > 0:
        download_changes = download_changes[:max_downloads]
        logger.info("Limiting this apply run to %d pending download(s).", len(download_changes))
    
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for index, change in enumerate(download_changes, start=1):
                if rate_limit_event.is_set():
                    break
                futures.append(executor.submit(process_change, change, index))
            for future in as_completed(futures):
                if future.result():
                    downloaded += 1
                if rate_limit_event.is_set():
                    break
    else:
        for index, change in enumerate(download_changes, start=1):
            if rate_limit_event.is_set():
                break
            if process_change(change, index):
                downloaded += 1

    if rate_limit_event.is_set():
        remaining = len(shared_payload.get("changes") or [])
        raise RateLimitDetected(
            f"Google rate limit detected after {downloaded} successful download(s); {remaining} pending file(s) remain."
        )

    return {"downloaded": downloaded, "remaining": len(shared_payload.get("changes") or [])}


def discard_file_changes(identifiers: list[str] | None = None) -> dict[str, int]:
    payload = read_files_changelog()
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
            if change.get("file_id") not in wanted
            and change.get("filename") not in wanted
            and change.get("folder_path") not in wanted
        ]
        discarded = len(changes) - len(remaining_changes)

    payload["changes"] = remaining_changes
    payload["generated_at"] = utc_now_iso()
    FILES_CHANGELOG_PATH.write_text(_render_files_changelog(payload), encoding="utf-8")
    return {"discarded": discarded, "remaining": len(remaining_changes)}
