from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_pdf_id(pdf_url: str) -> str:
    return hashlib.sha1(pdf_url.encode("utf-8")).hexdigest()[:12]


def normalize_extracted_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_text_valid(text: str, min_characters: int) -> bool:
    stripped = text.strip()
    if len(stripped) < min_characters:
        return False

    alpha_numeric_count = sum(character.isalnum() for character in stripped)
    return alpha_numeric_count >= max(40, min_characters // 3)


def timestamp_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_question_suffix(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or None


def normalize_subquestion_label(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip().lower()
    cleaned = re.sub(r"^[\(\[\{]+", "", cleaned)
    cleaned = re.sub(r"[\)\]\}\.\:\;\-]+$", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned or None


def normalize_question_number_token(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = re.sub(r"[^a-zA-Z0-9]+", "", value.strip().lower())
    return cleaned or None


def assign_question_ids(pdf_id: str, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_questions: list[dict[str, Any]] = []

    for index, question in enumerate(questions, start=1):
        question_copy = dict(question)
        question_number_token = normalize_question_number_token(
            str(question_copy.get("question_number", ""))
        )
        if question_number_token is None:
            question_number_token = f"q{index}"

        normalized_subquestion = normalize_subquestion_label(question_copy.get("subquestion"))
        if normalized_subquestion is not None:
            question_copy["subquestion"] = normalized_subquestion

        base_id = f"{pdf_id}_{question_number_token}"
        suffix = sanitize_question_suffix(normalized_subquestion)
        question_copy["question_id"] = f"{base_id}_{suffix}" if suffix else base_id
        normalized_questions.append(question_copy)

    return normalized_questions


def branch_name_from_file(path: Path) -> str:
    return path.stem.lower()
