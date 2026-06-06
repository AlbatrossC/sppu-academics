# Migrate Tracking

`tools/migrate_tracking.py` is a legacy migration helper for older local metadata.

It reads `mapping/local/` when that directory exists and creates or updates `tracking/manifest.db`. Fresh clones may not have `mapping/local/`; in that case, migrating zero rows can be a legitimate result.

Modern recovery should prefer:

```bash
python3 tools/sync.py --files
python3 tools/sync.py --files --apply
```

Those commands rebuild `tracking/manifest.db` from Drive reviews and reviewed downloads.

Use migration only when preserving an older local working copy:

```bash
python3 tools/migrate_tracking.py --print
```
