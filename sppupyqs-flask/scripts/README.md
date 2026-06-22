# PYQ Metadata Pipeline

This pipeline reads SPPU manifest subject JSON files, builds each PDF URL from the manifest provider data, downloads each PDF, extracts paper text, sends that text to Gemini using your existing prompt and schema files, and stores resumable structured metadata output inside `pyqs-metadata`.

## Folder Layout

The pipeline expects this structure:

```text
sppupyqs/
├── scripts/
│   ├── .env
│   ├── config.py
│   ├── extractor.py
│   ├── gemini_client.py
│   ├── json_manager.py
│   ├── logger.py
│   ├── main.py
│   ├── metadata.txt
│   ├── prompt.txt
│   ├── README.md
│   ├── requirements.txt
│   ├── structure_output.json
│   ├── strucutre_output.json
│   └── utils.py
├── manifest/
│   ├── 2012_subjects.json
│   ├── 2015_subjects.json
│   ├── 2019_subjects.json
│   └── honors_subjects.json
└── pyqs-metadata/
```

## How It Works

When you run `main.py`, the pipeline performs these steps:

1. Loads `.env` from `sppupyqs/scripts/.env`.
2. Loads the Gemini system prompt from `prompt.txt`.
3. Loads the response schema from `structure_output.json`.
   If that file is missing, it automatically falls back to the existing `strucutre_output.json`.
4. Reads all `*_subjects.json` files from `sppupyqs/manifest`.
5. Uses the R2 provider by default:
   `providers.r2BaseUrl + papers[].canonicalPath`
6. Iterates:
   `manifest -> subjects -> papers`
7. When you run `python main.py` without filters, prompts for:
   pattern/course -> branch -> year -> subject.
7. Downloads each PDF and extracts text with PyMuPDF using `page.get_text("text")`.
8. If extracted text is too small or invalid, retries using OCR fallback.
9. Sends extracted text to Gemini using:
   `gemini-3.1-flash-lite`
10. Tries `PRIMARY_GEMINI_API_KEY` first and retries with `SECONDARY_GEMINI_API_KEY` if needed.
11. Generates deterministic `pdf_id` values from `sha1(pdf_url)[:12]`.
12. Generates local `question_id` values after Gemini returns JSON.
13. Skips PDFs already present in the target subject metadata file.
14. Writes subject JSON files atomically so partial writes do not corrupt output.
15. Appends progress snapshots and failure logs to `metadata.txt`.

## Examples

```bash
python main.py
python main.py --pattern 2019
python main.py --branch aids
python main.py --pattern 2019 --branch aids --year te
python main.py --branch aids --semester sem-7
python main.py --branch aids --subject machine_learning_aids
python main.py --branch aids --limit 5
python main.py --provider cloudinary --limit 5
```

## Input Format

Each subject manifest inside `sppupyqs/manifest/*_subjects.json` should follow this shape:

```json
{
  "schemaVersion": 2,
  "pattern": "2019_pattern",
  "patternYear": "2019",
  "providers": {
    "r2BaseUrl": "https://sppu-pyqs.albatrossc.workers.dev",
    "cloudinaryRawBaseUrl": "https://res.cloudinary.com/example/raw/upload"
  },
  "subjects": {
    "machine_learning_aids": {
      "subjectKey": "machine_learning_aids",
      "fullName": "Machine Learning",
      "branchKey": "artificial-intelligence-and-data-science",
      "branchCode": "aids",
      "branchName": "Artificial Intelligence and Data Science",
      "yearKey": "be",
      "yearName": "BE",
      "semesterNo": 7,
      "papers": [
        {
          "pdfId": "1RBEqdUb-DvLTXys8i6oHjjNG8JeafEFu",
          "canonicalPath": "papers/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/endsem_nov_dec_2023_aids_mla_2019p.pdf",
          "exam": "endsem",
          "month": "nov_dec",
          "year": 2023
        }
      ]
    }
  }
}
```

By default, the example paper resolves to:

```text
https://sppu-pyqs.albatrossc.workers.dev/papers/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/endsem_nov_dec_2023_aids_mla_2019p.pdf
```

## Output Format

Output is written to:

```text
sppupyqs/pyqs-metadata/<branch>/<semester>/<subject-slug>.json
```

For manifest subjects with `semesterNo`, `<semester>` is `sem-<number>`. If a subject does not include `semesterNo`, the script falls back to the subject `yearKey`.

Example:

```text
pyqs-metadata/
└── aids/
    └── sem-7/
        └── machine_learning_aids.json
```

Each subject JSON looks like:

```json
{
  "subject_name": "Discrete Mathematics",
  "subject_slug": "discrete-mathematics-aids",
  "branch": "aids",
  "semester": "sem-3",
  "papers": [
    {
      "pdf_id": "1RBEqdUb-DvLTXys8i6oHjjNG8JeafEFu",
      "pdf_url": "https://sppu-pyqs.albatrossc.workers.dev/papers/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/endsem_nov_dec_2023_aids_mla_2019p.pdf",
      "canonical_path": "papers/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/endsem_nov_dec_2023_aids_mla_2019p.pdf",
      "pattern_key": "2019",
      "pattern_year": "2019",
      "year_key": "be",
      "year_name": "BE",
      "source_metadata": {
        "branch_key": "artificial-intelligence-and-data-science",
        "branch_name": "Artificial Intelligence and Data Science",
        "exam": "endsem",
        "month": "nov_dec",
        "year": 2023
      },
      "metadata": {},
      "questions": [],
      "extraction_info": {
        "method": "pymupdf_text",
        "used_ocr": false,
        "page_count": 4,
        "character_count": 5271,
        "processed_at": "2026-05-09 12:10:00"
      }
    }
  ]
}
```

## Environment Variables

Create `sppupyqs/scripts/.env` with:

```env
PRIMARY_GEMINI_API_KEY=your_primary_key
SECONDARY_GEMINI_API_KEY=your_secondary_key
GEMINI_MODEL=gemini-3.1-flash-lite
REQUEST_TIMEOUT_SECONDS=60
GEMINI_RETRIES_PER_KEY=3
GEMINI_RETRY_DELAY_SECONDS=3
PDF_TEXT_MIN_CHARACTERS=200
OCR_LANGUAGE=eng
TESSERACT_CMD=
```

`TESSERACT_CMD` is optional. Set it only if Tesseract is installed in a custom location.

## Install Dependencies

Install the pipeline dependencies from the `scripts` folder:

```bash
pip install -r requirements.txt
```

Main packages:

- `PyMuPDF` for default PDF text extraction
- `pytesseract` and `Pillow` for OCR fallback
- `google-genai` for Gemini requests
- `requests` for downloading manifest PDF URLs

## Running The Pipeline

From `sppupyqs/scripts`:

```bash
python main.py
```

With no filters, the script opens an interactive selector:

1. Choose `2019 Pattern`, `2015 Pattern`, `2012 Pattern`, or `M.B.A`.
2. Choose a branch, or `All branches`.
3. Choose a year, or `All years`.
4. Choose a subject, or `All subjects`.

Or from the repo root:

```bash
python sppupyqs/scripts/main.py
```

Useful filters:

- `--pattern` processes one manifest pattern, for example `2019` or `honors`
- `--branch` processes one branch code or branch key, for example `aids` or `computer-engineering`
- `--year` processes one year key, for example `se`, `te`, or `be`
- `--semester` narrows processing to one semester
- `--subject` narrows processing to one subject
- `--limit` processes only a fixed number of new PDFs
- `--provider` selects `r2` or `cloudinary`; it defaults to `r2`
- `--no-interactive` skips the selector when no filters are provided

## metadata.txt Logging

The script appends progress to:

```text
sppupyqs/scripts/metadata.txt
```

It records:

- processed count
- skipped count
- failed count
- remaining count
- current branch
- current semester
- current subject
- Gemini failures
- OCR usage
- timestamps

## Resumable Behavior

The pipeline is safe to rerun.

Before processing a PDF, it loads the existing subject output JSON and checks whether that `pdf_url` is already present in `papers`.

If found, the PDF is skipped.

This prevents duplicate processing and supports long-running incremental builds.

## Error Handling

The pipeline is designed to continue when one PDF fails.

- PDF extraction failures are logged and counted.
- Gemini failures are logged and counted separately.
- OCR is used only when normal text extraction is not good enough.
- Output writes are atomic.
- All files use UTF-8.

## Notes

- `extract.py` is an older standalone helper and is not used by the production pipeline.
- `structure_output.json` is now the preferred schema filename.
- `strucutre_output.json` is still supported as a fallback for compatibility.
