import json
import os
import re
from functools import lru_cache
from urllib.parse import urlparse

from .config import CLOUDINARY_RAW_BASE_URL, DEFAULT_PATTERN_YEAR, MANIFEST_DIR, PDF_SOURCE, R2_BASE_URL

HONORS_KEY = "honors"
REDIRECT_PATTERN_ORDER = ("2019", "2015", "2012", HONORS_KEY)
EXCEPTIONS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "exceptions.yml"))


def _safe_load_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except Exception:
        return None


def _parse_scalar(value):
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _minimal_yaml_load(file_path):
    data = {}
    stack = [(-1, data)]
    with open(file_path, "r", encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(" "))
            key, separator, value = line.strip().partition(":")
            if not separator:
                continue
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if value.strip():
                parent[key] = _parse_scalar(value)
                continue
            child = {}
            parent[key] = child
            stack.append((indent, child))
    return data


def _safe_load_yaml(file_path):
    if not os.path.exists(file_path):
        return {}
    try:
        import yaml  # type: ignore

        with open(file_path, "r", encoding="utf-8") as file_obj:
            return yaml.safe_load(file_obj) or {}
    except ImportError:
        return _minimal_yaml_load(file_path)
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _load_exceptions():
    data = _safe_load_yaml(EXCEPTIONS_FILE)
    return data if isinstance(data, dict) else {}


def _manifest_path(name):
    return os.path.join(MANIFEST_DIR, name)


def _available_pattern_years():
    years = []
    if not os.path.exists(MANIFEST_DIR):
        return []
    for filename in os.listdir(MANIFEST_DIR):
        stem, ext = os.path.splitext(filename)
        if ext == ".json" and stem.isdigit() and not stem.endswith("_subjects"):
            years.append(stem)
    return sorted(years, reverse=True)


def _title_case_identifier(value):
    return " ".join(part for part in str(value or "").replace("_", " ").replace("-", " ").split()).title()


def _abbreviation(name):
    return "".join(word[0] for word in str(name or "").split() if word and word[0].isalnum()).lower()


def _collapse_spaces(value):
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ")).strip()


def _display_settings():
    settings = _load_exceptions().get("display") or {}
    return settings if isinstance(settings, dict) else {}


def _subject_overrides(subject_key):
    overrides = _load_exceptions().get("subject_overrides") or {}
    value = overrides.get(subject_key) if isinstance(overrides, dict) else None
    return value if isinstance(value, dict) else {}


def _branch_overrides(branch_key):
    overrides = _load_exceptions().get("branch_overrides") or {}
    value = overrides.get(branch_key) if isinstance(overrides, dict) else None
    return value if isinstance(value, dict) else {}


def _normalize_elective_code(value):
    text = str(value or "").strip()
    spaced = re.fullmatch(r"([A-Za-z0-9]+)\s+Elec\s+([IVX]+)", text, re.IGNORECASE)
    if spaced:
        return f"{spaced.group(1).upper()} Elec {spaced.group(2).upper()}"
    match = re.fullmatch(r"([A-Za-z0-9]+)[_\-\s]*e([IVX]+)", text, re.IGNORECASE)
    if not match:
        return text.upper()
    return f"{match.group(1).upper()} Elec {match.group(2).upper()}"


def _normalize_elective_name(value):
    text = _collapse_spaces(value)
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"(?:\s+-\s+|\s+)Ele\.?\s*-\s*([IVX]+)\b", r" - Elective \1", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:\s+-\s+|\s+)Ele\.?\s+([IVX]+)\b", r" - Elective \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEle\.?\s*-\s*([IVX]+)\b", r"Elective \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEle\.?\s+([IVX]+)\b", r"Elective \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bElective\s+([ivx]+)\b", lambda m: f"Elective {m.group(1).upper()}", text)
    return _collapse_spaces(text)


def _is_elective(subject):
    haystack = " ".join(
        str(subject.get(key) or "")
        for key in ("shortCode", "fullName", "normalizedName", "subjectKey")
    )
    return bool(re.search(r"(^|[_\-\s])e(?:le\.?|lec|lective)?[_\-\s]*[IVX]+\b", haystack, re.IGNORECASE))


def _subject_sort_key(subject):
    return (
        1 if _is_elective(subject) else 0,
        _collapse_spaces(subject.get("fullName") or subject.get("subjectKey")).casefold(),
    )


def _apply_branch_exceptions(branch):
    branch = dict(branch or {})
    branch.update(_branch_overrides(branch.get("branchKey")))
    return branch


def _apply_subject_exceptions(subject):
    subject = dict(subject or {})
    subject.update(_subject_overrides(subject.get("subjectKey")))
    settings = _display_settings()
    if settings.get("normalizeElectiveNames", True):
        subject["fullName"] = _normalize_elective_name(subject.get("fullName") or subject.get("subjectKey"))
    if settings.get("normalizeElectiveCodes", True):
        subject["shortCode"] = _normalize_elective_code(subject.get("shortCode", ""))
    return subject


def _provider_base(subjects_manifest):
    providers = subjects_manifest.get("providers") or {}
    if PDF_SOURCE == "cloudinary":
        return (CLOUDINARY_RAW_BASE_URL or providers.get("cloudinaryRawBaseUrl") or "").rstrip("/")
    return (R2_BASE_URL or providers.get("r2BaseUrl") or "").rstrip("/")


def _paper_label(paper):
    exam = str(paper.get("exam") or "paper").upper()
    month = str(paper.get("month") or "").replace("_", " ").title()
    year = str(paper.get("year") or "").strip()
    return " ".join(part for part in [year, month, exam] if part).strip() or "Paper"


def _paper_url(base_url, canonical_path):
    if not base_url or not canonical_path:
        return ""
    return f"{base_url.rstrip('/')}/{str(canonical_path).lstrip('/')}"


def _seo_for_subject(subject, route_path):
    subject_name = subject.get("fullName") or subject.get("subject_name") or subject.get("subjectKey")
    branch_name = subject.get("branchName") or subject.get("branch_name") or "SPPU"
    pattern = str(subject.get("pattern") or subject.get("pattern_year") or "").replace("_", " ").strip()
    title_prefix = f"SPPU {subject_name}"
    if pattern:
        title_prefix = f"{title_prefix} {pattern.title()}"
    return {
        "title": f"{title_prefix} Question Papers",
        "description": (
            f"Download and view {subject_name} question papers for {branch_name} students of "
            "Savitribai Phule Pune University."
        ),
        "keywords": f"{subject_name}, {branch_name}, SPPU question papers, PYQ, {pattern}".strip(", "),
        "subject_name": subject_name,
        "canonical_path": route_path,
    }


def _normalize_subject(pattern_key, subject_key, subject, subjects_manifest):
    subject = _apply_subject_exceptions(subject)
    route_prefix = HONORS_KEY if pattern_key == HONORS_KEY else str(pattern_key)
    route_path = f"/{route_prefix}/{subject_key}"
    base_url = _provider_base(subjects_manifest)
    papers = []

    for paper in subject.get("papers") or []:
        if not isinstance(paper, dict):
            continue
        pdf_url = _paper_url(base_url, paper.get("canonicalPath"))
        if not pdf_url:
            continue
        filename = os.path.basename(urlparse(pdf_url).path)
        papers.append({
            "pdf_id": str(paper.get("pdfId") or os.path.splitext(filename)[0]).strip(),
            "pdf_url": pdf_url,
            "filename": filename,
            "paper_label": _paper_label(paper),
            "exam_type": str(paper.get("exam") or "unknown").lower(),
            "metadata": {},
            "questions": [],
            "question_count": 0,
            "has_structured_content": False,
            "canonical_path": paper.get("canonicalPath", ""),
        })

    subject_name = subject.get("fullName") or _title_case_identifier(subject_key)
    branch_overrides = _branch_overrides(subject.get("branchKey"))
    branch_name = branch_overrides.get("branchName") or subject.get("branchName") or _title_case_identifier(subject.get("branchKey"))
    branch_code = branch_overrides.get("branchCode") or subject.get("branchCode") or ""
    year_name = subject.get("yearName") or ""
    semester_no = subject.get("semesterNo")
    subject_obj = {
        "subject_name": subject_name,
        "fullName": subject_name,
        "seo_data": _seo_for_subject(subject, route_path),
        "papers": papers,
        "pdf_links": [paper["pdf_url"] for paper in papers],
        "branch_name": branch_name,
        "branch_code": branch_code,
        "branch_type": subject.get("branchType", ""),
        "pattern_key": pattern_key,
        "pattern_year": "" if pattern_key == HONORS_KEY else str(pattern_key),
        "year_key": subject.get("yearKey", ""),
        "year_name": year_name,
        "year_full_name": subject.get("yearFullName", ""),
        "semester": semester_no,
        "semester_key": f"sem-{semester_no}" if semester_no else "",
        "subject_link": subject_key,
        "route_path": route_path,
        "public_url": route_path,
        "shortCode": subject.get("shortCode", ""),
        "normalizedName": subject.get("normalizedName", ""),
    }
    return subject_obj


def _load_subject_manifest(pattern_key):
    name = f"{pattern_key}_subjects.json"
    if pattern_key == HONORS_KEY:
        name = "honors_subjects.json"
    data = _safe_load_json(_manifest_path(name)) or {}
    subjects_index = {}
    for subject_key, subject in (data.get("subjects") or {}).items():
        if isinstance(subject, dict):
            subjects_index[subject_key] = _normalize_subject(pattern_key, subject_key, subject, data)
    return data, subjects_index


def _subject_card(pattern_key, subject):
    subject = _apply_subject_exceptions(subject)
    subject_key = subject.get("subjectKey")
    route_prefix = HONORS_KEY if pattern_key == HONORS_KEY else str(pattern_key)
    code = str(subject.get("shortCode") or "")
    return {
        "type": "subject",
        "id": subject_key,
        "code": _normalize_elective_code(code) if _is_elective(subject) else code.upper(),
        "name": subject.get("fullName") or _title_case_identifier(subject_key),
        "url": f"/{route_prefix}/{subject_key}",
        "semester_no": subject.get("semesterNo"),
    }


def _nav_card(level_id, code, name, target_id):
    return {
        "type": "nav",
        "id": level_id,
        "code": str(code or "").upper(),
        "name": name,
        "target_id": target_id,
    }


def _add_subject_level(levels, pattern_key, level_id, heading, subjects, semester_included, breadcrumbs):
    grouped = []
    subjects = sorted((_apply_subject_exceptions(subject) for subject in subjects), key=_subject_sort_key)
    if semester_included:
        by_semester = {}
        for subject in subjects:
            sem_no = subject.get("semesterNo")
            by_semester.setdefault(sem_no, []).append(_subject_card(pattern_key, subject))
        for sem_no in sorted(by_semester, key=lambda value: (value is None, int(value) if str(value).isdigit() else 999, str(value or ""))):
            label = f"Semester {sem_no}" if sem_no else "Subjects"
            grouped.append({"heading": label, "items": by_semester[sem_no]})
    else:
        grouped.append({"heading": "", "items": [_subject_card(pattern_key, subject) for subject in subjects]})

    levels.append({
        "id": level_id,
        "heading": heading,
        "groups": grouped,
        "breadcrumbs": breadcrumbs,
    })


def _build_pattern_navigation(pattern_year, include_honors=False):
    data = _safe_load_json(_manifest_path(f"{pattern_year}.json")) or {}
    hierarchy = data.get("hierarchy") or {}
    nav_items = []
    levels = []

    for raw_branch in (hierarchy.get("standard") or {}).get("branches") or []:
        branch = _apply_branch_exceptions(raw_branch)
        branch_id = f"{pattern_year}-branch-{branch.get('branchKey')}"
        year_items = []
        years_list = branch.get("years") or []
        years_list = sorted(years_list, key=lambda y: {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}.get(y.get("yearFullName") or y.get("yearName"), 99))
        for year in years_list:
            year_id = f"{branch_id}-year-{year.get('yearKey')}"
            year_items.append(_nav_card(
                year_id,
                year.get("yearName"),
                year.get("yearFullName") or year.get("yearName"),
                year_id,
            ))
            _add_subject_level(
                levels,
                pattern_year,
                year_id,
                f"{branch.get('branchName')} - {year.get('yearName')}",
                year.get("subjects") or [],
                bool(year.get("semesterIncluded")),
                [
                    {"name": "Branches", "target_id": "root"},
                    {"name": branch.get("branchCode", "").upper(), "target_id": branch_id},
                    {"name": year.get("yearName", "")},
                ],
            )
        levels.append({
            "id": branch_id,
            "heading": f"{branch.get('branchName')} - Select Year",
            "groups": [{"heading": "", "items": year_items}],
            "breadcrumbs": [
                {"name": "Branches", "target_id": "root"},
                {"name": branch.get("branchCode", "").upper()},
            ],
        })
        nav_items.append(_nav_card(branch_id, branch.get("branchCode"), branch.get("branchName"), branch_id))

    first_year = hierarchy.get("firstYear") or {}
    if first_year.get("subjects"):
        fy_id = f"{pattern_year}-first-year"
        nav_items.append(_nav_card(fy_id, first_year.get("branchCode") or "FY", first_year.get("branchName") or "First Year", fy_id))
        _add_subject_level(
            levels,
            pattern_year,
            fy_id,
            first_year.get("branchName") or "First Year",
            first_year.get("subjects") or [],
            bool(first_year.get("semesterIncluded")),
            [{"name": "Branches", "target_id": "root"}, {"name": first_year.get("branchName") or "First Year"}],
        )

    mba = hierarchy.get("mba") or {}
    if mba.get("semesters"):
        mba_id = f"{pattern_year}-mba"
        sem_items = []
        for sem in mba.get("semesters") or []:
            sem_id = f"{mba_id}-sem-{sem.get('semesterNo') or sem.get('semesterKey')}"
            sem_items.append(_nav_card(sem_id, f"Sem {sem.get('semesterNo', '')}".strip(), sem.get("semesterName") or "Semester", sem_id))
            _add_subject_level(
                levels,
                pattern_year,
                sem_id,
                sem.get("semesterName") or f"MBA Semester {sem.get('semesterNo', '')}".strip(),
                sem.get("subjects") or [],
                False,
                [{"name": "Branches", "target_id": "root"}, {"name": "MBA", "target_id": mba_id}, {"name": sem.get("semesterName") or "Semester"}],
            )
        levels.append({
            "id": mba_id,
            "heading": "MBA - Select Semester",
            "groups": [{"heading": "", "items": sem_items}],
            "breadcrumbs": [{"name": "Branches", "target_id": "root"}, {"name": "MBA"}],
        })
        nav_items.append(_nav_card(mba_id, mba.get("branchCode") or "MBA", mba.get("branchName") or "MBA", mba_id))

    if include_honors:
        honors = _safe_load_json(_manifest_path("honors.json")) or {}
        honors_course = (honors.get("hierarchy") or {}).get("honorsCourse") or {}
        if honors_course.get("years"):
            honors_id = "honors-course"
            year_items = []
            years_list = honors_course.get("years") or []
            years_list = sorted(years_list, key=lambda y: {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}.get(y.get("yearFullName") or y.get("yearName"), 99))
            for year in years_list:
                year_id = f"{honors_id}-year-{year.get('yearKey')}"
                year_items.append(_nav_card(year_id, year.get("yearName"), year.get("yearFullName") or year.get("yearName"), year_id))
                _add_subject_level(
                    levels,
                    HONORS_KEY,
                    year_id,
                    f"{honors_course.get('branchName', 'Honors Course')} - {year.get('yearName')}",
                    year.get("subjects") or [],
                    False,
                    [{"name": "Branches", "target_id": "root"}, {"name": "HC", "target_id": honors_id}, {"name": year.get("yearName", "")}],
                )
            levels.append({
                "id": honors_id,
                "heading": f"{honors_course.get('branchName', 'Honors Course')} - Select Year",
                "groups": [{"heading": "", "items": year_items}],
                "breadcrumbs": [{"name": "Branches", "target_id": "root"}, {"name": "HC"}],
            })
            nav_items.append(_nav_card(honors_id, honors_course.get("branchCode") or "HC", honors_course.get("branchName") or "Honors Course", honors_id))

    return {
        "pattern_year": pattern_year,
        "pattern_label": f"{pattern_year} Pattern",
        "root_heading": f"Select Branch - {pattern_year} Pattern",
        "nav_items": nav_items,
        "levels": levels,
        "available_patterns": _available_pattern_years(),
        "include_honors": include_honors,
    }


@lru_cache(maxsize=1)
def load_question_papers():
    patterns = {}
    subjects_by_route = {}
    subjects_by_legacy_key = {}
    question_papers_list = []

    for pattern_year in _available_pattern_years():
        _subjects_manifest, subject_index = _load_subject_manifest(pattern_year)
        patterns[pattern_year] = {
            "navigation": _build_pattern_navigation(pattern_year, include_honors=(pattern_year == DEFAULT_PATTERN_YEAR)),
            "subjects_index": subject_index,
        }
        for subject_key, subject in subject_index.items():
            subjects_by_route[(pattern_year, subject_key)] = subject
            if subject_key not in subjects_by_legacy_key:
                subjects_by_legacy_key[subject_key] = subject
            question_papers_list.append(_search_entry(subject))

    _honors_manifest, honors_index = _load_subject_manifest(HONORS_KEY)
    patterns[HONORS_KEY] = {
        "navigation": None,
        "subjects_index": honors_index,
    }
    for subject_key, subject in honors_index.items():
        subjects_by_route[(HONORS_KEY, subject_key)] = subject
        if subject_key not in subjects_by_legacy_key:
            subjects_by_legacy_key[subject_key] = subject
        question_papers_list.append(_search_entry(subject))

    return {
        "patterns": patterns,
        "available_patterns": _available_pattern_years(),
        "question_papers_list": question_papers_list,
        "subjects_index": subjects_by_legacy_key,
        "subjects_by_route": subjects_by_route,
    }


def _search_entry(subject):
    subject_name = subject.get("subject_name", "")
    sem_no = subject.get("semester")
    year_label = " ".join(part for part in [subject.get("year_name"), subject.get("year_full_name")] if part).strip()
    return {
        "type": "QUESTION_PAPER",
        "subject_name": subject_name,
        "subject_link": subject.get("route_path", "").lstrip("/"),
        "branch_name": subject.get("branch_name", ""),
        "branch_code": subject.get("branch_code", ""),
        "sem_no": sem_no,
        "year_label": year_label,
        "pattern_year": subject.get("pattern_year", ""),
        "public_url": subject.get("route_path", ""),
        "repo_path": subject.get("route_path", "").lstrip("/"),
        "keywords": (subject.get("seo_data") or {}).get("keywords", ""),
        "abbreviation": _abbreviation(subject_name),
    }


def load_pattern_navigation(pattern_year):
    data = load_question_papers()
    pattern = data["patterns"].get(str(pattern_year))
    return pattern["navigation"] if pattern else None


def get_subject(pattern_key, subject_key):
    return load_question_papers()["subjects_by_route"].get((str(pattern_key), subject_key))


def get_legacy_redirect(subject_key):
    data = load_question_papers()
    for pattern_key in REDIRECT_PATTERN_ORDER:
        subject = data["subjects_by_route"].get((pattern_key, subject_key))
        if subject:
            return subject.get("route_path")
    return None


def load_sitemap_entries():
    return load_question_papers()["question_papers_list"]
