# Architecture Overview

The SPPU PYQ Sync Toolkit turns a public Google Drive archive of exam question papers into a normalized local `papers/` directory and publishable frontend manifest JSON.

## Pipeline at a Glance

```
Drive
  → map.py          (discover folder structure → mapping/*.json)
  → sync.py --folders   (detect new/changed Drive folders → changelog/folder.md)
  → sync.py --files     (detect new/changed PDFs → changelog/files.md)
  → sync.py --files --apply  (download PDFs → incoming/)
  → rename_folders.py  (normalize incoming/ folder names)
  → rename_files.py    (review PDF metadata → changelog/rename.json)
  → rename_files.py --apply  (rename PDFs in incoming/)
  → verify.py          (promote valid rows to VERIFIED)
  → move.py            (move VERIFIED files → papers/)
  → upload_pipeline.py (publish papers/ → R2 + Cloudinary → manifest/*.json)
```

Every write-heavy step is **review-first** where practical. Review commands scan Drive and write changelog files. Apply commands read those changelog files and do not re-scan Drive.

> **Always run from the project root.**

---

## Folder Families

The archive has **four distinct folder families** with different hierarchy depths. You must know which family a scope belongs to before running any scoped command.

### Standard Branches (4 levels)

```
Branch / Year / Pattern / Subject
```

**Mapping file:** `mapping/sync_mapping.json`  
**Incoming path:** `incoming/<branch>/<year>/<pattern>/<subject>/`

**Active standard branches:**

| Display Name | Normalized Incoming |
|---|---|
| Artificial Intelligence and Data Science | `artificial-intelligence-and-data-science` |
| Artificial Intelligence and Machine Learning | `artificial-intelligence-and-machine-learning` |
| Civil Engineering | `civil-engineering` |
| Computer Engineering | `computer-engineering` |
| E & TC Engineering | `e-and-tc-engineering` |
| Electrical Engineering | `electrical-engineering` |
| Electronics & Computer Engineering | `electronics-and-computer-engineering` |
| IT Engineering | `it-engineering` |
| Mechanical Engineering | `mechanical-engineering` |
| Robotics and Automation | `robotics-and-automation` |

**Example path:**
```
Artificial Intelligence and Data Science / BE / 2019 Pattern / Machine Learning
  → incoming/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/
```

> **ME (Master of Engineering) is excluded from the main mapping.** Any Drive path where the second level is `ME` is dropped and not synced.

---

### First Year (3 levels — NO year tier)

```
First Year / Pattern / Subject
```

**Mapping file:** `mapping/first_year_mapping.json`  
**Incoming path:** `incoming/first-year/<pattern>/<subject>/`

> [!IMPORTANT]
> First Year does NOT have a year level (BE/TE/SE). It goes directly from `First Year` → `Pattern` → `Subject`.

**Example path:**
```
First Year / 2019 Pattern / Engineering Mathematics - I
  → incoming/first-year/2019_pattern/engineering_mathematics_I_fy/
```

---

### MBA (4 levels — uses Semester instead of Year)

```
M.B.A / Semester / Pattern / Subject
```

**Mapping file:** `mapping/mba.json`  
**Incoming path:** `incoming/m-b-a/<semester>/<pattern>/<subject>/`

Semesters are named `SEM - I`, `SEM - II`, `SEM - III`, `SEM - IV`.

Some MBA subjects live under specialization sub-folders on Drive but are **flattened** under their pattern in the mapping. These entries have `drive_path` and `source_group` fields.

> [!IMPORTANT]
> MBA uses Semester names like `SEM - I`, `SEM - II`, etc. **instead of year codes.**

**Example path:**
```
M.B.A / SEM - II / 2019 Pattern / Financial Management
  → incoming/m-b-a/sem_II/2019_pattern/financial_management/
```

---

### Honors Course (3 levels — NO pattern tier)

```
Honors Course / Year / Subject
```

**Mapping file:** `mapping/honors_course_mapping.json`  
**Incoming path:** `incoming/honors-course/<year>/<subject>/`

> [!IMPORTANT]
> Honors Course does NOT have a pattern level. It goes directly from `Year` (BE, TE) → `Subject`. The year folder code is used as `pattern_code` during rename.

**Example path:**
```
Honors Course / TE / Artificial Intelligence
  → incoming/honors-course/te/artificial_intelligence_hc/
```

---

## Folder Name Normalization Rules

After `rename_folders.py` runs, folder names are normalized:

| Level | Separator | Example |
|---|---|---|
| Branch (top level) | Hyphens | `artificial-intelligence-and-data-science` |
| Year, Pattern, Subject | Underscores | `2019_pattern`, `deep_learning_ele_V` |

**Symbol replacements:**

| Symbol | Becomes |
|---|---|
| `&` | `and` |
| `+` | `plus` |
| `@` | `at` |
| `%` | `percent` |

**Roman numerals are preserved in uppercase:** `Ele V` → `ele_V`, `Engineering Mathematics - II` → `engineering_mathematics_II`

**Reference table:**

| Drive Name | Normalized Incoming Path |
|---|---|
| `E & TC Engineering` | `e-and-tc-engineering` |
| `2019 Pattern` | `2019_pattern` |
| `BE` | `be` |
| `TE` | `te` |
| `SE` | `se` |
| `First Year` | `first-year` |
| `M.B.A` | `m-b-a` |
| `Honors Course` | `honors-course` |
| `Deep Learning - Ele V` | `deep_learning_ele_V` |

---

## Stage Lifecycle (SQLite Tracking)

`tracking/manifest.db` is the durable local file tracker. Each Google Drive file ID has exactly one row that moves through these stages:

```
DISCOVERED → DOWNLOADED → FOLDER_RENAMED → FILE_RENAMED → VERIFIED → MOVED
```

Side states:
```
NEEDS_REVIEW   ← file could not be safely renamed or has a naming collision
MISSING        ← file expected but not found on disk
```

| Stage | Meaning |
|---|---|
| `DISCOVERED` | Drive file metadata known; download pending |
| `DOWNLOADED` | PDF exists under `incoming/` |
| `FOLDER_RENAMED` | Incoming folder normalized by `rename_folders.py` |
| `FILE_RENAMED` | `rename_files.py --apply` produced a normalized filename |
| `VERIFIED` | `verify.py` accepted the path and filename |
| `MOVED` | File is in `papers/` |
| `NEEDS_REVIEW` | Rename failed or produced a duplicate; file is in `needs_review/` |
| `MISSING` | File cannot be found at its recorded path |

**Important SQLite columns:**

| Column | Purpose |
|---|---|
| `file_id` | Google Drive file ID (primary key) |
| `current_stage` | Current lifecycle stage |
| `current_path` | Where the file is now |
| `expected_path` | Where the file should be in `papers/` |
| `retry_count` | Number of failed rename review attempts |
| `review_reason` | Why a file is in `NEEDS_REVIEW` |

---

## Tool Effects Summary

| Tool | Inputs | Outputs & Side Effects |
|---|---|---|
| `tools/validate_mappings.py` | Mapping files only | Non-network sanity check; no writes |
| `tools/map.py build/refresh` | Drive root from `config.json` | Rebuilds `mapping/*.json` |
| `tools/sync.py --folders` | Drive, mapping JSON | Writes `changelog/folder.md` |
| `tools/sync.py --folders --apply` | `changelog/folder.md` | Updates mapping JSON |
| `tools/sync.py --files` | Drive, mapping JSON, SQLite | Writes `changelog/files.md` |
| `tools/sync.py --files --apply` | `changelog/files.md` | Downloads to `incoming/`, updates SQLite |
| `tools/rename_folders.py --create` | Mapping JSON | Updates `mapping/folder_names.yml` |
| `tools/rename_folders.py` | `incoming/`, folder registry | Renames/merges folders under `incoming/` |
| `tools/rename_files.py` | `incoming/`, folder registry, PDF/OCR/Groq | Writes `changelog/rename.md` + `changelog/rename.json` |
| `tools/rename_files.py --apply` | `changelog/rename.json` | Renames PDFs; moves unsafe files to `needs_review/`; updates SQLite |
| `tools/verify.py` | SQLite + filesystem | Promotes valid rows to `VERIFIED`; records review/missing states |
| `tools/move.py` | SQLite + filesystem | Moves `VERIFIED` files to `papers/` |
| `tools/upload_pipeline.py` | `papers/`, upload env vars | Uploads to R2/Cloudinary; writes `manifest/*.json` |
| `tools/status.py` | SQLite + filesystem | Writes and prints `docs/status.md` |
| `tools/semester_mapping.py` | `papers/`, syllabus research | Stages semester assignments; applies to `mapping/semester_mapping.yml` |
| `tools/pipeline.py` | Multiple tools | Orchestrates the above tools in sequence |

---

## Key Data Files

| File | Purpose |
|---|---|
| `config.json` | Drive root folder ID and request settings |
| `mapping/sync_mapping.json` | Standard branch folder mapping |
| `mapping/first_year_mapping.json` | First Year folder mapping |
| `mapping/mba.json` | MBA folder mapping |
| `mapping/honors_course_mapping.json` | Honors Course folder mapping |
| `mapping/folder_names.yml` | Shared name registry: Drive names → normalized names, codes, IDs |
| `mapping/semester_mapping.yml` | Approved semester assignments per subject |
| `mapping/local/**/*.json` | Legacy per-pattern metadata; may be absent on fresh installs |
| `changelog/folder.md` | Pending folder changes (JSON block inside) |
| `changelog/files.md` | Pending file downloads (JSON block inside) |
| `changelog/rename.md` | Pending file renames (human-readable) |
| `changelog/rename.json` | Pending file renames (machine-readable; used by `--apply`) |
| `changelog/semester.md` | Pending semester mappings (JSON block inside) |
| `tracking/manifest.db` | SQLite file tracker (one row per Drive file ID) |
| `tracking/uploads.db` | SQLite upload tracker (one row per PDF in `papers/`) |
| `incoming/` | Temporary raw Drive download mirror |
| `papers/` | Final normalized PDFs |
| `needs_review/` | Files that could not be safely renamed |
| `manifest/` | Frontend JSON manifests for public website |
| `docs/status.md` | Human-readable status report (auto-generated) |

---

## Working / Output Folders

| Folder | Role |
|---|---|
| `incoming/` | Temporary raw Drive mirror; PDFs are renamed here before moving |
| `papers/` | Final archive; files are never overwritten here |
| `needs_review/` | Files that failed renaming or have collisions |
| `changelog/` | All review changelogs (folder, files, rename, semester) |
| `manifest/` | Generated frontend JSON; uploaded with papers |
| `sync_plan/` | Legacy sync plan output (older workflow) |
