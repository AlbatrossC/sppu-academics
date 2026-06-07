# Legacy Tracking Migration — `tools/migrate_tracking.py`

`tools/migrate_tracking.py` is a legacy migration helper for older local metadata. Use it only when preserving a working copy that predates the modern SQLite tracking system.

> [!WARNING]
> **Modern installs do not need this tool.** On fresh clones, prefer `tools/sync.py --files` and reviewed download apply to rebuild `tracking/manifest.db` from Drive.

---

## When to Use

Use migration only when you have an older local working copy with a `mapping/local/` directory and want to preserve its state without re-downloading everything from Drive.

`mapping/local/` may not exist on fresh installs. Migrating zero rows is a legitimate result when it is absent.

---

## Commands

```bash
# Preview migration without writing to SQLite
python3 tools/migrate_tracking.py --print

# Run the migration (reads mapping/local/, writes to tracking/manifest.db)
python3 tools/migrate_tracking.py
```

---

## Modern Alternative

For all new recovery and setup, prefer:

```bash
python3 tools/sync.py --files
python3 tools/sync.py --files --apply
```

These commands rebuild `tracking/manifest.db` from Drive reviews and reviewed downloads. They handle all four folder families (standard branches, First Year, MBA, Honors Course) and do not require legacy `mapping/local/` data.
