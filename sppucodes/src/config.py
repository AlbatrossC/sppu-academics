import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE_URL = os.getenv("SPPUCODES_SITE_URL", "https://sppucodes.vercel.app").strip().rstrip("/")
QUESTION_PAPERS_SITE_URL = os.getenv(
    "SPPUPYQS_SITE_URL",
    "https://sppupyqs.pages.dev",
).strip().rstrip("/")

QUESTIONS_DIR = os.path.join(BASE_DIR, "questions")
ANSWERS_DIR = os.path.join(BASE_DIR, "answers")

CF_WORKER_DB_URL = os.getenv("CF_WORKER_DB_URL", "").strip().rstrip("/")
DB_API_KEY = os.getenv("DB_API_KEY", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY", "karltos")

