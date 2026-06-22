from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from utils import ensure_directory, timestamp_string


@dataclass
class PipelineStats:
    total: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    gemini_failures: int = 0
    ocr_used: int = 0
    current_branch: str = "-"
    current_semester: str = "-"
    current_subject: str = "-"

    @property
    def remaining(self) -> int:
        remaining = self.total - (self.processed + self.skipped + self.failed)
        return max(0, remaining)


class ProgressLogger:
    def __init__(self, report_path: Path) -> None:
        self.report_path = report_path
        ensure_directory(report_path.parent)
        if not self.report_path.exists():
            self.report_path.write_text("", encoding="utf-8")

    def append_event(self, message: str) -> None:
        payload = f"[{timestamp_string()}] {message}\n"
        with self.report_path.open("a", encoding="utf-8") as handle:
            handle.write(payload)

    def append_snapshot(self, stats: PipelineStats) -> None:
        snapshot = (
            f"[{timestamp_string()}]\n\n"
            f"Processed: {stats.processed}\n"
            f"Skipped: {stats.skipped}\n"
            f"Failed: {stats.failed}\n"
            f"Remaining: {stats.remaining}\n"
            f"Gemini failures: {stats.gemini_failures}\n"
            f"OCR usage: {stats.ocr_used}\n\n"
            "Current:\n"
            f"Branch: {stats.current_branch}\n"
            f"Semester: {stats.current_semester}\n"
            f"Subject: {stats.current_subject}\n\n"
        )
        with self.report_path.open("a", encoding="utf-8") as handle:
            handle.write(snapshot)
