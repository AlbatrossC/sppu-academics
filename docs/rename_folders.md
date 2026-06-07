# Rename Incoming Folders — `tools/rename_folders.py`

`tools/rename_folders.py` normalizes folder names under `incoming/`. It uses `mapping/folder_names.yml` as the source of truth for original folder names, normalized names, short codes, and Drive folder IDs.

> **Run this before `rename_files.py`.** PDF filenames are never changed by this tool — only folder names are touched.

---

## Step 1 — Create / Update the Name Registry

Run this after any mapping JSON file is created or refreshed:

```bash
python3 tools/rename_folders.py --create
```

This reads all four mapping files:

```
mapping/sync_mapping.json
mapping/first_year_mapping.json
mapping/mba.json
mapping/honors_course_mapping.json
```

and updates:

```
mapping/folder_names.yml
```

Existing entries are preserved. New folder names are appended. Always run `--create` after:
- `tools/sync.py --folders --apply`
- `tools/map.py build` or `tools/map.py refresh`

---

## Step 2 — Preview (Dry Run)

Preview all folder renames under `incoming/` without touching anything:

```bash
python3 tools/rename_folders.py --dry-run
```

Preview only one branch subtree:

```bash
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science" --dry-run
python3 tools/rename_folders.py --path "incoming/First Year" --dry-run
python3 tools/rename_folders.py --path "incoming/M.B.A" --dry-run
python3 tools/rename_folders.py --path "incoming/Honors Course" --dry-run
```

---

## Step 3 — Apply Renames

Rename every folder under `incoming/`:

```bash
python3 tools/rename_folders.py
```

Rename only one branch subtree:

```bash
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science"
python3 tools/rename_folders.py --path "incoming/First Year"
python3 tools/rename_folders.py --path "incoming/M.B.A"
python3 tools/rename_folders.py --path "incoming/Honors Course"
```

---

## Naming Rules

| Level | Separator | Examples |
|---|---|---|
| Branch (top level) | Hyphens (`-`) | `artificial-intelligence-and-data-science` |
| Year | Underscores (`_`) | `be`, `te`, `se` |
| Pattern | Underscores (`_`) | `2019_pattern`, `2015_pattern` |
| Subject | Underscores (`_`) | `web_technology_comp`, `machine_learning_aids` |

**Symbol replacements:**

| Symbol | Replacement |
|---|---|
| `&` | `and` |
| `+` | `plus` |
| `@` | `at` |
| `%` | `percent` |

**Roman numerals are preserved in uppercase:**

```
Engineering Mathematics - II  →  engineering_mathematics_II
Deep Learning - Ele V         →  deep_learning_ele_V
```

**Concrete examples per family:**

| Family | Drive Name | Normalized |
|---|---|---|
| Standard | `Artificial Intelligence and Data Science` | `artificial-intelligence-and-data-science` |
| Standard | `E & TC Engineering` | `e-and-tc-engineering` |
| Standard | `2019 Pattern` | `2019_pattern` |
| Standard | `Machine Learning` | `machine_learning_aids` |
| First Year | `First Year` | `first-year` |
| First Year | `Engineering Mathematics - I` | `engineering_mathematics_I_fy` |
| MBA | `M.B.A` | `m-b-a` |
| MBA | `SEM - II` | `sem_II` |
| MBA | `Financial Management` | `financial_management` |
| Honors | `Honors Course` | `honors-course` |
| Honors | `Artificial Intelligence` | `artificial_intelligence_hc` |

---

## Merge Behavior

If the normalized destination already exists, the command **merges** the source directory into that destination instead of creating a numbered sibling like `_2`. This handles the common case where a partial sync has both the raw Drive display-name folder and the already-normalized folder for the same branch.

**Example:**

```
incoming/Artificial Intelligence and Data Science/  ← raw (from Drive)
incoming/artificial-intelligence-and-data-science/  ← normalized (already exists)
```

Running `rename_folders.py` merges the raw folder's contents into the normalized one.

---

## Unknown Incoming Names

If a folder exists in `incoming/` but is not in `mapping/folder_names.yml`, the script:

1. Normalizes it using the same rules
2. Appends the name to `incoming_unmapped` in `folder_names.yml`
3. Adds it to `name_registry`

These are not silently skipped — they appear in the output and in the YAML as unmapped entries for review.

---

## `folder_names.yml` Structure

```yaml
standard:
  branches:
    Artificial Intelligence and Data Science:
      id: "1abc..."
      normalized: "artificial-intelligence-and-data-science"
      code: "aids"
      years:
        BE:
          normalized: "be"
          code: "be"
          patterns:
            "2019 Pattern":
              normalized: "2019_pattern"
              code: "2019p"
              subjects:
                Machine Learning:
                  normalized: "machine_learning_aids"
                  code: "ml"

name_registry:
  "Artificial Intelligence and Data Science":
    normalized: "artificial-intelligence-and-data-science"
    code: "aids"
  "2019 Pattern":
    normalized: "2019_pattern"
    code: "2019p"
  "Machine Learning":
    normalized: "machine_learning_aids"
    code: "ml"
```

---

## After Running

Once folder names are normalized, continue with PDF renaming:

```bash
python3 tools/rename_files.py --ocr-workers 1
# review changelog/rename.md
python3 tools/rename_files.py --apply
```

See [rename_files.md](rename_files.md) for details.
