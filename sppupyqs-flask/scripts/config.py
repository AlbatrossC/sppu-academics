from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    base_dir: Path
    scripts_dir: Path
    input_dir: Path
    output_dir: Path
    prompt_path: Path
    schema_path: Path
    metadata_report_path: Path
    model_name: str
    request_timeout_seconds: int
    gemini_retries_per_key: int
    gemini_retry_delay_seconds: float
    pdf_text_min_characters: int
    gemini_api_keys: list[str]
    ocr_language: str
    tesseract_cmd: str | None


def load_config() -> AppConfig:
    scripts_dir = Path(__file__).resolve().parent
    base_dir = scripts_dir.parent
    env_path = scripts_dir / ".env"
    load_dotenv(env_path, override=False)

    schema_path = scripts_dir / "structure_output.json"
    if not schema_path.exists():
        legacy_schema_path = scripts_dir / "strucutre_output.json"
        if legacy_schema_path.exists():
            schema_path = legacy_schema_path

    gemini_api_keys = []
    for key, value in os.environ.items():
        if key.startswith("GEMINI_API_KEY") and value.strip():
            gemini_api_keys.append(value.strip())
    # remove duplicates and sort for consistency
    gemini_api_keys = list(sorted(set(gemini_api_keys)))

    return AppConfig(
        base_dir=base_dir,
        scripts_dir=scripts_dir,
        input_dir=base_dir / "manifest",
        output_dir=base_dir / "pyqs-metadata",
        prompt_path=scripts_dir / "prompt.txt",
        schema_path=schema_path,
        metadata_report_path=scripts_dir / "metadata.txt",
        model_name=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        gemini_retries_per_key=int(os.getenv("GEMINI_RETRIES_PER_KEY", "3")),
        gemini_retry_delay_seconds=float(os.getenv("GEMINI_RETRY_DELAY_SECONDS", "3")),
        pdf_text_min_characters=int(os.getenv("PDF_TEXT_MIN_CHARACTERS", "200")),
        gemini_api_keys=gemini_api_keys,
        ocr_language=os.getenv("OCR_LANGUAGE", "eng"),
        tesseract_cmd=os.getenv("TESSERACT_CMD", "").strip() or None,
    )
