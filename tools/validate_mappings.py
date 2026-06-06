"""Validate committed mapping files without calling Google Drive."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAPPING_DIR = PROJECT_ROOT / "mapping"
DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")


class Validator:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.folder_ids: Counter[str] = Counter()
        self.normalized_names: defaultdict[str, list[str]] = defaultdict(list)
        self.registry: dict[str, Any] = {}
        self.exception_folder_ids: dict[str, str] = {}

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def warn(self, path: str, message: str) -> None:
        self.warnings.append(f"{path}: {message}")

    def load_json(self, filename: str) -> dict[str, Any]:
        path = MAPPING_DIR / filename
        if not path.exists():
            self.error(filename, "missing file")
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.error(filename, f"invalid JSON: {exc}")
            return {}

    def load_yaml(self, filename: str) -> dict[str, Any]:
        path = MAPPING_DIR / filename
        if not path.exists():
            self.error(filename, "missing file")
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            self.error(filename, f"invalid YAML: {exc}")
            return {}

    def check_mapping_header(self, filename: str, data: dict[str, Any]) -> None:
        if data.get("schema_version") is None:
            self.error(filename, "missing schema_version")
        root = data.get("root")
        if not isinstance(root, dict) or not root.get("folder_id"):
            self.error(filename, "missing root.folder_id")
        elif not DRIVE_ID_RE.match(str(root["folder_id"])):
            self.error(filename, "root.folder_id does not look like a Drive ID")

    def check_folder_entry(self, filename: str, key_path: str, entry: Any, expected_path: str, expected_depth: int) -> None:
        if not isinstance(entry, dict):
            self.error(key_path, "entry must be an object")
            return
        folder_id = str(entry.get("folder_id", "")).strip()
        if not folder_id and expected_path in self.exception_folder_ids:
            folder_id = self.exception_folder_ids[expected_path]
            self.warn(key_path, "missing folder_id in active mapping; using exception audit folder_id for validation")
        if not folder_id:
            self.error(key_path, "missing folder_id")
        elif not DRIVE_ID_RE.match(folder_id):
            self.error(key_path, f"folder_id does not look like a Drive ID: {folder_id}")
        else:
            self.folder_ids[folder_id] += 1

        actual_path = str(entry.get("path", "")).strip()
        if actual_path != expected_path:
            self.error(key_path, f"path mismatch: expected {expected_path!r}, got {actual_path!r}")
        depth = len([part for part in actual_path.split("/") if part])
        if depth != expected_depth:
            self.error(key_path, f"expected hierarchy depth {expected_depth}, got {depth}")

        name = expected_path.split("/")[-1]
        registry_entry = self.registry.get(name)
        if not isinstance(registry_entry, dict):
            self.warn(key_path, f"missing name_registry entry for {name!r}")
        elif not registry_entry.get("normalized") or not registry_entry.get("code"):
            self.warn(key_path, f"incomplete name_registry entry for {name!r}")

    def validate_standard(self) -> None:
        filename = "sync_mapping.json"
        data = self.load_json(filename)
        self.check_mapping_header(filename, data)
        self.exception_folder_ids = {
            str(path): str(entry.get("folder_id", "")).strip()
            for path, entry in (data.get("exceptions") or {}).items()
            if isinstance(entry, dict) and entry.get("folder_id")
        }
        branches = data.get("branches")
        if not isinstance(branches, dict) or not branches:
            self.error(filename, "branches must be a non-empty object")
            return
        for branch, branch_entry in branches.items():
            branch_path = str(branch)
            self.check_folder_entry(filename, branch_path, branch_entry, branch_path, 1)
            years = branch_entry.get("years") if isinstance(branch_entry, dict) else None
            if not isinstance(years, dict):
                self.error(branch_path, "missing years object")
                continue
            for year, year_entry in years.items():
                year_path = f"{branch_path}/{year}"
                self.check_folder_entry(filename, year_path, year_entry, year_path, 2)
                patterns = year_entry.get("patterns") if isinstance(year_entry, dict) else None
                if not isinstance(patterns, dict):
                    self.error(year_path, "missing patterns object")
                    continue
                for pattern, pattern_entry in patterns.items():
                    pattern_path = f"{year_path}/{pattern}"
                    self.check_folder_entry(filename, pattern_path, pattern_entry, pattern_path, 3)
                    subjects = pattern_entry.get("subjects") if isinstance(pattern_entry, dict) else None
                    if not isinstance(subjects, dict):
                        self.error(pattern_path, "missing subjects object")
                        continue
                    for subject, subject_entry in subjects.items():
                        subject_path = f"{pattern_path}/{subject}"
                        self.check_folder_entry(filename, subject_path, subject_entry, subject_path, 4)

    def validate_first_year(self) -> None:
        filename = "first_year_mapping.json"
        data = self.load_json(filename)
        self.check_mapping_header(filename, data)
        if data.get("branch") != "First Year":
            self.error(filename, "branch must be First Year")
        self.check_folder_entry(filename, "First Year", data, "First Year", 1)
        patterns = data.get("patterns")
        if not isinstance(patterns, dict) or not patterns:
            self.error(filename, "patterns must be a non-empty object")
            return
        for pattern, pattern_entry in patterns.items():
            pattern_path = f"First Year/{pattern}"
            self.check_folder_entry(filename, pattern_path, pattern_entry, pattern_path, 2)
            subjects = pattern_entry.get("subjects") if isinstance(pattern_entry, dict) else None
            if not isinstance(subjects, dict):
                self.error(pattern_path, "missing subjects object")
                continue
            for subject, subject_entry in subjects.items():
                subject_path = f"{pattern_path}/{subject}"
                self.check_folder_entry(filename, subject_path, subject_entry, subject_path, 3)

    def validate_mba(self) -> None:
        filename = "mba.json"
        data = self.load_json(filename)
        self.check_mapping_header(filename, data)
        if data.get("branch") != "M.B.A":
            self.error(filename, "branch must be M.B.A")
        self.check_folder_entry(filename, "M.B.A", data, "M.B.A", 1)
        semesters = data.get("semesters")
        if not isinstance(semesters, dict) or not semesters:
            self.error(filename, "semesters must be a non-empty object")
            return
        for semester, semester_entry in semesters.items():
            semester_path = f"M.B.A/{semester}"
            self.check_folder_entry(filename, semester_path, semester_entry, semester_path, 2)
            patterns = semester_entry.get("patterns") if isinstance(semester_entry, dict) else None
            if not isinstance(patterns, dict):
                self.error(semester_path, "missing patterns object")
                continue
            for pattern, pattern_entry in patterns.items():
                pattern_path = f"{semester_path}/{pattern}"
                self.check_folder_entry(filename, pattern_path, pattern_entry, pattern_path, 3)
                subjects = pattern_entry.get("subjects") if isinstance(pattern_entry, dict) else None
                if not isinstance(subjects, dict):
                    self.error(pattern_path, "missing subjects object")
                    continue
                for subject, subject_entry in subjects.items():
                    subject_path = f"{pattern_path}/{subject}"
                    self.check_folder_entry(filename, subject_path, subject_entry, subject_path, 4)

    def validate_honors(self) -> None:
        filename = "honors_course_mapping.json"
        data = self.load_json(filename)
        self.check_mapping_header(filename, data)
        folders = data.get("folders")
        if not isinstance(folders, dict) or not folders:
            self.error(filename, "folders must be a non-empty object")
            return
        for folder_path, entry in folders.items():
            expected = str(folder_path)
            depth = len([part for part in expected.split("/") if part])
            if depth not in {1, 2, 3}:
                self.error(expected, f"Honors Course path must have depth 1, 2, or 3, got {depth}")
            self.check_folder_entry(filename, expected, entry, expected, depth)

    def validate_registry(self) -> None:
        data = self.load_yaml("folder_names.yml")
        if data.get("schema_version") is None:
            self.error("folder_names.yml", "missing schema_version")
        registry = data.get("name_registry")
        if not isinstance(registry, dict) or not registry:
            self.error("folder_names.yml", "name_registry must be a non-empty object")
            return
        self.registry = registry
        for original, entry in registry.items():
            key = f"folder_names.yml:name_registry.{original}"
            if not isinstance(entry, dict):
                self.error(key, "entry must be an object")
                continue
            normalized = str(entry.get("normalized", "")).strip()
            code = str(entry.get("code", "")).strip()
            if not normalized:
                self.error(key, "missing normalized")
            if not code:
                self.error(key, "missing code")
            if normalized:
                self.normalized_names[normalized].append(str(original))

        for normalized, originals in sorted(self.normalized_names.items()):
            unique_originals = sorted(set(originals))
            if len(unique_originals) > 1:
                self.warn("folder_names.yml", f"duplicate normalized name {normalized!r}: {', '.join(unique_originals[:8])}")

    def finish(self) -> int:
        duplicate_ids = sorted(folder_id for folder_id, count in self.folder_ids.items() if count > 1)
        for folder_id in duplicate_ids:
            self.warn("mapping/*.json", f"folder_id appears {self.folder_ids[folder_id]} times: {folder_id}")

        print("Mapping validation")
        print(f"- errors: {len(self.errors)}")
        print(f"- warnings: {len(self.warnings)}")
        if self.errors:
            print("\nErrors")
            for item in self.errors[:100]:
                print(f"- {item}")
            if len(self.errors) > 100:
                print(f"- ... {len(self.errors) - 100} more")
        if self.warnings:
            print("\nWarnings")
            for item in self.warnings[:100]:
                print(f"- {item}")
            if len(self.warnings) > 100:
                print(f"- ... {len(self.warnings) - 100} more")
        return 1 if self.errors else 0


def main() -> int:
    validator = Validator()
    validator.validate_registry()
    validator.validate_standard()
    validator.validate_first_year()
    validator.validate_mba()
    validator.validate_honors()
    return validator.finish()


if __name__ == "__main__":
    sys.exit(main())
