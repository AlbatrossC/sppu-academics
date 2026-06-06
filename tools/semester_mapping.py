"""Review and apply subject semester mappings for frontend manifests."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from upload_pipeline import (  # noqa: E402
    MANIFEST_DIR,
    PATTERN_FILES,
    SEMESTER_MAPPING_PATH,
    NameLookup,
    normalize_name,
    normalize_semester_value,
    read_yaml,
    strip_subject_suffix,
    write_json,
    year_full_name,
)

CHANGELOG_PATH = PROJECT_ROOT / "changelog" / "semester.md"
PAPERS_DIR = PROJECT_ROOT / "papers"
BEGIN_MARKER = "<!-- SEMESTER_MAPPING_PENDING_BEGIN -->"
END_MARKER = "<!-- SEMESTER_MAPPING_PENDING_END -->"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=True, allow_unicode=False)
    temp_path.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_scope(path_value: str, names: NameLookup) -> dict[str, str]:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    try:
        parts = path.relative_to(PROJECT_ROOT.resolve()).parts
    except ValueError as exc:
        raise RuntimeError(f"Path must be inside this project: {path}") from exc
    if not parts or parts[0] != "papers":
        raise RuntimeError("Semester review path must be under papers/.")

    branch = names.normalize_branch(parts[1]) if len(parts) > 1 else ""

    if branch == "first-year" and len(parts) in {3, 4}:
        pattern = names.normalize_pattern(parts[2])
        scope = {
            "branch_type": "first_year",
            "branch": branch,
            "branch_name": names.display(branch),
            "branch_code": names.code(branch),
            "year": "",
            "year_name": "First Year",
            "pattern": pattern,
            "pattern_name": names.display(pattern),
            "path": (PROJECT_ROOT / "papers" / parts[1] / parts[2]).relative_to(PROJECT_ROOT).as_posix(),
        }
        if len(parts) == 4:
            subject_key = names.normalize_other(parts[3])
            scope["focus_subject_key"] = subject_key
            scope["focus_subject_path"] = path.relative_to(PROJECT_ROOT).as_posix()
        return scope

    if branch not in {"first-year", "m-b-a", "honors-course"} and len(parts) in {4, 5}:
        year = names.normalize_other(parts[2])
        pattern = names.normalize_pattern(parts[3])
        scope = {
            "branch_type": "standard",
            "branch": branch,
            "branch_name": names.display(branch),
            "branch_code": names.code(branch),
            "year": year,
            "year_name": names.display(year),
            "pattern": pattern,
            "pattern_name": names.display(pattern),
            "path": (PROJECT_ROOT / "papers" / parts[1] / parts[2] / parts[3]).relative_to(PROJECT_ROOT).as_posix(),
        }
        if len(parts) == 5:
            subject_key = names.normalize_other(parts[4])
            scope["focus_subject_key"] = subject_key
            scope["focus_subject_path"] = path.relative_to(PROJECT_ROOT).as_posix()
        return scope

    raise RuntimeError("Use a pattern or subject folder under papers/.")


def list_subjects(scope: dict[str, str], names: NameLookup) -> list[dict[str, str]]:
    folder = PROJECT_ROOT / scope["path"]
    if not folder.exists() or not folder.is_dir():
        raise RuntimeError(f"Review folder does not exist: {folder}")
    subjects: list[dict[str, str]] = []
    branch_code = scope["branch_code"]
    year = scope["year"]
    for child in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        subject_key = names.normalize_other(child.name)
        normalized = strip_subject_suffix(subject_key, branch_code, year)
        subjects.append(
            {
                "subject_key": subject_key,
                "subject_name": names.display(normalized),
                "directory_name": child.name,
                "folder": child.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
    if not subjects:
        raise RuntimeError(f"No subject folders found under {folder}")
    return subjects


def context_payload(scope: dict[str, str], subjects: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "repo_context": "Sppu-pyqs question paper repository",
        "scope": scope,
        "subjects": subjects,
        "requirements": [
            "Map only these subject_key values.",
            "Search for SPPU syllabus sources for this branch/year/pattern.",
            "Prefer official SPPU or college PDFs.",
            "Return semester_no as a number when evidence is clear, other when reviewed but not numbered, or unresolved when evidence is not clear.",
            "Return only a JSON object with an entries array. Each entry must include subject_key, subject_name, semester_no, status, confidence, evidence, and sources.",
            "The subjects array was produced by listing the local subject directories directly. directory_name is the exact folder name on disk.",
        ],
    }


def context_json(scope: dict[str, str], subjects: list[dict[str, str]]) -> str:
    return json.dumps(context_payload(scope, subjects), indent=2)


def normalize_entry(entry: dict[str, Any], subject_lookup: dict[str, dict[str, str]]) -> dict[str, Any]:
    subject_key = str(entry.get("subject_key", "")).strip()
    subject = subject_lookup.get(subject_key)
    if not subject:
        return {}
    semester_no = normalize_stage_semester(entry.get("semester_no"))
    status = "mapped" if is_included_semester(semester_no) else "unresolved"
    sources = entry.get("sources") if isinstance(entry.get("sources"), list) else []
    return {
        "subject_key": subject_key,
        "subject_name": subject["subject_name"],
        "subject_path": subject["folder"],
        "semester_no": semester_no,
        "status": status,
        "confidence": str(entry.get("confidence") or "low"),
        "evidence": str(entry.get("evidence") or "").strip(),
        "sources": [
            {"title": str(source.get("title") or "").strip(), "url": str(source.get("url") or "").strip()}
            for source in sources
            if isinstance(source, dict) and source.get("url")
        ],
    }


def build_review(scope: dict[str, str], subjects: list[dict[str, str]], response: dict[str, Any], *, add_missing: bool = True) -> dict[str, Any]:
    subject_lookup = {subject["subject_key"]: subject for subject in subjects}
    entries = [normalize_entry(entry, subject_lookup) for entry in response.get("entries", []) if isinstance(entry, dict)]
    entries = [entry for entry in entries if entry]
    seen = {entry["subject_key"] for entry in entries}
    if add_missing:
        for subject in subjects:
            if subject["subject_key"] not in seen:
                entries.append(
                    {
                        "subject_key": subject["subject_key"],
                        "subject_name": subject["subject_name"],
                        "subject_path": subject["folder"],
                        "semester_no": "unresolved",
                        "status": "unresolved",
                        "confidence": "low",
                        "evidence": "No reviewed mapping was returned for this subject.",
                        "sources": [],
                    }
                )
    return {"scope": scope, "entries": entries}


def build_empty_review(scope: dict[str, str], subjects: list[dict[str, str]]) -> dict[str, Any]:
    focus = scope.get("focus_subject_key")
    draft_subjects = [subject for subject in subjects if subject["subject_key"] == focus] if focus else subjects
    return {
        "scope": scope,
        "entries": [
            {
                "subject_key": subject["subject_key"],
                "subject_name": subject["subject_name"],
                "subject_path": subject["folder"],
                "semester_no": "unresolved",
                "status": "unresolved",
                "confidence": "low",
                "evidence": "Awaiting AI-agent syllabus research. See docs/semester.md.",
                "sources": [],
            }
            for subject in draft_subjects
        ],
    }


def load_stage_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() in {".yml", ".yaml"}:
            return yaml.safe_load(handle) or {}
        return json.load(handle)


def reviews_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    names = NameLookup()
    if isinstance(payload.get("reviews"), list):
        reviews = []
        for review in payload["reviews"]:
            if not isinstance(review, dict):
                continue
            scope = review.get("scope")
            if not isinstance(scope, dict) and review.get("path"):
                scope = parse_scope(str(review["path"]), names)
            if not isinstance(scope, dict):
                raise RuntimeError("Each review must include scope or path.")
            subjects = list_subjects(scope, names)
            reviews.append(build_review(scope, subjects, {"entries": review.get("entries") or []}, add_missing=False))
        return reviews

    path = payload.get("path")
    if not path:
        raise RuntimeError("Stage payload must include reviews[] or path.")
    scope = parse_scope(str(path), names)
    subjects = list_subjects(scope, names)
    entries = payload.get("entries")
    if entries is None and payload.get("subject_key"):
        entries = [payload]
    if not isinstance(entries, list):
        raise RuntimeError("Stage payload entries must be a list.")
    return [build_review(scope, subjects, {"entries": entries}, add_missing=False)]


def markdown_safe(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("|", "\\|").strip()


def normalize_stage_semester(value: Any) -> int | str:
    semester = normalize_semester_value(value)
    if semester is not None:
        return semester
    if isinstance(value, str) and value.strip().lower() == "unresolved":
        return "unresolved"
    return "unresolved"


def is_included_semester(value: Any) -> bool:
    return normalize_semester_value(value) is not None


def semester_group_label(value: Any) -> str:
    if isinstance(value, int):
        return f"Semester {value}"
    if value == "other":
        return "Other"
    return "Unresolved"


def review_title(scope: dict[str, Any]) -> str:
    if scope.get("branch_type") == "first_year":
        return f"{scope.get('branch_name', 'First Year')} / {scope.get('pattern_name', scope.get('pattern', ''))}"
    return " / ".join(
        str(part)
        for part in (
            scope.get("branch_name") or scope.get("branch"),
            scope.get("year_name") or scope.get("year"),
            scope.get("pattern_name") or scope.get("pattern"),
        )
        if part
    )


def source_list(sources: list[dict[str, Any]]) -> str:
    links = []
    for source in sources:
        title = markdown_safe(source.get("title") or source.get("url") or "source")
        url = markdown_safe(source.get("url"))
        if url:
            links.append(f"[{title}]({url})")
    return ", ".join(links) if links else "No source URLs returned"


def render_review_sections(reviews: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, review in enumerate(reviews, start=1):
        scope = review.get("scope") or {}
        entries = [entry for entry in review.get("entries", []) if isinstance(entry, dict)]
        mapped = sum(1 for entry in entries if is_included_semester(entry.get("semester_no")))
        unresolved = len(entries) - mapped
        lines.extend(
            [
                f"## {index}. {review_title(scope)}",
                "",
                f"- Path: `{scope.get('path', '')}`",
                f"- Subjects: `{len(entries)}`",
                f"- Mapped: `{mapped}`",
                f"- Unresolved: `{unresolved}`",
                "",
            ]
        )

        grouped: dict[Any, list[dict[str, Any]]] = {}
        for entry in entries:
            semester = normalize_stage_semester(entry.get("semester_no"))
            grouped.setdefault(semester if is_included_semester(semester) else "unresolved", []).append(entry)
        ordered_keys = sorted([key for key in grouped if isinstance(key, int)])
        if "other" in grouped:
            ordered_keys.append("other")
        if "unresolved" in grouped:
            ordered_keys.append("unresolved")

        for semester in ordered_keys:
            group = sorted(grouped[semester], key=lambda item: str(item.get("subject_name") or item.get("subject_key")).lower())
            lines.extend(
                [
                    f"### {semester_group_label(semester)}",
                    "",
                    "| Subject | Key | Status | Confidence |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for entry in group:
                status = "mapped" if is_included_semester(entry.get("semester_no")) else "unresolved"
                lines.append(
                    "| "
                    f"{markdown_safe(entry.get('subject_name'))} | "
                    f"`{markdown_safe(entry.get('subject_key'))}` | "
                    f"{status} | "
                    f"{markdown_safe(entry.get('confidence'))} |"
                )
            lines.append("")
            for entry in group:
                lines.extend(
                    [
                        f"<details><summary>{markdown_safe(entry.get('subject_name'))}</summary>",
                        "",
                        f"- Subject key: `{markdown_safe(entry.get('subject_key'))}`",
                        f"- Subject path: `{markdown_safe(entry.get('subject_path'))}`",
                        f"- Evidence: {markdown_safe(entry.get('evidence')) or 'No evidence returned'}",
                        f"- Sources: {source_list(entry.get('sources') if isinstance(entry.get('sources'), list) else [])}",
                        "",
                        "</details>",
                        "",
                    ]
                )
    return lines


def write_changelog(reviews: list[dict[str, Any]]) -> None:
    entries = [entry for review in reviews for entry in review.get("entries", [])]
    payload = {
        "generated_at": utc_now(),
        "reviews": reviews,
    }

    lines = [
        "# Semester Mapping Review",
        "",
        "Review the proposed semester mappings, then run `python3 tools/semester_mapping.py apply` to update `mapping/semester_mapping.yml`.",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Reviewed folders: `{len(reviews)}`",
        f"- Pending subjects: `{len(entries)}`",
        "",
    ]
    lines.extend(render_review_sections(reviews))
    lines.extend(
        [
            "",
            BEGIN_MARKER,
            "```json",
            json.dumps(payload, indent=2, ensure_ascii=False),
            "```",
            END_MARKER,
            "",
        ]
    )
    CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    mapped = sum(1 for entry in entries if is_included_semester(entry.get("semester_no")))
    print(f"Wrote {CHANGELOG_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Reviewed folders: {len(reviews)}")
    print(f"Mapped subjects: {mapped}")
    print(f"Unresolved subjects: {len(entries) - mapped}")


def extract_pending_payload() -> dict[str, Any]:
    if not CHANGELOG_PATH.exists():
        raise RuntimeError("No semester changelog found. Run review first.")
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(BEGIN_MARKER)}\s*```json\s*(\{{.*?\}})\s*```\s*{re.escape(END_MARKER)}", text, re.DOTALL)
    if not match:
        raise RuntimeError("No machine-readable semester payload found in changelog/semester.md.")
    return json.loads(match.group(1))


def empty_mapping() -> dict[str, Any]:
    return {"schema_version": 1, "standard": {}, "first_year": {}}


def apply_review() -> None:
    payload = extract_pending_payload()
    reviews = payload.get("reviews")
    if not isinstance(reviews, list):
        reviews = [{"scope": payload.get("scope") or {}, "entries": payload.get("entries") or []}]
    mapping = read_yaml(SEMESTER_MAPPING_PATH) or empty_mapping()
    mapping.setdefault("schema_version", 1)
    mapping.setdefault("standard", {})
    mapping.setdefault("first_year", {})

    applied = 0
    for review in reviews:
        if not isinstance(review, dict):
            continue
        scope = review.get("scope") or {}
        entries = review.get("entries") or []
        if scope.get("branch_type") == "standard":
            target = (
                mapping["standard"]
                .setdefault(str(scope["branch"]), {})
                .setdefault(str(scope["year"]), {})
                .setdefault(str(scope["pattern"]), {})
            )
        elif scope.get("branch_type") == "first_year":
            target = mapping["first_year"].setdefault(str(scope["pattern"]), {})
        else:
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            semester_no = normalize_stage_semester(entry.get("semester_no"))
            target[str(entry["subject_key"])] = semester_no
            applied += 1

    write_yaml(SEMESTER_MAPPING_PATH, mapping)
    print(f"Applied semester mappings: {applied}")
    print(f"Updated {SEMESTER_MAPPING_PATH.relative_to(PROJECT_ROOT)}")
    fix_manifest(dry_run=False)


def discard_review() -> None:
    payload = {
        "generated_at": utc_now(),
        "reviews": [],
    }
    lines = [
        "# Semester Mapping Review",
        "",
        "No semester mappings are pending.",
        "",
        BEGIN_MARKER,
        "```json",
        json.dumps(payload, indent=2),
        "```",
        END_MARKER,
        "",
    ]
    CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Discarded pending semester review in {CHANGELOG_PATH.relative_to(PROJECT_ROOT)}")


def subject_semester(mapping: dict[str, Any], branch_type: str, branch: str, year: str, pattern: str, subject_key: str) -> int | str | None:
    value: Any = None
    if branch_type == "standard":
        value = mapping.get("standard", {}).get(branch, {}).get(year, {}).get(pattern, {}).get(subject_key)
    elif branch_type == "first_year":
        value = mapping.get("first_year", {}).get(pattern, {}).get(subject_key)
    return normalize_semester_value(value)


def patch_pattern_manifest(path: Path, mapping: dict[str, Any], *, dry_run: bool) -> bool:
    data = load_json(path)
    if not data:
        return False
    pattern = str(data.get("pattern") or path.stem)
    changed = False

    standard = data.get("hierarchy", {}).get("standard", {}).get("branches", [])
    if isinstance(standard, list):
        for branch in standard:
            if not isinstance(branch, dict):
                continue
            branch_key = str(branch.get("branchKey") or "")
            years = branch.get("years") or []
            if not isinstance(years, list):
                continue
            for year_node in years:
                if not isinstance(year_node, dict):
                    continue
                year_key = str(year_node.get("yearKey") or "")
                full_name = year_full_name(year_key)
                if year_node.get("yearFullName") != full_name:
                    year_node["yearFullName"] = full_name
                    changed = True
                subjects = year_node.get("subjects") or []
                mapped = [
                    subject_semester(mapping, "standard", branch_key, year_key, pattern, str(subject.get("subjectKey") or ""))
                    for subject in subjects
                    if isinstance(subject, dict)
                ]
                included = bool(mapped) and all(item is not None for item in mapped)
                if year_node.get("semesterIncluded") != included:
                    year_node["semesterIncluded"] = included
                    changed = True
                for subject in subjects:
                    if isinstance(subject, dict):
                        changed = subject.pop("semesterIncluded", None) is not None or changed
                        semester_no = subject_semester(
                            mapping,
                            "standard",
                            branch_key,
                            year_key,
                            pattern,
                            str(subject.get("subjectKey") or ""),
                        )
                        if semester_no is not None:
                            if subject.get("semesterNo") != semester_no:
                                subject["semesterNo"] = semester_no
                                changed = True
                        elif subject.pop("semesterNo", None) is not None:
                            changed = True

    first_year = data.get("hierarchy", {}).get("firstYear")
    if isinstance(first_year, dict):
        subjects = first_year.get("subjects") or []
        mapped = [
            subject_semester(mapping, "first_year", "", "", pattern, str(subject.get("subjectKey") or ""))
            for subject in subjects
            if isinstance(subject, dict)
        ]
        included = bool(mapped) and all(item is not None for item in mapped)
        if first_year.get("semesterIncluded") != included:
            first_year["semesterIncluded"] = included
            changed = True
        for subject in subjects:
            if isinstance(subject, dict):
                changed = subject.pop("semesterIncluded", None) is not None or changed
                semester_no = subject_semester(mapping, "first_year", "", "", pattern, str(subject.get("subjectKey") or ""))
                if semester_no is not None:
                    if subject.get("semesterNo") != semester_no:
                        subject["semesterNo"] = semester_no
                        changed = True
                elif subject.pop("semesterNo", None) is not None:
                    changed = True

    if changed and not dry_run:
        write_json(path, data)
    return changed


def patch_subject_manifest(path: Path, mapping: dict[str, Any], *, dry_run: bool) -> bool:
    data = load_json(path)
    if not data:
        return False
    pattern = str(data.get("pattern") or path.stem.replace("_subjects", ""))
    changed = False
    subjects = data.get("subjects") or {}
    if not isinstance(subjects, dict):
        return False
    for subject_key, subject in subjects.items():
        if not isinstance(subject, dict):
            continue
        branch_type = str(subject.get("branchType") or "")
        if branch_type != "mba" and "yearName" in subject:
            full_name = year_full_name(str(subject.get("yearKey") or ""), branch_type)
            if subject.get("yearFullName") != full_name:
                subject["yearFullName"] = full_name
                changed = True
        if branch_type == "standard":
            semester_no = subject_semester(
                mapping,
                branch_type,
                str(subject.get("branchKey") or ""),
                str(subject.get("yearKey") or ""),
                pattern,
                str(subject_key),
            )
        elif branch_type == "first_year":
            semester_no = subject_semester(mapping, branch_type, "", "", pattern, str(subject_key))
        else:
            semester_no = None
        if semester_no is not None:
            if subject.get("semesterNo") != semester_no:
                subject["semesterNo"] = semester_no
                changed = True
        elif subject.pop("semesterNo", None) is not None:
            changed = True
        if subject.pop("semesterIncluded", None) is not None:
            changed = True
    if changed and not dry_run:
        write_json(path, data)
    return changed


def patch_honors_manifest(path: Path, *, dry_run: bool) -> bool:
    data = load_json(path)
    if not data:
        return False
    changed = False
    years = data.get("hierarchy", {}).get("honorsCourse", {}).get("years") or []
    if not isinstance(years, list):
        return False
    for year_node in years:
        if not isinstance(year_node, dict):
            continue
        year_key = str(year_node.get("yearKey") or "")
        full_name = year_full_name(year_key)
        if year_node.get("yearFullName") != full_name:
            year_node["yearFullName"] = full_name
            changed = True
    if changed and not dry_run:
        write_json(path, data)
    return changed


def fix_manifest(*, dry_run: bool) -> None:
    mapping = read_yaml(SEMESTER_MAPPING_PATH) or empty_mapping()
    changed: list[str] = []
    for filename in PATTERN_FILES.values():
        pattern_path = MANIFEST_DIR / filename
        subject_path = MANIFEST_DIR / f"{Path(filename).stem}_subjects.json"
        if patch_pattern_manifest(pattern_path, mapping, dry_run=dry_run):
            changed.append(pattern_path.relative_to(PROJECT_ROOT).as_posix())
        if patch_subject_manifest(subject_path, mapping, dry_run=dry_run):
            changed.append(subject_path.relative_to(PROJECT_ROOT).as_posix())
    honors_path = MANIFEST_DIR / "honors.json"
    honors_subject_path = MANIFEST_DIR / "honors_subjects.json"
    if patch_honors_manifest(honors_path, dry_run=dry_run):
        changed.append(honors_path.relative_to(PROJECT_ROOT).as_posix())
    if patch_subject_manifest(honors_subject_path, mapping, dry_run=dry_run):
        changed.append(honors_subject_path.relative_to(PROJECT_ROOT).as_posix())
    action = "Would update" if dry_run else "Updated"
    print(f"{action} manifest files: {len(changed)}")
    for path in changed:
        print(f"- {path}")


def review(paths: list[str]) -> None:
    names = NameLookup()
    reviews: list[dict[str, Any]] = []
    for path in paths:
        scope = parse_scope(path, names)
        subjects = list_subjects(scope, names)
        print(f"Preparing {scope['path']} ({len(subjects)} subjects)")
        reviews.append(build_empty_review(scope, subjects))
    write_changelog(reviews)


def preview(paths: list[str]) -> None:
    names = NameLookup()
    for index, path in enumerate(paths, start=1):
        scope = parse_scope(path, names)
        subjects = list_subjects(scope, names)
        print(f"--- Context {index}: {scope['path']} ({len(subjects)} subjects) ---")
        print(context_json(scope, subjects))


def stage(path: str) -> None:
    payload = load_stage_payload(Path(path))
    write_changelog(reviews_from_payload(payload))


def format_changelog() -> None:
    payload = extract_pending_payload()
    reviews = payload.get("reviews")
    if not isinstance(reviews, list):
        reviews = [{"scope": payload.get("scope") or {}, "entries": payload.get("entries") or []}]
    write_changelog(reviews)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage/apply SPPU semester mappings.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    review_parser = subparsers.add_parser("review", help="Create an unresolved changelog draft for pattern folder(s).")
    review_parser.add_argument("paths", nargs="+", help="Pattern folder(s) under papers/.")

    preview_parser = subparsers.add_parser("preview", help="Print local context payload for AI-agent research.")
    preview_parser.add_argument("paths", nargs="+", help="Pattern folder(s) under papers/.")

    stage_parser = subparsers.add_parser("stage", help="Write researched semester results to changelog/semester.md.")
    stage_parser.add_argument("input", help="JSON/YAML payload produced by an AI agent.")

    subparsers.add_parser("apply", help="Apply reviewed mappings to mapping/semester_mapping.yml and generated manifests.")
    subparsers.add_parser("discard", help="Clear the pending semester changelog.")
    subparsers.add_parser("format-md", help="Reformat changelog/semester.md without changing mappings.")
    fix_parser = subparsers.add_parser("fix-manifest", help="Patch already-generated manifest JSON from approved mappings.")
    fix_parser.add_argument("--dry-run", action="store_true", help="Print manifest files that would change.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "review":
            review(args.paths)
        elif args.command == "preview":
            preview(args.paths)
        elif args.command == "stage":
            stage(args.input)
        elif args.command == "apply":
            apply_review()
        elif args.command == "discard":
            discard_review()
        elif args.command == "format-md":
            format_changelog()
        elif args.command == "fix-manifest":
            fix_manifest(dry_run=args.dry_run)
        return 0
    except (OSError, RuntimeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
