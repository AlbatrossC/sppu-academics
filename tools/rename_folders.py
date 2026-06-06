"""Normalize incoming folder names using mapping/folder_names.yml."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from common import tracking


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAPPING_DIR = PROJECT_ROOT / "mapping"
INCOMING_DIR = PROJECT_ROOT / "incoming"
FOLDER_NAMES_PATH = MAPPING_DIR / "folder_names.yml"
ROMAN_NUMERALS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
CODE_SKIP_WORDS = {"and", "of", "the", "for", "in"}
DEFAULT_PATTERN_ALIASES = {
    "2019 Pattren": "2019_pattern",
    "2019_pattren": "2019_pattern",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True, width=120)


def tokenise(value: str) -> list[str]:
    prepared = value.strip()
    prepared = re.sub(r"&", " and ", prepared)
    prepared = re.sub(r"\+", " plus ", prepared)
    prepared = re.sub(r"@", " at ", prepared)
    prepared = re.sub(r"%", " percent ", prepared)
    prepared = re.sub(r"[^A-Za-z0-9]+", " ", prepared)
    return [token for token in prepared.split() if token]


def normalize_name(value: str, level: str = "subject") -> str:
    separator = "-" if level == "branch" else "_"
    normalized_tokens: list[str] = []
    for token in tokenise(value):
        upper = token.upper()
        if upper in ROMAN_NUMERALS:
            normalized_tokens.append(upper)
        else:
            normalized_tokens.append(token.lower())
    return separator.join(normalized_tokens)


def code_for_name(normalized: str) -> str:
    tokens = [token for token in re.split(r"[-_]+", normalized) if token]
    prefix: list[str] = []
    suffix: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in {"ele", "elective"} and next_token in ROMAN_NUMERALS:
            suffix.append(f"e{next_token}")
            index += 2
            continue
        if token in ROMAN_NUMERALS:
            prefix.append(token)
        elif token.isdigit():
            prefix.append(token)
        elif token in CODE_SKIP_WORDS:
            pass
        else:
            prefix.append(token[0])
        index += 1
    base = "".join(prefix)
    return f"{base}_{'_'.join(suffix)}" if suffix else base


def pattern_aliases(data: dict[str, Any]) -> dict[str, str]:
    aliases = dict(DEFAULT_PATTERN_ALIASES)
    aliases.update((data.get("rules") or {}).get("pattern_aliases") or {})
    return aliases


def normalized_alias(data: dict[str, Any], folder_name: str) -> str | None:
    aliases = pattern_aliases(data)
    if folder_name in aliases:
        return str(aliases[folder_name])
    normalized = normalize_name(folder_name, "pattern")
    return aliases.get(normalized)


def branch_code_map(data: dict[str, Any]) -> dict[str, str]:
    codes: dict[str, str] = {
        "first-year": "fy",
        "m-b-a": "mba",
        "honors-course": "hc",
    }
    for entry in (data.get("name_registry") or {}).values():
        if not isinstance(entry, dict):
            continue
        normalized = entry.get("normalized")
        code = entry.get("code")
        if normalized and code:
            codes[str(normalized)] = str(code)
    return codes


def strip_subject_suffix(normalized: str, branch_code: str, year: str = "") -> str:
    suffix = f"_{branch_code}"
    if year and normalized.endswith(f"{suffix}_{year}"):
        return normalized[: -len(f"{suffix}_{year}")]
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)]
    return normalized


def path_under_base(path: Path) -> tuple[str, list[str]] | None:
    resolved = path.resolve()
    for base_name, base_path in (("papers", PROJECT_ROOT / "papers"), ("incoming", INCOMING_DIR)):
        try:
            return base_name, list(resolved.relative_to(base_path.resolve()).parts)
        except ValueError:
            continue
    return None


def local_subject_metadata(data: dict[str, Any], path: Path) -> dict[str, str] | None:
    under_base = path_under_base(path)
    if under_base is None:
        return None
    _base_name, parts = under_base
    if not parts:
        return None

    normalized_parts = [normalized_alias(data, part) or normalized_for_folder(data, part) for part in parts]
    branch = normalized_parts[0]
    codes = branch_code_map(data)
    branch_code = codes.get(branch, code_for_name(branch.replace("-", "_")))

    if branch == "first-year" and len(normalized_parts) == 3:
        pattern, subject = normalized_parts[1], normalized_parts[2]
        return {"branch": branch, "branch_code": branch_code, "year": "", "pattern": pattern, "subject": subject}
    if branch == "m-b-a" and len(normalized_parts) == 4:
        semester, pattern, subject = normalized_parts[1], normalized_parts[2], normalized_parts[3]
        return {"branch": branch, "branch_code": branch_code, "year": semester, "pattern": pattern, "subject": subject}
    if branch == "honors-course" and len(normalized_parts) == 3:
        year, subject = normalized_parts[1], normalized_parts[2]
        return {"branch": branch, "branch_code": branch_code, "year": year, "pattern": "honors", "subject": subject}
    if len(normalized_parts) == 4:
        year, pattern, subject = normalized_parts[1], normalized_parts[2], normalized_parts[3]
        return {"branch": branch, "branch_code": branch_code, "year": year, "pattern": pattern, "subject": subject}
    return None


def build_subject_collision_keys(data: dict[str, Any], root: Path) -> set[tuple[str, str]]:
    groups: dict[tuple[str, str], set[str]] = {}
    for current in sorted([item for item in root.rglob("*") if item.is_dir()]):
        metadata = local_subject_metadata(data, current)
        if not metadata:
            continue
        subject_base = strip_subject_suffix(metadata["subject"], metadata["branch_code"], metadata["year"])
        subject_key = f"{subject_base}_{metadata['branch_code']}"
        group_key = (metadata["pattern"], subject_key)
        groups.setdefault(group_key, set()).add(metadata["year"])
    return {group_key for group_key, years in groups.items() if len(years) > 1}


def normalized_for_path(data: dict[str, Any], path: Path, collision_keys: set[tuple[str, str]]) -> str:
    alias = normalized_alias(data, path.name)
    if alias:
        return alias

    metadata = local_subject_metadata(data, path)
    if metadata:
        subject_base = strip_subject_suffix(metadata["subject"], metadata["branch_code"], metadata["year"])
        subject_key = f"{subject_base}_{metadata['branch_code']}"
        if (metadata["pattern"], subject_key) in collision_keys and metadata["year"]:
            return f"{subject_key}_{metadata['year']}"
        return subject_key

    return normalized_for_folder(data, path.name)


def entry_for(
    original: str,
    folder_id: str = "",
    level: str = "subject",
    existing: dict[str, Any] | None = None,
    normalized_override: str = "",
) -> dict[str, Any]:
    existing = existing or {}
    aliases = DEFAULT_PATTERN_ALIASES if level == "pattern" else {}
    normalized = normalized_override or aliases.get(original) or existing.get("normalized") or normalize_name(original, level)
    code = code_for_name(normalized)
    entry = {"normalized": normalized, "code": code}
    if folder_id:
        entry["id"] = folder_id
    elif existing.get("id"):
        entry["id"] = existing["id"]
    return entry


def register_name(
    registry: dict[str, Any],
    original: str,
    folder_id: str = "",
    level: str = "subject",
    normalized_override: str = "",
) -> dict[str, Any]:
    entry = entry_for(original, folder_id, level, registry.get(original), normalized_override)
    registry[original] = entry
    return entry


def mapping_entry(
    registry: dict[str, Any],
    original: str,
    folder_id: str = "",
    level: str = "subject",
    normalized_override: str = "",
) -> dict[str, Any]:
    entry = register_name(registry, original, folder_id, level, normalized_override)
    result = {"id": entry.get("id", folder_id), "normalized": entry["normalized"], "code": entry["code"]}
    return {key: value for key, value in result.items() if value}


def branch_subject_normalized(subject_name: str, branch_code: str) -> str:
    subject_base = normalize_name(subject_name, "subject")
    return f"{strip_subject_suffix(subject_base, branch_code)}_{branch_code}"


def register_branch_subject(
    registry: dict[str, Any],
    subject_name: str,
    folder_id: str,
    branch_code: str,
) -> dict[str, Any]:
    scoped_normalized = branch_subject_normalized(subject_name, branch_code)
    # Keep the display-name entry generic, because the same subject name can exist in
    # multiple branches. Register the actual normalized folder name as the scoped key.
    register_name(registry, subject_name, folder_id, "subject")
    entry = entry_for(scoped_normalized, folder_id, "subject", registry.get(scoped_normalized), scoped_normalized)
    registry[scoped_normalized] = entry
    return {"id": folder_id, "normalized": scoped_normalized, "code": entry["code"]}


def build_standard(mapping: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {"branches": {}}
    for branch_name, branch in (mapping.get("branches") or {}).items():
        branch_out = mapping_entry(registry, branch_name, branch.get("folder_id", ""), "branch") | {"years": {}}
        branch_code = branch_out["code"]
        for year_name, year in (branch.get("years") or {}).items():
            year_out = mapping_entry(registry, year_name, year.get("folder_id", ""), "year") | {"patterns": {}}
            for pattern_name, pattern in (year.get("patterns") or {}).items():
                pattern_out = mapping_entry(registry, pattern_name, pattern.get("folder_id", ""), "pattern") | {"subjects": {}}
                for subject_name, subject in (pattern.get("subjects") or {}).items():
                    pattern_out["subjects"][subject_name] = register_branch_subject(
                        registry,
                        subject_name,
                        subject.get("folder_id", ""),
                        branch_code,
                    )
                year_out["patterns"][pattern_name] = pattern_out
            branch_out["years"][year_name] = year_out
        output["branches"][branch_name] = branch_out
    return output


def build_first_year(mapping: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    output = mapping_entry(registry, "First Year", mapping.get("folder_id", ""), "branch") | {"patterns": {}}
    branch_code = output["code"]
    for pattern_name, pattern in (mapping.get("patterns") or {}).items():
        pattern_out = mapping_entry(registry, pattern_name, pattern.get("folder_id", ""), "pattern") | {"subjects": {}}
        for subject_name, subject in (pattern.get("subjects") or {}).items():
            pattern_out["subjects"][subject_name] = register_branch_subject(registry, subject_name, subject.get("folder_id", ""), branch_code)
        output["patterns"][pattern_name] = pattern_out
    return output


def build_mba(mapping: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    output = mapping_entry(registry, "M.B.A", mapping.get("folder_id", ""), "branch") | {"semesters": {}}
    branch_code = output["code"]
    for semester_name, semester in (mapping.get("semesters") or {}).items():
        semester_out = mapping_entry(registry, semester_name, semester.get("folder_id", ""), "year") | {"patterns": {}}
        for pattern_name, pattern in (semester.get("patterns") or {}).items():
            pattern_out = mapping_entry(registry, pattern_name, pattern.get("folder_id", ""), "pattern") | {"subjects": {}}
            for subject_name, subject in (pattern.get("subjects") or {}).items():
                pattern_out["subjects"][subject_name] = register_branch_subject(registry, subject_name, subject.get("folder_id", ""), branch_code)
            semester_out["patterns"][pattern_name] = pattern_out
        output["semesters"][semester_name] = semester_out
    return output


def build_honors(mapping: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    branch_meta = (mapping.get("folders") or {}).get("Honors Course", {})
    output = mapping_entry(registry, "Honors Course", branch_meta.get("folder_id", ""), "branch") | {"years": {}}
    branch_code = output["code"]
    for folder_path, meta in (mapping.get("folders") or {}).items():
        parts = [part for part in folder_path.split("/") if part]
        if len(parts) == 2:
            output["years"].setdefault(parts[1], mapping_entry(registry, parts[1], meta.get("folder_id", ""), "year") | {"subjects": {}})
        elif len(parts) == 3:
            year_out = output["years"].setdefault(parts[1], mapping_entry(registry, parts[1], "", "year") | {"subjects": {}})
            year_out["subjects"][parts[2]] = register_branch_subject(registry, parts[2], meta.get("folder_id", ""), branch_code)
    return output


def create_folder_names() -> dict[str, Any]:
    existing = read_yaml(FOLDER_NAMES_PATH)
    registry = dict(existing.get("name_registry") or {})
    data: dict[str, Any] = {
        "schema_version": 1,
        "rules": {
            "branch_separator": "-",
            "other_separator": "_",
            "lowercase": True,
            "ampersand": "and",
            "pattern_aliases": DEFAULT_PATTERN_ALIASES,
            "preserve_roman_numerals": sorted(ROMAN_NUMERALS),
        },
        "name_registry": registry,
        "standard": build_standard(read_json(MAPPING_DIR / "sync_mapping.json"), registry),
        "first_year": build_first_year(read_json(MAPPING_DIR / "first_year_mapping.json"), registry),
        "mba": build_mba(read_json(MAPPING_DIR / "mba.json"), registry),
        "honors_course": build_honors(read_json(MAPPING_DIR / "honors_course_mapping.json"), registry),
        "incoming_unmapped": existing.get("incoming_unmapped") or {},
    }
    data["name_registry"] = dict(sorted(registry.items(), key=lambda item: item[0].lower()))
    write_yaml(FOLDER_NAMES_PATH, data)
    return data


def load_or_create_folder_names() -> dict[str, Any]:
    if not FOLDER_NAMES_PATH.exists():
        return create_folder_names()
    return read_yaml(FOLDER_NAMES_PATH)


def normalized_for_folder(data: dict[str, Any], folder_name: str) -> str:
    alias = normalized_alias(data, folder_name)
    if alias:
        return alias
    registry = data.setdefault("name_registry", {})
    known_normalized = {
        str(value.get("normalized"))
        for value in registry.values()
        if isinstance(value, dict) and value.get("normalized")
    }
    if folder_name in known_normalized:
        return folder_name
    entry = registry.get(folder_name)
    if entry:
        return str(entry["normalized"])
    duplicate = re.match(r"^(.+)_\d+$", folder_name)
    if duplicate:
        base = duplicate.group(1)
        if base in known_normalized:
            return base
    incoming_unmapped = data.setdefault("incoming_unmapped", {})
    entry = entry_for(folder_name, level="subject", existing=incoming_unmapped.get(folder_name))
    incoming_unmapped[folder_name] = entry
    registry[folder_name] = entry
    return str(entry["normalized"])


def unique_target(source: Path, target: Path) -> Path:
    if target.exists() and source.exists():
        try:
            if source.samefile(target):
                return target
        except OSError:
            pass
    if source.is_dir() and target.is_dir():
        return target
    if not target.exists():
        return target
    if source.parent == target.parent and source.name.lower() == target.name.lower():
        return target
    counter = 2
    while True:
        candidate = target.with_name(f"{target.name}_{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def perform_rename(source: Path, target: Path) -> None:
    if source.is_dir() and target.is_dir():
        merge_directories(source, target)
        return
    if source.parent == target.parent and source.name.lower() == target.name.lower() and source.name != target.name:
        temp = source.with_name(f"{source.name}.__rename_tmp__")
        counter = 2
        while temp.exists():
            temp = source.with_name(f"{source.name}.__rename_tmp__{counter}")
            counter += 1
        source.rename(temp)
        temp.rename(target)
    else:
        source.rename(target)


def merge_directories(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir(), key=lambda item: item.name.lower()):
        child_target = target / child.name
        if child.is_dir() and child_target.is_dir():
            merge_directories(child, child_target)
        else:
            child.rename(unique_target(child, child_target))
    source.rmdir()


def rename_incoming(path: Path, dry_run: bool = False) -> list[tuple[Path, Path]]:
    data = load_or_create_folder_names()
    root = path.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if root.is_file():
        raise ValueError(f"Expected a directory path, got file: {path}")

    changes: list[tuple[Path, Path]] = []
    collision_keys = build_subject_collision_keys(data, root)
    for current in sorted([item for item in root.rglob("*") if item.is_dir()], key=lambda item: len(item.parts), reverse=True):
        normalized = normalized_for_path(data, current, collision_keys)
        if normalized == current.name:
            continue
        target = unique_target(current, current.with_name(normalized))
        changes.append((current, target))
        if not dry_run:
            perform_rename(current, target)
            tracking.advance_path_prefix(display_path(current), display_path(target))

    normalized_root = normalized_for_path(data, root, collision_keys)
    if root.name != normalized_root and root != INCOMING_DIR.resolve():
        target = unique_target(root, root.with_name(normalized_root))
        changes.append((root, target))
        if not dry_run:
            perform_rename(root, target)
            tracking.advance_path_prefix(display_path(root), display_path(target))

    if not dry_run:
        write_yaml(FOLDER_NAMES_PATH, data)
    return changes


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create folder name mappings and normalize folders under incoming/.",
        epilog=(
            "Examples: python3 tools/rename_folders.py --create | "
            "python3 tools/rename_folders.py --dry-run | "
            "python3 tools/rename_folders.py --path \"incoming/Artificial Intelligence and Data Science\""
        ),
    )
    parser.add_argument("--create", action="store_true", help="Create or update mapping/folder_names.yml from mapping JSON files.")
    parser.add_argument("--path", default=str(INCOMING_DIR), help="Incoming subfolder to rename. Defaults to incoming/.")
    parser.add_argument("--dry-run", action="store_true", help="Show renames without changing folders.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.create:
            data = create_folder_names()
            print(f"Updated {FOLDER_NAMES_PATH.relative_to(PROJECT_ROOT)} with {len(data.get('name_registry', {}))} names.")
            return 0
        changes = rename_incoming(Path(args.path), dry_run=args.dry_run)
        action = "Would rename" if args.dry_run else "Renamed"
        for source, target in changes:
            print(f"{action}: {display_path(source)} -> {display_path(target)}")
        print(f"{action} {len(changes)} folders.")
        return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
