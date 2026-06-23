import json
import os


_STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
_MANIFEST_PATH = os.path.join(_STATIC_DIR, "asset-manifest.json")
_manifest_cache = {
    "mtime": None,
    "data": {},
}


def asset_path(filename):
    manifest = _load_manifest()
    return manifest.get(filename, filename)


def _load_manifest():
    try:
        mtime = os.path.getmtime(_MANIFEST_PATH)
    except OSError:
        _manifest_cache["mtime"] = None
        _manifest_cache["data"] = {}
        return {}

    if _manifest_cache["mtime"] == mtime:
        return _manifest_cache["data"]

    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as manifest_file:
            data = json.load(manifest_file)
    except (OSError, json.JSONDecodeError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    _manifest_cache["mtime"] = mtime
    _manifest_cache["data"] = data
    return data
