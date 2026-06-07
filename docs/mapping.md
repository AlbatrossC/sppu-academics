# Mapping Structure — `tools/map.py`

`mapping/` contains the source-of-truth folder structure for all Drive branches. These JSON files are committed and must survive a clone.

---

## When to Use `map.py`

Use `tools/map.py` for **full mapping rebuilds** — when the Drive root changes, branches are added, or the schema needs to be regenerated from scratch.

For **incremental folder changes** (new subjects, new patterns), prefer `tools/sync.py --folders`, which is lighter and only appends changes to `changelog/folder.md`.

---

## Commands

```bash
# Build the entire mapping from scratch
python3 tools/map.py build

# Refresh the full mapping (incremental, preserves existing data)
python3 tools/map.py refresh

# Refresh only selected top-level branches
python3 tools/map.py refresh --branch "Mechanical Engineering"
python3 tools/map.py refresh --branch "Mechanical Engineering" --branch "Robotics and Automation"
```

After any mapping refresh, always rebuild the name registry:

```bash
python3 tools/rename_folders.py --create
```

---

## Mapping Files

| File | Family | Structure |
|---|---|---|
| `mapping/sync_mapping.json` | Standard branches | `Branch / Year / Pattern / Subject` |
| `mapping/first_year_mapping.json` | First Year | `First Year / Pattern / Subject` |
| `mapping/mba.json` | MBA | `M.B.A / Semester / Pattern / Subject` |
| `mapping/honors_course_mapping.json` | Honors Course | `Honors Course / Year / Subject` |
| `mapping/folder_names.yml` | All families | Shared name registry |
| `mapping/semester_mapping.yml` | All families | Approved semester assignments |

---

## Standard Branch JSON Schema

```json
{
  "schema_version": 2,
  "generated_at": "2024-01-15T10:30:00Z",
  "root": {
    "folder_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM"
  },
  "branches": {
    "Computer Engineering": {
      "folder_id": "1abc123def456",
      "parent_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM",
      "path": "Computer Engineering",
      "years": {
        "TE": {
          "folder_id": "1ghi789jkl012",
          "parent_id": "1abc123def456",
          "path": "Computer Engineering/TE",
          "patterns": {
            "2019 Pattern": {
              "folder_id": "1mno345pqr678",
              "parent_id": "1ghi789jkl012",
              "path": "Computer Engineering/TE/2019 Pattern",
              "subjects": {
                "Web Technology": {
                  "folder_id": "1stu901vwx234",
                  "parent_id": "1mno345pqr678",
                  "path": "Computer Engineering/TE/2019 Pattern/Web Technology"
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

---

## First Year JSON Schema

First Year skips the `years` level — it goes directly from the branch to `patterns`:

```json
{
  "schema_version": 2,
  "generated_at": "2024-01-15T10:30:00Z",
  "root": { "folder_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM" },
  "branch": "First Year",
  "folder_id": "1fy_root_id",
  "parent_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM",
  "path": "First Year",
  "patterns": {
    "2019 Pattern": {
      "folder_id": "1fy_pat_id",
      "parent_id": "1fy_root_id",
      "path": "First Year/2019 Pattern",
      "subjects": {
        "Engineering Mathematics - I": {
          "folder_id": "1fy_sub_id",
          "parent_id": "1fy_pat_id",
          "path": "First Year/2019 Pattern/Engineering Mathematics - I"
        }
      }
    }
  },
  "exceptions": {}
}
```

---

## MBA JSON Schema

MBA uses `semesters` instead of `years`:

```json
{
  "schema_version": 2,
  "generated_at": "2024-01-15T10:30:00Z",
  "root": { "folder_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM" },
  "branch": "M.B.A",
  "folder_id": "1mba_root_id",
  "parent_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM",
  "path": "M.B.A",
  "semesters": {
    "SEM - II": {
      "folder_id": "1mba_sem_id",
      "parent_id": "1mba_root_id",
      "path": "M.B.A/SEM - II",
      "patterns": {
        "2019 Pattern": {
          "folder_id": "1mba_pat_id",
          "parent_id": "1mba_sem_id",
          "path": "M.B.A/SEM - II/2019 Pattern",
          "subjects": {
            "Financial Management": {
              "folder_id": "1mba_sub_id",
              "parent_id": "1mba_pat_id",
              "path": "M.B.A/SEM - II/2019 Pattern/Financial Management"
            }
          }
        }
      }
    }
  }
}
```

MBA subjects under specialization containers are flattened under their pattern and keep an additional `drive_path` and `source_group` field.

---

## Honors Course JSON Schema

Honors Course goes `Year → Subject` without a `patterns` level:

```json
{
  "schema_version": 2,
  "generated_at": "2024-01-15T10:30:00Z",
  "root": { "folder_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM" },
  "branch": "Honors Course",
  "folder_id": "1hc_root_id",
  "years": {
    "TE": {
      "folder_id": "1hc_year_id",
      "parent_id": "1hc_root_id",
      "path": "Honors Course/TE",
      "subjects": {
        "Artificial Intelligence": {
          "folder_id": "1hc_sub_id",
          "parent_id": "1hc_year_id",
          "path": "Honors Course/TE/Artificial Intelligence"
        }
      }
    }
  },
  "exceptions": {}
}
```

---

## Excluded Branches

### ME (Master of Engineering)

`ME` is intentionally excluded from all mapping files. The mapper drops any path where the second level is `ME`:

```
Computer Engineering / ME / Computer / 2017 Pattern / Machine Learning   ← dropped
E & TC Engineering / ME / VLSI & Embedded Systems / 2017 Pattern / ASIC Design   ← dropped
Robotics and Automation / ME / Robotics & Automation / 2017 Pattern / Machine Vision System   ← dropped
```

These paths are not normalized, not synced, and not present under `branches`.

---

## Exceptions Section

`exceptions` is an audit section for Drive folders that do not fit the standard hierarchy:

| Reason key | Meaning |
|---|---|
| `leaf_folder_without_pattern` | Folder stops at `Branch / Year / Subject` (no pattern level) |
| `leaf_folder_without_pattern_or_subject` | Folder stops at `Branch / Year` |
| `nonstandard_container_depth` | A deeper Drive container preserved only as audit metadata |

---

## `mapping/folder_names.yml` Structure

`mapping/folder_names.yml` is the shared name registry. It is built by `tools/rename_folders.py --create` from the four mapping JSON files.

```yaml
standard:
  branches:
    Computer Engineering:
      id: "1abc123def456"
      normalized: "computer-engineering"
      code: "comp"
      years:
        TE:
          normalized: "te"
          code: "te"
          patterns:
            "2019 Pattern":
              normalized: "2019_pattern"
              code: "2019p"
              subjects:
                Web Technology:
                  normalized: "web_technology_comp"
                  code: "wt"

first_year:
  patterns:
    "2019 Pattern":
      normalized: "2019_pattern"
      code: "2019p"
      subjects:
        "Engineering Mathematics - I":
          normalized: "engineering_mathematics_I_fy"
          code: "em1"

mba:
  semesters:
    "SEM - II":
      normalized: "sem_II"
      patterns:
        "2019 Pattern":
          subjects:
            Financial Management:
              normalized: "financial_management"
              code: "fm"

honors_course:
  years:
    TE:
      normalized: "te"
      subjects:
        "Artificial Intelligence":
          normalized: "artificial_intelligence_hc"
          code: "ai"

name_registry:
  "Computer Engineering":
    normalized: "computer-engineering"
    code: "comp"
  "2019 Pattern":
    normalized: "2019_pattern"
    code: "2019p"
```

The flat `name_registry` lets `rename_folders.py` quickly look up any original folder name by string without traversing the full tree.

---

## Validate Mappings

Run a non-network sanity check before any Drive API call:

```bash
python3 tools/validate_mappings.py
```

This checks:
- JSON schema version
- Required fields present
- No duplicate folder IDs
- `folder_names.yml` entries match mapping JSON entries
