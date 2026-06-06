# SPPU PYQ Sync Toolkit

This repository contains review-first Python tools for mapping a public Google Drive question-paper archive, downloading PDFs into a temporary `incoming/` mirror, normalizing folders, and moving cleanly renamed PDFs into `papers/`.

The tools are designed for humans and coding agents such as Codex, Gemini, or Claude. The main rule is: review first, apply second.

> **For AI agents:** Read [AGENTIC.md](AGENTIC.md) for complete agent instructions, use-case workflows, and CLI command reference.
## Setup

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Copy the safe templates before filling local values:

```bash
cp .env.example .env
cp config.example.json config.json
```

Create `.env` with the keys you need:

```env
GOOGLE_API_KEY=your_google_api_key
GROQ_API_KEY=your_groq_key
GROQ_API_KEY_2=optional_second_groq_key
GROQ_API_KEY_3=optional_third_groq_key
```

PDF metadata uses PyMuPDF header text first, PaddleOCR GPU second, and Groq only as a fallback. `GROQ_API_KEYS=key1,key2,key3` is also supported for optional Groq fallback keys.

Set the public Drive root folder ID in `config.json`:

```json
{
  "root_folder_id": "your-public-root-folder-id"
}
```

## Production Quickstart

For agents or careful manual runs, use the individual review/apply commands in this order:

```bash
python3 tools/validate_mappings.py
python3 tools/sync.py --folders
python3 tools/sync.py --folders --apply
python3 tools/sync.py --files
python3 tools/sync.py --files --apply --rclone --workers 8
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --dry-run
python3 tools/rename_folders.py
python3 tools/rename_files.py --ocr-workers 1
python3 tools/rename_files.py --apply
python3 tools/verify.py
python3 tools/move.py
python3 tools/status.py --print
```

Use `--gdown` only when the official Drive download path is blocked or rate-limited. Use `--download-delay` when Google throttles requests.

For a local summary at any point:

```bash
python3 tools/status.py
```

This writes:

```text
docs/status.md
```

For a one-command wrapper around the same tools:

```bash
python3 tools/pipeline.py --review --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
python3 tools/pipeline.py --apply-reviewed --gdown --download-delay 5
python3 tools/pipeline.py --apply-reviewed --rclone --workers 8
python3 tools/pipeline.py --apply-renames
```

To run review and apply stages together:

```bash
python3 tools/pipeline.py --full --apply --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
```

`pipeline.py` only orchestrates existing tools. It does not replace their changelog review/apply behavior.

Important wrapper semantics:

- `--scope` affects review commands only.
- `--apply-reviewed` applies all pending folder/file changelog entries, not just the passed scope.
- `--apply-renames --incoming-path PATH` scopes rename apply and move to that incoming subtree, while `verify.py` remains global.

## Documentation

- [Architecture overview](docs/overview.md)
- [Disaster recovery](docs/disaster_recovery.md)
- [Upload pipeline](docs/upload_pipeline.md)
- [Legacy tracking migration](docs/migrate_tracking.md)

## Tool Guide

| Tool | Purpose |
| --- | --- |
| `tools/validate_mappings.py` | Non-network sanity check for mapping JSON/YAML |
| `tools/map.py` | Full Drive mapping rebuild/refresh |
| `tools/sync.py` | Review/apply folder and file Drive changes |
| `tools/rename_folders.py` | Build folder registry and normalize `incoming/` folders |
| `tools/rename_files.py` | Review/apply normalized PDF filenames |
| `tools/verify.py` | Verify SQLite rows and renamed files |
| `tools/move.py` | Move verified PDFs into `papers/` |
| `tools/status.py` | Write/print workflow status |
| `tools/upload_pipeline.py` | Publish `papers/` to R2/Cloudinary and generate manifests |
| `tools/migrate_tracking.py` | Legacy migration from `mapping/local/` |
| `tools/download_drive.py` | Legacy sync-plan downloader |

### `tools/status.py`

Write a human-readable status report:

```bash
python3 tools/status.py
python3 tools/status.py --print
```

The report includes:

```text
SQLite stage counts
incoming PDF count
papers PDF count
needs_review PDF count
needs-review reasons
retry counts
filesystem drift
next suggested command
```

Output:

```text
docs/status.md
```

### `tools/pipeline.py`

Run the common workflow through one command while keeping the review/apply split.

Review Drive folder and file changes:

```bash
python3 tools/pipeline.py --review
python3 tools/pipeline.py --review --scope "Artificial Intelligence and Data Science/TE/2019 Pattern"
```

Apply reviewed folder/file changes, normalize `incoming/`, and generate rename review:

```bash
python3 tools/pipeline.py --apply-reviewed
python3 tools/pipeline.py --apply-reviewed --gdown --download-delay 5
python3 tools/pipeline.py --apply-reviewed --rclone --workers 8
```

Apply reviewed file renames, then verify and move:

```bash
python3 tools/pipeline.py --apply-renames
```

Run review and apply together:

```bash
python3 tools/pipeline.py --full --apply
python3 tools/pipeline.py --full --apply --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
```

Scoped rename stages can use normalized incoming paths:

```bash
python3 tools/pipeline.py --apply-renames --incoming-path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
```

Preview commands without executing:

```bash
python3 tools/pipeline.py --full --apply --dry-run
```

### `tools/sync.py`

Review and apply Drive folder/file changes.

Folder mapping review:

```bash
python3 tools/sync.py --folders
python3 tools/sync.py --folders "Artificial Intelligence and Data Science/BE"
python3 tools/sync.py --folders --apply
python3 tools/sync.py --folders --discard
```

File download review:

```bash
python3 tools/sync.py --files
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
python3 tools/sync.py --files --apply
python3 tools/sync.py --files --apply --gdown --download-delay 5
python3 tools/sync.py --files --apply --rclone --workers 8
python3 tools/sync.py --files --apply --max-downloads 100 --workers 1
python3 tools/sync.py --files --discard
```

Review writes:

```text
changelog/folder.md
changelog/files.md
```

Apply commands read those changelog files and do not re-scan Drive.

### `tools/rename_folders.py`

Create folder-name/code registry and normalize `incoming/` directories.

```bash
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --dry-run
python3 tools/rename_folders.py
```

Scoped run:

```bash
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science" --dry-run
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science"
```

This uses and updates:

```text
mapping/folder_names.yml
```

Only folder names change. PDF filenames are not changed by this tool.

### `tools/rename_files.py`

Review and apply normalized PDF filenames.

Review:

```bash
python3 tools/rename_files.py
```

If `changelog/rename.json` exists, the normal review command skips completed rows and retries only `retry_pending` model failures. Use `--fresh` to rebuild everything:

```bash
python3 tools/rename_files.py --fresh
```

Apply. This renames files in the working folder and updates SQLite one file at a time:

```bash
python3 tools/rename_files.py --apply
```

Scoped review/apply:

```bash
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
```

Finish renamed files:

```bash
python3 tools/verify.py
python3 tools/move.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
```

PyMuPDF header text is used first. When text is weak, watermark-only, or missing usable marks, PaddleOCR GPU tries page 1 crops at 45%, 65%, and then the full first page. Groq is used last only for:

```text
marks
month_code
year
```

Branch code, subject code, and pattern code are derived locally from the normalized path and `mapping/folder_names.yml`.

Successful rename apply writes:

```text
incoming/<same relative path>/<normalized filename>.pdf
```

Then `verify.py` promotes valid rows to `VERIFIED`, and `move.py` moves them to:

```text
papers/<same relative path>/<normalized filename>.pdf
```

Unsafe files move to:

```text
needs_review/<same incoming-relative path>/<original filename>
```

### `tools/map.py`

Build or refresh Drive folder mappings.

```bash
python3 tools/map.py build
python3 tools/map.py refresh
python3 tools/map.py refresh --branch "Mechanical Engineering"
```

Use this when the main mapping files need a larger rebuild. For normal incremental folder checks, prefer `tools/sync.py --folders`.

### `tools/upload_pipeline.py`

Upload reads from `papers/` only:

```bash
python3 tools/upload_pipeline.py preflight
python3 tools/upload_pipeline.py scan
python3 tools/upload_pipeline.py sync --workers 4
python3 tools/upload_pipeline.py manifest
python3 tools/upload_pipeline.py summary
```

See [docs/upload_pipeline.md](docs/upload_pipeline.md) for `--limit`, `--state FAILED`, `--target`, and `bulk-delete --dry-run`.

### `tools/migrate_tracking.py`

Legacy migration from `mapping/local/`:

```bash
python3 tools/migrate_tracking.py --print
```

`mapping/local/` may not exist on fresh installs. Prefer `python3 tools/sync.py --files` and reviewed download apply for modern recovery.

### `tools/download_drive.py`

Legacy downloader for `sync_plan/sync_plan.json`.

```bash
python3 tools/download_drive.py
```

Most current work should use `python3 tools/sync.py --files --apply` instead.

## Data Files

Mapping files:

```text
mapping/sync_mapping.json
mapping/first_year_mapping.json
mapping/mba.json
mapping/honors_course_mapping.json
mapping/folder_names.yml
mapping/local/     legacy runtime metadata; may not exist on fresh installs
```

Changelog/review files:

```text
changelog/folder.md
changelog/files.md
changelog/rename.md
changelog/rename.json
changelog/sync.md
```

Working/output folders:

```text
incoming/       temporary raw Drive mirror
papers/         final normalized PDFs
needs_review/   files that could not be safely renamed
sync_plan/      legacy sync plan output
manifest/       legacy download manifests
```

## Folder Families

Standard branches:

```text
Branch / Year / Pattern / Subject
```

First Year:

```text
First Year / Pattern / Subject
```

MBA:

```text
M.B.A / Semester / Pattern / Subject
```

Honors Course:

```text
Honors Course / Year / Subject
```

The sync and rename tools understand all four families.

## Agent Notes

Do not apply before review unless the user explicitly asks and the matching changelog exists.

Do not delete marker comments in folder/file changelogs. Rename review is human-readable in `changelog/rename.md`, while `tools/rename_files.py --apply` reads `changelog/rename.json`.

Do not hand-edit Drive IDs unless the user explicitly asks. Prefer `tools/sync.py --folders` for incremental mapping changes.

Do not assume `tools/pipeline.py --apply-reviewed --scope ...` scopes apply. It applies all pending folder/file changelog entries.

Do not overwrite files in `papers/`. `tools/rename_files.py` moves collisions to `needs_review/`.

Use scoped commands during testing to avoid large API runs:

```bash
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science" --dry-run
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
```

When Groq rate-limits, wait briefly and rerun `python3 tools/rename_files.py`; rate-limited rows stay `retry_pending` and are not moved to `needs_review/`.
