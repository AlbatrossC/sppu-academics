import os
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"


def load_env_file(path=ENV_FILE):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        os.environ.setdefault(key, _clean_env_value(value))


def env_choice(names, default, allowed):
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        normalized = value.strip().lower()
        if normalized in allowed:
            return normalized
    return default


def env_text(names, default=""):
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value.strip()
    return default


def env_bool(names, default=False):
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _clean_env_value(value):
    value = value.strip()
    if not value:
        return ""
    quote = value[0]
    if quote in {"'", '"'}:
        end_index = value.find(quote, 1)
        if end_index != -1:
            return value[1:end_index]
    return value.split("#", 1)[0].strip()
