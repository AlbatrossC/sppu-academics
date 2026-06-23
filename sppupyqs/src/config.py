import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
SITE_URL = os.getenv("SPPUPYQS_SITE_URL", "https://sppupyqs.vercel.app").strip().rstrip("/")
CODES_SITE_URL = os.getenv("SPPUCODES_SITE_URL", "https://sppucodes.vercel.app").strip().rstrip("/")
MANIFEST_DIR = str(BASE_DIR / "manifest")

PDF_SOURCE = (os.getenv("PDF_SOURCE") or os.getenv("pdf_source") or "r2").strip().lower()
if PDF_SOURCE not in {"r2", "cloudinary"}:
    PDF_SOURCE = "r2"

R2_BASE_URL = (os.getenv("R2_BASE_URL") or os.getenv("r2_base_url") or "").strip().rstrip("/")
CLOUDINARY_RAW_BASE_URL = (
    os.getenv("CLOUDINARY_RAW_BASE_URL")
    or os.getenv("CLOUDINARY_BASE_URL")
    or os.getenv("cloudinary_raw_base_url")
    or os.getenv("cloudinary_base_url")
    or ""
).strip().rstrip("/")

DEFAULT_EXAM_TYPE = os.getenv("DEFAULT_EXAM_TYPE", "endsem").strip().lower()
if DEFAULT_EXAM_TYPE not in {"insem", "endsem"}:
    DEFAULT_EXAM_TYPE = "endsem"
