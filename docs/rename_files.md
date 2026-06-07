# Rename Files — `tools/rename_files.py`

`tools/rename_files.py` renames downloaded PDFs after `incoming/` folder names have been normalized.

It is **review-first**: the default command produces a changelog but does not move or rename any files. Apply is a separate step that reads only from the generated changelog.

---

## Metadata Extraction Pipeline

```
PyMuPDF (header text)
  → PaddleOCR (page 1 crops: 45% / 65% / 100%)
  → Groq (last resort for marks / month_code / year)
```

Only three exam metadata values are extracted from the PDF:

| Field | Source |
|---|---|
| `marks` | Header text (PyMuPDF first, then PaddleOCR) |
| `month_code` | Filename first (e.g. `May_Jun_2024`); Groq fallback |
| `year` | Filename first; Groq fallback |

Everything else — branch code, subject code, pattern code, exam type — is derived **locally** from the normalized file path and `mapping/folder_names.yml`. No model is asked to decide these.

**Exam type from marks:**

| Marks value | Exam type |
|---|---|
| `30` | `insem` |
| `70` | `endsem` |
| Any other valid value | `other` |

---

## Output Filename Format

```
{exam_type}_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf
```

**Examples:**

| Scenario | Filename |
|---|---|
| End-sem, May-Jun 2024, AIDS, Big Data Analytics, Elective V | `endsem_may_jun_2024_aids_bda_eV_2019p.pdf` |
| In-sem, October 2023, CompE, Web Technology | `insem_oct_2023_comp_wt_2019p.pdf` |
| End-sem, Nov-Dec 2022, First Year, Engineering Maths I | `endsem_nov_dec_2022_fy_em1_2019p.pdf` |
| Honors Course, BE year used as pattern | `endsem_may_2024_hc_ml_be.pdf` |

**Month normalization:**

| Filename pattern | Output month |
|---|---|
| `Feb-2023.pdf` | `feb_2023` |
| `May_Jun_2024.pdf` | `may_jun_2024` |
| `August_2025.pdf` | `aug_2025` |
| `Nov_Dec_2022.pdf` | `nov_dec_2022` |

---

## Folder Family Paths

The script understands all four folder families:

| Family | Incoming path structure |
|---|---|
| Standard | `incoming/<branch>/<year>/<pattern>/<subject>/<file>.pdf` |
| First Year | `incoming/first-year/<pattern>/<subject>/<file>.pdf` |
| MBA | `incoming/m-b-a/<semester>/<pattern>/<subject>/<file>.pdf` |
| Honors Course | `incoming/honors-course/<year>/<subject>/<file>.pdf` |

For Honors Course, the year folder code (e.g. `be`, `te`) is used as `pattern_code` in the filename.

---

## Review Commands

### Review all PDFs

```bash
python3 tools/rename_files.py --ocr-workers 1
```

If `changelog/rename.json` already exists, this command skips completed rows and retries only `retry_pending` (Groq rate-limited) rows. To ignore the existing changelog and rebuild from scratch:

```bash
python3 tools/rename_files.py --fresh --ocr-workers 1
```

### Review a subtree

```bash
# Standard branch — one year
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"

# Standard branch — one subject
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids"

# First Year
python3 tools/rename_files.py --path "incoming/first-year/2019_pattern"

# MBA
python3 tools/rename_files.py --path "incoming/m-b-a/sem_II/2019_pattern"

# Honors Course
python3 tools/rename_files.py --path "incoming/honors-course/be"
```

### Review a single PDF

```bash
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern/deep_learning_ele_V/March_2024.pdf"
```

### Discard the current review

```bash
python3 tools/rename_files.py --discard
```

This clears `changelog/rename.json` without touching any PDF files.

---

## Apply Commands

### Apply all pending entries

```bash
python3 tools/rename_files.py --apply
```

Apply reads only from `changelog/rename.json` and does not call PyMuPDF, PaddleOCR, or Groq again. SQLite is updated after each individual file, so interrupted runs are resumable — just rerun the same command.

### Apply for one subtree

```bash
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science"
python3 tools/rename_files.py --apply --path "incoming/first-year"
python3 tools/rename_files.py --apply --path "incoming/m-b-a"
python3 tools/rename_files.py --apply --path "incoming/honors-course"
```

---

## File Destinations

After apply:

| Outcome | Destination |
|---|---|
| Successful rename | `incoming/<same relative path>/<normalized_name>.pdf` |
| Unsafe / failed / duplicate | `needs_review/<same incoming-relative path>/<original_name>` |

Existing files in `papers/` are never overwritten. If a normalized target already exists in `papers/`, the source file moves to `needs_review/` and the changelog records `duplicate` as the reason.

**SQLite updates during apply:**

| Outcome | Stage |
|---|---|
| Successful rename | `FILE_RENAMED` |
| Review failure | `NEEDS_REVIEW` |

`current_path` records where the file is now. `expected_path` records where it should eventually move under `papers/`.

---

## Groq Rate Limits

When Groq rate-limits a file, the row stays `retry_pending` in `changelog/rename.json`. It is **not** moved to `needs_review/`. Simply rerun:

```bash
python3 tools/rename_files.py --ocr-workers 1
```

Only `retry_pending` rows will be retried.

---

## OCR Configuration

PaddleOCR defaults to the first Windows CUDA GPU:

```bash
python3 tools/rename_files.py --ocr-device gpu:0
```

Set default once for the shell (PowerShell):

```powershell
$env:PADDLEOCR_DEVICE = "gpu:0"
```

Use CPU only as fallback:

```bash
python3 tools/rename_files.py --ocr-device cpu
```

Default OCR worker count is `1` for 4 GB VRAM. The expected stack is PaddleOCR `3.6.0`, PaddlePaddle GPU `3.3.0`, and PaddleX `3.6.1`.

---

## Groq API Keys

Set one optional Groq fallback key in `.env`:

```env
GROQ_API_KEY=your_key_here
```

Optional secondary keys:

```env
GROQ_API_KEY_2=your_second_key
GROQ_API_KEY_3=your_third_key

# Or use the comma-separated list form:
GROQ_API_KEYS=key_one,key_two,key_three
```

Optional model override:

```env
GROQ_MODEL=llama-3.3-70b-versatile
```

---

## Changelog Files

| File | Contents |
|---|---|
| `changelog/rename.md` | Human-readable review: subject summaries, planned renames with clickable links, needs-review blocks |
| `changelog/rename.json` | Machine-readable state used by `--apply` |

`changelog/rename.md` contains:
- Subject summary counts for `insem`, `endsem`, `other`, and `needs_review`
- Readable `Planned Renames` blocks with clickable incoming PDF links
- Readable `Needs Review` blocks for failed, ambiguous, duplicate, or unsafe files
- Initial filename, changed filename, type, marks, source, and reason

> [!CAUTION]
> Never edit `changelog/rename.json` by hand. Never delete the marker comments in `changelog/rename.md`.
> ```html
> <!-- RENAME_FILES_BEGIN -->
> <!-- RENAME_FILES_END -->
> ```

---

## After Apply

```bash
python3 tools/verify.py
python3 tools/move.py
```

`verify.py` promotes valid renamed files to `VERIFIED`. `move.py` moves only `VERIFIED` files to `papers/`. See [verify_move.md](verify_move.md).
