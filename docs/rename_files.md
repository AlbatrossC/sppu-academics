# Rename Files

> For agent-specific workflows and use cases, see [AGENTIC.md](../AGENTIC.md).

`tools/rename_files.py` renames downloaded PDFs after folders under `incoming/` have already been normalized.

It is review-first:

```bash
python3 tools/rename_files.py
```

creates:

```text
changelog/rename.md
```

and does not move files.

After reviewing the changelog:

```bash
python3 tools/rename_files.py --apply
```

renames files based only on `changelog/rename.json`. Apply mode does not call PyMuPDF, PaddleOCR, or Groq again.

## Metadata Responsibility

The metadata pipeline is:

```text
PyMuPDF header text -> PaddleOCR header crop -> Groq fallback
```

Only these exam metadata values are extracted:

```text
marks
month_code
year
```

The script decides exam type from marks:

```text
30 -> insem
70 -> endsem
any other valid marks value -> other
```

The script does not ask a model to decide branch, subject, pattern, branch code, subject code, or pattern code. Those values are derived locally from the file path and:

```text
mapping/folder_names.yml
```

The script prefers month/year from the PDF filename first. It supports single-month and two-month names such as `Aug_2025`, `Sep_2024`, `May_Jun_2023`, and `Nov_Dec_2022`. Groq month/year output is only a fallback if the filename cannot be parsed.

Marks are read from PyMuPDF header text first. If the header text is missing, garbled, watermark-only, or does not contain usable marks, PaddleOCR runs on page 1 crops only: top 45%, then top 65%, then the full first page. It checks lines near `Max Marks`, `Max. Marks`, `Maximum Marks`, or `Total Marks`. Groq is called only if local extraction is still incomplete; when OCR text exists, Groq receives that OCR text instead of the useless embedded watermark text.

## Setup

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

PaddleOCR now defaults to the first Windows CUDA GPU:

```bash
python3 tools/rename_files.py --ocr-device gpu:0
```

You can also set the default once for the shell:

```powershell
$env:PADDLEOCR_DEVICE = "gpu:0"
```

Use CPU only as a fallback:

```bash
python3 tools/rename_files.py --ocr-device cpu
```

The OCR settings remain conservative for an RTX 3050 Laptop GPU with 4 GB VRAM: one OCR worker, confidence threshold `0.85`, a relaxed direct-phrase threshold `0.55`, and page 1 crop attempts at `45%`, `65%`, and `100%`. The relaxed threshold is used only after OCR sees a direct `Max/Maximum/Total Marks` phrase. The expected local stack is PaddleOCR `3.6.0`, PaddlePaddle GPU `3.3.0`, and PaddleX `3.6.1`.

Set one optional Groq fallback key:

```bash
GROQ_API_KEY=your_key_here
```

Optional secondary keys:

```bash
GROQ_API_KEY_2=your_second_key_here
GROQ_API_KEY_3=your_third_key_here
```

or:

```bash
GROQ_API_KEYS=key_one,key_two,key_three
```

Optional model override:

```bash
GROQ_MODEL=llama-3.3-70b-versatile
```

## Output Filename

Successful PDFs are renamed in their current working folder, usually `incoming/`, and keep the same relative folder path. `verify.py` promotes valid renamed files to `VERIFIED`, then `move.py` moves them to `papers/`.

The filename format is:

```text
{exam_type}_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf
```

Example:

```text
endsem_may_jun_2024_aids_bda_eV_2019p.pdf
```

Months use short lowercase names:

```text
Feb - 2023.pdf -> feb_2023
May_Jun_2024.pdf -> may_jun_2024
August_2025.pdf -> aug_2025
```

## Folder Families

Standard branch paths:

```text
incoming/<branch>/<year>/<pattern>/<subject>/<file>.pdf
```

First Year paths:

```text
incoming/first-year/<pattern>/<subject>/<file>.pdf
```

MBA paths:

```text
incoming/m-b-a/<semester>/<pattern>/<subject>/<file>.pdf
```

Honors paths:

```text
incoming/honors-course/<year>/<subject>/<file>.pdf
```

For Honors, the year folder code is used as `pattern_code`.

## Review Commands

Review all PDFs:

```bash
python3 tools/rename_files.py
```

If `changelog/rename.json` already exists, this command skips completed rows and retries only `retry_pending` rows. This is useful after Groq rate limits.

Force a full rebuild:

```bash
python3 tools/rename_files.py --fresh
```

Review with compatibility worker flag:

```bash
python3 tools/rename_files.py --ocr-workers 1 --ocr-device gpu:0
```

Review mode checkpoints after each PDF. `--workers` is still accepted as a compatibility alias for `--ocr-workers`; the default remains `1` for 4 GB GPU VRAM, and the default OCR device is `gpu:0` unless `PADDLEOCR_DEVICE` is set.

Review one subtree:

```bash
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
```

Review one PDF:

```bash
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern/deep_learning_ele_V/March_2024.pdf"
```

Discard the current rename review without moving PDFs:

```bash
python3 tools/rename_files.py --discard
```

## Apply Commands

Apply all pending entries. This updates SQLite after each individual file, so interrupted runs are resumable:

```bash
python3 tools/rename_files.py --apply
```

Apply only entries from one source subtree:

```bash
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science"
```

Successful files are renamed in place under the working folder:

```text
incoming/<same relative folders>/<normalized filename>.pdf
```

Files that cannot be safely renamed move to:

```text
needs_review/<same incoming-relative folders>/<original filename>
```

Existing files in `papers/` are never overwritten. If a target already exists, the source file is moved to `needs_review/` and the changelog records the duplicate reason.

SQLite tracking is updated during apply:

- successful renames become `FILE_RENAMED`
- review failures become `NEEDS_REVIEW`
- Groq fallback key index/model and review reason are stored in `tracking/manifest.db`
- `current_path` records where the file is now
- `expected_path` records where the file should eventually move under `papers/`

After apply, run:

```bash
python3 tools/verify.py
python3 tools/move.py
```

`verify.py` promotes valid renamed files to `VERIFIED`. `move.py` moves only `VERIFIED` files to `papers/`.

## Changelog

`changelog/rename.md` contains:

- subject summary counts for `insem`, `endsem`, `other`, and `needs_review`
- readable `Planned Renames` blocks with clickable incoming PDF links
- readable `Needs Review` blocks for failed, ambiguous, duplicate, or unsafe files
- initial filename, changed filename, type, marks, source, and reason

`changelog/rename.json` contains the machine-readable state used by `--apply`.

The changelog is updated after each applied file, so if the command stops midway you can rerun:

```bash
python3 tools/rename_files.py --apply
```
