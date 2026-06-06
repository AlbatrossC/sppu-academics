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
    primary_gemini_api_key: str
    secondary_gemini_api_key: str
    ocr_language: str
    tesseract_cmd: str | None

    @property
    def gemini_api_keys(self) -> list[str]:
        return [key for key in [self.primary_gemini_api_key, self.secondary_gemini_api_key] if key]


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
        primary_gemini_api_key=os.getenv("PRIMARY_GEMINI_API_KEY", "").strip(),
        secondary_gemini_api_key=os.getenv("SECONDARY_GEMINI_API_KEY", "").strip(),
        ocr_language=os.getenv("OCR_LANGUAGE", "eng"),
        tesseract_cmd=os.getenv("TESSERACT_CMD", "").strip() or None,
    )
