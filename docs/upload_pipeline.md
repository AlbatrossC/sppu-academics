# Upload Pipeline

`tools/upload_pipeline.py` publishes normalized PDFs from `papers/` only. It does not scan `incoming/` or `needs_review/`.

## Commands

```bash
python3 tools/upload_pipeline.py preflight
python3 tools/upload_pipeline.py scan
python3 tools/upload_pipeline.py sync
python3 tools/upload_pipeline.py summary
python3 tools/upload_pipeline.py status
python3 tools/upload_pipeline.py manifest
python3 tools/upload_pipeline.py all
python3 tools/upload_pipeline.py bulk-delete --target cloud --dry-run
python3 tools/semester_mapping.py preview papers/artificial-intelligence-and-data-science/te/2019_pattern
python3 tools/semester_mapping.py review papers/artificial-intelligence-and-data-science/te/2019_pattern
python3 tools/semester_mapping.py stage /tmp/semester-stage.json
python3 tools/semester_mapping.py apply
python3 tools/semester_mapping.py fix-manifest --dry-run
```

`preflight` checks R2 and Cloudinary credentials. `scan` refreshes `tracking/uploads.db` from `papers/`. `sync` uploads pending or changed PDFs. `summary` prints progress and sample rows. `status` prints counts only. `manifest` writes frontend JSON under `manifest/` and reads approved semester data from `mapping/semester_mapping.yml`. `all` runs scan, sync, and manifest. `bulk-delete` deletes published/local assets under the managed `papers/` scope.

## Semester Mapping

Semester mapping is review-first, like folder and file sync. AI agents should follow [Semester Mapping Agent Workflow](semester.md).

Preview local context for AI-agent research:

```bash
python3 tools/semester_mapping.py preview papers/artificial-intelligence-and-data-science/te/2019_pattern
```

Create an unresolved draft for one or more normalized `papers/` pattern folders:

```bash
python3 tools/semester_mapping.py review papers/artificial-intelligence-and-data-science/te/2019_pattern
```

Review writes:

```text
changelog/semester.md
```

After an AI agent researches web/PDF sources, stage reviewed results:

```bash
python3 tools/semester_mapping.py stage /tmp/semester-stage.json
```

The changelog includes source URLs and evidence notes for manual checking. Approved compact mappings are applied only after manual review:

```bash
python3 tools/semester_mapping.py apply
```

Apply updates both:

- `mapping/semester_mapping.yml`
- generated `manifest/*.json` semester fields

The approved YAML stores only branch/year/pattern/subject semester values: a number, `other`, or `unresolved`. It does not store sources.

For already-generated manifests, preview and apply the temporary patch command:

```bash
python3 tools/semester_mapping.py fix-manifest --dry-run
python3 tools/semester_mapping.py fix-manifest
```

Manifest behavior:

- Standard branch year nodes keep short `yearName` values such as `SE`, `TE`, and `BE`, and also include `yearFullName` values such as `Second Year`, `Third Year`, and `Fourth Year`.
- Subject lookup entries with `yearName` also include `yearFullName`. MBA keeps `semesterName` and does not get `yearFullName`.
- Standard branches get `semesterIncluded` on each year node. It is true only when every subject in that year has a numeric semester or `other`.
- First Year gets `semesterIncluded` on the `firstYear` node. It is true only when every First Year subject in that pattern has a numeric semester or `other`.
- `unresolved`, missing, and invalid semester values make `semesterIncluded` false and do not write `semesterNo`.
- MBA and Honors do not get `semesterIncluded`.
- Subject lookup manifests may include numeric `semesterNo` or `semesterNo: "other"`; review sources are never written to manifests.

## Options

```bash
python3 tools/upload_pipeline.py sync --limit 100
python3 tools/upload_pipeline.py sync --workers 8
python3 tools/upload_pipeline.py sync --state FAILED
python3 tools/upload_pipeline.py bulk-delete --target both --dry-run
python3 tools/upload_pipeline.py bulk-delete --target cloud --yes
```

`--limit` caps an upload batch. `--workers` controls concurrent PDF uploads. `--state FAILED` retries failed rows while skipping already successful providers. `--target` for `bulk-delete` must be `cloud`, `local`, or `both`. `--dry-run` previews delete targets.

Always run:

```bash
python3 tools/upload_pipeline.py bulk-delete --target cloud --dry-run
```

before a real delete.

## Environment

Required for uploads:

```text
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_ENDPOINT_URL
CLOUDINARY_CLOUD_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
```

`R2_PUBLIC_BASE_URL` is used by consumers that need public links and defaults to `https://sppu-pyqs.albatrossc.workers.dev`. `R2_BUCKET_NAME` defaults to `sppu-pyqs` when omitted, but production runs should set it explicitly.
