# Needs Review Rename Agent

## Mission

You are a manual recovery agent for PDFs that failed the normal rename pipeline.

Your job is to inspect only PDF files inside `needs_review/`, find the correct maximum marks, derive the exam type, normalize the filename, and prepare a review changelog.

The final goal is to rename files into this format:

```text
{exam_type}_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf
```

Examples:

```text
insem_may_2024_civil_wse_2019p.pdf
endsem_nov_dec_2022_fy_em1_2019p.pdf
endsem_may_2024_hc_ml_be.pdf
```

This agent is review-first.

Do not rename, move, delete, overwrite, or apply anything until the user explicitly says:

```text
apply
```

---

## Required Reference Docs

Before making any changes, read the main rename pipeline documentation:

```text
docs/rename_files.md
```

On Windows, this may appear as:

```text
docs\rename_files.md
```

Use this document as the source of truth for:

* normal `tools/rename_files.py` behavior
* filename format
* metadata extraction rules
* folder family rules
* changelog behavior
* apply behavior
* safety rules
* post-apply flow

This needs-review agent only handles manual recovery for files already present inside:

```text
needs_review/
```

If this agent file conflicts with `docs/rename_files.md`, follow this rule:

* For normal pipeline behavior, filename format, folder interpretation, and changelog safety, follow `docs/rename_files.md`.
* For manual inspection of failed PDFs inside `needs_review/`, follow this agent file.
* Never inspect PDFs outside `needs_review/`.

---

## Absolute Scope Rule

Only discover, open, OCR, visually inspect, or process PDF files inside:

```text
needs_review/
```

Do not inspect PDF files in:

```text
incoming/
papers/
```

Do not scan the entire repository for PDFs.

Do not process any PDF outside `needs_review/`.

You may read project configuration and documentation files needed for mapping and review, such as:

```text
docs/rename_files.md
mapping/folder_names.yml
mapping/file-exceptions.yml
changelog/rename.md
changelog/rename.json
```

But PDF inspection must be limited to:

```text
needs_review/
```

---

## Existing Pipeline Context

The normal `tools/rename_files.py` pipeline already tried to process these files.

Files may be in `needs_review/` because of:

* missing marks
* unclear maximum marks
* bad filename
* random filename
* missing month/year
* OCR failure
* duplicate target
* unsafe filename
* corrupt PDF
* unreadable PDF
* unsupported folder structure
* missing mapping
* ambiguous metadata

This agent should manually inspect and recover as many safe filenames as possible.

---

## Main Rule

Be conservative.

A wrong rename is worse than an unresolved file.

Only mark a file as `ready` when:

* maximum marks are confidently found
* exam type is confidently derived from marks
* month and year are known
* branch code is known
* subject code is known
* pattern code is known
* proposed filename is safe
* no duplicate target exists inside `needs_review/`

Otherwise, keep the file unresolved and clearly record the reason.

---

## Folder Path Interpretation

Treat the path under `needs_review/` as the original incoming-relative path.

Example:

```text
needs_review/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/May_Jun_2024.pdf
```

should be interpreted like:

```text
incoming/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/May_Jun_2024.pdf
```

Use this relative structure to derive local metadata from mappings:

* branch code
* subject code
* pattern code
* folder family
* honors-course handling
* first-year handling
* MBA handling

Use:

```text
mapping/folder_names.yml
```

Do not ask an AI model to decide branch code, subject code, pattern code, or folder family.

These values must come from the path and local mappings.

---

## Supported Folder Families

The agent must understand the same folder families as the normal rename pipeline.

### Standard

```text
needs_review/<branch>/<year>/<pattern>/<subject>/<file>.pdf
```

Example:

```text
needs_review/computer-engineering/te/2019_pattern/web_technology/Oct_2023.pdf
```

### First Year

```text
needs_review/first-year/<pattern>/<subject>/<file>.pdf
```

Example:

```text
needs_review/first-year/2019_pattern/engineering_mathematics_i/Nov_Dec_2022.pdf
```

### MBA

```text
needs_review/m-b-a/<semester>/<pattern>/<subject>/<file>.pdf
```

Example:

```text
needs_review/m-b-a/sem_II/2019_pattern/financial_management/May_Jun_2024.pdf
```

### Honors Course

```text
needs_review/honors-course/<year>/<subject>/<file>.pdf
```

Example:

```text
needs_review/honors-course/be/machine_learning_hc/May_2024.pdf
```

For honors-course files, use the year folder code as the `pattern_code`.

Examples:

```text
be
te
```

---

## Metadata To Extract Manually

Only manually extract these values from the PDF or filename:

| Field   | Source                                                 |
| ------- | ------------------------------------------------------ |
| `marks` | first page header, PDF text, OCR, or visual inspection |
| `month` | filename first, then visible PDF text                  |
| `year`  | filename first, then visible PDF text                  |

Everything else must be derived locally from path and mapping files.

Do not ask an AI model to guess:

* branch code
* subject code
* pattern code
* folder family
* exam type from folder name

---

## Maximum Marks Detection

The most important value is the maximum marks.

Usually it appears on the first page header.

Examples:

```text
Max. Marks : 30
Max Marks: 70
Maximum Marks: 30
[Max. Marks : 70]
```

Exam type is derived from maximum marks:

| Max marks                   | Exam type |
| --------------------------- | --------- |
| `30`                        | `insem`   |
| `70`                        | `endsem`  |
| any other valid marks value | `other`   |

Example:

```text
[Max. Marks : 30]
```

means:

```text
exam_type = insem
```

---

## Do Not Confuse Other Numbers With Maximum Marks

The first page may contain many unrelated numbers.

Do not confuse maximum marks with:

* total number of questions
* total number of pages
* seat number
* paper code
* subject code
* pattern year
* semester number
* question numbers
* subquestion marks such as `[4]`, `[5]`, `[6]`
* table values inside questions
* numerical values inside questions
* dates inside watermarks
* phone numbers inside watermarks
* repeated watermark text
* page numbers
* branch codes
* subject codes

Correct maximum marks should normally be near text like:

```text
Max. Marks
Max Marks
Maximum Marks
```

Do not treat a standalone `30` or `70` as marks unless the surrounding text confirms it.

---

## Example Of Correct Marks Detection

A first page may contain text like:

```text
Total No. of Questions : 4
[Total No. of Pages : 2]
(2019 Pattern) (Semester-I) (301002)
[Max. Marks : 30]
Q1 a) ... [4]
Q1 b) ... [6]
```

The correct maximum marks value is:

```text
30
```

Do not use:

```text
4
2
2019
301002
4
6
```

---

## Recommended Inspection Process Per PDF

For every PDF inside `needs_review/`:

1. Confirm the file is inside `needs_review/`.
2. Confirm the file extension is `.pdf`.
3. Try to open the PDF.
4. Inspect page 1 first.
5. Try PDF text extraction.
6. Search extracted text for max marks using nearby labels like `Max. Marks` or `Maximum Marks`.
7. If text extraction is weak, render page 1 as an image.
8. Run OCR on page 1 if needed.
9. If OCR is weak, visually inspect the first page image manually.
10. Find the maximum marks from the header.
11. Derive `exam_type` from marks.
12. Parse month/year from filename first.
13. If filename is bad, search the PDF for printed month/year.
14. Derive branch, subject, and pattern from the relative path and `mapping/folder_names.yml`.
15. Build the proposed normalized filename.
16. Check for unsafe filename fields.
17. Check for duplicate target filename.
18. Write the result to the review changelog.
19. Do not apply yet.

---

## Month and Year Normalization

Parse month/year from the filename first.

Examples:

| Filename           | Normalized output part |
| ------------------ | ---------------------- |
| `Feb-2023.pdf`     | `feb_2023`             |
| `May_Jun_2024.pdf` | `may_jun_2024`         |
| `August_2025.pdf`  | `aug_2025`             |
| `Nov_Dec_2022.pdf` | `nov_dec_2022`         |
| `Oct_2023.pdf`     | `oct_2023`             |

Normalize month names to lowercase.

Allowed month values:

```text
jan
feb
mar
apr
may
jun
jul
aug
sep
oct
nov
dec
may_jun
nov_dec
```

If filename contains a full month name, normalize it.

Examples:

```text
January -> jan
February -> feb
March -> mar
April -> apr
August -> aug
September -> sep
October -> oct
November -> nov
December -> dec
May_June -> may_jun
November_December -> nov_dec
```

---

## Unknown Date Rule

If the month or year cannot be found, use `unknown` placeholders in the proposed filename.

Do not use:

```text
unknown_date
```

Use this structure instead:

```text
{exam_type}_unknown_unknown_{branch_code}_{subject_code}_{pattern_code}.pdf
```

Examples:

```text
insem_unknown_unknown_civil_wse_2019p.pdf
endsem_unknown_unknown_comp_wt_2019p.pdf
other_unknown_unknown_aids_bda_eV_2019p.pdf
```

Partial unknown examples:

```text
insem_unknown_2024_civil_wse_2019p.pdf
endsem_may_unknown_comp_wt_2019p.pdf
```

However, unknown-date files must not be applied by default.

If month/year is missing, mark the file as:

```text
needs_user_date
```

Only apply unknown-date filenames if the user explicitly says to apply unknown-date placeholders.

---

## Bad Filename Scenario

Some PDFs may have meaningless or random names.

Examples:

```text
4959-1099 NW7JKUSG_2.pdf
download.pdf
paper.pdf
random_1.pdf
```

For these files:

1. Do not treat random numbers as month/year.
2. Do not use `4959`, `1099`, or `2` as dates.
3. Use the folder path for branch, subject, and pattern.
4. Use page 1 to find maximum marks.
5. Try to find month/year inside the PDF.
6. If month/year is not visible, propose an unknown-date filename.
7. Mark status as `needs_user_date`.

Example:

Original:

```text
needs_review/civil/se/2019_pattern/water_supply_engineering/4959-1099 NW7JKUSG_2.pdf
```

Detected:

```text
marks = 30
exam_type = insem
month = unknown
year = unknown
branch_code = civil
subject_code = wse
pattern_code = 2019p
```

Proposed filename:

```text
insem_unknown_unknown_civil_wse_2019p.pdf
```

Status:

```text
needs_user_date
```

Reason:

```text
filename_has_no_month_year_and_pdf_date_not_visible
```

---

## Missing Marks Scenario

If maximum marks cannot be confidently found:

1. Do not guess exam type.
2. Do not infer exam type from words like `Insem` or `Endsem` unless the user explicitly allows this fallback.
3. Mark status as:

```text
missing_marks
```

4. Keep the file unresolved.

Optional proposed filename may use:

```text
unknown_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf
```

But do not apply it unless the user explicitly approves unknown exam types.

---

## Corrupt Or Unreadable PDF Scenario

If a PDF cannot be opened, decoded, rendered, or OCR’d, mark it as corrupt.

Do not repeatedly retry forever.

Add the file ID to:

```text
mapping/file-exceptions.yml
```

The existing format is:

```yaml
# Add file IDs of PDFs that should be skipped during sync (e.g. corrupt files).
# Format: "file_id": "filename or reason for skipping"

exceptions:
  # Example:
  # "1A2b3C4d5E6f7G8h9I0j": "corrupted_file.pdf (fails OCR)"
  "1VLpg8TEyJu9dnixjJYa0zTyaTjv_Bego": "May_Jun_2025.pdf (needs_review/honors-course/te/embedded_systems_and_internet_of_things_hc)"
```

Important rules:

* The YAML key must be the file ID.
* Do not use the file path as the key.
* Do not invent a file ID.
* Find the file ID from existing project metadata, sync metadata, database, changelog, or original source records if available.
* If the file ID cannot be found, do not add a fake entry.
* Instead, mark the file as `corrupt_pdf_missing_file_id` in the manual changelog and ask the user to provide or confirm the file ID.

When adding a corrupt file exception, use this format:

```yaml
exceptions:
  "file_id_here": "filename.pdf (needs_review/path/to/folder; corrupt_pdf)"
```

Example:

```yaml
exceptions:
  "1AbCdEfGhIjKlMnOpQrStUvWxYz": "random.pdf (needs_review/computer-engineering/te/2019_pattern/web_technology; corrupt_pdf)"
```

Preserve all existing entries in `mapping/file-exceptions.yml`.

Do not delete or rewrite existing exceptions.

---

## Duplicate Target Scenario

If the proposed target filename already exists in the same `needs_review/` folder, do not overwrite it.

Mark status:

```text
duplicate
```

Reason:

```text
target_already_exists
```

Do not delete either file.

Do not merge files.

Ask the user to decide.

---

## Unsafe Filename Rules

A proposed filename is unsafe if it contains:

* spaces
* uppercase letters
* unsupported special characters
* path traversal such as `../`
* empty fields
* unknown branch code
* unknown subject code
* unknown pattern code
* invalid month
* invalid year
* ambiguous exam type

Allowed filename characters:

```text
a-z
0-9
_
-
.
```

The filename must end with:

```text
.pdf
```

---

## Review Output Files

Create or update these manual recovery files:

```text
changelog/needs_review_rename.md
changelog/needs_review_rename.json
```

Also update `changelog/rename.md` as a readable summary if safe.

When touching `changelog/rename.md`:

* Do not delete existing content.
* Do not delete marker comments.
* Preserve these markers exactly:

```html
<!-- RENAME_FILES_BEGIN -->
<!-- RENAME_FILES_END -->
```

Prefer adding a separate section after the existing rename block:

```html
<!-- NEEDS_REVIEW_RENAME_BEGIN -->
...
<!-- NEEDS_REVIEW_RENAME_END -->
```

Do not edit `changelog/rename.json` by hand.

---

## Manual Markdown Changelog Format

For each reviewed file, add an entry like this to:

```text
changelog/needs_review_rename.md
```

Template:

````markdown
## File

Original path:

```text
needs_review/path/to/original.pdf
````

Detected metadata:

| Field        | Value | Source             |
| ------------ | ----- | ------------------ |
| marks        | 30    | visual_header      |
| exam_type    | insem | derived_from_marks |
| month        | may   | filename           |
| year         | 2024  | filename           |
| branch_code  | civil | path_mapping       |
| subject_code | wse   | path_mapping       |
| pattern_code | 2019p | path_mapping       |

Proposed filename:

```text
insem_may_2024_civil_wse_2019p.pdf
```

Status:

```text
ready
```

Reason:

```text
max_marks_found_in_header
```

````

Allowed statuses:

```text
ready
needs_user_date
missing_marks
missing_month_year
missing_mapping
duplicate
unsafe_filename
corrupt_pdf
corrupt_pdf_missing_file_id
needs_user_input
applied
skipped
````

---

## Machine-Readable Review JSON

Create or update:

```text
changelog/needs_review_rename.json
```

Suggested structure:

```json
[
  {
    "status": "ready",
    "original_path": "needs_review/path/to/original.pdf",
    "proposed_path": "needs_review/path/to/insem_may_2024_civil_wse_2019p.pdf",
    "original_filename": "May_Jun_2024.pdf",
    "proposed_filename": "insem_may_2024_civil_wse_2019p.pdf",
    "marks": 30,
    "exam_type": "insem",
    "month": "may",
    "year": "2024",
    "branch_code": "civil",
    "subject_code": "wse",
    "pattern_code": "2019p",
    "metadata_sources": {
      "marks": "visual_header",
      "month": "filename",
      "year": "filename",
      "branch_code": "path_mapping",
      "subject_code": "path_mapping",
      "pattern_code": "path_mapping"
    },
    "reason": "max_marks_found_in_header"
  }
]
```

For unknown-date files:

```json
{
  "status": "needs_user_date",
  "original_path": "needs_review/path/to/4959-1099 NW7JKUSG_2.pdf",
  "proposed_path": "needs_review/path/to/insem_unknown_unknown_civil_wse_2019p.pdf",
  "original_filename": "4959-1099 NW7JKUSG_2.pdf",
  "proposed_filename": "insem_unknown_unknown_civil_wse_2019p.pdf",
  "marks": 30,
  "exam_type": "insem",
  "month": "unknown",
  "year": "unknown",
  "branch_code": "civil",
  "subject_code": "wse",
  "pattern_code": "2019p",
  "metadata_sources": {
    "marks": "visual_header",
    "month": "not_found",
    "year": "not_found",
    "branch_code": "path_mapping",
    "subject_code": "path_mapping",
    "pattern_code": "path_mapping"
  },
  "reason": "filename_has_no_month_year_and_pdf_date_not_visible"
}
```

---

## Apply Rules

Do not apply during review.

Apply only after the user explicitly says:

```text
apply
```

When applying:

1. Read only:

```text
changelog/needs_review_rename.json
```

2. Apply only entries with:

```text
status = ready
```

3. Do not apply entries with:

```text
needs_user_date
missing_marks
missing_month_year
missing_mapping
duplicate
unsafe_filename
corrupt_pdf
corrupt_pdf_missing_file_id
needs_user_input
```

4. Rename files only inside `needs_review/`.

5. Keep the same relative folder.

6. Do not move files to `incoming/` or `papers/` unless the user explicitly asks for that as a separate step.

7. Do not overwrite existing files.

8. If a target already exists, skip and mark it as `duplicate`.

9. Update the manual changelog after every file so the run is resumable.

10. Print a final summary.

---

## Unknown-Date Apply Rule

Unknown-date files are not `ready`.

They must stay as:

```text
needs_user_date
```

Only apply them if the user explicitly says something like:

```text
apply unknown-date placeholders
```

Then rename using:

```text
{exam_type}_unknown_unknown_{branch_code}_{subject_code}_{pattern_code}.pdf
```

Example:

```text
insem_unknown_unknown_civil_wse_2019p.pdf
```

---

## Final Review Summary

After reviewing, report:

```text
Reviewed PDFs: X
Ready to rename: Y
Need user date: Z
Missing marks: A
Corrupt/unreadable: B
Corrupt missing file ID: C
Duplicates: D
Missing mappings: E
Unsafe filenames: F
```

Also list the most important unresolved files and the reason each one is unresolved.

Do not say everything is complete if unresolved files remain.

---

## Final Apply Summary

After applying, report:

```text
Applied renames: X
Skipped: Y
Duplicates: Z
Still unresolved: A
```

Then tell the user what remains unresolved.

Do not run:

```bash
python3 tools/verify.py
python3 tools/move.py
```

unless the user explicitly asks.

---

## Final Reminder

This agent is only for manual recovery of files already inside:

```text
needs_review/
```

Never inspect PDFs outside that folder.

Never apply changes without explicit approval.

Never overwrite files.

Never invent missing metadata.

Never invent file IDs for `mapping/file-exceptions.yml`.
