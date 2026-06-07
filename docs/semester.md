# Semester Mapping Agent Workflow — `tools/semester_mapping.py`

Use this document when a user asks an AI agent to assign semester numbers to subjects in the `papers/` archive.

**The agent must research and stage proposals only.** Do not edit `mapping/semester_mapping.yml` or generated manifests directly. The human reviews `changelog/semester.md` first, then chooses whether to apply.

---

## Scope Rules

| Folder type | Behavior |
|---|---|
| Standard branch pattern folder | Map every subject in that pattern folder |
| Standard branch subject folder | Map that subject; include sibling subject folders as context |
| First Year pattern folder | Map every First Year subject in that pattern |
| MBA | **Skip** — semester is already part of the MBA hierarchy |
| Honors Course | **Skip** — semester mapping is not used for Honors |

If the user gives a subject folder, use `scope.focus_subject_key` and `scope.focus_subject_path` to identify the requested subject. The `subjects[]` list still contains sibling subjects in the same pattern folder for research context.

**Only map subjects present in the `subjects[]` preview payload.** Do not add subjects that are not listed.

---

## Step 1 — Generate Local Context

Run the `preview` command first to see what subjects are in scope:

```bash
# For a pattern folder
python3 tools/semester_mapping.py preview papers/artificial-intelligence-and-data-science/te/2019_pattern

# For a subject folder
python3 tools/semester_mapping.py preview papers/artificial-intelligence-and-data-science/te/2019_pattern/artificial_nueral_network_aids

# First Year
python3 tools/semester_mapping.py preview papers/first-year/2019_pattern

# Scoped to a year
python3 tools/semester_mapping.py preview papers/computer-engineering/se/2019_pattern
```

The preview payload contains:

```json
{
  "scope": {
    "branch_name": "Artificial Intelligence and Data Science",
    "year_name": "TE",
    "pattern_name": "2019 Pattern",
    "focus_subject_key": null,
    "focus_subject_path": null
  },
  "subjects": [
    {
      "subject_key": "artificial_nueral_network_aids",
      "subject_name": "Artificial Neural Network",
      "directory_name": "artificial_nueral_network_aids",
      "folder": "papers/artificial-intelligence-and-data-science/te/2019_pattern/artificial_nueral_network_aids"
    }
  ]
}
```

---

## Step 2 — Research Semester Assignments

For each subject in `subjects[]`:

1. **Search for the official SPPU syllabus document** using:
   - `SPPU {branch_name} {year_name} {pattern_name} syllabus PDF`
   - `SPPU {subject_name}`
   - `site:sppu.unipune.ac.in {subject_name}`
   - `site:sppu.unipune.ac.in {branch_name} {pattern_name}`

2. **Open and inspect at least one source** — if a PDF is found, read its contents directly.

3. **Extract the semester assignment** from the syllabus document.

4. **If no syllabus is found**, perform at least 3 independent searches:
   - `{subject_name} {pattern_name}`
   - `{subject_name} syllabus PDF`
   - `{branch_name} {year_name} syllabus PDF`

5. Only mark `unresolved` after **all** searches fail.

---

## Source Ranking

Use evidence in this order. Tier 1 always wins over lower tiers:

| Tier | Sources |
|---|---|
| **Tier 1 (Preferred)** | `sppu.unipune.ac.in`, official SPPU PDFs, official curriculum documents |
| **Tier 2** | Affiliated college syllabus mirrors, department curriculum pages |
| **Tier 3** | Educational repositories |
| **Tier 4 (Last Resort)** | Question paper websites, student forums |

> Question-paper sites are **never** primary evidence. They can confirm a semester number found in Tier 1–3 sources but cannot establish it independently.

---

## Source Validation

Before recording any source:

- Open the URL and verify it is accessible
- Verify the document matches the correct branch, year, and pattern
- Do not cite search-result pages — cite the actual document

If a URL is inaccessible or does not match, discard it and continue searching.

---

## Academic Year Normalization

| Folder code | Full name | Semesters |
|---|---|---|
| `fe` / `FE` | First Year (First Engineering) | Semesters 1–2 |
| `se` / `SE` | Second Year (Second Engineering) | Semesters 3–4 |
| `te` / `TE` | Third Year (Third Engineering) | Semesters 5–6 |
| `be` / `BE` | Final Year (Bachelor of Engineering) | Semesters 7–8 |

Do not assume a year code implies a specific semester without verifying the syllabus. If the syllabus labels a subject under a different year than the folder path implies, flag the discrepancy in the evidence field.

---

## No-Guessing Rule

> [!CAUTION]
> **Never infer a semester from:**
> - Common curriculum patterns
> - Neighboring subjects in the same pattern folder
> - Branch-wide conventions
> - Subject difficulty or level
> - Previous semester mappings for other subjects

If explicit syllabus evidence is unavailable, set `semester_no = "unresolved"`. No exceptions.

---

## Conflicting Sources

When sources disagree:

1. Prefer official SPPU sources (Tier 1)
2. Prefer newer syllabus versions
3. Prefer documents matching the exact pattern year
4. If conflict remains → `semester_no = "unresolved"` and document both positions in evidence

---

## Semester Values

| Value | When to use |
|---|---|
| A number like `5` | Evidence clearly supports a numbered semester |
| `"other"` | Subject is intentionally included but not tied to a numbered semester |
| `"unresolved"` | Evidence is missing, conflicting, or only guessed from convention |

---

## Evidence Format

Each evidence statement must include:

- Source title
- Source URL
- Quoted syllabus section when possible

```
Evidence:
"Artificial Neural Network (410243) appears under Semester VI."

Quote:
"Semester VI: Artificial Neural Network"

Source:
https://example.edu/sppu-te-aids-2019-syllabus.pdf
```

---

## Step 3 — Stage Results

Write a JSON file and stage it:

```bash
python3 tools/semester_mapping.py stage /tmp/semester-stage.json
```

The stage command writes `changelog/semester.md`.

### Single pattern payload

```json
{
  "path": "papers/artificial-intelligence-and-data-science/te/2019_pattern",
  "entries": [
    {
      "subject_key": "artificial_nueral_network_aids",
      "subject_name": "Artificial Neural Network",
      "semester_no": 6,
      "status": "mapped",
      "confidence": "high",
      "evidence": "Artificial Neural Network (410243) is listed under Semester VI in the SPPU TE AI&DS 2019 Pattern syllabus.",
      "sources": [
        {
          "title": "SPPU TE Artificial Intelligence and Data Science 2019 Pattern Syllabus",
          "url": "https://example.edu/sppu-te-aids-2019-syllabus.pdf"
        }
      ]
    }
  ]
}
```

### Single subject payload

```json
{
  "path": "papers/artificial-intelligence-and-data-science/te/2019_pattern/artificial_nueral_network_aids",
  "subject_key": "artificial_nueral_network_aids",
  "subject_name": "Artificial Neural Network",
  "semester_no": 6,
  "status": "mapped",
  "confidence": "high",
  "evidence": "Artificial Neural Network is listed under Semester VI in the SPPU Third Year AI&DS 2019 Pattern syllabus.",
  "sources": [
    {
      "title": "SPPU TE AI&DS 2019 Pattern Syllabus",
      "url": "https://example.edu/syllabus.pdf"
    }
  ]
}
```

### Unresolved subject

```json
{
  "subject_key": "some_subject_key",
  "subject_name": "Some Subject",
  "semester_no": "unresolved",
  "status": "unresolved",
  "confidence": "low",
  "evidence": "No accessible official syllabus found after three independent searches.",
  "sources": []
}
```

### Non-numbered subject (`other`)

```json
{
  "subject_key": "example_subject_key",
  "subject_name": "Example Subject",
  "semester_no": "other",
  "status": "mapped",
  "confidence": "high",
  "evidence": "Reviewed as intentionally included without a numbered semester.",
  "sources": []
}
```

### Multi-folder payload

```json
{
  "reviews": [
    {
      "path": "papers/artificial-intelligence-and-data-science/se/2019_pattern",
      "entries": []
    },
    {
      "path": "papers/artificial-intelligence-and-data-science/te/2019_pattern",
      "entries": []
    }
  ]
}
```

---

## Step 4 — Human Review Gate

After staging, tell the user to inspect:

```
changelog/semester.md
```

Do **not** apply automatically. Ask the user whether to proceed.

---

## Step 5 — Apply or Discard

If the user approves:

```bash
python3 tools/semester_mapping.py apply
```

Apply updates:
- `mapping/semester_mapping.yml`
- Generated `manifest/*.json` semester fields

If the user rejects or wants to restart:

```bash
python3 tools/semester_mapping.py discard
```

For already-generated manifests with missing semester data:

```bash
python3 tools/semester_mapping.py fix-manifest --dry-run
python3 tools/semester_mapping.py fix-manifest
```

---

## Accepted Data in `semester_mapping.yml`

The approved YAML stores only the semester value per subject — no review sources:

```yaml
artificial-intelligence-and-data-science:
  te:
    "2019_pattern":
      artificial_nueral_network_aids: 6
      cloud_computing_aids: 6
      computer_networks_aids: 5
      data_science_aids: 5
```

---

## Acceptance Checklist

Before staging, verify all of these:

- [ ] Changelog is grouped by folder and semester
- [ ] Every staged `subject_key` exists in the local preview payload
- [ ] Every mapped subject has a source URL or clear evidence note
- [ ] Uncertain subjects use `semester_no: "unresolved"`
- [ ] No review sources are written to the approved YAML or manifests
