# Verify And Move

`tools/verify.py` and `tools/move.py` finish the SQLite workflow after `rename_files.py --apply`.

`verify.py` is global. `move.py` is scope-aware through `--path`.

## Correct Order

```bash
python3 tools/rename_files.py --apply --path "incoming/artificial-intelligence-and-data-science"
python3 tools/verify.py
python3 tools/move.py --path "incoming/artificial-intelligence-and-data-science"
```

## Verify

`verify.py` checks:

- renamed filename format
- folder structure for `standard`, `first_year`, `mba`, and `honors`
- SQLite consistency
- duplicate `expected_path`
- file existence at `current_path`

Valid renamed files become:

```text
VERIFIED
```

If a file was physically renamed but the DB row is still `DOWNLOADED`, `verify.py` can recover it when the filename already matches the final format.

Dry run:

```bash
python3 tools/verify.py --dry-run
```

## Move

`move.py` moves only:

```text
current_stage = VERIFIED
```

Files move from `incoming/` or `needs_review/` directly to `papers/` using `expected_path`.

Dry run:

```bash
python3 tools/move.py --dry-run
```

Scoped move:

```bash
python3 tools/move.py --path "incoming/artificial-intelligence-and-data-science"
```

If the destination already exists, the row returns to `NEEDS_REVIEW` with a duplicate filename reason.
