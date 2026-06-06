# Disaster Recovery

Fresh clone recovery assumes committed mapping files are present and `.env` has been recreated locally.

```bash
python3 -m pip install -r requirements.txt

python3 tools/map.py build
python3 tools/rename_folders.py --create

python3 tools/sync.py --files
python3 tools/sync.py --files --apply --rclone --workers 8

python3 tools/rename_folders.py --dry-run
python3 tools/rename_folders.py

python3 tools/rename_files.py --ocr-workers 1
python3 tools/rename_files.py --apply

python3 tools/verify.py
python3 tools/move.py
python3 tools/status.py --print

python3 tools/upload_pipeline.py preflight
python3 tools/upload_pipeline.py scan
python3 tools/upload_pipeline.py sync
python3 tools/upload_pipeline.py manifest
python3 tools/upload_pipeline.py summary
```

Run this first for a non-network mapping sanity check:

```bash
python3 tools/validate_mappings.py
```

## Limits

`.env` cannot be recovered from git. Use `.env.example` as the shape and fill real secrets locally.

`tracking/*.db` is regenerated. `incoming/`, `papers/`, `needs_review/`, `changelog/`, and `manifest/*.json` are runtime/generated data.

`mapping/*.json` and `mapping/folder_names.yml` are committed source files and should survive a clone. `mapping/local/` is legacy runtime metadata and may legitimately be absent.
