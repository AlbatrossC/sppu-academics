# Pipeline Orchestrator — `tools/pipeline.py`

`tools/pipeline.py` wraps the individual tools into a single command while preserving the review/apply separation. It is useful when you want to run the full workflow with minimal prompting.

> **`pipeline.py` orchestrates existing tools. It does not replace their changelog review/apply behavior.** For fine-grained control, use the individual tools directly.

---

## Commands

### Review only

Scan Drive for folder and file changes:

```bash
python3 tools/pipeline.py --review
```

Scoped to one branch:

```bash
python3 tools/pipeline.py --review --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
python3 tools/pipeline.py --review --scope "First Year/2019 Pattern"
python3 tools/pipeline.py --review --scope "M.B.A/SEM - II"
python3 tools/pipeline.py --review --scope "Honors Course/TE"
```

This runs `sync.py --folders` and `sync.py --files` for the given scope, then `status.py --print`.

### Apply reviewed changes (download phase)

After reviewing `changelog/folder.md` and `changelog/files.md`, apply:

```bash
# Google Drive API (default)
python3 tools/pipeline.py --apply-reviewed

# gdown fallback
python3 tools/pipeline.py --apply-reviewed --gdown --download-delay 5

# rclone bulk download
python3 tools/pipeline.py --apply-reviewed --rclone --workers 8
```

This runs:
1. `sync.py --folders --apply`
2. `sync.py --files --apply` (with chosen download method)
3. `rename_folders.py --create`
4. `rename_folders.py`
5. `rename_files.py`

> [!IMPORTANT]
> `--apply-reviewed` applies **all** pending folder/file changelog entries, regardless of what `--scope` was used during review. There is no apply scope.

### Apply reviewed renames (rename phase)

After reviewing `changelog/rename.md`, apply:

```bash
python3 tools/pipeline.py --apply-renames
```

Scoped to one incoming subtree:

```bash
python3 tools/pipeline.py --apply-renames --incoming-path "incoming/artificial-intelligence-and-data-science/be/2019_pattern"
python3 tools/pipeline.py --apply-renames --incoming-path "incoming/first-year"
python3 tools/pipeline.py --apply-renames --incoming-path "incoming/m-b-a"
python3 tools/pipeline.py --apply-renames --incoming-path "incoming/honors-course"
```

This runs:
1. `rename_files.py --apply` (optionally scoped)
2. `verify.py`
3. `move.py` (scoped if `--incoming-path` given)

### Full review + apply in one shot

```bash
python3 tools/pipeline.py --full --apply
```

Scoped:

```bash
python3 tools/pipeline.py --full --apply --scope "Artificial Intelligence and Data Science/BE/2019 Pattern"
```

`--full --apply` runs `--review`, then `--apply-reviewed`, then `--apply-renames` in sequence.

### Dry run

Preview all commands without executing any:

```bash
python3 tools/pipeline.py --full --apply --dry-run
```

---

## Scope Behavior

| Flag | Scope effect |
|---|---|
| `--scope` | Applies to `--review` commands only |
| `--apply-reviewed` | Always applies **all** pending changelog entries |
| `--incoming-path` | Applies to `rename_files.py --apply` and `move.py` only |

---

## When to Use `pipeline.py` vs Individual Tools

| Situation | Recommendation |
|---|---|
| Quick full-branch sync | `pipeline.py --full --apply --scope "..."` |
| Careful incremental update | Individual tools with manual changelog review |
| Debugging a specific stage | Individual tools directly |
| Testing without API calls | `pipeline.py --full --apply --dry-run` |
| Large download with rclone | `pipeline.py --apply-reviewed --rclone --workers 8` |
