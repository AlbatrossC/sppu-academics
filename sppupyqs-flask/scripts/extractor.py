from __future__ import annotations

import io
from dataclasses import dataclass

import fitz
import requests
from PIL import Image

from utils import is_text_valid, normalize_extracted_text


@dataclass
class ExtractedDocument:
    text: str
    extraction_method: str
    used_ocr: bool
    page_count: int
    character_count: int


class PDFTextExtractor:
    def __init__(
        self,
        timeout_seconds: int,
        min_text_characters: int,
        ocr_language: str = "eng",
        tesseract_cmd: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.min_text_characters = min_text_characters
        self.ocr_language = ocr_language
        self.session = requests.Session()
        self._ocr_ready = False
        self._tesseract_import_error: Exception | None = None

        try:
            import pytesseract

            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            self._pytesseract = pytesseract
            self._ocr_ready = True
        except Exception as error:  # pragma: no cover
            self._pytesseract = None
            self._tesseract_import_error = error

    def extract_from_url(self, pdf_url: str) -> ExtractedDocument:
        response = self.session.get(pdf_url, timeout=self.timeout_seconds)
        response.raise_for_status()
        pdf_bytes = response.content

        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            page_count = len(document)
            extracted_text = self._extract_text(document)

            if is_text_valid(extracted_text, self.min_text_characters):
                return ExtractedDocument(
                    text=extracted_text,
                    extraction_method="pymupdf_text",
                    used_ocr=False,
                    page_count=page_count,
                    character_count=len(extracted_text),
                )

            ocr_text = self._extract_text_with_ocr(document)
            combined_text = normalize_extracted_text(ocr_text)
            if not is_text_valid(combined_text, max(40, self.min_text_characters // 2)):
                raise RuntimeError("PDF text extraction failed after OCR fallback.")
            return ExtractedDocument(
                text=combined_text,
                extraction_method="ocr_fallback",
                used_ocr=True,
                page_count=page_count,
                character_count=len(combined_text),
            )

    def _extract_text(self, document: fitz.Document) -> str:
        parts = [page.get_text("text") for page in document]
        return normalize_extracted_text("\n".join(parts))

    def _extract_text_with_ocr(self, document: fitz.Document) -> str:
        if not self._ocr_ready or self._pytesseract is None:
            raise RuntimeError(
                "OCR fallback was required but pytesseract/Tesseract is not available."
            ) from self._tesseract_import_error

        parts: list[str] = []
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            png_bytes = pixmap.tobytes("png")
            image = Image.open(io.BytesIO(png_bytes))
            parts.append(self._pytesseract.image_to_string(image, lang=self.ocr_language))

        return "\n".join(parts)
