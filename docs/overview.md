# Architecture Overview

The toolkit turns a public Google Drive archive into normalized local PDFs and frontend manifest JSON:

```text
Drive -> mapping -> sync review -> download -> folder normalize -> PDF rename -> verify -> move -> upload -> manifest
```

All write-heavy steps are review-first where practical. `tools/sync.py --folders` and `tools/sync.py --files` scan Drive and write changelog files. Their `--apply` modes read pending changelog entries and do not re-scan Drive.

## Folder Families

Standard branches use:

```text
Branch / Year / Pattern / Subject
mapping/sync_mapping.json
```

First Year uses:

```text
First Year / Pattern / Subject
mapping/first_year_mapping.json
```

MBA uses:

```text
M.B.A / Semester / Pattern / Subject
mapping/mba.json
```

Honors Course uses:

```text
Honors Course / Year / Subject
mapping/honors_course_mapping.json
```

`mapping/folder_names.yml` is the shared name registry. It maps Drive display names to normalized folder names, short codes, and folder IDs.

## Stage Lifecycle

`tracking/manifest.db` is the durable local file tracker. Rows move through:

```text
DISCOVERED -> DOWNLOADED -> FOLDER_RENAMED -> FILE_RENAMED -> VERIFIED -> MOVED
```

Rows can also become:

```text
NEEDS_REVIEW
MISSING
```

`DISCOVERED` means Drive file metadata is known and a download is pending. `DOWNLOADED` means the PDF exists under `incoming/`. `FOLDER_RENAMED` records normalized incoming folders. `FILE_RENAMED` means `rename_files.py --apply` produced a normalized filename. `VERIFIED` means `verify.py` accepted the path and filename. `MOVED` means the file is in `papers/`. `NEEDS_REVIEW` and `MISSING` are inspection states.

## Tool Effects

| Tool | Inputs | Outputs and side effects |
| --- | --- | --- |
| `tools/map.py` | Drive root from `config.json` | Rebuilds `mapping/*.json` |
| `tools/sync.py --folders` | Drive, mapping JSON | Writes `changelog/folder.md` |
| `tools/sync.py --folders --apply` | `changelog/folder.md` | Updates mapping JSON |
| `tools/sync.py --files` | Drive, mapping JSON, SQLite | Writes `changelog/files.md` |
| `tools/sync.py --files --apply` | `changelog/files.md` | Downloads to `incoming/`, updates SQLite |
| `tools/rename_folders.py --create` | Mapping JSON | Updates `mapping/folder_names.yml` |
| `tools/rename_folders.py` | `incoming/`, folder registry | Renames/merges folders under `incoming/` |
| `tools/rename_files.py` | `incoming/`, folder registry, PDF text/OCR/Groq | Writes `changelog/rename.md` and `changelog/rename.json` |
| `tools/rename_files.py --apply` | `changelog/rename.json` | Renames PDFs, moves unsafe files to `needs_review/`, updates SQLite |
| `tools/verify.py` | SQLite and filesystem | Promotes valid rows to `VERIFIED` or records review/missing states |
| `tools/move.py` | SQLite and filesystem | Moves `VERIFIED` files to `papers/` |
| `tools/upload_pipeline.py` | `papers/`, upload env vars | Uploads to R2/Cloudinary and writes `manifest/*.json` |
| `tools/status.py --print` | SQLite and filesystem | Writes and prints `docs/status.md` |
| `tools/validate_mappings.py` | Mapping files only | Non-network mapping sanity check |
