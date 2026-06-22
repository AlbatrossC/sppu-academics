"""
Generate static/search.1.json from manifest files.
Run from sppupyqs/: python scripts/generate_search.py
"""

import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.utils import load_question_papers  # noqa: E402

SEARCH_VERSION = 1
OUTPUT_FILE = os.path.join(ROOT_DIR, "static", f"search.{SEARCH_VERSION}.json")


def generate():
    entries = load_question_papers()["question_papers_list"]
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file_obj:
        json.dump(entries, file_obj, ensure_ascii=False, separators=(",", ":"))
    print(f"Generated {OUTPUT_FILE} with {len(entries)} entries")


if __name__ == "__main__":
    generate()
