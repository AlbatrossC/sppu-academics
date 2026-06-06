# AGENTIC.md — SPPU PYQ Sync Toolkit Agent Instructions

> **Audience:** AI coding agents — Antigravity, Claude Code, OpenAI Codex, or any LLM-driven agent.
> **Golden Rule:** REVIEW FIRST, APPLY SECOND. Never apply without reviewing the changelog first.

---

## 1  Project Overview

This repository syncs exam question-paper PDFs from a public Google Drive archive into a normalized local `papers/` directory. The workflow is:

1. **Map** — discover Drive folder structure → `mapping/*.json`
2. **Sync Folders** — detect new/changed folders → `changelog/folder.md`
3. **Sync Files** — detect new/changed PDF files → `changelog/files.md`
4. **Download** — apply reviewed file changes → `incoming/`
5. **Normalize Folders** — rename `incoming/` directories → `mapping/folder_names.yml`
6. **Rename Files** — PyMuPDF/PaddleOCR PDF renaming with Groq fallback → `changelog/rename.md` → `papers/`

**Working directory:** always run commands from the project root.

```text
/home/jadha/Sppu-pyqs
```

Older local Windows checkouts may use a different path, but commands in this environment should run from the project root above.

---

## 2  Folder Families (Critical Context)

The project has **four distinct folder families** with different hierarchy depths. You **must** know which family a branch belongs to before running scoped commands.

### 2.1  Standard Branches (4 levels)

```text
Branch / Year / Pattern / Subject
```

Mapping file: `mapping/sync_mapping.json`
Legacy local metadata: `mapping/local/<Branch>/<Year>/<Pattern>.json` if present
Incoming path: `incoming/<Branch>/<Year>/<Pattern>/<Subject>/<file>.pdf`

**Standard branches:**
- Artificial Intelligence and Data Science
- Artificial Intelligence and Machine Learning
- Civil Engineering
- Computer Engineering
- E & TC Engineering
- Electrical Engineering
- Electronics & Computer Engineering
- IT Engineering
- Mechanical Engineering
- Robotics and Automation

### 2.2  First Year (3 levels — NO year tier)

```text
First Year / Pattern / Subject
```

Mapping file: `mapping/first_year_mapping.json`
Legacy local metadata: `mapping/local/First Year/<Pattern>.json` if present
Incoming path: `incoming/First Year/<Pattern>/<Subject>/<file>.pdf`

> [!IMPORTANT]
> First Year does NOT have a year level (like BE/TE/SE). It jumps directly from `First Year` → `Pattern` → `Subject`.

### 2.3  MBA (4 levels — uses Semester instead of Year)

```text
M.B.A / Semester / Pattern / Subject
```

Mapping file: `mapping/mba.json`
Legacy local metadata: `mapping/local/M.B.A/<Semester>/<Pattern>.json` if present
Incoming path: `incoming/M.B.A/<Semester>/<Pattern>/<Subject>/<file>.pdf`

> [!IMPORTANT]
> MBA uses Semester names like `SEM - I`, `SEM - II`, `SEM - III`, `SEM - IV` instead of year codes.
> Some MBA subjects live under specialization sub-folders on Drive but are flattened under their pattern in the mapping. These entries have `drive_path` and `source_group` fields.

### 2.4  Honors Course (3 levels — NO pattern tier)

```text
Honors Course / Year / Subject
```

Mapping file: `mapping/honors_course_mapping.json`
Legacy local metadata: `mapping/local/Honors Course/<Year>.json` if present
Incoming path: `incoming/Honors Course/<Year>/<Subject>/<file>.pdf`

> [!IMPORTANT]
> Honors Course does NOT have a pattern level. It goes directly from `Year` (BE, TE) → `Subject`.
> The year folder code is used as `pattern_code` during rename.

---

## 3  Tool Reference

### 3.1  `tools/status.py` — Generate Status Report

Shows counts of incoming PDFs, papers, pending changes, and the next suggested command.

```bash
# Write status report to docs/status.md
python3 tools/status.py

# Also print to stdout
python3 tools/status.py --print
```

**Always run this** after completing any stage to verify state.

---

### 3.2  `tools/sync.py` — Sync Folders & Files from Drive

The main review-first sync CLI. It has two independent modes: `--folders` and `--files`.

#### 3.2.1  Folder Sync (detect new/changed Drive folders)

```bash
# Review ALL folder changes (scans Drive, writes changelog/folder.md)
python3 tools/sync.py --folders

# Review one branch only
python3 tools/sync.py --folders "Computer Engineering"
python3 tools/sync.py --folders "Computer Engineering/TE"
python3 tools/sync.py --folders "First Year"
python3 tools/sync.py --folders "M.B.A/SEM - II"
python3 tools/sync.py --folders "Honors Course/TE"

# Apply reviewed changes (reads changelog/folder.md, updates mapping JSON)
python3 tools/sync.py --folders --apply

# Discard all pending folder changes
python3 tools/sync.py --folders --discard

# Discard specific changes
python3 tools/sync.py --folders --discard "Computer Engineering/TE/2019 Pattern/New Subject"
```

**Writes:** `changelog/folder.md`
**Apply updates:** `mapping/sync_mapping.json`, `mapping/first_year_mapping.json`, `mapping/mba.json`, or `mapping/honors_course_mapping.json`

#### 3.2.2  File Sync (detect new/changed PDF files)

```bash
# Review ALL file changes (scans Drive, writes changelog/files.md)
python3 tools/sync.py --files

# Review one scope
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
python3 tools/sync.py --files "First Year/2019 Pattern"
python3 tools/sync.py --files "M.B.A/SEM - II"
python3 tools/sync.py --files "Honors Course/TE"

# Apply reviewed downloads (downloads to incoming/)
python3 tools/sync.py --files --apply

# Apply with gdown fallback and throttling
python3 tools/sync.py --files --apply --gdown --download-delay 5

# Apply with rclone bulk copyurl
python3 tools/sync.py --files --apply --rclone --workers 8

# Discard all pending file downloads
python3 tools/sync.py --files --discard
```

**Writes:** `changelog/files.md`
**Apply downloads to:** `incoming/` and updates `tracking/manifest.db`. `mapping/local/` is legacy metadata and may be absent on fresh installs.

---

### 3.3  `tools/rename_folders.py` — Normalize Incoming Folder Names

Uses `mapping/folder_names.yml` to normalize folder names under `incoming/`.

```bash
# Create/update the name registry from mapping JSON files
python3 tools/rename_folders.py --create

# Preview all renames (dry run)
python3 tools/rename_folders.py --dry-run

# Apply all renames
python3 tools/rename_folders.py

# Preview/apply for one branch
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science" --dry-run
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science"
```

**Reads:** `mapping/sync_mapping.json`, `mapping/first_year_mapping.json`, `mapping/mba.json`, `mapping/honors_course_mapping.json`
**Updates:** `mapping/folder_names.yml`
**Renames:** directories under `incoming/` only (NOT PDF filenames)

---

### 3.4  `tools/rename_files.py` — Normalize PDF Filenames

Uses PyMuPDF header text first, PaddleOCR GPU second, and Groq fallback last to extract exam metadata (marks, month, year) and build normalized filenames.

```bash
# Review all PDFs under incoming/ (or retry retry_pending rows if changelog exists)
python3 tools/rename_files.py --ocr-workers 1

# Force fresh rebuild (ignore existing changelog)
python3 tools/rename_files.py --fresh --ocr-workers 1

# Review one subtree
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern" --ocr-workers 1

# Apply reviewed renames (moves PDFs to papers/ or needs_review/)
python3 tools/rename_files.py --apply

# Apply for one subtree
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science"
```

**Writes:** `changelog/rename.md`
**Moves to:** `papers/<same path>/<normalized_name>.pdf` or `needs_review/<same path>/<original_name>`

**Output filename format:**
```text
{exam_type}_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf
```

Example: `endsem_may_jun_2024_aids_bda_eV_2019p.pdf`

---

### 3.5  `tools/map.py` — Build/Refresh Drive Folder Mapping

For full mapping rebuilds. Use `sync.py --folders` for incremental changes.

```bash
# Full build from scratch
python3 tools/map.py build

# Refresh existing mapping
python3 tools/map.py refresh

# Refresh specific branches
python3 tools/map.py refresh --branch "Mechanical Engineering" --branch "Robotics and Automation"
```

---

### 3.6  `tools/pipeline.py` — Orchestrated Workflow

Wraps the individual tools into a single command. Still uses review/apply separation.

```bash
# Review only
python3 tools/pipeline.py --review
python3 tools/pipeline.py --review --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"

# Apply reviewed folder/file changes + normalize + review renames
python3 tools/pipeline.py --apply-reviewed
python3 tools/pipeline.py --apply-reviewed --gdown --download-delay 5
python3 tools/pipeline.py --apply-reviewed --rclone --workers 8

# Apply reviewed renames
python3 tools/pipeline.py --apply-renames
python3 tools/pipeline.py --apply-renames --incoming-path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"

# Full review + apply in one go
python3 tools/pipeline.py --full --apply
python3 tools/pipeline.py --full --apply --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"

# Dry run (print commands without executing)
python3 tools/pipeline.py --full --apply --dry-run
```

`--scope` scopes review commands only. `--apply-reviewed --scope ...` still applies every pending folder/file changelog entry.

---

### 3.7  `tools/download_drive.py` — Legacy Downloader

```bash
python3 tools/download_drive.py
```

> [!WARNING]
> This is a legacy tool. Prefer `python3 tools/sync.py --files --apply` for new work.

### 3.8  Upload and Publishing

Upload reads from `papers/` only:

```bash
python3 tools/upload_pipeline.py preflight
python3 tools/upload_pipeline.py scan
python3 tools/upload_pipeline.py sync --workers 4
python3 tools/upload_pipeline.py sync --state FAILED
python3 tools/upload_pipeline.py manifest
python3 tools/upload_pipeline.py summary
```

Always preview destructive cleanup:

```bash
python3 tools/upload_pipeline.py bulk-delete --target cloud --dry-run
```

---

## 4  Use Cases — Agent Workflows

### USE CASE 1: "Sync all the folders"

**Intent:** Check if any new Drive folders have been added or removed.

**Steps:**
1. Run folder review:
   ```bash
   python3 tools/sync.py --folders
   ```
2. **REVIEW** `changelog/folder.md` — read it and verify the pending changes make sense.
3. If changes look correct, apply:
   ```bash
   python3 tools/sync.py --folders --apply
   ```
4. Verify:
   ```bash
   python3 tools/status.py --print
   ```

> [!CAUTION]
> The `--apply` command updates JSON files in `mapping/`. Always review `changelog/folder.md` before applying.

---

### USE CASE 2: "Check if [branch] is up to date" / "Check files for [branch]"

**Intent:** Check if new PDF files have been added for a specific branch.

**Steps:**

1. **Look up the exact branch name** from `mapping/folder_names.yml` or this reference:

   | User says | Exact scope for `--files` |
   |---|---|
   | AIDS / AI&DS | `"Artificial Intelligence and Data Science"` |
   | AIML | `"Artificial Intelligence and Machine Learning"` |
   | Comp / CompE | `"Computer Engineering"` |
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

2. Run file review (scope it to the branch + year + pattern if known):
   ```bash
   python3 tools/sync.py --files "Artificial Intelligence and Data Science"
   ```
   Or more specific:
   ```bash
   python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
   ```

3. **REVIEW** `changelog/files.md` — verify the listed files and download targets.

4. If files look correct, apply downloads:
   ```bash
   python3 tools/sync.py --files --apply
   ```

5. After download, normalize folder names:
   ```bash
   python3 tools/rename_folders.py --create
   python3 tools/rename_folders.py --dry-run
   python3 tools/rename_folders.py
   ```

6. Review and apply PDF renames:
   ```bash
   python3 tools/rename_files.py --ocr-workers 1
   ```
   Review `changelog/rename.md`, then:
   ```bash
   python3 tools/rename_files.py --apply
   ```

7. Verify:
   ```bash
   python3 tools/status.py --print
   ```

---

### USE CASE 3: "Full sync everything"

**Steps:**
```bash
python3 tools/pipeline.py --review
```
Review changelogs, then:
```bash
python3 tools/pipeline.py --apply-reviewed --gdown --download-delay 5
```
Review rename changelog, then:
```bash
python3 tools/pipeline.py --apply-renames
```

Or if the user explicitly wants everything in one shot:
```bash
python3 tools/pipeline.py --full --apply
```

---

### USE CASE 4: "Check First Year files"

> [!IMPORTANT]
> First Year has NO year level. Scope directly with pattern.

```bash
python3 tools/sync.py --files "First Year"
python3 tools/sync.py --files "First Year/2019 Pattern"
```

After review & download:
```bash
python3 tools/sync.py --files --apply
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --path "incoming/First Year" --dry-run
python3 tools/rename_folders.py --path "incoming/First Year"
python3 tools/rename_files.py --path "incoming/first-year" --ocr-workers 1
python3 tools/rename_files.py --apply --path "incoming/first-year"
```

---

### USE CASE 5: "Check MBA files"

> [!IMPORTANT]
> MBA uses Semester names like `SEM - I`, `SEM - II`, etc. instead of year codes.

```bash
python3 tools/sync.py --files "M.B.A"
python3 tools/sync.py --files "M.B.A/SEM - II"
python3 tools/sync.py --files "M.B.A/SEM - II/2019 Pattern"
```

After review & download:
```bash
python3 tools/sync.py --files --apply
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --path "incoming/M.B.A" --dry-run
python3 tools/rename_folders.py --path "incoming/M.B.A"
python3 tools/rename_files.py --path "incoming/m-b-a" --ocr-workers 1
python3 tools/rename_files.py --apply --path "incoming/m-b-a"
```

---

### USE CASE 6: "Check Honors Course files"

> [!IMPORTANT]
> Honors Course has NO pattern level. It goes `Year → Subject` directly.

```bash
python3 tools/sync.py --files "Honors Course"
python3 tools/sync.py --files "Honors Course/TE"
```

After review & download:
```bash
python3 tools/sync.py --files --apply
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --path "incoming/Honors Course" --dry-run
python3 tools/rename_folders.py --path "incoming/Honors Course"
python3 tools/rename_files.py --path "incoming/honors-course" --ocr-workers 1
python3 tools/rename_files.py --apply --path "incoming/honors-course"
```

---

### USE CASE 7: "Rebuild the mapping"

```bash
python3 tools/map.py build
python3 tools/rename_folders.py --create
python3 tools/status.py --print
```

---

### USE CASE 8: "Refresh only specific branches"

```bash
python3 tools/map.py refresh --branch "Mechanical Engineering" --branch "Civil Engineering"
python3 tools/rename_folders.py --create
```

---

### USE CASE 9: "Groq rate-limited / rename failed"

If Groq rate-limits, just rerun it. Rate-limited rows stay `retry_pending` and are not moved to `needs_review/`.

```bash
python3 tools/rename_files.py --ocr-workers 1
```

---

### USE CASE 10: "Generate status report"

```bash
python3 tools/status.py --print
```

---

## 5  Key Data Files

| File | Purpose |
|---|---|
| `config.json` | Drive root folder ID and request settings |
| `mapping/sync_mapping.json` | Standard branch folder mapping |
| `mapping/first_year_mapping.json` | First Year folder mapping |
| `mapping/mba.json` | MBA folder mapping |
| `mapping/honors_course_mapping.json` | Honors Course folder mapping |
| `mapping/folder_names.yml` | Name registry with normalized names, codes, and Drive IDs |
| `mapping/local/**/*.json` | Legacy per-pattern metadata; may be absent |
| `changelog/folder.md` | Pending folder changes (machine-readable JSON inside) |
| `changelog/files.md` | Pending file downloads (machine-readable JSON inside) |
| `changelog/rename.md` | Pending file renames (machine-readable JSON inside) |
| `incoming/` | Temporary raw Drive download mirror |
| `papers/` | Final normalized PDFs |
| `needs_review/` | Files that could not be safely renamed |
| `docs/status.md` | Human-readable status report |

---

## 6  Normalized Path Reference

After `rename_folders.py` runs, folder names are normalized:

| Drive Name | Normalized Incoming Path |
|---|---|
| `Artificial Intelligence and Data Science` | `artificial-intelligence-and-data-science` |
| `Computer Engineering` | `computer-engineering` |
| `E & TC Engineering` | `e-and-tc-engineering` |
| `First Year` | `first-year` |
| `M.B.A` | `m-b-a` |
| `Honors Course` | `honors-course` |
| `BE` | `be` |
| `TE` | `te` |
| `SE` | `se` |
| `2019 Pattern` | `2019_pattern` |
| `Deep Learning - Ele V` | `deep_learning_ele_V` |

**Rules:**
- Branch names use **hyphens** (`-`)
- Years, patterns, subjects use **underscores** (`_`)
- `&` → `and`, `+` → `plus`, `@` → `at`, `%` → `percent`
- Roman numerals are **preserved** in uppercase (I, II, III, IV, V, VI, VII, VIII, IX, X)

---

## 7  Agent Rules (MUST Follow)

1. **Never apply before reviewing** unless the user explicitly asks AND the matching changelog exists.

2. **Never delete marker comments** in changelog files:
   - `<!-- FOLDER_SYNC_PENDING_BEGIN -->` / `<!-- FOLDER_SYNC_PENDING_END -->`
   - `<!-- FILE_SYNC_PENDING_BEGIN -->` / `<!-- FILE_SYNC_PENDING_END -->`
   - `<!-- RENAME_FILES_BEGIN -->` / `<!-- RENAME_FILES_END -->`

3. **Never hand-edit Drive IDs** unless explicitly asked. Use `tools/sync.py --folders` for mapping changes.

4. **Never overwrite files in `papers/`**. Collisions go to `needs_review/`.

5. **Use scoped commands** during testing to avoid large API runs:
   ```bash
   python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
   python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science" --dry-run
   python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern" --ocr-workers 1
   ```

6. **After any mapping refresh**, always run:
   ```bash
   python3 tools/rename_folders.py --create
   ```

7. **Use `--gdown` only** when the official Drive download is blocked or rate-limited.

8. **Use `--download-delay`** when Google throttles requests.

9. **File download is resumable.** If `--files --apply` fails midway, rerun the same command. Already downloaded files are skipped.

10. **Check `mapping/folder_names.yml`** to find the exact Drive name and normalized name for any branch/subject before running scoped commands.

11. **Do not assume pipeline apply scope.** `tools/pipeline.py --apply-reviewed --scope ...` applies all pending folder/file changelog entries.

---

## 8  Common Mistakes to Avoid

| Mistake | Correct Approach |
|---|---|
| Running `--files --apply` before `--files` review | Always run `--files` first, read `changelog/files.md`, then `--files --apply` |
| Using wrong case/spelling in scope | Use exact Drive names from `mapping/folder_names.yml` |
| Running `rename_files.py` before `rename_folders.py` | Always normalize folders first: `rename_folders.py --create` → `rename_folders.py` → then `rename_files.py` |
| Editing `changelog/*.md` marker comments | Never. The apply commands parse these. |
| Using `--files` and `--folders` together | They are mutually exclusive. Run them separately. |
| Forgetting `--create` after mapping changes | Always run `rename_folders.py --create` after `sync.py --folders --apply` or `map.py` |

---

## 9  Quick Command Cheat Sheet

```bash
# Status check
python3 tools/status.py --print

# Full folder sync
python3 tools/sync.py --folders
# review changelog/folder.md
python3 tools/sync.py --folders --apply

# Full file sync for a branch
python3 tools/sync.py --files "Artificial Intelligence and Data Science"
# review changelog/files.md
python3 tools/sync.py --files --apply

# Normalize + rename
python3 tools/rename_folders.py --create
python3 tools/rename_folders.py --dry-run
python3 tools/rename_folders.py
python3 tools/rename_files.py --ocr-workers 1
# review changelog/rename.md
python3 tools/rename_files.py --apply

# One-shot pipeline
python3 tools/pipeline.py --full --apply --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
```

---

## 10  Environment Setup

```bash
# Install dependencies
python3 -m pip install -r requirements.txt
```

Required `.env` keys:
```env
GOOGLE_API_KEY=your_google_api_key
GROQ_API_KEY=your_groq_key
```

Optional:
```env
GROQ_API_KEY_2=optional_second_groq_key
GROQ_API_KEYS=key1,key2,key3
GROQ_MODEL=llama-3.1-8b-instant
```

Config file (`config.json`):
```json
{
  "root_folder_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM",
  "request_timeout": 30,
  "max_retries": 5,
  "backoff_factor": 1.5
}
```
