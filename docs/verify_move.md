# Verify and Move — `tools/verify.py` + `tools/move.py`

These two tools finish the SQLite workflow after `rename_files.py --apply`. They are always run in this order: verify first, then move.

---

## When to Run

After `rename_files.py --apply` completes:

```bash
python3 tools/verify.py
python3 tools/move.py
```

Or scoped to one subtree:

```bash
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science"
python3 tools/verify.py
python3 tools/move.py --path "incoming/artificial-intelligence-and-data-science"
```

---

## `tools/verify.py`

`verify.py` is **always global** — it checks all `FILE_RENAMED` rows in SQLite regardless of scope.

### What it checks

- Normalized filename format matches `{exam_type}_{month}_{year}_{branch_code}_{subject_code}_{pattern_code}.pdf`
- Folder structure for the correct family (`standard`, `first_year`, `mba`, `honors`)
- SQLite consistency — `current_path` points to an existing file
- No duplicate `expected_path` entries
- File existence at `current_path`

### Outcomes

| Check result | Stage |
|---|---|
| All checks pass | `VERIFIED` |
| Filename mismatch or path issue | `NEEDS_REVIEW` |
| File missing from disk | `MISSING` |

If a file was physically renamed but the DB row is still `DOWNLOADED` (e.g. from a previous incomplete run), `verify.py` can recover it when the filename already matches the final expected format.

### Commands

```bash
# Standard (promotes or flags all FILE_RENAMED rows)
python3 tools/verify.py

# Preview only — no DB writes
python3 tools/verify.py --dry-run
```

---

## `tools/move.py`

`move.py` moves only rows in `VERIFIED` stage. It reads `expected_path` from SQLite and moves each file from `incoming/` to `papers/`.

### Outcomes

| Condition | Action |
|---|---|
| `current_stage = VERIFIED` | Move to `papers/<expected_path>` |
| Target already exists in `papers/` | Return row to `NEEDS_REVIEW` with `duplicate` reason |
| File missing at `current_path` | Record as `MISSING` |

**Files in `papers/` are never overwritten.**

### Commands

```bash
# Move all VERIFIED rows
python3 tools/move.py

# Preview only — no filesystem writes
python3 tools/move.py --dry-run

# Scoped move (by incoming branch path)
python3 tools/move.py --path "incoming/artificial-intelligence-and-data-science"
python3 tools/move.py --path "incoming/first-year"
python3 tools/move.py --path "incoming/m-b-a"
python3 tools/move.py --path "incoming/honors-course"
```

The `--path` flag scopes which files are moved by matching `current_path` against the given prefix.

---

## Full Example Flows

### Standard branch (scoped)

```bash
# 1. Review + apply rename for AIDS/BE
python3 tools/rename_files.py --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern" --ocr-workers 1
# 2. Read changelog/rename.md, then:
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
# 3. Verify (global)
python3 tools/verify.py
# 4. Move only AIDS files
python3 tools/move.py --path "incoming/artificial-intelligence-and-data-science"
```

### First Year (scoped)

```bash
python3 tools/rename_files.py --path "incoming/first-year" --ocr-workers 1
python3 tools/rename_files.py --apply --path "incoming/first-year"
python3 tools/verify.py
python3 tools/move.py --path "incoming/first-year"
```

### MBA (scoped)

```bash
python3 tools/rename_files.py --path "incoming/m-b-a" --ocr-workers 1
python3 tools/rename_files.py --apply --path "incoming/m-b-a"
python3 tools/verify.py
python3 tools/move.py --path "incoming/m-b-a"
```

### Honors Course (scoped)

```bash
python3 tools/rename_files.py --path "incoming/honors-course" --ocr-workers 1
python3 tools/rename_files.py --apply --path "incoming/honors-course"
python3 tools/verify.py
python3 tools/move.py --path "incoming/honors-course"
```

---

## Final Output

Moved files land at:

```
papers/<branch>/<year>/<pattern>/<subject>/<normalized_name>.pdf
```

Examples:

```
papers/artificial-intelligence-and-data-science/be/2019_pattern/machine_learning_aids/endsem_may_jun_2024_aids_ml_2019p.pdf
papers/first-year/2019_pattern/engineering_mathematics_I_fy/endsem_nov_dec_2022_fy_em1_2019p.pdf
papers/m-b-a/sem_II/2019_pattern/financial_management/endsem_may_jun_2024_mba_fm_2019p.pdf
papers/honors-course/te/artificial_intelligence_hc/endsem_may_2024_hc_ai_te.pdf
```

Check the final state:

```bash
python3 tools/status.py --print
```
