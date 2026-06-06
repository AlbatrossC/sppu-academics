"""Review and apply normalized PDF filenames with PyMuPDF/PaddleOCR/Groq metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from common import tracking


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INCOMING_DIR = PROJECT_ROOT / "incoming"
PAPERS_DIR = PROJECT_ROOT / "papers"
NEEDS_REVIEW_DIR = PROJECT_ROOT / "needs_review"
CHANGELOG_PATH = PROJECT_ROOT / "changelog" / "rename.md"
CHANGELOG_JSON_PATH = PROJECT_ROOT / "changelog" / "rename.json"
FOLDER_NAMES_PATH = PROJECT_ROOT / "mapping" / "folder_names.yml"
BEGIN_RENAME = "<!-- RENAME_FILES_BEGIN -->"
END_RENAME = "<!-- RENAME_FILES_END -->"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_OCR_CONFIDENCE = 0.85
DEFAULT_OCR_RELAXED_CONFIDENCE = 0.55
DEFAULT_OCR_CROP_RATIO = 0.45
DEFAULT_OCR_CROP_RATIOS = (0.45, 0.65, 1.0)
DEFAULT_OCR_WORKERS = 1
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
VALID_EXAM_TYPES = {"insem", "endsem", "other"}
FILENAME_RE = re.compile(r"^(insem|endsem|other)_[a-z]{3}(?:_[a-z]{3})?_\d{4}_[A-Za-z0-9_]+_[A-Za-z0-9_]+_[A-Za-z0-9_]+\.pdf$")
ANSI_RESET = "\033[0m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_DIM = "\033[2m"


class RenameError(RuntimeError):
    """Raised when rename review/apply cannot continue."""


class RetryLaterError(RenameError):
    """Raised when a provider failed temporarily and the PDF should be retried."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RenameError(f"Missing {path.relative_to(PROJECT_ROOT)}. Run: python3 tools/rename_folders.py --create")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_code_lookup() -> dict[str, dict[str, str]]:
    data = read_yaml(FOLDER_NAMES_PATH)
    lookup: dict[str, dict[str, str]] = {}
    for original, entry in (data.get("name_registry") or {}).items():
        normalized = str(entry.get("normalized", "")).strip()
        code = str(entry.get("code", "")).strip()
        if normalized and code and normalized not in lookup:
            lookup[normalized] = {
                "original": str(original),
                "normalized": normalized,
                "code": code,
                "id": str(entry.get("id", "")),
            }
    return lookup


def display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def path_in_scope(path: Path, scope: Path) -> bool:
    try:
        path.resolve().relative_to(scope.resolve())
        return True
    except ValueError:
        return False


def workflow_relative(path: Path) -> tuple[str, Path]:
    resolved = path.resolve()
    for root_name, root in (("incoming", INCOMING_DIR), ("needs_review", NEEDS_REVIEW_DIR)):
        try:
            return root_name, resolved.relative_to(root.resolve())
        except ValueError:
            pass
    raise RenameError(f"Path is not under incoming/ or needs_review/: {path}")


def incoming_relative(path: Path) -> Path:
    root_name, rel = workflow_relative(path)
    if root_name != "incoming":
        raise RenameError(f"Path is not under incoming/: {path}")
    return rel


def code_for_segment(lookup: dict[str, dict[str, str]], segment: str, label: str) -> str:
    entry = lookup.get(segment)
    if not entry:
        raise RenameError(f"No code found in mapping/folder_names.yml for {label}: {segment}")
    return entry["code"]


def derive_context(pdf_path: Path, lookup: dict[str, dict[str, str]]) -> dict[str, str]:
    _root_name, rel = workflow_relative(pdf_path)
    parts = rel.parts
    if len(parts) < 2:
        raise RenameError(f"Expected a PDF below a subject folder: {rel.as_posix()}")

    branch = parts[0]
    if branch == "first-year":
        if len(parts) < 4:
            raise RenameError(f"Expected First Year path: incoming/first-year/<pattern>/<subject>/<file>, got {rel.as_posix()}")
        pattern = parts[1]
        subject = parts[2]
    elif branch == "m-b-a":
        if len(parts) < 5:
            raise RenameError(f"Expected MBA path: incoming/m-b-a/<semester>/<pattern>/<subject>/<file>, got {rel.as_posix()}")
        pattern = parts[2]
        subject = parts[3]
    elif branch == "honors-course":
        if len(parts) < 4:
            raise RenameError(f"Expected Honors path: incoming/honors-course/<year>/<subject>/<file>, got {rel.as_posix()}")
        pattern = parts[1]
        subject = parts[2]
    else:
        if len(parts) < 5:
            raise RenameError(f"Expected standard path: incoming/<branch>/<year>/<pattern>/<subject>/<file>, got {rel.as_posix()}")
        pattern = parts[2]
        subject = parts[3]

    return {
        "relative_dir": Path(*parts[:-1]).as_posix(),
        "branch": branch,
        "pattern": pattern,
        "subject": subject,
        "branch_code": code_for_segment(lookup, branch, "branch"),
        "pattern_code": code_for_segment(lookup, pattern, "pattern/year"),
        "subject_code": code_for_segment(lookup, subject, "subject"),
    }


def extract_first_page_text(path: Path) -> str:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RenameError("PyMuPDF is not installed. Install dependencies with: python3 -m pip install -r requirements.txt") from exc

    try:
        with fitz.open(path) as document:
            if document.page_count < 1:
                raise RenameError("PDF has no pages.")
            text = document.load_page(0).get_text("text")
    except Exception as exc:  # PyMuPDF raises several document-specific exceptions.
        raise RenameError(f"Could not extract first page text: {exc}") from exc
    return re.sub(r"\s+", " ", text).strip()[:8000]


def extract_first_page_header_text(path: Path) -> str:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RenameError("PyMuPDF is not installed. Install dependencies with: python3 -m pip install -r requirements.txt") from exc

    try:
        with fitz.open(path) as document:
            if document.page_count < 1:
                raise RenameError("PDF has no pages.")
            page = document.load_page(0)
            rect = page.rect
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + (rect.height * DEFAULT_OCR_CROP_RATIO))
            text = page.get_text("text", clip=clip)
            if not text.strip():
                text = page.get_text("text")
    except Exception as exc:  # PyMuPDF raises several document-specific exceptions.
        raise RenameError(f"Could not extract first page header text: {exc}") from exc

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact = " ".join(lines[:45])
    return re.sub(r"\s+", " ", compact).strip()[:3500]


def render_first_page_header_image(path: Path, crop_ratio: float = DEFAULT_OCR_CROP_RATIO) -> Path:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RenameError("PyMuPDF is not installed. Install dependencies with: python3 -m pip install -r requirements.txt") from exc

    import tempfile

    try:
        with fitz.open(path) as document:
            if document.page_count < 1:
                raise RenameError("PDF has no pages.")
            page = document.load_page(0)
            rect = page.rect
            crop_ratio = min(max(crop_ratio, 0.10), 1.0)
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + (rect.height * crop_ratio))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
            temp = tempfile.NamedTemporaryFile(prefix="rename_paddleocr_", suffix=".png", delete=False)
            temp_path = Path(temp.name)
            temp.close()
            pixmap.save(temp_path)
            return temp_path
    except Exception as exc:
        raise RenameError(f"Could not render first page header image: {exc}") from exc


class PaddleOCRRunner:
    def __init__(
        self,
        confidence_threshold: float = DEFAULT_OCR_CONFIDENCE,
        crop_ratios: tuple[float, ...] = DEFAULT_OCR_CROP_RATIOS,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.crop_ratios = crop_ratios
        self._ocr: Any | None = None

    def _instance(self) -> Any:
        if self._ocr is not None:
            return self._ocr
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RenameError("PaddleOCR is not installed. Install it in the GPU environment before running review.") from exc
        try:
            self._ocr = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
        except Exception:
            self._ocr = PaddleOCR(lang="en")
        return self._ocr

    def extract_lines(self, pdf_path: Path, crop_ratio: float) -> list[tuple[str, float | None]]:
        image_path = render_first_page_header_image(pdf_path, crop_ratio)
        try:
            ocr = self._instance()
            if hasattr(ocr, "ocr"):
                try:
                    result = ocr.ocr(str(image_path), cls=False)
                except TypeError:
                    result = ocr.ocr(str(image_path))
            elif hasattr(ocr, "predict"):
                result = ocr.predict(str(image_path))
            else:
                raise RenameError("Unsupported PaddleOCR object: missing ocr() or predict().")
            return flatten_ocr_lines(result)
        finally:
            try:
                image_path.unlink()
            except OSError:
                pass

    def extract_marks(self, pdf_path: Path) -> tuple[int | None, float | None, str]:
        best_text = ""
        for crop_ratio in self.crop_ratios:
            lines = self.extract_lines(pdf_path, crop_ratio)
            joined = " ".join(text for text, _score in lines)
            if len(joined) > len(best_text):
                best_text = joined
            marks = extract_marks_from_ocr_lines(lines, self.confidence_threshold)
            if marks is not None:
                return marks, crop_ratio, re.sub(r"\s+", " ", joined).strip()[:3500]
        return None, None, re.sub(r"\s+", " ", best_text).strip()[:3500]


def flatten_ocr_lines(result: Any) -> list[tuple[str, float | None]]:
    lines: list[tuple[str, float | None]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "rec_texts" in value:
                scores = value.get("rec_scores") or []
                for index, text in enumerate(value.get("rec_texts") or []):
                    score = scores[index] if index < len(scores) else None
                    lines.append((str(text), float(score) if score is not None else None))
                return
            if "text" in value:
                score = value.get("score")
                lines.append((str(value["text"]), float(score) if score is not None else None))
                return
            for child in value.values():
                visit(child)
            return
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and isinstance(value[1], (list, tuple)) and value[1]:
                maybe_text = value[1][0]
                maybe_score = value[1][1] if len(value[1]) > 1 else None
                if isinstance(maybe_text, str):
                    lines.append((maybe_text, float(maybe_score) if maybe_score is not None else None))
                    return
            for child in value:
                visit(child)

    visit(result)
    deduped: list[tuple[str, float | None]] = []
    seen: set[str] = set()
    for text, score in lines:
        clean = re.sub(r"\s+", " ", text).strip()
        if clean and clean not in seen:
            deduped.append((clean, score))
            seen.add(clean)
    return deduped


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


def groq_client() -> Any:
    keys = groq_api_keys()
    try:
        from groq import Groq  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RenameError("groq is not installed. Install dependencies with: python3 -m pip install -r requirements.txt") from exc
    return Groq(api_key=keys[0])


def groq_api_keys() -> list[str]:
    load_dotenv_if_available()
    raw_keys: list[str] = []
    raw_keys.extend(key.strip() for key in os.environ.get("GROQ_API_KEYS", "").split(",") if key.strip())
    raw_keys.append(os.environ.get("GROQ_API_KEY", "").strip())
    for index in range(2, 21):
        raw_keys.append(os.environ.get(f"GROQ_API_KEY_{index}", "").strip())
    raw_keys.append(os.environ.get("GROQ_SECONDARY_API_KEY", "").strip())
    raw_keys = [key for key in raw_keys if key]
    keys = list(dict.fromkeys(raw_keys))
    if not keys:
        raise RenameError("GROQ_API_KEY is missing. Add GROQ_API_KEY, GROQ_API_KEY_2, or GROQ_API_KEYS to your environment or .env file.")
    return keys


def groq_clients() -> list[Any]:
    keys = groq_api_keys()
    try:
        from groq import Groq  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RenameError("groq is not installed. Install dependencies with: python3 -m pip install -r requirements.txt") from exc
    return [Groq(api_key=key) for key in keys]


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def metadata_prompt(pdf_path: Path, header_text: str) -> str:
    return (
        f"PDF filename: {pdf_path.name}\n"
        "Extract only metadata needed to rename this university exam PDF.\n"
        "Return strict JSON with exactly these keys: marks, month_code, year, extracted, reason.\n"
        "marks must be the total/max marks visible on the first page header, as an integer, or null.\n"
        "month_code and year should come from the filename when present. "
        "month_code must be lowercase normalized month text such as feb, may_jun, nov_dec, aug. "
        "year must be a four digit exam year, or null.\n"
        "extracted must be true only when marks, month_code, and year are all extracted. "
        "Do not return exam_type.\n"
        "First page header/top-half text:\n"
        f"{header_text}"
    )


def normalize_marks(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"}))
    match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", text)
    if not match:
        return None
    marks = int(match.group(1))
    return marks if 1 <= marks <= 100 else None


def text_quality_is_usable(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) < 40:
        return False
    alpha = sum(1 for char in compact if char.isalpha())
    printable = sum(1 for char in compact if char.isprintable())
    return printable >= max(1, int(len(compact) * 0.85)) and alpha >= max(10, int(len(compact) * 0.20))


MARKS_DIRECT_PATTERNS = [
    re.compile(r"(?i)\bmax(?:imum)?\.?\s*marks?\s*[:\-\]\[]?\s*([0-9OoIl]{1,3})\b"),
    re.compile(r"(?i)\btotal\s*marks?\s*[:\-\]\[]?\s*([0-9OoIl]{1,3})\b"),
    re.compile(r"(?i)\[\s*max(?:imum)?\.?\s*marks?\s*[:\-\]\[]?\s*([0-9OoIl]{1,3})\b"),
]


def marks_candidates_from_lines(
    lines: list[tuple[str, float | None]],
    require_phrase: bool,
    min_confidence: float | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, (line, score) in enumerate(lines):
        window_parts = []
        window_scores = []
        for neighbor in range(max(0, index - 1), min(len(lines), index + 2)):
            window_parts.append(lines[neighbor][0])
            if lines[neighbor][1] is not None:
                window_scores.append(float(lines[neighbor][1]))
        window = re.sub(r"\s+", " ", " ".join(window_parts)).strip()
        matches = [match for pattern in MARKS_DIRECT_PATTERNS for match in pattern.finditer(window)]
        if require_phrase and not matches:
            continue
        for match in matches:
            marks = normalize_marks(match.group(1))
            if marks is None:
                continue
            confidence = max(window_scores) if window_scores else (score if score is not None else 1.0)
            if min_confidence is not None and confidence < min_confidence:
                continue
            candidates.append(
                {
                    "marks": marks,
                    "confidence": confidence,
                    "distance": match.start(1) - match.start(0),
                    "line_index": index,
                }
            )
    candidates.sort(key=lambda item: (item["distance"], -float(item["confidence"]), item["line_index"]))
    return candidates


def extract_marks_from_text(header_text: str) -> int | None:
    if not text_quality_is_usable(header_text):
        return None
    lines = [(line.strip(), 1.0) for line in re.split(r"[\r\n]+", header_text) if line.strip()]
    candidates = marks_candidates_from_lines(lines, require_phrase=True)
    return int(candidates[0]["marks"]) if candidates else None


def extract_marks_from_ocr_lines(lines: list[tuple[str, float | None]], confidence_threshold: float) -> int | None:
    candidates = marks_candidates_from_lines(lines, require_phrase=True, min_confidence=confidence_threshold)
    if not candidates:
        candidates = marks_candidates_from_lines(lines, require_phrase=True, min_confidence=DEFAULT_OCR_RELAXED_CONFIDENCE)
    return int(candidates[0]["marks"]) if candidates else None


def provider_result_is_usable(result: dict[str, Any], filename: str) -> bool:
    if result.get("extracted") is False:
        return False
    marks = normalize_marks(result.get("marks"))
    filename_month = normalize_month_code(filename)
    filename_year = normalize_year(filename)
    month_code = filename_month or normalize_month_code(result.get("month_code"), result.get("year"))
    year = filename_year or normalize_year(result.get("year")) or normalize_year(result.get("month_code"))
    return marks is not None and bool(month_code) and bool(year)


def is_retryable_provider_error(exc: Exception) -> bool:
    text = str(exc).lower()
    retry_terms = [
        "rate limit",
        "429",
        "too many requests",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "temporary",
        "connection",
        "network",
        "503",
        "502",
        "500",
    ]
    return any(term in text for term in retry_terms)


def ask_groq(client: Any, pdf_path: Path, relative_path: str, first_page_text: str) -> dict[str, Any]:
    model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    messages = [
        {
            "role": "system",
            "content": (
                "You extract only exam metadata for renaming a university exam PDF. "
                "Return only strict JSON with keys: marks, month_code, year, extracted, reason. "
                "marks must be the total/max marks visible on the first page header, or null if unclear. "
                "month_code and year should come from the filename when present, not from the paper pattern, subject code, course code, or body text. "
                "month_code must use short lowercase month names, examples: feb, may_jun, nov_dec, aug. "
                "year must be the four digit exam year, or null if unavailable. "
                "extracted must be true only when marks, month_code, and year were extracted. "
                "Do not return exam_type. "
                "reason should briefly explain the marks/date extraction only."
            ),
        },
        {"role": "user", "content": metadata_prompt(pdf_path, first_page_text)},
    ]
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    parsed = parse_json_object(content)
    return {
        "marks": parsed.get("marks"),
        "month_code": parsed.get("month_code"),
        "year": parsed.get("year"),
        "extracted": bool(parsed.get("extracted")),
        "reason": str(parsed.get("reason", "")).strip(),
        "model": model,
        "provider": "groq",
    }


def ask_groq_with_fallback(clients: list[Any], preferred_index: int, pdf_path: Path, relative_path: str, first_page_text: str) -> dict[str, Any]:
    if not clients:
        raise RetryLaterError("No Groq clients are configured.")
    errors: list[str] = []
    retryable = False
    for offset in range(len(clients)):
        client_index = (preferred_index + offset) % len(clients)
        try:
            result = ask_groq(clients[client_index], pdf_path, relative_path, first_page_text)
            result["groq_key_index"] = client_index + 1
            return result
        except Exception as exc:
            retryable = retryable or is_retryable_provider_error(exc)
            errors.append(f"key {client_index + 1}: {exc}")
    message = "Groq request failed for every configured key: " + " | ".join(errors)
    if retryable:
        raise RetryLaterError(message)
    raise RenameError(message)


def exam_type_from_marks(marks: Any) -> str:
    try:
        numeric = int(str(marks).strip())
    except (TypeError, ValueError):
        return "other"
    if numeric == 30:
        return "insem"
    if numeric == 70:
        return "endsem"
    return "other"


def normalize_month_code(value: Any, year: Any = None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    raw = re.sub(r"(?<!\d)\d{4}(?!\d)", " ", raw)
    tokens = [token for token in re.split(r"[^a-z]+", raw) if token]
    months = [MONTH_ALIASES[token] for token in tokens if token in MONTH_ALIASES]
    if not months:
        return ""
    if len(months) > 2:
        months = months[:2]
    return "_".join(months)


def normalize_year(value: Any) -> str:
    match = re.search(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", str(value or ""))
    return match.group(1) if match else ""


def month_year_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    year = normalize_year(stem)
    month = normalize_month_code(stem)
    return f"{month}_{year}" if month and year else ""


def final_filename(exam_type: str, month_code: str, year: str, context: dict[str, str]) -> str:
    return (
        f"{exam_type}_{month_code}_{year}_"
        f"{context['branch_code']}_{context['subject_code']}_{context['pattern_code']}.pdf"
    )


def validate_filename(filename: str) -> bool:
    return bool(FILENAME_RE.fullmatch(filename))


def terminal_color(text: str, color: str) -> str:
    if os.environ.get("NO_COLOR"):
        return text
    if not sys.stdout.isatty() and os.environ.get("FORCE_COLOR") not in {"1", "true", "TRUE"}:
        return text
    return f"{color}{text}{ANSI_RESET}"


def metadata_source_label(entry: dict[str, Any]) -> str:
    source = str(entry.get("metadata_source") or entry.get("action") or "unknown")
    if source == "text":
        return terminal_color("TEXT", ANSI_DIM)
    if source == "paddleocr":
        return terminal_color("PADDLEOCR", ANSI_YELLOW)
    if source == "groq":
        return terminal_color("GROQ", ANSI_BLUE)
    if source == "already_normalized":
        return terminal_color("SKIP", ANSI_DIM)
    if source == "retry":
        return "RETRY"
    if source == "review":
        return "REVIEW"
    return source.upper()


def print_review_result(entry: dict[str, Any]) -> None:
    label = metadata_source_label(entry)
    source = entry.get("source", "")
    if entry.get("action") == "rename":
        target = entry.get("target") or entry.get("filename") or ""
        print(
            f"  {label} {entry.get('status', '')} | {source} -> {target} | "
            f"marks={entry.get('marks', '')} | {entry.get('month_code', '')}_{entry.get('year', '')} | "
            f"source={entry.get('metadata_source', '')}"
        )
        return
    if entry.get("status") == "retry_pending":
        print(f"  {label} later  | {source} | {entry.get('reason', '')}")
        return
    if entry.get("action") == "review":
        print(f"  {label} planned | {source} -> {entry.get('needs_review_target', '')} | {entry.get('reason', '')}")
        return
    print(f"  {label}        | {source}")


def should_stop_after_retry(entry: dict[str, Any]) -> bool:
    if entry.get("status") != "retry_pending":
        return False
    reason = str(entry.get("reason") or "").lower()
    return "groq" in reason and ("rate limit" in reason or "429" in reason or "tokens per day" in reason)


def retry_entry(base: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **base,
        "status": "retry_pending",
        "action": "retry",
        "target": "",
        "expected_path": "",
        "needs_review_target": "",
        "exam_type": "retry",
        "marks": None,
        "month_code": "",
        "year": "",
        "filename": base.get("original_filename", ""),
        "reason": reason,
        "metadata_source": "retry",
    }


def review_entry(base: dict[str, Any], rel: Path, reason: str) -> dict[str, Any]:
    review_target = NEEDS_REVIEW_DIR / rel
    if base.get("file_id"):
        tracking.record_review_failure(
            base["file_id"],
            review_category=review_category(reason),
            review_reason=reason,
        )
    return {
        **base,
        "action": "review",
        "target": "",
        "expected_path": "",
        "needs_review_target": display_path(review_target),
        "exam_type": "needs_review",
        "marks": None,
        "month_code": "",
        "year": "",
        "filename": base.get("original_filename", ""),
        "reason": reason,
        "metadata_source": "review",
    }


def rename_entry_from_metadata(
    base: dict[str, Any],
    root_name: str,
    context: dict[str, str],
    pdf_path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    marks = normalize_marks(metadata.get("marks"))
    if marks is None:
        raise RenameError("Metadata did not include usable marks.")
    exam_type = exam_type_from_marks(marks)
    filename_month = normalize_month_code(pdf_path.name)
    filename_year = normalize_year(pdf_path.name)
    month_code = filename_month or normalize_month_code(metadata.get("month_code"), metadata.get("year"))
    year = (
        filename_year
        or normalize_year(metadata.get("year"))
        or normalize_year(metadata.get("month_code"))
    )
    if not month_code or not year:
        raise RenameError("Metadata did not include a usable month_code and year.")

    filename = final_filename(exam_type, month_code, year, context)
    if not validate_filename(filename):
        raise RenameError(f"Final filename did not pass validation: {filename}")

    working_root = INCOMING_DIR if root_name == "incoming" else NEEDS_REVIEW_DIR
    target = working_root / context["relative_dir"] / filename
    expected_target = PAPERS_DIR / context["relative_dir"] / filename
    source_name = str(metadata.get("provider") or "metadata")
    date_source = "filename" if filename_month and filename_year else source_name
    return {
        **base,
        **context,
        "action": "rename",
        "target": display_path(target),
        "expected_path": display_path(expected_target),
        "needs_review_target": "",
        "exam_type": exam_type,
        "marks": marks,
        "month_code": month_code,
        "year": year,
        "filename": filename,
        "reason": f"marks={marks}; date_from={date_source}; {metadata.get('reason', '')}",
        "metadata_source": source_name,
        "groq_model": metadata.get("model", "") if source_name == "groq" else "",
        "groq_key_index": metadata.get("groq_key_index", ""),
    }


def load_groq_clients_for_fallback() -> list[Any]:
    try:
        return groq_clients()
    except Exception as exc:
        raise RetryLaterError(f"Groq fallback is unavailable: {exc}") from exc


def local_metadata(marks: int, pdf_path: Path, provider: str, reason: str) -> dict[str, Any]:
    return {
        "marks": marks,
        "month_code": normalize_month_code(pdf_path.name),
        "year": normalize_year(pdf_path.name),
        "extracted": bool(normalize_month_code(pdf_path.name) and normalize_year(pdf_path.name)),
        "reason": reason,
        "provider": provider,
    }


def make_review_entry(
    pdf_path: Path,
    lookup: dict[str, dict[str, str]],
    clients: list[Any] | None = None,
    preferred_client_index: int = 0,
    ocr_runner: PaddleOCRRunner | None = None,
) -> dict[str, Any]:
    root_name, rel = workflow_relative(pdf_path)
    source = f"{root_name}/{rel.as_posix()}"
    tracked = tracking.find_by_current_path(source)
    base = {
        "status": "pending",
        "source": source,
        "original_filename": pdf_path.name,
        "file_id": tracked.get("file_id", "") if tracked else "",
    }
    try:
        context = derive_context(pdf_path, lookup)
        header_text = extract_first_page_header_text(pdf_path)
        filename_month = normalize_month_code(pdf_path.name)
        filename_year = normalize_year(pdf_path.name)

        text_marks = extract_marks_from_text(header_text)
        if text_marks is not None:
            text_data = local_metadata(text_marks, pdf_path, "text", "marks from PyMuPDF header text")
            if provider_result_is_usable(text_data, pdf_path.name):
                return rename_entry_from_metadata(base, root_name, context, pdf_path, text_data)

        ocr_error = ""
        ocr_text = ""
        if ocr_runner is not None:
            try:
                ocr_marks, ocr_crop_ratio, ocr_text = ocr_runner.extract_marks(pdf_path)
                if ocr_marks is not None:
                    crop_text = f"{int((ocr_crop_ratio or DEFAULT_OCR_CROP_RATIO) * 100)}% first-page crop"
                    ocr_data = local_metadata(ocr_marks, pdf_path, "paddleocr", f"marks from PaddleOCR {crop_text}")
                    if provider_result_is_usable(ocr_data, pdf_path.name):
                        return rename_entry_from_metadata(base, root_name, context, pdf_path, ocr_data)
                crops = ", ".join(f"{int(ratio * 100)}%" for ratio in ocr_runner.crop_ratios)
                ocr_error = f"PaddleOCR did not find direct marks near a marks phrase in first-page crops: {crops}"
            except Exception as exc:
                ocr_error = f"PaddleOCR failed: {exc}"

        groq_clients_for_file = clients if clients is not None else load_groq_clients_for_fallback()
        groq_context_text = ocr_text or header_text
        try:
            groq_data = ask_groq_with_fallback(groq_clients_for_file, preferred_client_index, pdf_path, rel.as_posix(), groq_context_text)
        except RetryLaterError as exc:
            parts = [part for part in [ocr_error, str(exc)] if part]
            return retry_entry(base, "; ".join(parts))
        if not provider_result_is_usable(groq_data, pdf_path.name):
            missing = []
            if text_marks is None:
                missing.append("text marks missing")
            if not filename_month or not filename_year:
                missing.append("filename date incomplete")
            if ocr_error:
                missing.append(ocr_error)
            missing.append(f"Groq did not extract usable metadata: {groq_data.get('reason', '')}")
            return review_entry(base, rel, "; ".join(missing))
        return rename_entry_from_metadata(base, root_name, context, pdf_path, groq_data)
    except RetryLaterError as exc:
        return retry_entry(base, str(exc))
    except Exception as exc:
        return review_entry(base, rel, str(exc))


def send_entry_to_review(entry: dict[str, Any], reason: str) -> None:
    source = resolve_repo_path(entry["source"])
    try:
        review_target = NEEDS_REVIEW_DIR / incoming_relative(source)
    except RenameError:
        review_target = NEEDS_REVIEW_DIR / Path(entry["original_filename"])
    entry["action"] = "review"
    entry["target"] = ""
    entry["needs_review_target"] = display_path(review_target)
    entry["expected_path"] = ""
    entry["exam_type"] = "needs_review"
    entry["reason"] = reason
    if entry.get("file_id"):
        tracking.record_review_failure(
            entry["file_id"],
            review_category=review_category(reason),
            review_reason=reason,
        )


def variant_filename(filename: str, variant: int) -> str:
    path = Path(filename)
    return f"{path.stem}_v{variant}{path.suffix}"


def assign_variant_target(entry: dict[str, Any], variant: int) -> None:
    filename = variant_filename(str(entry["filename"]), variant)
    target = resolve_repo_path(entry["target"]).with_name(filename)
    expected = resolve_repo_path(entry["expected_path"]).with_name(filename)
    entry["filename"] = filename
    entry["target"] = display_path(target)
    entry["expected_path"] = display_path(expected)
    entry["reason"] = f"{entry.get('reason', '')}; duplicate_variant=v{variant}".strip("; ")


def mark_duplicate_or_existing_targets(entries: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for entry in entries:
        if entry.get("action") != "rename" or entry.get("status") != "pending":
            continue
        expected_path = str(entry.get("expected_path", ""))
        target = str(entry.get("target", ""))
        if not target or not expected_path:
            send_entry_to_review(entry, "Missing target path.")
            continue
        if resolve_repo_path(expected_path).exists():
            send_entry_to_review(entry, f"Target already exists: {expected_path}")
            continue
        if expected_path in seen:
            variant = seen[expected_path] + 1
            while True:
                assign_variant_target(entry, variant)
                expected_path = str(entry.get("expected_path", ""))
                if expected_path not in seen and not resolve_repo_path(expected_path).exists():
                    break
                variant += 1
        seen[expected_path] = seen.get(expected_path, 1)


def run_groq_review(
    pdfs: list[Path],
    lookup: dict[str, dict[str, str]],
    clients: list[Any],
    workers: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    total = len(pdfs)
    entries: list[dict[str, Any]] = []
    ocr_runner = PaddleOCRRunner()
    print(f"Using {len(clients)} Groq key(s); review checkpoints sequentially.")
    if workers not in {None, DEFAULT_OCR_WORKERS}:
        print(f"--workers is accepted as an alias; OCR runs with {DEFAULT_OCR_WORKERS} worker for GPU memory safety.")
    for index, pdf_path in enumerate(pdfs):
        entry = make_review_entry(pdf_path, lookup, clients, index % max(1, len(clients)), ocr_runner)
        entries.append(entry)
        print(f"Reviewed PDF {index + 1}/{total}: {display_path(pdf_path)}")
    return entries, DEFAULT_OCR_WORKERS


def read_changelog_if_exists() -> dict[str, Any] | None:
    if not CHANGELOG_JSON_PATH.exists() and not CHANGELOG_PATH.exists():
        return None
    try:
        return read_changelog()
    except Exception:
        return None


def is_already_normalized_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf" and validate_filename(path.name)


def collect_review_pdfs(scope: Path) -> list[Path]:
    pdfs = [scope] if scope.is_file() else sorted(scope.rglob("*.pdf"))
    pdfs = [path for path in pdfs if path_in_scope(path, INCOMING_DIR) or path_in_scope(path, NEEDS_REVIEW_DIR)]
    if scope.is_dir() and path_in_scope(scope, INCOMING_DIR):
        try:
            review_scope = NEEDS_REVIEW_DIR / scope.resolve().relative_to(INCOMING_DIR.resolve())
        except ValueError:
            review_scope = None
        if review_scope and review_scope.exists():
            pdfs.extend(sorted(review_scope.rglob("*.pdf")))
    return sorted(dict.fromkeys(path.resolve() for path in pdfs))


def source_for_pdf(path: Path) -> str:
    root_name, rel = workflow_relative(path)
    return f"{root_name}/{rel.as_posix()}"


def entry_is_completed_for_review(entry: dict[str, Any]) -> bool:
    status = str(entry.get("status") or "")
    action = str(entry.get("action") or "")
    if status == "retry_pending" or action == "retry":
        return False
    return status in {"pending", "applied", "skipped", "review_moved", "missing"} or action in {"rename", "review", "skip"}


def reopen_stale_applied_entry(entry: dict[str, Any]) -> bool:
    if entry.get("status") != "applied" or entry.get("action") != "rename":
        return False
    source = resolve_repo_path(str(entry.get("source") or ""))
    target = resolve_repo_path(str(entry.get("target") or ""))
    if not source.exists() or target.exists():
        return False
    entry["status"] = "pending"
    reason = str(entry.get("reason") or "").strip()
    note = "reopened because source still exists and target is absent"
    entry["reason"] = f"{reason}; {note}" if reason and note not in reason else note
    return True


def already_normalized_entry(pdf_path: Path, lookup: dict[str, dict[str, str]]) -> dict[str, Any]:
    root_name, rel = workflow_relative(pdf_path)
    source = f"{root_name}/{rel.as_posix()}"
    tracked = tracking.find_by_current_path(source)
    base = {
        "status": "skipped",
        "source": source,
        "original_filename": pdf_path.name,
        "file_id": tracked.get("file_id", "") if tracked else "",
    }
    try:
        context = derive_context(pdf_path, lookup)
    except Exception:
        context = {
            "relative_dir": rel.parent.as_posix(),
            "branch": rel.parts[0] if rel.parts else "",
            "pattern": "",
            "subject": rel.parent.name,
            "branch_code": "",
            "pattern_code": "",
            "subject_code": "",
        }
    match = FILENAME_RE.fullmatch(pdf_path.name)
    exam_type = match.group(1) if match else "other"
    return {
        **base,
        **context,
        "action": "skip",
        "target": display_path(pdf_path),
        "expected_path": "",
        "needs_review_target": "",
        "exam_type": exam_type,
        "marks": None,
        "month_code": normalize_month_code(pdf_path.name),
        "year": normalize_year(pdf_path.name),
        "filename": pdf_path.name,
        "reason": "Already matches normalized filename format.",
        "metadata_source": "already_normalized",
    }


def replace_entry(entries: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    source = str(entry.get("source") or "")
    for index, existing in enumerate(entries):
        if existing.get("source") == source:
            entries[index] = entry
            return
    entries.append(entry)


def checkpoint_payload(payload: dict[str, Any]) -> None:
    payload["generated_at"] = utc_now_iso()
    mark_duplicate_or_existing_targets(payload.get("entries") or [])
    write_changelog(payload)


def configured_groq_key_count() -> int | str:
    try:
        return len(groq_api_keys())
    except Exception:
        return ""


def review_pdfs(scope: Path, ocr_workers: int | None = None, fresh: bool = False) -> dict[str, Any]:
    if not scope.exists():
        raise RenameError(f"Path does not exist: {scope}")
    if scope.is_file() and scope.suffix.lower() != ".pdf":
        raise RenameError(f"Expected a directory or PDF file: {scope}")
    lookup = build_code_lookup()
    pdfs = collect_review_pdfs(scope)
    existing_payload = None if fresh else read_changelog_if_exists()
    entries: list[dict[str, Any]] = list((existing_payload or {}).get("entries") or [])
    existing_by_source = {str(entry.get("source") or ""): entry for entry in entries}

    already_normalized: list[Path] = []
    previously_reviewed: list[Path] = []
    reopened_for_apply: list[Path] = []
    retry_pending: list[Path] = []
    to_process: list[Path] = []
    for pdf_path in pdfs:
        source = source_for_pdf(pdf_path)
        existing = existing_by_source.get(source)
        if is_already_normalized_pdf(pdf_path):
            already_normalized.append(pdf_path)
            if not existing or existing.get("metadata_source") != "already_normalized":
                replace_entry(entries, already_normalized_entry(pdf_path, lookup))
            continue
        if existing and reopen_stale_applied_entry(existing):
            reopened_for_apply.append(pdf_path)
            continue
        if existing and entry_is_completed_for_review(existing):
            previously_reviewed.append(pdf_path)
            continue
        if existing and (existing.get("status") == "retry_pending" or existing.get("action") == "retry"):
            retry_pending.append(pdf_path)
        to_process.append(pdf_path)

    worker_count = max(1, ocr_workers or DEFAULT_OCR_WORKERS)
    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "scope": display_path(scope),
        "metadata_pipeline": "pymupdf_text,paddleocr,groq",
        "paddleocr_crop_ratios": list(DEFAULT_OCR_CROP_RATIOS),
        "paddleocr_confidence": DEFAULT_OCR_CONFIDENCE,
        "paddleocr_relaxed_confidence": DEFAULT_OCR_RELAXED_CONFIDENCE,
        "groq_keys": configured_groq_key_count(),
        "workers": worker_count,
        "total_pdfs": len(pdfs),
        "already_normalized": len(already_normalized),
        "previously_reviewed": len(previously_reviewed),
        "reopened_for_apply": len(reopened_for_apply),
        "retry_pending": len(retry_pending),
        "remaining": len(to_process),
        "entries": entries,
    }
    checkpoint_payload(payload)

    print(f"Total PDFs: {len(pdfs)}")
    print(f"Already normalized: {len(already_normalized)}")
    print(f"Previously checkpointed: {len(previously_reviewed)}")
    print(f"Reopened for apply: {len(reopened_for_apply)}")
    print(f"Retry pending: {len(retry_pending)}")
    print(f"Remaining to process: {len(to_process)}")
    print("Pipeline: PyMuPDF header text -> PaddleOCR first-page crops -> Groq fallback.")
    if worker_count != DEFAULT_OCR_WORKERS:
        print(f"OCR worker count requested as {worker_count}; review still checkpoints one PDF at a time.")

    clients: list[Any] | None = None
    ocr_runner = PaddleOCRRunner()
    for index, pdf_path in enumerate(to_process, start=1):
        print(f"WORK {index}/{len(to_process)} | {display_path(pdf_path)}")
        entry = make_review_entry(pdf_path, lookup, clients, 0, ocr_runner)
        if entry.get("metadata_source") == "groq" and clients is None:
            clients = load_groq_clients_for_fallback()
        replace_entry(entries, entry)
        payload["entries"] = entries
        payload["remaining"] = len(to_process) - index
        checkpoint_payload(payload)
        print_review_result(entry)
        if should_stop_after_retry(entry):
            print("Groq fallback is rate-limited. Stopping this run after checkpoint; rerun later to continue remaining PDFs.")
            break
    return payload


def retry_needs_review(scope: Path, workers: int | None = None) -> dict[str, Any] | None:
    if not CHANGELOG_PATH.exists():
        return None
    payload = read_changelog()
    entries = payload.get("entries") or []
    retry_indexes = [
        index
        for index, entry in enumerate(entries)
        if entry.get("status") == "pending"
        and entry.get("action") != "rename"
        and entry_in_apply_scope(entry, scope)
        and resolve_repo_path(entry.get("source", "")).exists()
    ]
    if not retry_indexes:
        return None

    lookup = build_code_lookup()
    clients = groq_clients()
    pdfs = [resolve_repo_path(entries[index]["source"]) for index in retry_indexes]
    retry_entries, worker_count = run_groq_review(pdfs, lookup, clients, workers)
    for index, replacement in zip(retry_indexes, retry_entries):
        entries[index] = replacement
    mark_duplicate_or_existing_targets(entries)
    payload["generated_at"] = utc_now_iso()
    payload["scope"] = display_path(scope)
    payload["groq_keys"] = len(clients)
    payload["workers"] = worker_count
    payload["entries"] = entries
    write_changelog(payload)
    print(f"Retried {len(retry_indexes)} needs-review file(s) from existing changelog.")
    return payload


def read_changelog() -> dict[str, Any]:
    if CHANGELOG_JSON_PATH.exists():
        return json.loads(CHANGELOG_JSON_PATH.read_text(encoding="utf-8"))
    if not CHANGELOG_PATH.exists():
        raise RenameError("changelog/rename.md does not exist. Run: python3 tools/rename_files.py")
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    start = text.rfind(BEGIN_RENAME)
    end = text.rfind(END_RENAME)
    if start == -1 or end == -1 or end <= start:
        raise RenameError("changelog/rename.json does not exist, and changelog/rename.md has no legacy JSON block.")
    block = text[start:end]
    json_start = block.find("```json")
    if json_start == -1:
        raise RenameError("changelog/rename.md is missing the JSON fence.")
    json_text = block[json_start + len("```json") :]
    json_end = json_text.find("```")
    if json_end == -1:
        raise RenameError("changelog/rename.md has an unterminated JSON fence.")
    return json.loads(json_text[:json_end].strip())


def summary_by_subject(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: {"insem": 0, "endsem": 0, "other": 0, "needs_review": 0})
    for entry in entries:
        subject = entry.get("subject") or Path(entry.get("source", "")).parent.name or "unknown"
        exam_type = entry.get("exam_type") if entry.get("action") == "rename" else "needs_review"
        if exam_type not in {"insem", "endsem", "other"}:
            exam_type = "needs_review"
        summary[subject][exam_type] += 1
    return dict(sorted(summary.items()))


def review_category(reason: str) -> str:
    lowered = reason.lower()
    if "duplicate target" in lowered or "target already exists" in lowered:
        return "duplicate_target"
    if "groq" in lowered or "rate limit" in lowered or "request failed" in lowered:
        return "groq_error"
    if "month" in lowered or "year" in lowered:
        return "date_parse"
    if "code found" in lowered or "expected" in lowered:
        return "path_mapping"
    if "pdf" in lowered or "first page" in lowered or "extract" in lowered:
        return "pdf_read"
    return "manual_check"


def markdown_escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")


def markdown_file_link(path_value: Any, label: str | None = None) -> str:
    path_text = str(path_value or "").strip()
    if not path_text:
        return "`missing`"
    target = Path(path_text)
    if target.is_absolute():
        try:
            target = target.relative_to(PROJECT_ROOT)
        except ValueError:
            return f"[{markdown_escape(label or target.name)}]({target.as_posix()})"
    href = "../" + target.as_posix()
    return f"[{markdown_escape(label or target.name)}]({href.replace(' ', '%20')})"


def entry_heading(index: int, entry: dict[str, Any]) -> str:
    action = str(entry.get("action") or "")
    status = str(entry.get("status") or "")
    if status == "retry_pending" or action == "retry":
        label = "Retry"
    elif action == "review":
        label = "Needs Review"
    elif action == "skip":
        label = "Already Normalized"
    else:
        label = str(entry.get("exam_type") or "rename").upper()
    return f"### {index}. {label} - {markdown_escape(entry.get('original_filename') or Path(str(entry.get('source') or '')).name)}"


def render_entry_block(index: int, entry: dict[str, Any]) -> list[str]:
    source = str(entry.get("source") or "")
    target = str(entry.get("target") or entry.get("needs_review_target") or "")
    expected = str(entry.get("expected_path") or "")
    reason = str(entry.get("reason") or "").strip() or "No reason recorded."
    changed_filename = entry.get("filename") or (Path(target).name if target else "")
    lines = [
        entry_heading(index, entry),
        "",
        f"- PDF: {markdown_file_link(source, 'Open PDF')}",
        f"- Incoming path: `{markdown_escape(source)}`",
        f"- Initial filename: `{markdown_escape(entry.get('original_filename') or Path(source).name)}`",
    ]
    if changed_filename:
        lines.append(f"- Changed filename: `{markdown_escape(changed_filename)}`")
    if entry.get("exam_type"):
        lines.append(f"- Type: `{markdown_escape(entry.get('exam_type'))}`")
    if entry.get("marks") not in {None, ""}:
        lines.append(f"- Marks: `{markdown_escape(entry.get('marks'))}`")
    month_year = "_".join(part for part in [str(entry.get("month_code") or ""), str(entry.get("year") or "")] if part)
    if month_year:
        lines.append(f"- Month/year: `{markdown_escape(month_year)}`")
    if entry.get("metadata_source"):
        lines.append(f"- Source: `{markdown_escape(entry.get('metadata_source'))}`")
    if target:
        lines.append(f"- Working target: `{markdown_escape(target)}`")
    if expected:
        lines.append(f"- Expected papers path: `{markdown_escape(expected)}`")
    lines.extend([f"- Reason: {markdown_escape(reason)}", ""])
    return lines


def render_changelog(payload: dict[str, Any]) -> str:
    entries = payload.get("entries") or []
    pending = [entry for entry in entries if entry.get("status") == "pending"]
    rename_entries = [entry for entry in entries if entry.get("action") == "rename"]
    review_entries = [entry for entry in entries if entry.get("action") == "review"]
    retry_entries = [entry for entry in entries if entry.get("status") == "retry_pending" or entry.get("action") == "retry"]
    skip_entries = [entry for entry in entries if entry.get("action") == "skip"]
    source_counts = Counter(str(entry.get("metadata_source") or "unknown") for entry in entries)
    exam_counts = Counter(str(entry.get("exam_type") or "unknown") for entry in entries)
    marks_counts = Counter(str(entry.get("marks")) for entry in rename_entries)
    lines = [
        "# PDF Rename Review",
        "",
        "This file is generated by `python3 tools/rename_files.py`.",
        "Review the planned moves below, then run `python3 tools/rename_files.py --apply`.",
        "",
        "Machine-readable state is stored separately in `changelog/rename.json`.",
        "",
        f"- Generated at: `{payload.get('generated_at', '')}`",
        f"- Scope: `{payload.get('scope', 'incoming')}`",
        f"- Pending entries: `{len(pending)}`",
        f"- Planned renames: `{len(rename_entries)}`",
        f"- Needs review: `{len(review_entries)}`",
        f"- Retry later: `{len(retry_entries)}`",
    ]
    for label, key in (
        ("Total PDFs", "total_pdfs"),
        ("Already normalized", "already_normalized"),
        ("Previously checkpointed", "previously_reviewed"),
        ("Reopened for apply", "reopened_for_apply"),
        ("Retry pending", "retry_pending"),
        ("Remaining", "remaining"),
    ):
        if payload.get(key) not in {None, ""}:
            lines.append(f"- {label}: `{payload.get(key)}`")
    if payload.get("metadata_pipeline") not in {None, ""}:
        lines.append(f"- Metadata pipeline: `{payload.get('metadata_pipeline')}`")
    crop_ratios = payload.get("paddleocr_crop_ratios") or payload.get("paddleocr_crop_ratio")
    if crop_ratios is not None and crop_ratios != "":
        lines.append(f"- PaddleOCR crop ratios: `{crop_ratios}`")
    if payload.get("paddleocr_confidence") not in {None, ""}:
        lines.append(f"- PaddleOCR confidence threshold: `{payload.get('paddleocr_confidence')}`")
    if payload.get("paddleocr_relaxed_confidence") not in {None, ""}:
        lines.append(f"- PaddleOCR relaxed direct-phrase threshold: `{payload.get('paddleocr_relaxed_confidence')}`")
    if payload.get("groq_keys") not in {None, ""}:
        lines.append(f"- Groq keys: `{payload.get('groq_keys')}`")
    if payload.get("workers") not in {None, ""}:
        lines.append(f"- Workers: `{payload.get('workers')}`")
    lines.extend(
        [
            "",
            "## Quick Counts",
            "",
            "### Exam Types",
            "",
        ]
    )
    for label in ("insem", "endsem", "other", "needs_review"):
        lines.append(f"- `{label}`: `{exam_counts.get(label, 0)}`")
    lines.extend(["", "### Marks", ""])
    for marks, count in sorted(marks_counts.items(), key=lambda item: (999 if not item[0].isdigit() else int(item[0]), item[0])):
        lines.append(f"- `{marks}`: `{count}`")
    lines.extend(["", "### Metadata Sources", ""])
    for source, count in sorted(source_counts.items()):
        lines.append(f"- `{source}`: `{count}`")
    lines.extend(["", "### Already Normalized", "", f"- Count: `{len(skip_entries)}`", ""])

    if review_entries:
        lines.extend(["## Needs Review", ""])
        for index, entry in enumerate(review_entries, start=1):
            lines.extend(render_entry_block(index, entry))

    if retry_entries:
        lines.extend(["## Retry Later", ""])
        for index, entry in enumerate(retry_entries, start=1):
            lines.extend(render_entry_block(index, entry))

    lines.extend(["## Planned Renames", ""])
    if not rename_entries:
        lines.append("No planned renames.")
        lines.append("")
    for index, entry in enumerate(rename_entries, start=1):
        lines.extend(render_entry_block(index, entry))
    return "\n".join(lines)


def write_changelog(payload: dict[str, Any]) -> None:
    CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    CHANGELOG_PATH.write_text(render_changelog(payload), encoding="utf-8")


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def tracking_row_for_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the SQLite row at apply time, even for older changelog entries."""
    file_id = str(entry.get("file_id") or "").strip()
    if file_id:
        row = tracking.get_file(file_id)
        if row:
            return row
    candidates = [
        str(entry.get("source") or ""),
        str(entry.get("target") or ""),
        str(entry.get("expected_path") or ""),
        str(entry.get("needs_review_target") or ""),
    ]
    row = tracking.find_by_any_path(candidates)
    if row:
        entry["file_id"] = row["file_id"]
    return row


def unique_review_target(target: Path) -> Path:
    if not target.exists():
        return target
    counter = 2
    while True:
        candidate = target.with_name(f"{target.stem}_{counter}{target.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


def entry_in_apply_scope(entry: dict[str, Any], scope: Path) -> bool:
    source = resolve_repo_path(entry["source"])
    if path_in_scope(source, scope):
        return True
    try:
        source_rel = source.resolve().relative_to(NEEDS_REVIEW_DIR.resolve())
        incoming_equivalent = INCOMING_DIR / source_rel
        return path_in_scope(incoming_equivalent, scope)
    except ValueError:
        return False


def apply_review(scope: Path) -> dict[str, int]:
    payload = read_changelog()
    entries = payload.get("entries") or []
    moved = 0
    reviewed = 0
    skipped = 0
    for entry in entries:
        if entry.get("status") != "pending" or not entry_in_apply_scope(entry, scope):
            continue
        source = resolve_repo_path(entry["source"])
        tracked = tracking_row_for_entry(entry)
        if not source.exists():
            entry["status"] = "missing"
            entry["reason"] = f"Source file no longer exists: {entry['source']}"
            if tracked:
                tracking.update_stage(
                    tracked["file_id"],
                    "MISSING",
                    review_reason=entry["reason"],
                    reason=entry["reason"],
                )
            skipped += 1
            write_changelog(payload)
            continue

        if entry.get("action") == "rename":
            target = resolve_repo_path(entry["target"])
            expected_conflict = tracking.find_by_any_path([str(entry.get("expected_path") or "")])
            has_db_conflict = bool(
                expected_conflict
                and tracked
                and expected_conflict.get("file_id") != tracked.get("file_id")
            )
            if target.exists() or has_db_conflict:
                _root_name, source_rel = workflow_relative(source)
                review_target = unique_review_target(resolve_repo_path(entry["needs_review_target"] or f"needs_review/{source_rel.as_posix()}"))
                move_file(source, review_target)
                entry["status"] = "review_moved"
                entry["blocked_target"] = expected_conflict.get("expected_path") if has_db_conflict and expected_conflict else display_path(target)
                entry["target"] = ""
                entry["needs_review_target"] = display_path(review_target)
                entry["reason"] = f"Target already exists: {entry['blocked_target']}"
                if tracked:
                    tracking.update_stage(
                        tracked["file_id"],
                        "NEEDS_REVIEW",
                        current_path=entry["needs_review_target"],
                        review_category="duplicate_filename",
                        review_reason=entry["reason"],
                        reason=entry["reason"],
                    )
                reviewed += 1
            else:
                move_file(source, target)
                entry["status"] = "applied"
                if tracked:
                    tracking.update_stage(
                        tracked["file_id"],
                        "FILE_RENAMED",
                        current_path=entry["target"],
                        expected_path=entry.get("expected_path") or None,
                        renamed_filename=entry.get("filename") or Path(entry["target"]).name,
                        groq_key_index=int(entry["groq_key_index"]) if str(entry.get("groq_key_index", "")).isdigit() else None,
                        groq_model=entry.get("groq_model") or None,
                        reason="File renamed in working folder",
                    )
                else:
                    entry["reason"] = f"{entry.get('reason', '')} | WARNING: no SQLite row matched at apply time.".strip()
                moved += 1
        else:
            review_target = unique_review_target(resolve_repo_path(entry["needs_review_target"]))
            move_file(source, review_target)
            entry["status"] = "review_moved"
            entry["needs_review_target"] = display_path(review_target)
            if tracked:
                tracking.update_stage(
                    tracked["file_id"],
                    "NEEDS_REVIEW",
                    current_path=entry["needs_review_target"],
                    review_category=review_category(str(entry.get("reason", ""))),
                    review_reason=str(entry.get("reason", "")),
                    reason=str(entry.get("reason", "")),
                )
            reviewed += 1
        payload["generated_at"] = utc_now_iso()
        write_changelog(payload)
        print(f"Applied {moved + reviewed + skipped}: {entry['source']} -> {entry.get('target') or entry.get('needs_review_target')}")
    return {"moved": moved, "reviewed": reviewed, "skipped": skipped}


def discard_changelog() -> bool:
    removed = False
    for path in (CHANGELOG_PATH, CHANGELOG_JSON_PATH):
        if path.exists():
            path.unlink()
            removed = True
    return removed


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def rollback_needs_review(scope: Path) -> dict[str, int]:
    moved = 0
    restored = 0
    missing = 0
    skipped = 0
    for row in tracking.all_files():
        if row.get("current_stage") != "NEEDS_REVIEW":
            continue
        current_value = str(row.get("current_path") or "")
        if not current_value:
            skipped += 1
            continue
        current_path = resolve_repo_path(current_value)

        incoming_target: Path | None = None
        if path_in_scope(current_path, NEEDS_REVIEW_DIR):
            rel = current_path.resolve().relative_to(NEEDS_REVIEW_DIR.resolve())
            incoming_target = INCOMING_DIR / rel
        elif path_in_scope(current_path, INCOMING_DIR):
            incoming_target = current_path
        else:
            skipped += 1
            continue

        if not path_in_scope(incoming_target, scope):
            skipped += 1
            continue

        if current_path.exists() and path_in_scope(current_path, NEEDS_REVIEW_DIR):
            if incoming_target.exists():
                skipped += 1
                continue
            move_file(current_path, incoming_target)
            moved += 1
        elif not incoming_target.exists():
            missing += 1
            continue

        incoming_rel = repo_relative(incoming_target)
        with tracking.connect() as connection:
            connection.execute(
                """
                UPDATE files
                SET current_stage = 'FOLDER_RENAMED',
                    current_path = ?,
                    expected_path = NULL,
                    final_path = NULL,
                    renamed_filename = NULL,
                    review_category = NULL,
                    review_reason = NULL,
                    updated_at = ?
                WHERE file_id = ?
                """,
                (incoming_rel, utc_now_iso(), row["file_id"]),
            )
            tracking.add_event(
                connection,
                row["file_id"],
                row.get("current_stage"),
                "FOLDER_RENAMED",
                incoming_rel,
                "Rolled back needs_review file to incoming",
            )
        restored += 1
    discarded = discard_changelog()
    return {"moved": moved, "restored": restored, "missing": missing, "skipped": skipped, "discarded": int(discarded)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review-first PDF renamer for incoming/ using PyMuPDF, PaddleOCR, Groq fallback, and mapping/folder_names.yml.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 tools/rename_files.py
      Review remaining PDFs under incoming/. Existing changelog entries are skipped or retried.

  python3 tools/rename_files.py --fresh
      Rebuild changelog/rename.md from all PDFs under incoming/.

  python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
      Review one subtree only.

  python3 tools/rename_files.py --ocr-workers 1
      OCR worker count for GPU memory safety. Defaults to 1 on 4 GB VRAM.

  python3 tools/rename_files.py --apply
      Move reviewed files into papers/ or needs_review/. Does not call PyMuPDF, PaddleOCR, or Groq.

  python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science"
      Apply reviewed entries only for one source subtree.

  python3 tools/rename_files.py --discard
      Delete changelog/rename.md and changelog/rename.json without moving any PDFs.

  python3 tools/rename_files.py --rollback-needs-review
      Delete stale rename changelogs and restore NEEDS_REVIEW rows/files to incoming/.

Environment:
  PaddleOCR GPU is used only on page 1 crops: 45%, 65%, then full first page.
  GROQ_API_KEY is optional unless PyMuPDF/PaddleOCR cannot extract usable metadata.
  GROQ_API_KEY_2 or GROQ_API_KEYS=key1,key2 can be used for fallback.
  GROQ_MODEL is optional; default is llama-3.3-70b-versatile.
""",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changelog/rename.json without calling PyMuPDF, PaddleOCR, or Groq.")
    parser.add_argument("--discard", action="store_true", help="Delete changelog/rename.md and changelog/rename.json without moving any PDFs.")
    parser.add_argument("--rollback-needs-review", action="store_true", help="Move needs_review/ PDFs back to incoming/, reset NEEDS_REVIEW rows, and discard rename changelog.")
    parser.add_argument("--path", default=str(INCOMING_DIR), help="Incoming directory or PDF path to review/apply. Defaults to incoming/.")
    parser.add_argument("--ocr-workers", type=int, default=None, help="OCR worker count. Defaults to 1 for 4 GB GPU VRAM.")
    parser.add_argument("--workers", type=int, default=None, help="Compatibility alias for --ocr-workers.")
    parser.add_argument("--fresh", action="store_true", help="Ignore existing changelog/rename.md and rebuild review for the selected scope.")
    parser.add_argument("--retry-needs-review", action="store_true", help="Retry pending needs-review entries in the rename changelog with Groq.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        selected_actions = sum(bool(value) for value in (args.apply, args.discard, args.retry_needs_review, args.rollback_needs_review))
        if selected_actions > 1:
            raise RenameError("Use only one of --apply, --discard, --rollback-needs-review, or --retry-needs-review.")
        if args.discard:
            removed = discard_changelog()
            if removed:
                print("Deleted changelog/rename.md and changelog/rename.json. No PDFs were moved.")
            else:
                print("No rename changelog exists. Nothing to discard.")
            return 0
        scope = resolve_repo_path(args.path)
        if args.rollback_needs_review:
            result = rollback_needs_review(scope)
            print(
                "Rolled back needs-review state: "
                f"{result['moved']} file(s) moved to incoming; "
                f"{result['restored']} DB row(s) restored; "
                f"{result['missing']} missing; {result['skipped']} skipped; "
                f"discarded_changelog={bool(result['discarded'])}."
            )
            return 0
        if args.retry_needs_review:
            payload = retry_needs_review(scope, args.ocr_workers if args.ocr_workers is not None else args.workers)
            if payload is None:
                print("No pending needs-review entries to retry.")
            else:
                entries = payload.get("entries") or []
                review_count = sum(1 for entry in entries if entry.get("action") == "review" and entry.get("status") == "pending")
                rename_count = sum(1 for entry in entries if entry.get("action") == "rename" and entry.get("status") == "pending")
                print(f"Groq retry complete; {rename_count} ready to rename; {review_count} still need review.")
            return 0
        if args.apply:
            result = apply_review(scope)
            print(f"Renamed {result['moved']} files in working folders; {result['reviewed']} files to needs_review; skipped {result['skipped']}.")
        else:
            ocr_workers = args.ocr_workers if args.ocr_workers is not None else args.workers
            payload = review_pdfs(scope, ocr_workers=ocr_workers, fresh=args.fresh)
            entries = payload.get("entries") or []
            review_count = sum(1 for entry in entries if entry.get("action") == "review" and entry.get("status") == "pending")
            retry_count = sum(1 for entry in entries if entry.get("status") == "retry_pending")
            print(f"Review generated with {len(entries)} tracked entries; {review_count} need review; {retry_count} retry later.")
        return 0
    except (RenameError, OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
