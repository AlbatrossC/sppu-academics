# Agent Instructions — SPPU PYQ Sync Toolkit

> **Audience:** AI coding agents — Antigravity, Claude Code, OpenAI Codex, or any LLM-driven agent.
>
> This file is what `main.py` is for a human: it describes every operation you can perform, how to choose the right command, and the rules you must follow.

---

## Golden Rules

1. **REVIEW FIRST, APPLY SECOND.** Never apply without reading the changelog first.
2. **Never delete changelog marker comments.** Apply and discard commands parse them.
3. **Never overwrite files in `papers/`.** Collisions go to `needs_review/`.
4. **Never hand-edit Drive IDs.** Use `tools/sync.py --folders` for mapping changes.
5. **Always run from the project root.**

---

## Project Structure at a Glance

```
Drive Archive
  → mapping/*.json          (folder structure maps — committed)
  → changelog/              (review changelogs — generated)
  → incoming/               (raw downloaded PDFs — temporary)
  → papers/                 (final normalized PDFs — permanent)
  → needs_review/           (files that failed renaming — inspect)
  → tracking/manifest.db    (SQLite file tracker)
  → mapping/semester_mapping.yml  (approved semester assignments)
  → manifest/               (frontend JSON for website)
```

---

## Folder Families (Critical Context)

You MUST know which folder family a scope belongs to before running scoped commands.

| Family | Drive structure | Mapping file | Incoming path pattern |
|---|---|---|---|
| **Standard** | `Branch / Year / Pattern / Subject` | `mapping/sync_mapping.json` | `incoming/<branch>/<year>/<pattern>/<subject>/` |
| **First Year** | `First Year / Pattern / Subject` | `mapping/first_year_mapping.json` | `incoming/first-year/<pattern>/<subject>/` |
| **MBA** | `M.B.A / Semester / Pattern / Subject` | `mapping/mba.json` | `incoming/m-b-a/<semester>/<pattern>/<subject>/` |
| **Honors Course** | `Honors Course / Year / Subject` | `mapping/honors_course_mapping.json` | `incoming/honors-course/<year>/<subject>/` |

> [!IMPORTANT]
> - **First Year** has NO year tier (no BE/TE/SE). Scope: `"First Year"` → `"First Year/2019 Pattern"`
> - **MBA** uses Semester names (`SEM - I`, `SEM - II`, ...) instead of year codes.
> - **Honors Course** has NO pattern tier. Scope: `"Honors Course"` → `"Honors Course/TE"`

**Standard branches:**

| Short name | Exact scope string |
|---|---|
| AIDS / AI&DS | `"Artificial Intelligence and Data Science"` |
| AIML | `"Artificial Intelligence and Machine Learning"` |
| CompE / Comp | `"Computer Engineering"` |
| IT | `"IT Engineering"` |
| Civil | `"Civil Engineering"` |
| E&TC / ENTC | `"E & TC Engineering"` |
| Electrical / EE | `"Electrical Engineering"` |
| ECE / Electronics & Computer | `"Electronics & Computer Engineering"` |
| Mech | `"Mechanical Engineering"` |
| Robotics | `"Robotics and Automation"` |

---

## Use Case 1 — "Check status" / "What's the current state?"

```bash
python3 tools/status.py --print
```

This writes and prints `docs/status.md`. It shows:
- SQLite stage counts (DISCOVERED, DOWNLOADED, FILE_RENAMED, VERIFIED, MOVED, etc.)
- Incoming PDF count
- Papers PDF count
- Needs-review PDF count and reasons
- Retry counts
- Filesystem drift
- Next suggested command

**Always run this** after completing any stage to verify the current state.

---

## Use Case 2 — "Scan all folders" / "Check if folders are up to date"

Review all Drive folder structure changes:

```bash
python3 tools/sync.py --folders
```

Read `changelog/folder.md`. If changes look correct:

```bash
python3 tools/sync.py --folders --apply
python3 tools/rename_folders.py --create
python3 tools/status.py --print
```

> [!CAUTION]
> `--apply` updates mapping JSON files. Always review `changelog/folder.md` before applying.

---

## Use Case 3 — "Scan [branch]" / "Check if [branch] is up to date"

### Standard branch

```bash
# Scope to entire branch
python3 tools/sync.py --files "Artificial Intelligence and Data Science"

# Scope to one year
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE"

# Scope to one pattern
python3 tools/sync.py --files "Artificial Intelligence and Data Science/BE/2019 Pattern"
```

### First Year

> First Year has NO year level. Go directly to pattern:

```bash
python3 tools/sync.py --files "First Year"
python3 tools/sync.py --files "First Year/2019 Pattern"
```

### MBA

> MBA uses Semester names, not year codes:

```bash
python3 tools/sync.py --files "M.B.A"
python3 tools/sync.py --files "M.B.A/SEM - II"
python3 tools/sync.py --files "M.B.A/SEM - II/2019 Pattern"
```

### Honors Course

> Honors Course has NO pattern level:

```bash
python3 tools/sync.py --files "Honors Course"
python3 tools/sync.py --files "Honors Course/TE"
```

After review, read `changelog/files.md`, then download:

```bash
# Recommended: rclone
python3 tools/sync.py --files --apply --rclone --workers 8

# Alternative: Google Drive API
python3 tools/sync.py --files --apply

# Fallback if throttled:
python3 tools/sync.py --files --apply --gdown --download-delay 5
```

---

## Use Case 4 — "Rename folders" / "Normalize incoming folder names"

Run after downloading new files:

```bash
# Rebuild name registry (always after mapping changes)
python3 tools/rename_folders.py --create

# Preview renames
python3 tools/rename_folders.py --dry-run

# Apply renames
python3 tools/rename_folders.py
```

Scoped to one branch:

```bash
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science" --dry-run
python3 tools/rename_folders.py --path "incoming/Artificial Intelligence and Data Science"

python3 tools/rename_folders.py --path "incoming/First Year"
python3 tools/rename_folders.py --path "incoming/M.B.A"
python3 tools/rename_folders.py --path "incoming/Honors Course"
```

---

## Use Case 5 — "Rename files" / "Review PDF renames"

Run after folder normalization:

```bash
python3 tools/rename_files.py --ocr-workers 1
```

If `changelog/rename.json` exists, this retries only `retry_pending` rows. Force a full rebuild:

```bash
python3 tools/rename_files.py --fresh --ocr-workers 1
```

Scoped to one subtree:

```bash
# Standard branch
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern" --ocr-workers 1

# First Year
python3 tools/rename_files.py --path "incoming/first-year" --ocr-workers 1

# MBA
python3 tools/rename_files.py --path "incoming/m-b-a" --ocr-workers 1

# Honors Course
python3 tools/rename_files.py --path "incoming/honors-course" --ocr-workers 1
```

Read `changelog/rename.md`, then apply:

```bash
python3 tools/rename_files.py --apply

# Scoped apply
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science"
```

---

## Use Case 6 — "Fix needs_review files"

### Step 1: Understand why files are in needs_review

```bash
python3 tools/status.py --print
```

Check the `Needs Review Reasons` section. Common reasons:

| Reason | Meaning | Action |
|---|---|---|
| `invalid_pdf` | PDF is corrupted or too small | Inspect the file; discard if junk |
| `duplicate` | Target path already exists in `papers/` | Check for duplicates; keep the better one |
| `groq_failed` | OCR + Groq could not extract metadata | Retry rename review |
| `bad_filename` | Could not parse month/year from filename | Rename source file and rerun review |
| `verify_failed` | Filename format doesn't match expected pattern | Check path and rerun verify |

### Step 2: For Groq failures — just rerun rename review

```bash
python3 tools/rename_files.py --ocr-workers 1
python3 tools/rename_files.py --apply
python3 tools/verify.py
python3 tools/move.py
```

### Step 3: For persistent failures — inspect manually

```bash
# Check what's in needs_review
python3 tools/status.py --print
```

Files in `needs_review/` stay there until manually resolved. The SQLite row has `NEEDS_REVIEW` stage and a `review_reason` field.

---

## Use Case 7 — "Verify folder" / "Run verify"

```bash
python3 tools/verify.py

# Preview only
python3 tools/verify.py --dry-run
```

`verify.py` is always global. It promotes valid `FILE_RENAMED` rows to `VERIFIED`.

---

## Use Case 8 — "Move folder" / "Move verified files to papers"

```bash
# Move all VERIFIED files
python3 tools/move.py

# Preview only
python3 tools/move.py --dry-run

# Scoped move
python3 tools/move.py --path "incoming/artificial-intelligence-and-data-science"
python3 tools/move.py --path "incoming/first-year"
python3 tools/move.py --path "incoming/m-b-a"
python3 tools/move.py --path "incoming/honors-course"
```

---

## Use Case 9 — "Upload to cloud" / "Publish papers"

```bash
python3 tools/upload_pipeline.py preflight
python3 tools/upload_pipeline.py scan
python3 tools/upload_pipeline.py sync --workers 4
python3 tools/upload_pipeline.py manifest
python3 tools/upload_pipeline.py summary
```

Or in one command:

```bash
python3 tools/upload_pipeline.py all
```

Retry failed uploads:

```bash
python3 tools/upload_pipeline.py sync --state FAILED
```

---

## Use Case 10 — "Map semester for [branch/pattern]"

Run after files are in `papers/`. See [semester.md](semester.md) for the full research workflow.

```bash
# Preview local context
python3 tools/semester_mapping.py preview papers/artificial-intelligence-and-data-science/te/2019_pattern

# Create unresolved draft
python3 tools/semester_mapping.py review papers/artificial-intelligence-and-data-science/te/2019_pattern
```

Research syllabus sources for each subject. Then stage results:

```bash
python3 tools/semester_mapping.py stage /tmp/semester-stage.json
```

Tell the user to review `changelog/semester.md`. After approval:

```bash
python3 tools/semester_mapping.py apply
```

---

## Use Case 11 — "Full sync everything"

```bash
# Review phase
python3 tools/pipeline.py --review

# Read changelog/folder.md and changelog/files.md, then:
python3 tools/pipeline.py --apply-reviewed --rclone --workers 8

# Read changelog/rename.md, then:
python3 tools/pipeline.py --apply-renames
```

Or explicitly skip review confirmation:

```bash
python3 tools/pipeline.py --full --apply
python3 tools/pipeline.py --full --apply --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
```

---

## Use Case 12 — "Rebuild the mapping"

For a full Drive mapping rebuild (rarely needed):

```bash
python3 tools/map.py build
python3 tools/rename_folders.py --create
python3 tools/status.py --print
```

For specific branches only:

```bash
python3 tools/map.py refresh --branch "Mechanical Engineering" --branch "Civil Engineering"
python3 tools/rename_folders.py --create
```

---

## Use Case 13 — "Discard pending changes"

```bash
# Discard all pending folder changes
python3 tools/sync.py --folders --discard

# Discard all pending file downloads
python3 tools/sync.py --files --discard

# Discard specific folder change
python3 tools/sync.py --folders --discard "Computer Engineering/TE/2019 Pattern/New Subject"

# Discard specific file download
python3 tools/sync.py --files --discard "1DriveFileId"

# Discard current rename review
python3 tools/rename_files.py --discard

# Discard pending semester mapping
python3 tools/semester_mapping.py discard
```

---

## Decision Tree for Common Requests

```
User says → What to run

"Scan folders" / "Check folder structure"
  → tools/sync.py --folders
  → [review changelog/folder.md]
  → tools/sync.py --folders --apply
  → tools/rename_folders.py --create

"Scan [branch] files" / "Check if [branch] is up to date"
  → tools/sync.py --files "[Branch]"
  → [review changelog/files.md]
  → tools/sync.py --files --apply --rclone --workers 8
  → tools/rename_folders.py --create
  → tools/rename_folders.py
  → tools/rename_files.py --ocr-workers 1
  → [review changelog/rename.md]
  → tools/rename_files.py --apply
  → tools/verify.py
  → tools/move.py

"Rename folders"
  → tools/rename_folders.py --create
  → tools/rename_folders.py --dry-run
  → tools/rename_folders.py

"Rename files" / "Review PDF renames"
  → tools/rename_files.py --ocr-workers 1
  → [review changelog/rename.md]
  → tools/rename_files.py --apply

"Fix needs_review files"
  → tools/status.py --print   (check reasons)
  → tools/rename_files.py --ocr-workers 1   (if groq_failed)
  → tools/rename_files.py --apply
  → tools/verify.py
  → tools/move.py

"Verify folder"
  → tools/verify.py

"Move files" / "Move to papers"
  → tools/move.py [--path incoming/...]

"Upload to cloud"
  → tools/upload_pipeline.py preflight
  → tools/upload_pipeline.py scan
  → tools/upload_pipeline.py sync --workers 4
  → tools/upload_pipeline.py manifest

"Map semester for [branch]"
  → tools/semester_mapping.py preview papers/...
  → [research SPPU syllabi]
  → tools/semester_mapping.py stage /tmp/semester-stage.json
  → [human review changelog/semester.md]
  → tools/semester_mapping.py apply

"Full sync"
  → tools/pipeline.py --full --apply [--scope "..."]
```

---

## Normalized Path Quick Reference

After `rename_folders.py` runs, incoming paths follow these patterns:

| Family | Pattern | Example |
|---|---|---|
| Standard | `incoming/<branch>/<year>/<pattern>/<subject>/` | `incoming/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/` |
| First Year | `incoming/first-year/<pattern>/<subject>/` | `incoming/first-year/2019_pattern/engineering_mathematics_I_fy/` |
| MBA | `incoming/m-b-a/<semester>/<pattern>/<subject>/` | `incoming/m-b-a/sem_II/2019_pattern/financial_management/` |
| Honors | `incoming/honors-course/<year>/<subject>/` | `incoming/honors-course/te/artificial_intelligence_hc/` |

**Naming rules:**
- Branch names: **hyphens** (`artificial-intelligence-and-data-science`)
- Everything else: **underscores** (`2019_pattern`, `machine_learning_aids`)
- `&` → `and`, `+` → `plus`, `@` → `at`, `%` → `percent`
- Roman numerals preserved in uppercase: `ele_V`, `engineering_mathematics_II`

---

## Output Filename Format

```
{exam_type}_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf
```

| Exam type | Marks |
|---|---|
| `insem` | 30 |
| `endsem` | 70 |
| `other` | Any other valid value |

Examples:

```
endsem_may_jun_2024_aids_bda_eV_2019p.pdf
insem_oct_2023_comp_wt_2019p.pdf
endsem_nov_dec_2022_fy_em1_2019p.pdf
endsem_may_2024_hc_ai_te.pdf
```

---

## Common Mistakes to Avoid

| Mistake | Correct Approach |
|---|---|
| Running `--files --apply` before `--files` review | Always run `--files` first, read `changelog/files.md`, then `--files --apply` |
| Wrong case or spelling in scope | Use exact Drive names from `mapping/folder_names.yml` |
| Running `rename_files.py` before `rename_folders.py` | Always normalize folders first |
| Editing changelog marker comments | Never. Apply parses these. |
| Using `--files` and `--folders` together | Mutually exclusive. Run separately. |
| Forgetting `--create` after mapping changes | Always run `rename_folders.py --create` after `sync.py --folders --apply` or `map.py` |
| Assuming `--apply-reviewed --scope` scopes apply | `--apply-reviewed` applies all pending changelog entries, regardless of scope |
| Running scoped rename with display-name path | Use normalized path: `incoming/artificial-intelligence-and-data-science/...` |
| Treating First Year like a standard branch | First Year has NO year tier. `"First Year/2019 Pattern"` not `"First Year/BE/2019 Pattern"` |
| Treating Honors Course like a standard branch | Honors has NO pattern tier. `"Honors Course/TE"` not `"Honors Course/TE/2019 Pattern"` |

---

## Key Files for Agent Reference

| File | Read this when... |
|---|---|
| `mapping/folder_names.yml` | You need exact Drive display names or normalized folder names before running scoped commands |
| `changelog/folder.md` | You need to review pending folder changes before applying |
| `changelog/files.md` | You need to review pending file downloads before applying |
| `changelog/rename.md` | You need to review planned PDF renames before applying |
| `changelog/semester.md` | You need to review pending semester assignments before applying |
| `docs/status.md` | You need a quick snapshot of current pipeline state |
| `tracking/manifest.db` | You need to query file stages directly (SQLite) |

---

## Environment Setup

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

Required `config.json`:

```json
{
  "root_folder_id": "0Bz9C0ysJZ7PnMGZKeWcybUpXWGM",
  "request_timeout": 30,
  "max_retries": 5,
  "backoff_factor": 1.5
}
```

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```
