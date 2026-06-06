# Rename Incoming Folders

> For agent-specific workflows and use cases, see [AGENTIC.md](../AGENTIC.md).

`tools/rename_folders.py` normalizes folder names under `incoming/`.

It uses:

```text
mapping/folder_names.yml
```

as the source of truth for original folder names, normalized folder names, short codes, and Drive folder IDs.

## Create The Name Registry

Run this after mapping JSON files are created or refreshed:

```bash
python3 tools/rename_folders.py --create
```

This reads:

```text
mapping/sync_mapping.json
mapping/first_year_mapping.json
mapping/mba.json
mapping/honors_course_mapping.json
```

and updates:

```text
mapping/folder_names.yml
```

Existing entries are preserved. New folder names are appended.

## Naming Rules

Branches use hyphens:

```text
Artificial Intelligence and Data Science -> artificial-intelligence-and-data-science
```

Years, patterns, and subjects use underscores:

```text
2019 Pattern -> 2019_pattern
Deep Learning - Ele V -> deep_learning_ele_V
```

Symbols are normalized:

```text
& -> and
+ -> plus
@ -> at
% -> percent
```

Roman numerals are preserved:

```text
Ele V -> ele_V
Engineering Mathematics - II -> engineering_mathematics_II
```

Each name also gets a short code:

```text
artificial-intelligence-and-data-science -> aids
deep_learning_ele_V -> dl_eV
```

## YAML Structure

The YAML file is structured by mapping family:

```text
standard:
  branches:
    Branch:
      years:
        Year:
          patterns:
            Pattern:
              subjects:
                Subject:

first_year:
  patterns:
    Pattern:
      subjects:
        Subject:

mba:
  semesters:
    Semester:
      patterns:
        Pattern:
          subjects:
            Subject:

honors_course:
  years:
    Year:
      subjects:
        Subject:
```

Every entry includes:

```text
id
normalized
code
```

There is also a flat `name_registry` so the rename command can quickly map any original folder name to its normalized name.

## Preview Renames

Preview all folder renames under `incoming/`:

```bash
python3 tools/rename_folders.py --dry-run
```

Preview one folder subtree:

```bash
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science" --dry-run
```

## Rename Folders

Rename every folder under `incoming/`:

```bash
python3 tools/rename_folders.py
```

Rename one folder subtree:

```bash
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science"
```

Only folders are renamed. PDF filenames are not changed.

If the normalized destination already exists, the command merges the source directory into that destination instead of creating a numbered sibling such as `_2`. This is important after a partial sync where Drive display names and normalized local names both exist for the same branch.

## Unknown Incoming Names

If a folder exists in `incoming/` but not in `mapping/folder_names.yml`, the script normalizes it using the same rules and appends it to:

```text
incoming_unmapped
```

It also adds the name to `name_registry`.

## Agent Notes

Run `python3 tools/rename_folders.py --create` after mapping refreshes.

Run `python3 tools/rename_folders.py --dry-run` before large rename operations.

Use `--path` for safer scoped renames.

Do not manually rename `incoming/` folders if you want repeatable normalization; update `mapping/folder_names.yml` instead.
