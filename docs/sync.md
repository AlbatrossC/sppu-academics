# Sync CLI

> For agent-specific workflows and use cases, see [AGENTIC.md](../AGENTIC.md).

`tools/sync.py` is the review-first sync CLI for this repository.

It has three jobs:

1. Create the older read-only PDF sync plan.
2. Review and apply Google Drive folder mapping changes.
3. Review and apply Google Drive PDF downloads.

The important design rule is simple: review commands call Drive and write a markdown changelog; apply/discard commands read the changelog and do the local action.

## Quick Commands

Create the legacy PDF sync plan:

```bash
python3 tools/sync.py
```

Review folder mapping changes:

```bash
python3 tools/sync.py --folders
python3 tools/sync.py --folders "Computer Engineering/TE"
```

Apply or discard reviewed folder changes:

```bash
python3 tools/sync.py --folders --apply
python3 tools/sync.py --folders --discard
python3 tools/sync.py --folders --discard "Computer Engineering/TE/2019 Pattern/New Subject"
```

Review file downloads:

```bash
python3 tools/sync.py --files
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
```

Apply or discard reviewed file downloads:

```bash
python3 tools/sync.py --files --apply
python3 tools/sync.py --files --discard
python3 tools/sync.py --files --discard "1DriveFileId"
```

Use `gdown` only when explicitly requested:

```bash
python3 tools/sync.py --files --apply --gdown
python3 tools/sync.py --files --apply --gdown --download-delay 5
```

## Mapping Families

The project has four folder families. Folder and file sync both understand all four.

### Standard Branches

Drive structure:

```text
Branch / Year / Pattern / Subject
```

Example:

```text
Artificial Intelligence and Data Science / BE / 2019 Pattern / Machine Learning
```

Folder mapping:

```text
mapping/sync_mapping.json
```

Local file tracking:

```text
tracking/manifest.db
```

Incoming raw files:

```text
incoming/<Branch>/<Year>/<Pattern>/<Subject>/<filename>
```

### First Year

Drive structure:

```text
First Year / Pattern / Subject
```

Example:

```text
First Year / 2019 Pattern / Engineering Mathematics - I
```

Folder mapping:

```text
mapping/first_year_mapping.json
```

Local file tracking:

```text
tracking/manifest.db
```

Incoming raw files:

```text
incoming/First Year/<Pattern>/<Subject>/<filename>
```

### MBA

Drive structure:

```text
M.B.A / Semester / Pattern / Subject
```

Example:

```text
M.B.A / SEM - II / 2019 Pattern / Financial Management
```

Folder mapping:

```text
mapping/mba.json
```

Local file tracking:

```text
tracking/manifest.db
```

Incoming raw files:

```text
incoming/M.B.A/<Semester>/<Pattern>/<Subject>/<filename>
```

Some MBA Drive folders contain specialization containers. The mapping flattens final leaf subjects under the pattern while preserving useful source metadata in the mapping file.

### Honors Course

Drive structure:

```text
Honors Course / Year / Subject
```

Example:

```text
Honors Course / TE / Artificial Intelligence
```

Folder mapping:

```text
mapping/honors_course_mapping.json
```

Local file tracking:

```text
tracking/manifest.db
```

Incoming raw files:

```text
incoming/Honors Course/<Year>/<Subject>/<filename>
```

## Folder Workflow

Folder review checks Drive folders against mapping JSON files under `mapping/`.

Review all folders:

```bash
python3 tools/sync.py --folders
```

Review one scope:

```bash
python3 tools/sync.py --folders "Computer Engineering"
python3 tools/sync.py --folders "Computer Engineering/TE"
python3 tools/sync.py --folders "First Year"
python3 tools/sync.py --folders "M.B.A/SEM - II"
python3 tools/sync.py --folders "Honors Course/TE"
```

`--folder` is an alias for `--folders`.

Folder review writes:

```text
changelog/folder.md
```

That file has a human table and a machine-readable JSON block. New review runs append only unique pending changes. Existing pending rows stay until you apply or discard them.

Apply reviewed folder changes:

```bash
python3 tools/sync.py --folders --apply
```

Apply does not call Drive. It reads `changelog/folder.md` and edits the matching mapping JSON file.

Discard all pending folder changes:

```bash
python3 tools/sync.py --folders --discard
```

Discard selected folder changes by path or folder ID:

```bash
python3 tools/sync.py --folders --discard "Computer Engineering/TE/2019 Pattern/New Subject"
python3 tools/sync.py --folders --discard "1abcDriveFolderId"
```

Discard only edits `changelog/folder.md`. It does not edit mapping JSON files.

## File Workflow

File review checks PDFs inside mapped subject folders against SQLite tracking:

```text
tracking/manifest.db
```

Review all mapped files:

```bash
python3 tools/sync.py --files
```

Review one scope:

```bash
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
python3 tools/sync.py --files "First Year/2019 Pattern"
python3 tools/sync.py --files "M.B.A/SEM - II"
python3 tools/sync.py --files "Honors Course/TE"
```

Speed up review scans by checking multiple subject folders in parallel:

```bash
python3 tools/sync.py --files "Artificial Intelligence and Data Science" --workers 4
```

Use a lower value if Google starts throttling requests. The interactive menu uses 4 workers for file review.

`--file` is an alias for `--files`.

File review writes:

```text
changelog/files.md
```

Pending file rows include Drive file ID, filename, folder path, target incoming path, and target local metadata path inside the machine-readable JSON block.

The target incoming path is resolved through `mapping/folder_names.yml` before download. For example, a Drive folder named:

```text
Artificial Intelligence and Data Science / SE / 2019 Pattern / Discrete Mathematics
```

is staged as:

```text
incoming/artificial-intelligence-and-data-science/se/2019_pattern/discrete_mathematics
```

This lets file sync recognize that the normalized local folder is the same Drive branch instead of creating a second top-level folder with the display name.

Apply reviewed downloads with the official Drive API:

```bash
python3 tools/sync.py --files --apply
```

If Google starts blocking automated requests, slow the run down or use smaller batches:

```bash
python3 tools/sync.py --files --apply --workers 1 --download-delay 10
python3 tools/sync.py --files --apply --workers 1 --download-delay 10 --max-downloads 50
```

When the downloader detects Google's anti-automation/rate-limit page, it stops the current run and leaves the remaining entries in `changelog/files.md` so you can resume later.

Apply reviewed downloads with `gdown`:

```bash
python3 tools/sync.py --files --apply --gdown
python3 tools/sync.py --files --apply --gdown --workers 1 --download-delay 10
```

Apply reviewed downloads in bulk with `rclone`:

```bash
python3 tools/sync.py --files --apply --rclone --workers 8
```

This uses `rclone copyurl --urls <csv> <project-root>` under the hood. The generated CSV contains each public Drive download URL plus its normalized `incoming/...` destination path. `--workers` maps to rclone `--transfers`. After rclone exits, the sync tool verifies every downloaded file before updating `tracking/manifest.db` and removing it from `changelog/files.md`; missing, tiny, or HTML error responses stay pending.

Throttle downloads if Google starts blocking automated requests:

```bash
python3 tools/sync.py --files --apply --download-delay 5
python3 tools/sync.py --files --apply --gdown --download-delay 5
```

Discard all pending file downloads:

```bash
python3 tools/sync.py --files --discard
```

Discard selected pending downloads by file ID, filename, or folder path:

```bash
python3 tools/sync.py --files --discard "1DriveFileId"
python3 tools/sync.py --files --discard "May_Jun_2025.pdf"
python3 tools/sync.py --files --discard "Artificial Intelligence and Data Science/BE/2019 Pattern/Machine Learning"
```

## Resumable File Apply

`--files --apply` is designed to survive partial failures.

After every successful file:

1. The PDF is written under `incoming/`.
2. The matching SQLite row is updated to `DOWNLOADED`.
3. The file is removed from `changelog/files.md`.

If an apply run fails midway, rerun:

```bash
python3 tools/sync.py --files --apply
```

or:

```bash
python3 tools/sync.py --files --apply --gdown --download-delay 5
```

The command resumes from the remaining pending entries in `changelog/files.md`. Already recorded file IDs are skipped.

## Incoming Files

`incoming/` is a temporary raw download and processing area. New downloads are written with normalized folder names from `mapping/folder_names.yml`.

Examples:

```text
incoming/computer-engineering/te/2019_pattern/web_technology/question-paper.pdf
incoming/first-year/2019_pattern/engineering_mathematics_I/question-paper.pdf
incoming/m-b-a/sem_II/2019_pattern/financial_management/question-paper.pdf
incoming/honors-course/te/artificial_intelligence/question-paper.pdf
```

Do not treat `incoming/` as the durable sync database. The durable file sync comparison source is `tracking/manifest.db`, keyed by Google Drive `file_id`.

After downloads finish, normalize folders, rename PDFs, verify, and move with:

```bash
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --dry-run
python3 tools/rename_folders.py
python3 tools/rename_files.py
python3 tools/rename_files.py --apply
python3 tools/verify.py
python3 tools/move.py
```

`tools/rename_folders.py` normalizes older display-name directories under `incoming/` and merges them into an existing normalized target when both represent the same folder. `tools/rename_files.py --apply` renames files in the working folder and updates SQLite one file at a time. `tools/verify.py` promotes valid rows to `VERIFIED`. `tools/move.py` moves only `VERIFIED` rows into `papers/`.

Generate a status report at any point:

```bash
python3 tools/status.py
```

This writes `docs/status.md`.

## SQLite Tracking

`tracking/manifest.db` stores one row per Google Drive file ID. Important columns:

- `file_id`: primary identity from Google Drive
- `current_stage`: `DISCOVERED`, `DOWNLOADED`, `FILE_RENAMED`, `NEEDS_REVIEW`, `VERIFIED`, `MOVED`, or `MISSING`
- `current_path`: where the file is now
- `expected_path`: where the file should move under `papers/`
- `retry_count`: number of failed rename review attempts
- `review_reason`: why a file is in `NEEDS_REVIEW`

`mapping/local/` is legacy metadata. It may not exist on fresh installs and should not be treated as the modern tracking source.

## Downloader Choices

Default:

```bash
python3 tools/sync.py --files --apply
```

Uses the official Google Drive API client and API key.

Optional:

```bash
python3 tools/sync.py --files --apply --gdown
```

Uses `gdown` with public Drive file IDs. This is useful as a fallback, but it can still hit Google anti-automation blocking. Install it with:

```bash
python3 -m pip install -r requirements.txt
```

During `--gdown` applies, the CLI logs the `gdown` URL, the selected gdown call style, and whether it falls back to the direct HTTP request. These details are printed only to the terminal; they are not stored in mapping files.

## Agent Rules

Do not apply before review unless the user explicitly asks and the matching changelog exists.

Do not manually infer folder IDs or file IDs. Use IDs from Drive scans or the pending JSON block.

Do not delete the marker comments in `changelog/folder.md` or `changelog/files.md`; apply/discard commands parse those sections.

Do not hand-edit `changelog/rename.json`; `python3 tools/rename_files.py --apply` reads that sidecar state. `changelog/rename.md` is for human review.

Use `--folders --apply` only for folder mapping changes.

Use `--files --apply` only for pending downloads.

Pending changelog apply is not scoped by the review scope that produced it. If `changelog/files.md` contains pending rows from multiple scopes, `--files --apply` processes the pending rows in that changelog.

Use `--discard` when the user rejects pending changes. With no arguments it discards all pending changes for the selected mode.

If Google blocks downloads, prefer waiting and rerunning, or use `--download-delay`. Use `--gdown` only when the user explicitly wants the unofficial fallback.
