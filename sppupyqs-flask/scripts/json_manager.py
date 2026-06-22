from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from utils import ensure_directory, load_json_file


@dataclass(frozen=True)
class ManifestPdfItem:
    pattern_key: str
    pattern_year: str
    branch: str
    branch_key: str
    branch_name: str
    semester: str
    year_key: str
    year_name: str
    subject_slug: str
    subject_name: str
    pdf_id: str
    pdf_url: str
    canonical_path: str
    paper: dict[str, Any]


def iter_branch_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.glob("*.json") if path.is_file())


def iter_subject_manifest_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.glob("*_subjects.json") if path.is_file())


def pattern_key_from_manifest_file(path: Path) -> str:
    stem = path.stem
    return stem[: -len("_subjects")] if stem.endswith("_subjects") else stem


def manifest_provider_base(manifest_payload: dict[str, Any], provider: str = "r2") -> str:
    providers = manifest_payload.get("providers") or {}
    if provider == "cloudinary":
        return str(providers.get("cloudinaryRawBaseUrl") or "").rstrip("/")
    return str(providers.get("r2BaseUrl") or "").rstrip("/")


def build_manifest_pdf_url(base_url: str, canonical_path: str) -> str:
    if not base_url or not canonical_path:
        return ""
    return f"{base_url.rstrip('/')}/{canonical_path.lstrip('/')}"


def semester_slug_for_subject(subject_payload: dict[str, Any]) -> str:
    semester_no = subject_payload.get("semesterNo")
    if semester_no not in (None, ""):
        return f"sem-{semester_no}"
    return str(subject_payload.get("yearKey") or "subjects")


def iter_manifest_pdf_items(
    manifest_payload: dict[str, Any],
    *,
    pattern_key: str,
    provider: str = "r2",
) -> Iterable[ManifestPdfItem]:
    base_url = manifest_provider_base(manifest_payload, provider=provider)
    pattern_year = str(manifest_payload.get("patternYear") or pattern_key)

    for subject_slug, subject_payload in (manifest_payload.get("subjects") or {}).items():
        if not isinstance(subject_payload, dict):
            continue

        branch = str(subject_payload.get("branchCode") or subject_payload.get("branchKey") or "unknown")
        semester = semester_slug_for_subject(subject_payload)
        subject_name = str(subject_payload.get("fullName") or subject_slug)

        for paper in subject_payload.get("papers") or []:
            if not isinstance(paper, dict):
                continue
            canonical_path = str(paper.get("canonicalPath") or "")
            pdf_url = build_manifest_pdf_url(base_url, canonical_path)
            if not pdf_url:
                continue
            yield ManifestPdfItem(
                pattern_key=pattern_key,
                pattern_year=pattern_year,
                branch=branch,
                branch_key=str(subject_payload.get("branchKey") or ""),
                branch_name=str(subject_payload.get("branchName") or ""),
                semester=semester,
                year_key=str(subject_payload.get("yearKey") or ""),
                year_name=str(subject_payload.get("yearName") or ""),
                subject_slug=str(subject_slug),
                subject_name=subject_name,
                pdf_id=str(paper.get("pdfId") or ""),
                pdf_url=pdf_url,
                canonical_path=canonical_path,
                paper=paper,
            )


def iter_branch_items(branch_payload: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for semester, semester_payload in branch_payload.items():
        if not semester.startswith("sem-") or not isinstance(semester_payload, dict):
            continue

        for subject_slug, subject_payload in semester_payload.items():
            if not isinstance(subject_payload, dict):
                continue
            yield semester, subject_slug, subject_payload


def read_json(path: Path) -> dict[str, Any]:
    return load_json_file(path)


def subject_output_path(output_dir: Path, branch: str, semester: str, subject_slug: str) -> Path:
    return output_dir / branch / semester / f"{subject_slug}.json"


def load_subject_document(
    output_dir: Path,
    branch: str,
    semester: str,
    subject_slug: str,
    subject_name: str,
) -> tuple[Path, dict[str, Any]]:
    output_path = subject_output_path(output_dir, branch, semester, subject_slug)

    if output_path.exists():
        return output_path, read_json(output_path)

    return output_path, {
        "subject_name": subject_name,
        "subject_slug": subject_slug,
        "branch": branch,
        "semester": semester,
        "papers": [],
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_directory(path.parent)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=path.parent,
        suffix=".tmp",
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)

    os.replace(temp_path, path)


def count_total_pdfs(branch_files: list[Path]) -> int:
    total = 0

    for branch_file in branch_files:
        branch_payload = read_json(branch_file)
        for _, _, subject_payload in iter_branch_items(branch_payload):
            pdf_links = subject_payload.get("pdf_links", [])
            if isinstance(pdf_links, list):
                total += len(pdf_links)

    return total


def count_target_pdfs(
    branch_files: list[Path],
    branch_filter: str | None = None,
    semester_filter: str | None = None,
    subject_filter: str | None = None,
) -> int:
    total = 0

    for branch_file in branch_files:
        if branch_filter and branch_file.stem.lower() != branch_filter:
            continue

        branch_payload = read_json(branch_file)
        for semester, subject_slug, subject_payload in iter_branch_items(branch_payload):
            if semester_filter and semester != semester_filter:
                continue
            if subject_filter and subject_slug != subject_filter:
                continue

            pdf_links = subject_payload.get("pdf_links", [])
            if isinstance(pdf_links, list):
                total += len(pdf_links)

    return total


def count_target_manifest_pdfs(
    manifest_files: list[Path],
    *,
    pattern_filter: str | None = None,
    branch_filter: str | None = None,
    year_filter: str | None = None,
    semester_filter: str | None = None,
    subject_filter: str | None = None,
    provider: str = "r2",
) -> int:
    total = 0

    for manifest_file in manifest_files:
        pattern_key = pattern_key_from_manifest_file(manifest_file)
        if pattern_filter and pattern_key != pattern_filter:
            continue

        manifest_payload = read_json(manifest_file)
        for item in iter_manifest_pdf_items(manifest_payload, pattern_key=pattern_key, provider=provider):
            if branch_filter and branch_filter not in {item.branch, item.branch_key}:
                continue
            if year_filter and item.year_key != year_filter:
                continue
            if semester_filter and item.semester != semester_filter:
                continue
            if subject_filter and item.subject_slug != subject_filter:
                continue
            total += 1

    return total
