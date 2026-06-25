from pathlib import Path

from .env import env_bool, env_choice, env_text, load_env_file


BASE_DIR = Path(__file__).resolve().parents[1]
load_env_file()

SITE_URL = env_text(("SPPUPYQS_SITE_URL",), "https://sppupyqs.pages.dev").rstrip("/")
CODES_SITE_URL = env_text(("SPPUCODES_SITE_URL",), "https://sppucodes.vercel.app").rstrip("/")
MANIFEST_DIR = str(BASE_DIR / "manifest")

PDF_SOURCE = env_choice(("PDF_SOURCE", "pdf_source"), "r2", {"r2", "cloudinary"})
R2_BASE_URL = env_text(("R2_BASE_URL", "r2_base_url"), "").rstrip("/")
CLOUDINARY_RAW_BASE_URL = env_text(
    (
        "CLOUDINARY_RAW_BASE_URL",
        "CLOUDINARY_BASE_URL",
        "cloudinary_raw_base_url",
        "cloudinary_base_url",
    ),
    "",
).rstrip("/")
DEFAULT_EXAM_TYPE = env_choice(("EXAM_TYPE", "DEFAULT_EXAM_TYPE"), "endsem", {"insem", "endsem"})
_pattern_year = env_text(("PATTERN_YEAR", "DEFAULT_PATTERN_YEAR"), "2019") or "2019"
DEFAULT_PATTERN_YEAR = _pattern_year if _pattern_year.isdigit() else "2019"
MAINTENANCE_MODE = env_bool(("MAINTENANCE_MODE", "MAINTAINCE_MODE"), False)
