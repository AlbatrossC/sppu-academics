# Mapping Structure

> For agent-specific workflows and use cases, see [AGENTIC.md](../AGENTIC.md).

`mapping/sync_mapping.json` is the main sync mapping. It is organized into this standard shape:

```text
Branch / Year / Pattern / Subject
```

Example:

```text
Computer Engineering / TE / 2019 Pattern / Web Technology
```

The JSON structure is:

```json
{
  "schema_version": 2,
  "generated_at": "timestamp",
  "root": {
    "folder_id": "drive-root-folder-id"
  },
  "branches": {
    "Branch Name": {
      "folder_id": "drive-folder-id",
      "parent_id": "drive-parent-folder-id",
      "path": "Branch Name",
      "years": {
        "BE": {
          "folder_id": "drive-folder-id",
          "parent_id": "drive-parent-folder-id",
          "path": "Branch Name/BE",
          "patterns": {
            "2019 Pattern": {
              "folder_id": "drive-folder-id",
              "parent_id": "drive-parent-folder-id",
              "path": "Branch Name/BE/2019 Pattern",
              "subjects": {
                "Subject Name": {
                  "folder_id": "drive-folder-id",
                  "parent_id": "drive-parent-folder-id",
                  "path": "Branch Name/BE/2019 Pattern/Subject Name"
                }
              }
            }
          }
        }
      }
    }
  },
  "exceptions": {}
}
```

## Standardized Branches

The main mapping now keeps all syncable subjects in the standard four-level format.

Current standard branches:

```text
Artificial Intelligence and Data Science
Artificial Intelligence and Machine Learning
Civil Engineering
Computer Engineering
E & TC Engineering
Electrical Engineering
Electronics & Computer Engineering
IT Engineering
Mechanical Engineering
Robotics and Automation
```

`First Year`, `M.B.A`, and `Honors Course` are intentionally not included as normal branches in `sync_mapping.json`; they are special-case mappings.

## Excluded ME Folders

`ME` is intentionally excluded from the main sync mapping.

The mapper drops any path where the second level is `ME`, for example:

```text
Computer Engineering / ME / Computer / 2017 Pattern / Machine Learning
Computer Engineering / ME / Data Science / 2017 Pattern / Machine Learning
E & TC Engineering / ME / VLSI & Embedded Systems / 2017 Pattern / ASIC Design
Robotics and Automation / ME / Robotics & Automation / 2017 Pattern / Machine Vision System
```

These are not normalized, not synced, and not present under `branches`.

The active year levels in the main mapping are currently `BE`, `SE`, and `TE`.

## Exceptions

`exceptions` is an audit section for folders that do not naturally fit the standard sync hierarchy.

Common reasons:

```text
leaf_folder_without_pattern
```

The folder stops at `Branch / Year / Subject`.

```text
leaf_folder_without_pattern_or_subject
```

The folder stops at `Branch / Year`.

```text
nonstandard_container_depth
```

A deeper Drive container was preserved only as audit metadata.

## Special-Case Mapping Files

These branches are stored separately:

```text
mapping/first_year_mapping.json
mapping/mba.json
mapping/honors_course_mapping.json
```

`mapping/first_year_mapping.json` is categorized as:

```text
First Year / Pattern / Subject
```

Example:

```text
First Year / 2019 Pattern / Engineering Mathematics - I
```

Its JSON structure is:

```json
{
  "schema_version": 2,
  "generated_at": "timestamp",
  "root": {
    "folder_id": "drive-root-folder-id"
  },
  "branch": "First Year",
  "folder_id": "drive-folder-id",
  "parent_id": "drive-parent-folder-id",
  "path": "First Year",
  "patterns": {
    "2019 Pattern": {
      "folder_id": "drive-folder-id",
      "parent_id": "drive-parent-folder-id",
      "path": "First Year/2019 Pattern",
      "subjects": {
        "Engineering Mathematics - I": {
          "folder_id": "drive-folder-id",
          "parent_id": "drive-parent-folder-id",
          "path": "First Year/2019 Pattern/Engineering Mathematics - I"
        }
      }
    }
  },
  "exceptions": {}
}
```

`mapping/honors_course_mapping.json` keeps raw folder paths because its Drive layout is not the same as the branch/year/pattern/subject hierarchy used for syncing.

`mapping/mba.json` is categorized as:

```text
M.B.A / Semester / Pattern / Subject
```

Example:

```text
M.B.A / SEM - II / 2019 Pattern / Financial Management
```

Its JSON structure is:

```json
{
  "schema_version": 2,
  "generated_at": "timestamp",
  "root": {
    "folder_id": "drive-root-folder-id"
  },
  "branch": "M.B.A",
  "folder_id": "drive-folder-id",
  "parent_id": "drive-parent-folder-id",
  "path": "M.B.A",
  "semesters": {
    "SEM - II": {
      "folder_id": "drive-folder-id",
      "parent_id": "drive-parent-folder-id",
      "path": "M.B.A/SEM - II",
      "patterns": {
        "2019 Pattern": {
          "folder_id": "drive-folder-id",
          "parent_id": "drive-parent-folder-id",
          "path": "M.B.A/SEM - II/2019 Pattern",
          "subjects": {
            "Financial Management": {
              "folder_id": "drive-folder-id",
              "parent_id": "drive-parent-folder-id",
              "path": "M.B.A/SEM - II/2019 Pattern/Financial Management"
            }
          }
        }
      }
    }
  }
}
```

MBA subjects that live under specialization containers are flattened under their pattern and keep their original `drive_path` plus `source_group`.

## Commands

Build the full mapping:

```bash
python3 tools/map.py build
```

Refresh the full mapping:

```bash
python3 tools/map.py refresh
```

Refresh only selected top-level branches:

```bash
python3 tools/map.py refresh --branch "Mechanical Engineering" --branch "Robotics and Automation"
```

Create a read-only sync plan from the current mapping:

```bash
python3 tools/sync.py
```

This legacy manifest behavior is standard-branch-only. Modern file recovery should use `tools/sync.py --files` so all four folder families are handled through SQLite tracking.

Download only files listed in the sync plan:

```bash
python3 tools/download_drive.py
```

## Current Snapshot

Regenerate the snapshot after running the next full build, because MBA now writes to `mapping/mba.json` instead of `mapping/sync_mapping.json`.
