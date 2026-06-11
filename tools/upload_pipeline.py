"""Publish local papers to R2/Cloudinary and build frontend manifests."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience import.
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAPERS_DIR = PROJECT_ROOT / "papers"
TRACKING_DB = PROJECT_ROOT / "tracking" / "manifest.db"
UPLOAD_DB = PROJECT_ROOT / "tracking" / "uploads.db"
MANIFEST_DIR = PROJECT_ROOT / "manifest"
FOLDER_NAMES_PATH = PROJECT_ROOT / "mapping" / "folder_names.yml"
SEMESTER_MAPPING_PATH = PROJECT_ROOT / "mapping" / "semester_mapping.yml"

PATTERN_ALIASES = {
    "2019_pattren": "2019_pattern",
    "2019 Pattren": "2019_pattern",
}
VALID_STATES = {"PENDING", "UPLOADED", "MODIFIED", "RENAMED", "REMOVED", "FAILED", "NEEDS_TRACKING_ID"}
PUBLISH_STATES = {"UPLOADED"}
PATTERN_FILES = {"2012_pattern": "2012.json", "2015_pattern": "2015.json", "2019_pattern": "2019.json"}
PATTERN_LABELS = {"2012_pattern": "2012", "2015_pattern": "2015", "2019_pattern": "2019"}
DELETE_PREFIX = "papers/"
DEFAULT_R2_BUCKET = "sppu-pyqs"
DEFAULT_R2_ENDPOINT = "https://6941a537dfa8bea2a69f8510462ea7d4.r2.cloudflarestorage.com"
DEFAULT_R2_PUBLIC_BASE_URL = "https://sppu-pyqs.albatrossc.workers.dev"
SKIP_WORDS = {"and", "of", "the", "for", "in"}
ROMAN_NUMERALS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=True, allow_unicode=False)
    temp_path.replace(path)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temp_path.replace(path)


def load_environment() -> None:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env")
        return

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tokenise(value: str) -> list[str]:
    prepared = value.strip()
    prepared = re.sub(r"&", " and ", prepared)
    prepared = re.sub(r"\+", " plus ", prepared)
    prepared = re.sub(r"@", " at ", prepared)
    prepared = re.sub(r"%", " percent ", prepared)
    prepared = re.sub(r"[^A-Za-z0-9]+", " ", prepared)
    return [token for token in prepared.split() if token]


def normalize_name(value: str, *, branch: bool = False) -> str:
    separator = "-" if branch else "_"
    parts: list[str] = []
    for token in tokenise(value):
        upper = token.upper()
        parts.append(upper if upper in ROMAN_NUMERALS else token.lower())
    return separator.join(parts)


def code_for_name(normalized: str) -> str:
    tokens = [token for token in re.split(r"[-_]+", normalized) if token]
    prefix: list[str] = []
    suffix: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in {"ele", "elective"} and next_token in ROMAN_NUMERALS:
            suffix.append(f"e{next_token}")
            index += 2
            continue
        if token in ROMAN_NUMERALS or token.isdigit():
            prefix.append(token)
        elif token not in SKIP_WORDS:
            prefix.append(token[0])
        index += 1
    base = "".join(prefix)
    return f"{base}_{'_'.join(suffix)}" if suffix else base


class NameLookup:
    def __init__(self) -> None:
        data = read_yaml(FOLDER_NAMES_PATH)
        self.registry = data.get("name_registry") or {}
        self.pattern_aliases = dict(PATTERN_ALIASES)
        self.pattern_aliases.update((data.get("rules") or {}).get("pattern_aliases") or {})
        self.normalized_to_display: dict[str, str] = {}
        self.normalized_to_code: dict[str, str] = {
            "first-year": "fy",
            "m-b-a": "mba",
            "honors-course": "hc",
        }
        for original, entry in self.registry.items():
            if not isinstance(entry, dict):
                continue
            normalized = entry.get("normalized")
            if not normalized:
                continue
            normalized_str = str(normalized)
            self.normalized_to_display.setdefault(normalized_str, str(original))
            if entry.get("code"):
                self.normalized_to_code[normalized_str] = str(entry["code"])

    def normalize_pattern(self, value: str) -> str:
        return self.pattern_aliases.get(value) or self.pattern_aliases.get(normalize_name(value)) or normalize_name(value)

    def normalize_branch(self, value: str) -> str:
        if value in self.pattern_aliases:
            return self.pattern_aliases[value]
        if value in self.normalized_to_display:
            return value
        entry = self.registry.get(value)
        if isinstance(entry, dict) and entry.get("normalized"):
            return str(entry["normalized"])
        return normalize_name(value, branch=True)

    def normalize_other(self, value: str) -> str:
        if value in self.pattern_aliases:
            return self.pattern_aliases[value]
        if value in self.normalized_to_display:
            return value
        entry = self.registry.get(value)
        if isinstance(entry, dict) and entry.get("normalized"):
            return str(entry["normalized"])
        return normalize_name(value)

    def display(self, normalized: str) -> str:
        return self.normalized_to_display.get(normalized, normalized.replace("-", " ").replace("_", " ").title())

    def code(self, normalized: str) -> str:
        return self.normalized_to_code.get(normalized, code_for_name(normalized.replace("-", "_")))


def strip_subject_suffix(subject: str, branch_code: str, year_or_semester: str = "") -> str:
    if year_or_semester and subject.endswith(f"_{branch_code}_{year_or_semester}"):
        return subject[: -len(f"_{branch_code}_{year_or_semester}")]
    if subject.endswith(f"_{branch_code}"):
        return subject[: -len(f"_{branch_code}")]
    return subject


def parse_papers_path(path: Path, names: NameLookup) -> dict[str, str] | None:
    try:
        parts = path.relative_to(PROJECT_ROOT).parts
    except ValueError:
        return None
    if len(parts) < 5 or parts[0] != "papers":
        return None

    branch = names.normalize_branch(parts[1])
    branch_code = names.code(branch)
    branch_name = names.display(branch)

    if branch == "first-year" and len(parts) == 5:
        pattern = names.normalize_pattern(parts[2])
        subject_key = names.normalize_other(parts[3])
        normalized_subject = strip_subject_suffix(subject_key, branch_code)
        return {
            "branch_type": "first_year",
            "branch": branch,
            "branch_code": branch_code,
            "branch_name": branch_name,
            "year_or_semester": "",
            "pattern": pattern,
            "subject_key": subject_key,
            "normalized_subject": normalized_subject,
            "subject_name": names.display(normalized_subject),
            "filename": parts[4],
        }

    if branch == "m-b-a" and len(parts) == 6:
        semester = names.normalize_other(parts[2])
        pattern = names.normalize_pattern(parts[3])
        subject_key = names.normalize_other(parts[4])
        normalized_subject = strip_subject_suffix(subject_key, branch_code, semester)
        return {
            "branch_type": "mba",
            "branch": branch,
            "branch_code": branch_code,
            "branch_name": branch_name,
            "year_or_semester": semester,
            "pattern": pattern,
            "subject_key": subject_key,
            "normalized_subject": normalized_subject,
            "subject_name": names.display(normalized_subject),
            "filename": parts[5],
        }

    if branch == "honors-course" and len(parts) == 5:
        year = names.normalize_other(parts[2])
        subject_key = names.normalize_other(parts[3])
        normalized_subject = strip_subject_suffix(subject_key, branch_code, year)
        return {
            "branch_type": "honors",
            "branch": branch,
            "branch_code": branch_code,
            "branch_name": branch_name,
            "year_or_semester": year,
            "pattern": "",
            "subject_key": subject_key,
            "normalized_subject": normalized_subject,
            "subject_name": names.display(normalized_subject),
            "filename": parts[4],
        }

    if len(parts) == 6:
        year = names.normalize_other(parts[2])
        pattern = names.normalize_pattern(parts[3])
        subject_key = names.normalize_other(parts[4])
        normalized_subject = strip_subject_suffix(subject_key, branch_code, year)
        return {
            "branch_type": "standard",
            "branch": branch,
            "branch_code": branch_code,
            "branch_name": branch_name,
            "year_or_semester": year,
            "pattern": pattern,
            "subject_key": subject_key,
            "normalized_subject": normalized_subject,
            "subject_name": names.display(normalized_subject),
            "filename": parts[5],
        }
    return None


def comparable_path(path: str, names: NameLookup) -> str:
    normalized = Path(path).as_posix()
    parts = normalized.split("/")
    if len(parts) < 5 or parts[0] != "papers":
        return normalized.replace("2019_pattren", "2019_pattern")
    parsed = parse_papers_path(PROJECT_ROOT / normalized, names)
    if not parsed:
        return normalized.replace("2019_pattren", "2019_pattern")
    if parsed["branch_type"] == "first_year":
        canonical_parts = ["papers", parsed["branch"], parsed["pattern"], parsed["normalized_subject"], parsed["filename"]]
    elif parsed["branch_type"] == "mba":
        canonical_parts = [
            "papers",
            parsed["branch"],
            parsed["year_or_semester"],
            parsed["pattern"],
            parsed["normalized_subject"],
            parsed["filename"],
        ]
    elif parsed["branch_type"] == "honors":
        canonical_parts = ["papers", parsed["branch"], parsed["year_or_semester"], parsed["normalized_subject"], parsed["filename"]]
    else:
        canonical_parts = [
            "papers",
            parsed["branch"],
            parsed["year_or_semester"],
            parsed["pattern"],
            parsed["normalized_subject"],
            parsed["filename"],
        ]
    return "/".join(canonical_parts)


def load_tracking_lookup(names: NameLookup) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not TRACKING_DB.exists():
        return lookup
    with sqlite3.connect(TRACKING_DB) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT file_id, current_path, expected_path, final_path FROM files").fetchall()
    for row in rows:
        for key in ("final_path", "expected_path", "current_path"):
            value = row[key]
            if value:
                lookup.setdefault(comparable_path(str(value), names), str(row["file_id"]))
    return lookup


def connect_upload_db() -> sqlite3.Connection:
    UPLOAD_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(UPLOAD_DB)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS uploaded_pdfs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          pdf_id TEXT,
          local_path TEXT NOT NULL,
          canonical_path TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          mtime_ns INTEGER,
          branch_type TEXT NOT NULL,
          branch_code TEXT NOT NULL,
          branch_name TEXT NOT NULL,
          year_or_semester TEXT,
          pattern TEXT,
          subject_key TEXT NOT NULL,
          subject_name TEXT NOT NULL,
          filename TEXT NOT NULL,
          r2_status TEXT NOT NULL,
          cloudinary_status TEXT NOT NULL,
          state TEXT NOT NULL CHECK (
            state IN ('PENDING', 'UPLOADED', 'MODIFIED', 'RENAMED', 'REMOVED', 'FAILED', 'NEEDS_TRACKING_ID')
          ),
          first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          uploaded_at TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_uploaded_pdf_id ON uploaded_pdfs(pdf_id) WHERE pdf_id IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_uploaded_canonical_path ON uploaded_pdfs(canonical_path);
        CREATE INDEX IF NOT EXISTS idx_uploaded_state ON uploaded_pdfs(state);
        CREATE INDEX IF NOT EXISTS idx_uploaded_local_path ON uploaded_pdfs(local_path);
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(uploaded_pdfs)")}
    if "mtime_ns" not in columns:
        connection.execute("ALTER TABLE uploaded_pdfs ADD COLUMN mtime_ns INTEGER")
    connection.commit()
    return connection


def existing_rows(connection: sqlite3.Connection) -> tuple[dict[str, sqlite3.Row], dict[str, sqlite3.Row]]:
    by_pdf_id: dict[str, sqlite3.Row] = {}
    by_path: dict[str, sqlite3.Row] = {}
    for row in connection.execute("SELECT * FROM uploaded_pdfs"):
        if row["pdf_id"]:
            by_pdf_id[str(row["pdf_id"])] = row
        by_path[str(row["canonical_path"])] = row
    return by_pdf_id, by_path


def record_for_pdf(path: Path, names: NameLookup, tracking_lookup: dict[str, str], existing: sqlite3.Row | None = None) -> dict[str, Any] | None:
    metadata = parse_papers_path(path, names)
    if not metadata:
        return None
    local_path = project_relative(path)
    canonical_path = local_path.replace("2019_pattren", "2019_pattern")
    pdf_id = tracking_lookup.get(comparable_path(canonical_path, names))
    stat = path.stat()
    mtime_ns = stat.st_mtime_ns
    sha256 = ""
    if (
        existing
        and existing["sha256"]
        and int(existing["size_bytes"]) == stat.st_size
        and existing["mtime_ns"] is not None
        and int(existing["mtime_ns"]) == mtime_ns
    ):
        sha256 = str(existing["sha256"])
    else:
        sha256 = sha256_file(path)
    return {
        **metadata,
        "pdf_id": pdf_id,
        "local_path": local_path,
        "canonical_path": canonical_path,
        "sha256": sha256,
        "size_bytes": stat.st_size,
        "mtime_ns": mtime_ns,
    }


def upsert_scan_record(connection: sqlite3.Connection, record: dict[str, Any], now: str, by_pdf_id: dict[str, sqlite3.Row], by_path: dict[str, sqlite3.Row]) -> str:
    existing = by_pdf_id.get(record["pdf_id"] or "") if record["pdf_id"] else by_path.get(record["canonical_path"])
    state = "NEEDS_TRACKING_ID" if not record["pdf_id"] else "PENDING"
    r2_status = "PENDING" if record["pdf_id"] else "SKIPPED"
    cloudinary_status = "PENDING" if record["pdf_id"] else "SKIPPED"

    if existing:
        if not record["pdf_id"]:
            state = "NEEDS_TRACKING_ID"
        elif existing["canonical_path"] != record["canonical_path"]:
            state = "RENAMED"
        elif existing["sha256"] != record["sha256"] or int(existing["size_bytes"]) != int(record["size_bytes"]):
            state = "MODIFIED"
        elif existing["state"] in {"UPLOADED", "FAILED"}:
            state = str(existing["state"])
        else:
            state = "PENDING"
        if state in {"UPLOADED", "FAILED"}:
            r2_status = str(existing["r2_status"])
            cloudinary_status = str(existing["cloudinary_status"])
        unchanged_fields = (
            ("pdf_id", record["pdf_id"]),
            ("local_path", record["local_path"]),
            ("canonical_path", record["canonical_path"]),
            ("sha256", record["sha256"]),
            ("size_bytes", record["size_bytes"]),
            ("mtime_ns", record["mtime_ns"]),
            ("branch_type", record["branch_type"]),
            ("branch_code", record["branch_code"]),
            ("branch_name", record["branch_name"]),
            ("year_or_semester", record["year_or_semester"]),
            ("pattern", record["pattern"]),
            ("subject_key", record["subject_key"]),
            ("subject_name", record["subject_name"]),
            ("filename", record["filename"]),
            ("r2_status", r2_status),
            ("cloudinary_status", cloudinary_status),
            ("state", state),
        )
        if all(existing[key] == value for key, value in unchanged_fields):
            return state
        connection.execute(
            """
            UPDATE uploaded_pdfs
            SET pdf_id = ?, local_path = ?, canonical_path = ?, sha256 = ?, size_bytes = ?, mtime_ns = ?,
                branch_type = ?, branch_code = ?, branch_name = ?, year_or_semester = ?,
                pattern = ?, subject_key = ?, subject_name = ?, filename = ?,
                r2_status = ?, cloudinary_status = ?, state = ?, last_seen_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                record["pdf_id"],
                record["local_path"],
                record["canonical_path"],
                record["sha256"],
                record["size_bytes"],
                record["mtime_ns"],
                record["branch_type"],
                record["branch_code"],
                record["branch_name"],
                record["year_or_semester"],
                record["pattern"],
                record["subject_key"],
                record["subject_name"],
                record["filename"],
                r2_status,
                cloudinary_status,
                state,
                now,
                now,
                existing["id"],
            ),
        )
        return state

    connection.execute(
        """
        INSERT INTO uploaded_pdfs (
          pdf_id, local_path, canonical_path, sha256, size_bytes, mtime_ns, branch_type,
          branch_code, branch_name, year_or_semester, pattern, subject_key,
          subject_name, filename, r2_status, cloudinary_status, state,
          first_seen_at, last_seen_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["pdf_id"],
            record["local_path"],
            record["canonical_path"],
            record["sha256"],
            record["size_bytes"],
            record["mtime_ns"],
            record["branch_type"],
            record["branch_code"],
            record["branch_name"],
            record["year_or_semester"],
            record["pattern"],
            record["subject_key"],
            record["subject_name"],
            record["filename"],
            r2_status,
            cloudinary_status,
            state,
            now,
            now,
            now,
        ),
    )
    return state


def scan_papers() -> Counter[str]:
    names = NameLookup()
    tracking_lookup = load_tracking_lookup(names)
    now = utc_now()
    counts: Counter[str] = Counter()
    seen_ids: set[int] = set()

    all_pdfs = sorted(PAPERS_DIR.rglob("*.pdf"))
    total = len(all_pdfs)
    commit_interval = 100
    print(f"Scanning {total} papers (hash changed files + DB upsert)...", flush=True)

    with connect_upload_db() as connection:
        by_pdf_id, by_path = existing_rows(connection)
        for index, path in enumerate(all_pdfs, start=1):
            if index == 1 or index % 100 == 0 or index == total:
                print(f"Scan progress: {index}/{total} papers", flush=True)
            local_path = project_relative(path)
            canonical_path = local_path.replace("2019_pattren", "2019_pattern")
            pdf_id = tracking_lookup.get(comparable_path(canonical_path, names))
            existing = by_pdf_id.get(pdf_id or "") if pdf_id else by_path.get(canonical_path)
            record = record_for_pdf(path, names, tracking_lookup, existing)
            if not record:
                counts["SKIPPED"] += 1
                continue
            state = upsert_scan_record(connection, record, now, by_pdf_id, by_path)
            counts[state] += 1
            if index % commit_interval == 0:
                connection.commit()
        connection.commit()
        current_paths = {project_relative(p) for p in all_pdfs}
        for row in connection.execute("SELECT id, local_path, state FROM uploaded_pdfs WHERE state != 'REMOVED'").fetchall():
            if row["local_path"] not in current_paths:
                connection.execute(
                    "UPDATE uploaded_pdfs SET state = 'REMOVED', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                counts["REMOVED"] += 1
                seen_ids.add(int(row["id"]))
        connection.commit()
    print(f"Scan complete: {total} papers processed", flush=True)
    return counts


def upload_to_r2(path: Path, canonical_path: str) -> None:
    try:
        import boto3
        from boto3.s3.transfer import TransferConfig
    except ImportError as exc:
        raise RuntimeError("boto3 is required for R2 uploads. Install requirements.txt first.") from exc

    bucket = os.environ.get("R2_BUCKET_NAME") or os.environ.get("CLOUDFLARE_R2_BUCKET") or DEFAULT_R2_BUCKET
    endpoint = os.environ.get("R2_ENDPOINT_URL") or os.environ.get("CLOUDFLARE_R2_ENDPOINT") or DEFAULT_R2_ENDPOINT
    endpoint = endpoint.rstrip("/")
    bucket_suffix = f"/{bucket}"
    if endpoint.endswith(bucket_suffix):
        endpoint = endpoint[: -len(bucket_suffix)]

    access_key = os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        raise RuntimeError("R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are required for R2 uploads.")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.environ.get("R2_REGION", "auto"),
    )
    transfer_config = TransferConfig(
        multipart_threshold=int(os.environ.get("R2_MULTIPART_THRESHOLD_MB", "64")) * 1024 * 1024,
        multipart_chunksize=int(os.environ.get("R2_MULTIPART_CHUNK_MB", "16")) * 1024 * 1024,
        max_concurrency=int(os.environ.get("R2_MULTIPART_CONCURRENCY", "4")),
        use_threads=True,
    )
    client.upload_file(
        str(path),
        bucket,
        canonical_path,
        ExtraArgs={"ContentType": "application/pdf"},
        Config=transfer_config,
    )


def r2_client() -> tuple[Any, str]:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for R2 operations. Install requirements.txt first.") from exc

    bucket = os.environ.get("R2_BUCKET_NAME") or os.environ.get("CLOUDFLARE_R2_BUCKET") or DEFAULT_R2_BUCKET
    endpoint = os.environ.get("R2_ENDPOINT_URL") or os.environ.get("CLOUDFLARE_R2_ENDPOINT") or DEFAULT_R2_ENDPOINT
    endpoint = endpoint.rstrip("/")
    bucket_suffix = f"/{bucket}"
    if endpoint.endswith(bucket_suffix):
        endpoint = endpoint[: -len(bucket_suffix)]

    access_key = os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        raise RuntimeError("R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are required for R2 operations.")

    return (
        boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=os.environ.get("R2_REGION", "auto"),
        ),
        bucket,
    )


def validate_upload_environment() -> None:
    missing_packages = [
        package
        for package, module in (
            ("boto3", "boto3"),
            ("cloudinary", "cloudinary"),
            ("requests", "requests"),
        )
        if importlib.util.find_spec(module) is None
    ]
    if missing_packages:
        install_command = (
            f'"{sys.executable}" -m pip install '
            + " ".join(missing_packages)
        )
        raise RuntimeError(
            "Missing upload packages: "
            f"{', '.join(missing_packages)}. Install them in this Python environment with: "
            f"{install_command}"
        )

    missing: list[str] = []
    if not (os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")):
        missing.append("R2_ACCESS_KEY_ID")
    if not (os.environ.get("R2_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")):
        missing.append("R2_SECRET_ACCESS_KEY")
    for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        if not os.environ.get(key):
            missing.append(key)
    if missing:
        raise RuntimeError(f"Missing upload environment variables: {', '.join(missing)}")


def validate_cloud_delete_environment() -> None:
    missing: list[str] = []
    if not (os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")):
        missing.append("R2_ACCESS_KEY_ID")
    if not (os.environ.get("R2_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")):
        missing.append("R2_SECRET_ACCESS_KEY")
    for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        if not os.environ.get(key):
            missing.append(key)
    if missing:
        raise RuntimeError(f"Missing cloud delete environment variables: {', '.join(missing)}")


def upload_to_cloudinary(path: Path, canonical_path: str) -> None:
    try:
        import cloudinary
        import cloudinary.uploader
        import requests
    except ImportError as exc:
        raise RuntimeError("cloudinary and requests are required for Cloudinary uploads. Install requirements.txt first.") from exc

    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
    api_key = os.environ.get("CLOUDINARY_API_KEY")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET")
    if not all([cloud_name, api_key, api_secret]):
        raise RuntimeError("CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET are required.")

    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
    asset_folder = str(Path(canonical_path).parent).replace("\\", "/")
    result = cloudinary.uploader.upload(
        str(path),
        public_id=canonical_path,
        asset_folder=asset_folder,
        display_name=Path(canonical_path).name,
        resource_type="raw",
        overwrite=True,
        use_filename=False,
        unique_filename=False,
    )
    secure_url = result.get("secure_url")
    if not secure_url:
        raise RuntimeError("Cloudinary upload did not return secure_url.")

    response = requests.get(str(secure_url), timeout=30)
    if response.status_code != 200:
        cloudinary_error = response.headers.get("x-cld-error")
        detail = f"Cloudinary delivery URL returned HTTP {response.status_code}"
        if cloudinary_error:
            detail = f"{detail}: {cloudinary_error}"
        raise RuntimeError(detail)


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def list_r2_keys(prefix: str = DELETE_PREFIX) -> tuple[Any, str, list[str]]:
    client, bucket = r2_client()
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(str(item["Key"]) for item in page.get("Contents", []))
    return client, bucket, sorted(keys)


def delete_r2_prefix(prefix: str = DELETE_PREFIX, *, dry_run: bool = False) -> int:
    client, bucket, keys = list_r2_keys(prefix)
    print(f"R2 bucket: {bucket}")
    print(f"R2 objects under {prefix!r}: {len(keys)}")
    for key in keys[:20]:
        print(f"- r2://{bucket}/{key}")
    if len(keys) > 20:
        print(f"- ... {len(keys) - 20} more")
    if dry_run or not keys:
        return len(keys)

    for batch in chunked(keys, 1000):
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
        )
    return len(keys)


def configure_cloudinary() -> None:
    try:
        import cloudinary
    except ImportError as exc:
        raise RuntimeError("cloudinary is required for Cloudinary operations. Install requirements.txt first.") from exc

    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
    api_key = os.environ.get("CLOUDINARY_API_KEY")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET")
    if not all([cloud_name, api_key, api_secret]):
        raise RuntimeError("CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET are required.")
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)


def list_cloudinary_public_ids(resource_type: str, prefix: str = DELETE_PREFIX) -> list[str]:
    try:
        import cloudinary.api
    except ImportError as exc:
        raise RuntimeError("cloudinary is required for Cloudinary operations. Install requirements.txt first.") from exc

    public_ids: list[str] = []
    next_cursor = None
    while True:
        options: dict[str, Any] = {
            "resource_type": resource_type,
            "type": "upload",
            "prefix": prefix,
            "max_results": 500,
        }
        if next_cursor:
            options["next_cursor"] = next_cursor
        result = cloudinary.api.resources(**options)
        public_ids.extend(str(item["public_id"]) for item in result.get("resources", []))
        next_cursor = result.get("next_cursor")
        if not next_cursor:
            break
    return sorted(public_ids)


def delete_cloudinary_prefix(prefix: str = DELETE_PREFIX, *, dry_run: bool = False) -> Counter[str]:
    try:
        import cloudinary.api
    except ImportError as exc:
        raise RuntimeError("cloudinary is required for Cloudinary operations. Install requirements.txt first.") from exc

    configure_cloudinary()
    counts: Counter[str] = Counter()
    for resource_type in ("raw", "image"):
        public_ids = list_cloudinary_public_ids(resource_type, prefix)
        counts[resource_type] = len(public_ids)
        print(f"Cloudinary {resource_type} assets under {prefix!r}: {len(public_ids)}")
        for public_id in public_ids[:20]:
            print(f"- cloudinary://{resource_type}/upload/{public_id}")
        if len(public_ids) > 20:
            print(f"- ... {len(public_ids) - 20} more")
        if dry_run:
            continue
        for batch in chunked(public_ids, 100):
            cloudinary.api.delete_resources(batch, resource_type=resource_type, type="upload")
    return counts


def local_paper_files() -> list[Path]:
    if not PAPERS_DIR.exists():
        return []
    return sorted(path for path in PAPERS_DIR.rglob("*.pdf") if path.is_file())


def delete_local_papers(*, dry_run: bool = False) -> int:
    files = local_paper_files()
    print(f"Local PDF files under {project_relative(PAPERS_DIR)}/: {len(files)}")
    for path in files[:20]:
        print(f"- {project_relative(path)}")
    if len(files) > 20:
        print(f"- ... {len(files) - 20} more")
    if dry_run:
        return len(files)

    for path in files:
        path.unlink()
    if PAPERS_DIR.exists():
        for directory in sorted((path for path in PAPERS_DIR.rglob("*") if path.is_dir()), key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
    return len(files)


def delete_upload_db(*, dry_run: bool = False) -> bool:
    if not UPLOAD_DB.exists():
        print(f"Upload DB already absent: {project_relative(UPLOAD_DB)}")
        return False
    print(f"{'Would delete' if dry_run else 'Deleting'} upload DB: {project_relative(UPLOAD_DB)}")
    if not dry_run:
        UPLOAD_DB.unlink()
    return True


def generated_manifest_paths() -> list[Path]:
    paths: list[Path] = []
    for filename in PATTERN_FILES.values():
        manifest_path = MANIFEST_DIR / filename
        paths.append(manifest_path)
        paths.append(MANIFEST_DIR / f"{manifest_path.stem}_subjects.json")
    paths.extend([MANIFEST_DIR / "honors.json", MANIFEST_DIR / "honors_subjects.json"])

    legacy_static = MANIFEST_DIR / "static"
    if legacy_static.exists():
        paths.extend(sorted(legacy_static.glob("*.json")))
    return sorted({path for path in paths})


def delete_generated_manifests(*, dry_run: bool = False) -> int:
    paths = [path for path in generated_manifest_paths() if path.exists()]
    print(f"Generated manifest files: {len(paths)}")
    for path in paths:
        print(f"- {project_relative(path)}")
    if dry_run:
        return len(paths)

    for path in paths:
        path.unlink()
    legacy_static = MANIFEST_DIR / "static"
    if legacy_static.exists():
        try:
            legacy_static.rmdir()
        except OSError:
            pass
    return len(paths)


def choose_bulk_delete_target() -> str:
    choices = {
        "1": "cloud",
        "2": "local",
        "3": "both",
    }
    print("Bulk delete target")
    print("1. Delete from cloud only")
    print("2. Delete local papers/ files only")
    print("3. Delete both cloud and local papers/ files")
    selected = input("Choose 1, 2, or 3: ").strip()
    if selected not in choices:
        raise RuntimeError("Bulk delete cancelled: invalid target selection.")
    return choices[selected]


def confirm_bulk_delete(target: str) -> None:
    expected = f"delete {target}"
    print(f"This will delete {DELETE_PREFIX!r} scoped assets for target={target!r}.")
    print(f"Type {expected!r} to continue.")
    if input("> ").strip().lower() != expected:
        raise RuntimeError("Bulk delete cancelled.")


def bulk_delete(target: str = "", *, dry_run: bool = False, yes: bool = False) -> Counter[str]:
    if not target:
        target = choose_bulk_delete_target()
    if target not in {"cloud", "local", "both"}:
        raise RuntimeError("bulk-delete --target must be one of: cloud, local, both.")
    if not dry_run and not yes:
        confirm_bulk_delete(target)

    counts: Counter[str] = Counter()
    try:
        if target in {"cloud", "both"}:
            validate_cloud_delete_environment()
            counts["r2"] = delete_r2_prefix(DELETE_PREFIX, dry_run=dry_run)
            cloudinary_counts = delete_cloudinary_prefix(DELETE_PREFIX, dry_run=dry_run)
            counts["cloudinary_raw"] = cloudinary_counts["raw"]
            counts["cloudinary_image"] = cloudinary_counts["image"]
        if target in {"local", "both"}:
            counts["local_pdf"] = delete_local_papers(dry_run=dry_run)
    except Exception:
        if not dry_run:
            print("Bulk delete failed before upload DB reset.", file=sys.stderr)
        raise

    if not dry_run:
        counts["upload_db_deleted"] = 1 if delete_upload_db(dry_run=False) else 0
        counts["manifest_deleted"] = delete_generated_manifests(dry_run=False)
    else:
        delete_upload_db(dry_run=True)
        counts["manifest_deleted"] = delete_generated_manifests(dry_run=True)
    return counts


def sync_one_upload(row: dict[str, Any]) -> dict[str, Any]:
    path = PROJECT_ROOT / row["local_path"]
    if not path.exists():
        return {
            "id": row["id"],
            "local_path": row["local_path"],
            "canonical_path": row["canonical_path"],
            "state": "REMOVED",
            "r2_status": row["r2_status"],
            "cloudinary_status": row["cloudinary_status"],
        }

    r2_status = str(row["r2_status"] or "PENDING")
    cloudinary_status = str(row["cloudinary_status"] or "PENDING")
    state = "UPLOADED"
    can_skip_successful_provider = row["state"] == "FAILED"

    if not (can_skip_successful_provider and r2_status == "UPLOADED"):
        try:
            upload_to_r2(path, row["canonical_path"])
            r2_status = "UPLOADED"
        except Exception as exc:  # noqa: BLE001 - CLI should record provider failures.
            r2_status = f"FAILED: {exc}"
            state = "FAILED"
    if not (can_skip_successful_provider and cloudinary_status == "UPLOADED"):
        try:
            upload_to_cloudinary(path, row["canonical_path"])
            cloudinary_status = "UPLOADED"
        except Exception as exc:  # noqa: BLE001 - CLI should record provider failures.
            cloudinary_status = f"FAILED: {exc}"
            state = "FAILED"
    if r2_status != "UPLOADED" or cloudinary_status != "UPLOADED":
        state = "FAILED"
    return {
        "id": row["id"],
        "local_path": row["local_path"],
        "canonical_path": row["canonical_path"],
        "state": state,
        "r2_status": r2_status,
        "cloudinary_status": cloudinary_status,
    }


def short_status(value: str, limit: int = 140) -> str:
    cleaned = " ".join(str(value).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def sync_uploads(workers: int = 4, limit: int = 0, state_filter: str = "") -> Counter[str]:
    validate_upload_environment()
    now = utc_now()
    counts: Counter[str] = Counter()
    upload_states = ("PENDING", "MODIFIED", "RENAMED", "FAILED")
    if state_filter:
        upload_states = (state_filter,)
    placeholders = ",".join("?" for _ in upload_states)
    with connect_upload_db() as connection:
        rows = [dict(row) for row in connection.execute(
            f"""
            SELECT * FROM uploaded_pdfs
            WHERE state IN ({placeholders})
              AND pdf_id IS NOT NULL
            ORDER BY canonical_path
            """,
            upload_states,
        ).fetchall()]
        if limit > 0:
            rows = rows[:limit]
        if not rows:
            scope = f" in state {state_filter}" if state_filter else ""
            print(f"No uploadable PDFs remain{scope}. Everything is either uploaded, removed, or waiting for review.", flush=True)
            return counts

        total = len(rows)
        if limit > 0:
            print(f"Upload limit: {limit} PDF(s)", flush=True)
        print(f"Upload batch: {total} PDF(s), workers={max(1, workers)}", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(sync_one_upload, row): row for row in rows}
            for completed, future in enumerate(as_completed(futures), start=1):
                source_row = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - keep batch resumable after unexpected worker failures.
                    result = {
                        "id": source_row["id"],
                        "local_path": source_row["local_path"],
                        "canonical_path": source_row["canonical_path"],
                        "state": "FAILED",
                        "r2_status": source_row["r2_status"],
                        "cloudinary_status": f"FAILED: {exc}",
                    }
                state = result["state"]
                r2_status = result["r2_status"]
                cloudinary_status = result["cloudinary_status"]
                row_id = result["id"]
                now = utc_now()
                counts[state] += 1
                connection.execute(
                    """
                    UPDATE uploaded_pdfs
                    SET r2_status = ?, cloudinary_status = ?, state = ?, uploaded_at = CASE WHEN ? = 'UPLOADED' THEN ? ELSE uploaded_at END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (r2_status, cloudinary_status, state, state, now, now, row_id),
                )
                connection.commit()
                remaining = total - completed
                print(
                    f"[{completed}/{total}] {state} remaining={remaining} "
                    f"file={result['local_path']} r2={short_status(r2_status)} cloudinary={short_status(cloudinary_status)}",
                    flush=True,
                )
    return counts


def preflight_upload() -> Counter[str]:
    validate_upload_environment()
    scan_papers()
    counts = status_counts()
    print("Upload preflight OK")
    print(f"R2 bucket: {os.environ.get('R2_BUCKET_NAME') or os.environ.get('CLOUDFLARE_R2_BUCKET') or DEFAULT_R2_BUCKET}")
    endpoint = os.environ.get("R2_ENDPOINT_URL") or os.environ.get("CLOUDFLARE_R2_ENDPOINT") or DEFAULT_R2_ENDPOINT
    print(f"R2 endpoint: {endpoint}")
    print(f"Cloudinary cloud: {os.environ.get('CLOUDINARY_CLOUD_NAME')}")
    return counts


def upload_summary(sample_limit: int = 8) -> Counter[str]:
    scan_papers()
    counts = status_counts()
    print_counts("Upload status", counts)
    with connect_upload_db() as connection:
        samples = connection.execute(
            """
            SELECT state, local_path, r2_status, cloudinary_status
            FROM uploaded_pdfs
            WHERE state IN ('PENDING', 'MODIFIED', 'RENAMED', 'FAILED', 'NEEDS_TRACKING_ID')
            ORDER BY
              CASE state
                WHEN 'FAILED' THEN 0
                WHEN 'NEEDS_TRACKING_ID' THEN 1
                WHEN 'MODIFIED' THEN 2
                WHEN 'RENAMED' THEN 3
                ELSE 4
              END,
              local_path
            LIMIT ?
            """,
            (sample_limit,),
        ).fetchall()
    if samples:
        print("Next files")
        for row in samples:
            print(
                f"- {row['state']}: {row['local_path']} "
                f"r2={short_status(row['r2_status'], 80)} cloudinary={short_status(row['cloudinary_status'], 80)}"
            )
    return counts


def parse_pdf_filename(filename: str) -> dict[str, Any]:
    stem = Path(filename).stem
    match = re.match(r"^(insem|endsem|other)_([a-z]+(?:_[a-z]+)*)_(\d{4})_", stem)
    if not match:
        return {"exam": "", "month": "", "year": None}
    exam, month, year = match.groups()
    return {"exam": exam, "month": month, "year": int(year)}


def load_semester_mapping() -> dict[str, Any]:
    data = read_yaml(SEMESTER_MAPPING_PATH)
    if not data:
        return {"schema_version": 1, "standard": {}, "first_year": {}}
    data.setdefault("schema_version", 1)
    data.setdefault("standard", {})
    data.setdefault("first_year", {})
    return data


def normalize_semester_value(value: Any) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized.isdigit():
            return int(normalized)
        if normalized == "other":
            return "other"
    return None


def mapped_semester(mapping: dict[str, Any], row: sqlite3.Row) -> int | str | None:
    branch_type = str(row["branch_type"])
    pattern = str(row["pattern"] or "")
    subject_key = str(row["subject_key"])
    value: Any = None
    if branch_type == "standard":
        value = (
            mapping.get("standard", {})
            .get(branch_key(row), {})
            .get(str(row["year_or_semester"] or ""), {})
            .get(pattern, {})
            .get(subject_key)
        )
    elif branch_type == "first_year":
        value = mapping.get("first_year", {}).get(pattern, {}).get(subject_key)
    return normalize_semester_value(value)


def subject_summary(row: sqlite3.Row) -> dict[str, str]:
    normalized = strip_subject_suffix(str(row["subject_key"]), str(row["branch_code"]), str(row["year_or_semester"] or ""))
    return {
        "subjectKey": row["subject_key"],
        "shortCode": code_for_name(normalized),
        "fullName": row["subject_name"],
        "normalizedName": normalized,
    }


def navigation_subject(row: sqlite3.Row) -> dict[str, Any]:
    return subject_summary(row)


def branch_key(row: sqlite3.Row) -> str:
    return str(row["canonical_path"]).split("/")[1]


def year_name(value: str) -> str:
    return value.upper() if value else ""


def year_full_name(value: str, branch_type: str = "") -> str:
    if branch_type == "first_year":
        return "First Year"
    names = {
        "se": "Second Year",
        "te": "Third Year",
        "be": "Fourth Year",
    }
    return names.get(value.lower(), year_name(value))


def provider_bases() -> dict[str, str]:
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    return {
        "cloudinaryRawBaseUrl": f"https://res.cloudinary.com/{cloud_name}/raw/upload" if cloud_name else "",
        "r2BaseUrl": (os.environ.get("R2_PUBLIC_BASE_URL") or DEFAULT_R2_PUBLIC_BASE_URL).rstrip("/"),
    }


def empty_pattern_manifest(pattern: str) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "pattern": pattern,
        "patternYear": PATTERN_LABELS.get(pattern, pattern),
        "generatedAt": utc_now(),
        "hierarchy": {
            "standard": {"branches": {}},
            "firstYear": {"branchKey": "first-year", "branchCode": "fy", "branchName": "First Year", "semesterIncluded": True, "subjects": []},
            "mba": {"branchKey": "m-b-a", "branchCode": "mba", "branchName": "M.B.A", "semesters": {}},
        },
    }


def empty_subject_manifest(pattern: str) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "pattern": pattern,
        "patternYear": PATTERN_LABELS.get(pattern, pattern),
        "generatedAt": utc_now(),
        "providers": provider_bases(),
        "subjects": {},
    }


def empty_honors_manifest() -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "family": "honors",
        "generatedAt": utc_now(),
        "hierarchy": {
            "honorsCourse": {"branchKey": "honors-course", "branchCode": "hc", "branchName": "Honors Course", "years": {}},
        },
    }


def empty_honors_subject_manifest() -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "family": "honors",
        "generatedAt": utc_now(),
        "providers": provider_bases(),
        "subjects": {},
    }


def add_subject_to_hierarchy(manifest: dict[str, Any], row: sqlite3.Row, semester_mapping: dict[str, Any]) -> None:
    summary = navigation_subject(row)
    branch_type = row["branch_type"]
    branch = branch_key(row)
    year = str(row["year_or_semester"] or "")
    if branch_type == "standard":
        semester_no = mapped_semester(semester_mapping, row)
        if semester_no is not None:
            summary["semesterNo"] = semester_no
        branch_node = manifest["hierarchy"]["standard"]["branches"].setdefault(
            branch,
            {
                "branchKey": branch,
                "branchCode": row["branch_code"],
                "branchName": row["branch_name"],
                "years": {},
            },
        )
        year_node = branch_node["years"].setdefault(
            year,
            {"yearKey": year, "yearName": year_name(year), "yearFullName": year_full_name(year), "semesterIncluded": True, "subjects": []},
        )
        if semester_no is None:
            year_node["semesterIncluded"] = False
        if not any(item["subjectKey"] == summary["subjectKey"] for item in year_node["subjects"]):
            year_node["subjects"].append(summary)
    elif branch_type == "first_year":
        semester_no = mapped_semester(semester_mapping, row)
        if semester_no is not None:
            summary["semesterNo"] = semester_no
        first_year = manifest["hierarchy"]["firstYear"]
        if semester_no is None:
            first_year["semesterIncluded"] = False
        subjects = first_year["subjects"]
        if not any(item["subjectKey"] == summary["subjectKey"] for item in subjects):
            subjects.append(summary)
    elif branch_type == "mba":
        sem_node = manifest["hierarchy"]["mba"]["semesters"].setdefault(
            year,
            {"semesterKey": year, "semesterName": year_name(year), "subjects": []},
        )
        if not any(item["subjectKey"] == summary["subjectKey"] for item in sem_node["subjects"]):
            sem_node["subjects"].append(summary)


def add_subject_to_honors(manifest: dict[str, Any], row: sqlite3.Row) -> None:
    summary = navigation_subject(row)
    year = str(row["year_or_semester"] or "")
    year_node = manifest["hierarchy"]["honorsCourse"]["years"].setdefault(
        year,
        {"yearKey": year, "yearName": year_name(year), "yearFullName": year_full_name(year), "subjects": []},
    )
    if not any(item["subjectKey"] == summary["subjectKey"] for item in year_node["subjects"]):
        year_node["subjects"].append(summary)


def add_paper(subjects: dict[str, Any], row: sqlite3.Row, semester_mapping: dict[str, Any] | None = None) -> None:
    summary = subject_summary(row)
    subject_key = str(row["subject_key"])
    branch_type = str(row["branch_type"])
    period_key = str(row["year_or_semester"] or "")
    subject_data: dict[str, Any] = {
        **summary,
        "branchType": branch_type,
        "branchKey": branch_key(row),
        "branchCode": row["branch_code"],
        "branchName": row["branch_name"],
        "pattern": row["pattern"] or "",
        "papers": [],
    }
    if branch_type == "mba":
        subject_data["semesterKey"] = period_key
        subject_data["semesterName"] = year_name(period_key)
    else:
        subject_data["yearKey"] = period_key
        subject_data["yearName"] = year_name(period_key)
        subject_data["yearFullName"] = year_full_name(period_key, branch_type)
        if semester_mapping is not None:
            semester_no = mapped_semester(semester_mapping, row)
            if semester_no is not None:
                subject_data["semesterNo"] = semester_no

    subject = subjects.setdefault(subject_key, subject_data)
    metadata = parse_pdf_filename(row["filename"])
    subject["papers"].append(
        {
            "pdfId": row["pdf_id"],
            "canonicalPath": row["canonical_path"],
            "exam": metadata["exam"],
            "month": metadata["month"],
            "year": metadata["year"],
        }
    )


def sort_subject_manifest(data: dict[str, Any]) -> dict[str, Any]:
    for subject in data.get("subjects", {}).values():
        subject["papers"].sort(key=lambda item: (item.get("year") or 0, item.get("month") or "", item.get("exam") or "", item["canonicalPath"]))
    return data


def sort_subjects(subjects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(subjects, key=lambda item: (item["fullName"].lower(), item["subjectKey"]))


def finalize_pattern_manifest(data: dict[str, Any]) -> dict[str, Any]:
    standard = data["hierarchy"]["standard"]
    branches = []
    for branch in standard["branches"].values():
        years = []
        for year in branch["years"].values():
            year["subjects"] = sort_subjects(year["subjects"])
            years.append(year)
        branch["years"] = sorted(years, key=lambda item: item["yearKey"])
        branches.append(branch)
    standard["branches"] = sorted(branches, key=lambda item: item["branchName"].lower())
    if not data["hierarchy"]["firstYear"]["subjects"]:
        data["hierarchy"]["firstYear"]["semesterIncluded"] = False
    data["hierarchy"]["firstYear"]["subjects"] = sort_subjects(data["hierarchy"]["firstYear"]["subjects"])
    semesters = []
    for semester in data["hierarchy"]["mba"]["semesters"].values():
        semester["subjects"] = sort_subjects(semester["subjects"])
        semesters.append(semester)
    data["hierarchy"]["mba"]["semesters"] = sorted(semesters, key=lambda item: item["semesterKey"])
    return data


def finalize_honors_manifest(data: dict[str, Any]) -> dict[str, Any]:
    years = []
    for year in data["hierarchy"]["honorsCourse"]["years"].values():
        year["subjects"] = sort_subjects(year["subjects"])
        years.append(year)
    data["hierarchy"]["honorsCourse"]["years"] = sorted(years, key=lambda item: item["yearKey"])
    return data


def remove_legacy_static_manifests() -> None:
    static_dir = MANIFEST_DIR / "static"
    if not static_dir.exists():
        return
    for path in static_dir.glob("*.json"):
        path.unlink()
    try:
        static_dir.rmdir()
    except OSError:
        pass


def generate_manifests() -> Counter[str]:
    semester_mapping = load_semester_mapping()
    manifests = {pattern: empty_pattern_manifest(pattern) for pattern in PATTERN_FILES}
    subject_manifests = {pattern: empty_subject_manifest(pattern) for pattern in PATTERN_FILES}
    honors = empty_honors_manifest()
    honors_subjects = empty_honors_subject_manifest()
    counts: Counter[str] = Counter()
    with connect_upload_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM uploaded_pdfs
            WHERE state = 'UPLOADED' AND pdf_id IS NOT NULL
            ORDER BY branch_name, year_or_semester, subject_key, filename
            """
        ).fetchall()
    for row in rows:
        if row["branch_type"] == "honors":
            add_subject_to_honors(honors, row)
            add_paper(honors_subjects["subjects"], row)
            counts["honors"] += 1
            continue
        pattern = row["pattern"]
        if pattern not in manifests:
            counts["skipped_pattern"] += 1
            continue
        add_subject_to_hierarchy(manifests[pattern], row, semester_mapping)
        add_paper(subject_manifests[pattern]["subjects"], row, semester_mapping)
        counts[pattern] += 1

    remove_legacy_static_manifests()
    for pattern, filename in PATTERN_FILES.items():
        stem = Path(filename).stem
        write_json(MANIFEST_DIR / filename, finalize_pattern_manifest(manifests[pattern]))
        write_json(MANIFEST_DIR / f"{stem}_subjects.json", sort_subject_manifest(subject_manifests[pattern]))
    write_json(MANIFEST_DIR / "honors.json", finalize_honors_manifest(honors))
    write_json(MANIFEST_DIR / "honors_subjects.json", sort_subject_manifest(honors_subjects))
    return counts


def status_counts() -> Counter[str]:
    paper_total = len(local_paper_files())
    with connect_upload_db() as connection:
        rows = connection.execute("SELECT state, COUNT(*) FROM uploaded_pdfs GROUP BY state").fetchall()
    counts: Counter[str] = Counter({state: 0 for state in VALID_STATES})
    for state, count in rows:
        counts[str(state)] = int(count)
    uploaded = counts["UPLOADED"]
    tracked = sum(counts[state] for state in VALID_STATES if state != "REMOVED")
    untracked_local = max(paper_total - tracked, 0)
    counts["PAPERS"] = paper_total
    counts["TRACKED"] = tracked
    counts["LOCAL_UNTRACKED"] = untracked_local
    counts["UPLOADABLE_REMAINING"] = counts["PENDING"] + counts["MODIFIED"] + counts["RENAMED"] + counts["FAILED"]
    counts["NOT_UPLOADED"] = max(paper_total - uploaded, 0)
    counts["REMAINING"] = counts["NOT_UPLOADED"]
    return counts


def print_counts(title: str, counts: Counter[str]) -> None:
    print(title)
    preferred_order = [
        "PAPERS",
        "UPLOADED",
        "NOT_UPLOADED",
        "REMAINING",
        "UPLOADABLE_REMAINING",
        "TRACKED",
        "LOCAL_UNTRACKED",
        "PENDING",
        "MODIFIED",
        "RENAMED",
        "FAILED",
        "NEEDS_TRACKING_ID",
        "REMOVED",
    ]
    seen: set[str] = set()
    for key in preferred_order:
        if key in counts:
            print(f"- {key}: {counts[key]}")
            seen.add(key)
    for key in sorted(set(counts) - seen):
        print(f"- {key}: {counts[key]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload papers/ PDFs and generate static frontend manifests.")
    parser.add_argument("command", choices=["preflight", "scan", "sync", "manifest", "status", "summary", "all", "bulk-delete"])
    parser.add_argument("--workers", type=int, default=4, help="Concurrent PDF upload workers for sync/all. Defaults to 4.")
    parser.add_argument("--limit", type=int, default=0, help="Upload at most this many PDFs in this run. 0 means no limit.")
    parser.add_argument("--sample", type=int, default=8, help="Number of pending/failed sample rows to print for summary.")
    parser.add_argument(
        "--target",
        choices=["cloud", "local", "both"],
        default="",
        help="bulk-delete target. Omit to choose interactively.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview bulk-delete targets without deleting anything.")
    parser.add_argument("--yes", action="store_true", help="Skip bulk-delete confirmation prompt.")
    parser.add_argument(
        "--state",
        choices=["PENDING", "MODIFIED", "RENAMED", "FAILED"],
        default="",
        help="Restrict sync to one upload state. Useful for retrying FAILED only.",
    )
    return parser.parse_args()


def main() -> int:
    load_environment()
    args = parse_args()
    try:
        if args.command == "preflight":
            print_counts("Preflight status", preflight_upload())
        elif args.command == "scan":
            print_counts("Scan complete", scan_papers())
        elif args.command == "sync":
            print_counts("Upload sync complete", sync_uploads(args.workers, args.limit, args.state))
        elif args.command == "manifest":
            print_counts("Manifest generation complete", generate_manifests())
        elif args.command == "status":
            print_counts("Upload status", status_counts())
        elif args.command == "summary":
            upload_summary(args.sample)
        elif args.command == "all":
            print_counts("Scan complete", scan_papers())
            print_counts("Upload sync complete", sync_uploads(args.workers, args.limit, args.state))
            print_counts("Manifest generation complete", generate_manifests())
        elif args.command == "bulk-delete":
            print_counts("Bulk delete complete", bulk_delete(args.target, dry_run=args.dry_run, yes=args.yes))
        return 0
    except (OSError, RuntimeError, sqlite3.Error, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
