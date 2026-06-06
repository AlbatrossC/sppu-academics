"""SQLite tracking store keyed by Google Drive file ID."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from common.utils import PROJECT_ROOT, TRACKING_DB_PATH, utc_now_iso


STAGES = (
    "DISCOVERED",
    "DOWNLOADED",
    "FOLDER_RENAMED",
    "FILE_RENAMED",
    "NEEDS_REVIEW",
    "VERIFIED",
    "MOVED",
    "MISSING",
)
STAGE_ORDER = {stage: index for index, stage in enumerate(STAGES)}
BRANCH_TYPES = {"standard", "first_year", "mba", "honors"}


def connect() -> sqlite3.Connection:
    TRACKING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(TRACKING_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    ensure_schema(connection)
    return connection


def ensure_schema(connection: sqlite3.Connection | None = None) -> None:
    own_connection = connection is None
    if connection is None:
        TRACKING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(TRACKING_DB_PATH)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
          file_id TEXT PRIMARY KEY,
          drive_filename TEXT NOT NULL,
          drive_modified_time TEXT,
          drive_folder_id TEXT,
          drive_folder_path TEXT NOT NULL,
          branch_type TEXT NOT NULL CHECK (
            branch_type IN ('standard', 'first_year', 'mba', 'honors')
          ),
          branch TEXT,
          year TEXT,
          semester TEXT,
          pattern TEXT,
          subject TEXT NOT NULL,
          current_stage TEXT NOT NULL CHECK (
            current_stage IN (
              'DISCOVERED',
              'DOWNLOADED',
              'FOLDER_RENAMED',
              'FILE_RENAMED',
              'NEEDS_REVIEW',
              'VERIFIED',
              'MOVED',
              'MISSING'
            )
          ),
          current_path TEXT,
          expected_path TEXT,
          final_path TEXT,
          original_filename TEXT NOT NULL,
          renamed_filename TEXT,
          retry_count INTEGER NOT NULL DEFAULT 0,
          last_retry_at TEXT,
          last_groq_key_index INTEGER,
          groq_model TEXT,
          review_category TEXT,
          review_reason TEXT,
          discovered_at TEXT NOT NULL,
          downloaded_at TEXT,
          folder_renamed_at TEXT,
          file_renamed_at TEXT,
          verified_at TEXT,
          moved_at TEXT,
          missing_at TEXT,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS file_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          file_id TEXT NOT NULL REFERENCES files(file_id),
          from_stage TEXT,
          to_stage TEXT NOT NULL,
          path TEXT,
          reason TEXT,
          groq_key_index INTEGER,
          created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_files_stage ON files(current_stage);
        CREATE INDEX IF NOT EXISTS idx_files_branch_type ON files(branch_type);
        CREATE INDEX IF NOT EXISTS idx_files_current_path ON files(current_path);
        CREATE INDEX IF NOT EXISTS idx_files_expected_path ON files(expected_path);
        CREATE INDEX IF NOT EXISTS idx_files_final_path ON files(final_path);
        CREATE INDEX IF NOT EXISTS idx_files_retry_count ON files(retry_count);
        CREATE INDEX IF NOT EXISTS idx_files_review_category ON files(review_category);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_files_expected_path_unique
          ON files(expected_path)
          WHERE expected_path IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_files_final_path_unique
          ON files(final_path)
          WHERE final_path IS NOT NULL;
        PRAGMA user_version = 1;
        """
    )
    connection.commit()
    if own_connection:
        connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def project_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def infer_branch_metadata(folder_path: str) -> dict[str, str]:
    parts = [part for part in folder_path.split("/") if part]
    if not parts:
        return {"branch_type": "standard", "branch": "", "year": "", "semester": "", "pattern": "", "subject": ""}

    if parts[0] == "First Year":
        return {
            "branch_type": "first_year",
            "branch": "First Year",
            "year": "",
            "semester": "",
            "pattern": parts[1] if len(parts) > 1 else "",
            "subject": parts[2] if len(parts) > 2 else parts[-1],
        }
    if parts[0] == "M.B.A":
        return {
            "branch_type": "mba",
            "branch": "M.B.A",
            "year": "",
            "semester": parts[1] if len(parts) > 1 else "",
            "pattern": parts[2] if len(parts) > 2 else "",
            "subject": parts[3] if len(parts) > 3 else parts[-1],
        }
    if parts[0] == "Honors Course":
        return {
            "branch_type": "honors",
            "branch": "Honors Course",
            "year": parts[1] if len(parts) > 1 else "",
            "semester": "",
            "pattern": "",
            "subject": parts[2] if len(parts) > 2 else parts[-1],
        }
    return {
        "branch_type": "standard",
        "branch": parts[0],
        "year": parts[1] if len(parts) > 1 else "",
        "semester": "",
        "pattern": parts[2] if len(parts) > 2 else "",
        "subject": parts[3] if len(parts) > 3 else parts[-1],
    }


def known_file_ids() -> set[str]:
    with connect() as connection:
        return {row["file_id"] for row in connection.execute("SELECT file_id FROM files")}


def file_exists(file_id: str) -> bool:
    with connect() as connection:
        row = connection.execute("SELECT 1 FROM files WHERE file_id = ?", (file_id,)).fetchone()
        return row is not None


def file_has_local_copy(file_id: str) -> bool:
    with connect() as connection:
        row = connection.execute(
            "SELECT current_stage, current_path FROM files WHERE file_id = ?",
            (file_id,),
        ).fetchone()
    if not row:
        return False
    return bool(row["current_path"]) and STAGE_ORDER.get(row["current_stage"], 0) >= STAGE_ORDER["DOWNLOADED"]


def get_file(file_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        return row_to_dict(connection.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone())


def find_by_current_path(path: str) -> dict[str, Any] | None:
    normalized = Path(path).as_posix()
    with connect() as connection:
        return row_to_dict(connection.execute("SELECT * FROM files WHERE current_path = ?", (normalized,)).fetchone())


def find_by_any_path(paths: Iterable[str]) -> dict[str, Any] | None:
    candidates = [Path(path).as_posix() for path in paths if path]
    if not candidates:
        return None
    placeholders = ",".join("?" for _ in candidates)
    query = (
        "SELECT * FROM files WHERE current_path IN ({0}) OR expected_path IN ({0}) "
        "OR final_path IN ({0}) LIMIT 1"
    ).format(placeholders)
    with connect() as connection:
        return row_to_dict(connection.execute(query, (*candidates, *candidates, *candidates)).fetchone())


def all_files() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute("SELECT * FROM files ORDER BY drive_folder_path, drive_filename").fetchall()
        return [dict(row) for row in rows]


def upsert_discovered_file(change: dict[str, Any]) -> None:
    now = utc_now_iso()
    folder_path = str(change.get("folder_path", ""))
    metadata = infer_branch_metadata(folder_path)
    with connect() as connection:
        existing = connection.execute("SELECT current_stage FROM files WHERE file_id = ?", (change["file_id"],)).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE files
                SET drive_filename = ?, drive_modified_time = ?, drive_folder_id = ?,
                    drive_folder_path = ?, branch_type = ?, branch = ?, year = ?,
                    semester = ?, pattern = ?, subject = ?, updated_at = ?
                WHERE file_id = ?
                """,
                (
                    change.get("filename", ""),
                    change.get("modified_time", ""),
                    change.get("folder_id", ""),
                    folder_path,
                    metadata["branch_type"],
                    metadata["branch"],
                    metadata["year"],
                    metadata["semester"],
                    metadata["pattern"],
                    metadata["subject"],
                    now,
                    change["file_id"],
                ),
            )
            return
        connection.execute(
            """
            INSERT INTO files (
              file_id, drive_filename, drive_modified_time, drive_folder_id,
              drive_folder_path, branch_type, branch, year, semester, pattern,
              subject, current_stage, current_path, expected_path, final_path,
              original_filename, renamed_filename, discovered_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISCOVERED', NULL, NULL, NULL, ?, NULL, ?, ?)
            """,
            (
                change["file_id"],
                change.get("filename", ""),
                change.get("modified_time", ""),
                change.get("folder_id", ""),
                folder_path,
                metadata["branch_type"],
                metadata["branch"],
                metadata["year"],
                metadata["semester"],
                metadata["pattern"],
                metadata["subject"],
                change.get("filename", ""),
                now,
                now,
            ),
        )
        add_event(connection, change["file_id"], None, "DISCOVERED", None, "Discovered in Drive")


def add_event(
    connection: sqlite3.Connection,
    file_id: str,
    from_stage: str | None,
    to_stage: str,
    path: str | None,
    reason: str | None,
    groq_key_index: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO file_events (file_id, from_stage, to_stage, path, reason, groq_key_index, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (file_id, from_stage, to_stage, path, reason, groq_key_index, utc_now_iso()),
    )


def update_stage(
    file_id: str,
    stage: str,
    *,
    current_path: str | None = None,
    expected_path: str | None = None,
    final_path: str | None = None,
    renamed_filename: str | None = None,
    review_category: str | None = None,
    review_reason: str | None = None,
    groq_key_index: int | None = None,
    groq_model: str | None = None,
    increment_retry: bool = False,
    reason: str | None = None,
) -> None:
    if stage not in STAGE_ORDER:
        raise ValueError(f"Unknown tracking stage: {stage}")
    now = utc_now_iso()
    timestamp_column = {
        "DOWNLOADED": "downloaded_at",
        "FOLDER_RENAMED": "folder_renamed_at",
        "FILE_RENAMED": "file_renamed_at",
        "VERIFIED": "verified_at",
        "MOVED": "moved_at",
        "MISSING": "missing_at",
    }.get(stage)
    with connect() as connection:
        row = connection.execute("SELECT current_stage FROM files WHERE file_id = ?", (file_id,)).fetchone()
        if not row:
            raise KeyError(f"No tracking row for file_id: {file_id}")
        assignments = ["current_stage = ?", "updated_at = ?"]
        values: list[Any] = [stage, now]
        if current_path is not None:
            assignments.append("current_path = ?")
            values.append(Path(current_path).as_posix())
        if expected_path is not None:
            assignments.append("expected_path = ?")
            values.append(Path(expected_path).as_posix())
        if final_path is not None:
            assignments.append("final_path = ?")
            values.append(Path(final_path).as_posix())
        if renamed_filename is not None:
            assignments.append("renamed_filename = ?")
            values.append(renamed_filename)
        if review_category is not None:
            assignments.append("review_category = ?")
            values.append(review_category)
        if review_reason is not None:
            assignments.append("review_reason = ?")
            values.append(review_reason)
        if groq_key_index is not None:
            assignments.append("last_groq_key_index = ?")
            values.append(groq_key_index)
        if groq_model is not None:
            assignments.append("groq_model = ?")
            values.append(groq_model)
        if increment_retry:
            assignments.append("retry_count = retry_count + 1")
            assignments.append("last_retry_at = ?")
            values.append(now)
        if timestamp_column:
            assignments.append(f"{timestamp_column} = COALESCE({timestamp_column}, ?)")
            values.append(now)
        values.append(file_id)
        connection.execute(f"UPDATE files SET {', '.join(assignments)} WHERE file_id = ?", values)
        add_event(connection, file_id, row["current_stage"], stage, current_path, reason or review_reason, groq_key_index)


def record_review_failure(
    file_id: str,
    *,
    review_category: str,
    review_reason: str,
    groq_key_index: int | None = None,
    groq_model: str | None = None,
) -> None:
    now = utc_now_iso()
    with connect() as connection:
        row = connection.execute("SELECT current_stage, current_path FROM files WHERE file_id = ?", (file_id,)).fetchone()
        if not row:
            raise KeyError(f"No tracking row for file_id: {file_id}")
        connection.execute(
            """
            UPDATE files
            SET retry_count = retry_count + 1,
                last_retry_at = ?,
                last_groq_key_index = COALESCE(?, last_groq_key_index),
                groq_model = COALESCE(?, groq_model),
                review_category = ?,
                review_reason = ?,
                updated_at = ?
            WHERE file_id = ?
            """,
            (now, groq_key_index, groq_model, review_category, review_reason, now, file_id),
        )
        add_event(connection, file_id, row["current_stage"], row["current_stage"], row["current_path"], review_reason, groq_key_index)


def advance_path_prefix(source_prefix: str, target_prefix: str, stage: str = "FOLDER_RENAMED") -> int:
    source = Path(source_prefix).as_posix().rstrip("/")
    target = Path(target_prefix).as_posix().rstrip("/")
    now = utc_now_iso()
    changed = 0
    with connect() as connection:
        rows = connection.execute(
            "SELECT file_id, current_stage, current_path FROM files WHERE current_path = ? OR current_path LIKE ?",
            (source, f"{source}/%"),
        ).fetchall()
        for row in rows:
            current = str(row["current_path"])
            suffix = current[len(source) :].lstrip("/")
            new_path = f"{target}/{suffix}" if suffix else target
            next_stage = stage if STAGE_ORDER.get(row["current_stage"], 0) < STAGE_ORDER[stage] else row["current_stage"]
            connection.execute(
                """
                UPDATE files
                SET current_path = ?, current_stage = ?, folder_renamed_at = COALESCE(folder_renamed_at, ?), updated_at = ?
                WHERE file_id = ?
                """,
                (new_path, next_stage, now, now, row["file_id"]),
            )
            add_event(connection, row["file_id"], row["current_stage"], next_stage, new_path, "Folder path normalized")
            changed += 1
    return changed


def counts_by_stage() -> Counter[str]:
    with connect() as connection:
        rows = connection.execute("SELECT current_stage, COUNT(*) AS count FROM files GROUP BY current_stage").fetchall()
    counts: Counter[str] = Counter({stage: 0 for stage in STAGES})
    for row in rows:
        counts[row["current_stage"]] = row["count"]
    return counts


def needs_review_reasons() -> Counter[str]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT COALESCE(NULLIF(review_category, ''), 'manual_check') AS category, COUNT(*) AS count
            FROM files
            WHERE current_stage = 'NEEDS_REVIEW'
            GROUP BY category
            """
        ).fetchall()
    return Counter({row["category"]: row["count"] for row in rows})


def retry_summary() -> Counter[str]:
    with connect() as connection:
        rows = connection.execute("SELECT retry_count FROM files WHERE retry_count > 0").fetchall()
    summary: Counter[str] = Counter()
    for row in rows:
        retry_count = int(row["retry_count"])
        summary["3+ retries" if retry_count >= 3 else f"{retry_count} retry"] += 1
    return summary
