# Sync CLI — `tools/sync.py`

`tools/sync.py` is the review-first sync CLI. It detects changes in Google Drive and stages them as changelogs before any local file is touched.

**Two independent modes:**

| Mode | What it does |
|---|---|
| `--folders` | Scans Drive for new/changed folder structure; writes `changelog/folder.md` |
| `--files` | Scans Drive for new/changed PDF files; writes `changelog/files.md` |

> **Design rule:** Review commands scan Drive and write changelogs. Apply commands read changelogs and do not re-scan Drive. Never run `--apply` before reading the changelog.

---

## Folder Sync

### Review

```bash
# Scan all folders across all branches
python3 tools/sync.py --folders

# Scope to one branch
python3 tools/sync.py --folders "Computer Engineering"

# Scope to one year
python3 tools/sync.py --folders "Computer Engineering/TE"

# Special families
python3 tools/sync.py --folders "First Year"
python3 tools/sync.py --folders "M.B.A/SEM - II"
python3 tools/sync.py --folders "Honors Course/TE"
```

Review writes `changelog/folder.md`. That file contains a human-readable table and a machine-readable JSON block between marker comments. New review runs append only unique pending changes; existing pending rows stay until you apply or discard them.

### Apply

```bash
# Apply all pending folder changes (reads changelog/folder.md, updates mapping JSON)
python3 tools/sync.py --folders --apply
```

Apply does not call Drive. It edits the matching mapping JSON file (`sync_mapping.json`, `first_year_mapping.json`, `mba.json`, or `honors_course_mapping.json`).

> [!IMPORTANT]
> After applying folder changes, always run `python3 tools/rename_folders.py --create` to rebuild the name registry.

### Discard

```bash
# Discard all pending folder changes
python3 tools/sync.py --folders --discard

# Discard one specific change (by path or folder ID)
python3 tools/sync.py --folders --discard "Computer Engineering/TE/2019 Pattern/New Subject"
python3 tools/sync.py --folders --discard "1abcDriveFolderId"
```

Discard only edits `changelog/folder.md`. Mapping JSON files are not touched.

---

## File Sync

### Review

```bash
# Scan all files across all branches
python3 tools/sync.py --files

# Standard branch scope
python3 tools/sync.py --files "Artificial Intelligence and Data Science"
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"

# First Year (NO year level — scope directly with pattern)
python3 tools/sync.py --files "First Year"
python3 tools/sync.py --files "First Year/2019 Pattern"

# MBA (uses Semester names, not year codes)
python3 tools/sync.py --files "M.B.A"
python3 tools/sync.py --files "M.B.A/SEM - II"
python3 tools/sync.py --files "M.B.A/SEM - II/2019 Pattern"

# Honors Course (NO pattern level)
python3 tools/sync.py --files "Honors Course"
python3 tools/sync.py --files "Honors Course/TE"

# Speed up with parallel workers
python3 tools/sync.py --files "Artificial Intelligence and Data Science" --workers 4
```

Review writes `changelog/files.md`. Pending rows include Drive file ID, filename, folder path, and the normalized target `incoming/` path.

### Apply (Download)

Three downloader options:

```bash
# Option 1 — Official Google Drive API (default)
python3 tools/sync.py --files --apply

# Option 2 — gdown fallback (use only if API is blocked or rate-limited)
python3 tools/sync.py --files --apply --gdown
python3 tools/sync.py --files --apply --gdown --download-delay 5

# Option 3 — rclone bulk copyurl (fastest for large batches)
python3 tools/sync.py --files --apply --rclone --workers 8
```

**Throttling options** (when Google blocks automated requests):

```bash
python3 tools/sync.py --files --apply --workers 1 --download-delay 10
python3 tools/sync.py --files --apply --workers 1 --download-delay 10 --max-downloads 50
```

After every successful file:
1. The PDF is written under `incoming/`
2. The SQLite row is updated to `DOWNLOADED`
3. The file is removed from `changelog/files.md`

If the run fails midway, rerun the same command — already downloaded files are skipped.

### Discard

```bash
# Discard all pending downloads
python3 tools/sync.py --files --discard

# Discard by file ID, filename, or folder path
python3 tools/sync.py --files --discard "1DriveFileId"
python3 tools/sync.py --files --discard "May_Jun_2025.pdf"
python3 tools/sync.py --files --discard "Artificial Intelligence and Data Science/BE/2019 Pattern/Machine Learning"
```

---

## Scoping Reference

| User says | Correct scope string |
|---|---|
| AIDS / AI&DS | `"Artificial Intelligence and Data Science"` |
| AIML | `"Artificial Intelligence and Machine Learning"` |
| CompE / Comp | `"Computer Engineering"` |
| IT | `"IT Engineering"` |
| Civil | `"Civil Engineering"` |
| E&TC / ENTC | `"E & TC Engineering"` |
| Electrical / EE | `"Electrical Engineering"` |
| Mech | `"Mechanical Engineering"` |
| Robotics | `"Robotics and Automation"` |
| Electronics & Computer | `"Electronics & Computer Engineering"` |
| First Year / FY | `"First Year"` |
| MBA | `"M.B.A"` |
| Honors | `"Honors Course"` |

Append year and pattern for tighter scopes:

```bash
# Standard: Branch/Year/Pattern
python3 tools/sync.py --files "Computer Engineering/TE/2019 Pattern"

# First Year: First Year/Pattern (NO year tier)
python3 tools/sync.py --files "First Year/2019 Pattern"

# MBA: M.B.A/SEM - X/Pattern (Semester instead of year)
python3 tools/sync.py --files "M.B.A/SEM - I/2019 Pattern"

# Honors: Honors Course/Year (NO pattern tier)
python3 tools/sync.py --files "Honors Course/BE"
```

---

## Changelog Marker Comments

> [!CAUTION]
> Never delete or edit the marker comments in `changelog/folder.md` or `changelog/files.md`. The apply and discard commands parse these sections by marker.

```html
<!-- FOLDER_SYNC_PENDING_BEGIN -->
<!-- FOLDER_SYNC_PENDING_END -->

<!-- FILE_SYNC_PENDING_BEGIN -->
<!-- FILE_SYNC_PENDING_END -->
```

---

## Incoming Path Resolution

File sync resolves the normalized `incoming/` path through `mapping/folder_names.yml` before download. A Drive folder named:

```
Artificial Intelligence and Data Science / SE / 2019 Pattern / Discrete Mathematics
```

is staged as:

```
incoming/artificial-intelligence-and-data-science/se/2019_pattern/discrete_mathematics
```

This lets file sync recognize that the normalized local folder is the same Drive branch instead of creating a duplicate top-level folder with the raw display name.

---

## SQLite Tracking

`tracking/manifest.db` stores one row per Google Drive file ID.

Key columns:

| Column | Purpose |
|---|---|
| `file_id` | Primary identity from Google Drive |
| `current_stage` | `DISCOVERED`, `DOWNLOADED`, `FILE_RENAMED`, `NEEDS_REVIEW`, `VERIFIED`, `MOVED`, or `MISSING` |
| `current_path` | Where the file is now |
| `expected_path` | Where the file should move under `papers/` |
| `retry_count` | Number of failed rename review attempts |
| `review_reason` | Why a file is in `NEEDS_REVIEW` |

`mapping/local/` is legacy metadata. It may not exist on fresh installs and should not be treated as the modern tracking source.

---

## After Downloading

Once `--files --apply` finishes, continue the pipeline:

```bash
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --dry-run
python3 tools/rename_folders.py
python3 tools/rename_files.py --ocr-workers 1
# review changelog/rename.md
python3 tools/rename_files.py --apply
python3 tools/verify.py
python3 tools/move.py
```

See [rename_folders.md](rename_folders.md), [rename_files.md](rename_files.md), and [verify_move.md](verify_move.md) for details.
