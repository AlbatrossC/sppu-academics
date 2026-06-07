# Upload Pipeline — `tools/upload_pipeline.py`

`tools/upload_pipeline.py` publishes normalized PDFs from `papers/` to Cloudflare R2 and Cloudinary, then generates frontend manifest JSON files.

> **It reads from `papers/` only.** It does not scan `incoming/` or `needs_review/`.

---

## Commands

```bash
# Check R2 and Cloudinary credentials
python3 tools/upload_pipeline.py preflight

# Refresh tracking/uploads.db from papers/
python3 tools/upload_pipeline.py scan

# Upload pending or changed PDFs
python3 tools/upload_pipeline.py sync

# Print progress and sample rows
python3 tools/upload_pipeline.py summary

# Print upload counts only
python3 tools/upload_pipeline.py status

# Write frontend JSON manifests
python3 tools/upload_pipeline.py manifest

# Run scan + sync + manifest in sequence
python3 tools/upload_pipeline.py all

# Preview destructive cleanup (always run --dry-run first)
python3 tools/upload_pipeline.py bulk-delete --target cloud --dry-run
python3 tools/upload_pipeline.py bulk-delete --target local --dry-run
python3 tools/upload_pipeline.py bulk-delete --target both --dry-run
```

---

## Options

```bash
# Cap upload batch size
python3 tools/upload_pipeline.py sync --limit 100

# Control concurrent uploads
python3 tools/upload_pipeline.py sync --workers 8

# Retry only failed rows (skip already-successful providers)
python3 tools/upload_pipeline.py sync --state FAILED

# Delete from cloud only, with confirmation
python3 tools/upload_pipeline.py bulk-delete --target cloud --yes
```

> [!WARNING]
> Always run `bulk-delete --dry-run` before a real delete. `--target cloud` deletes from R2 and Cloudinary. `--target local` removes local files from `papers/`.

---

## Environment Variables

Required for uploads:

```env
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret
R2_BUCKET_NAME=sppu-pyqs
R2_ENDPOINT_URL=https://your-account.r2.cloudflarestorage.com

CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

Optional:

```env
R2_PUBLIC_BASE_URL=https://sppu-pyqs.albatrossc.workers.dev
```

`R2_BUCKET_NAME` defaults to `sppu-pyqs` when omitted, but production runs should set it explicitly.

---

## Upload Tracking

`tracking/uploads.db` stores one row per PDF in `papers/`. Upload states:

| State | Meaning |
|---|---|
| `PENDING` | Not yet uploaded |
| `UPLOADED` | Successfully on R2 and Cloudinary |
| `MODIFIED` | Local file changed since last upload |
| `RENAMED` | File was renamed since last upload |
| `REMOVED` | File removed from `papers/` |
| `FAILED` | Upload attempt failed |
| `NEEDS_TRACKING_ID` | Missing provider ID in DB |

---

## Semester Mapping

Semester mapping is review-first and feeds into the manifest. See [semester.md](semester.md) for the full agent workflow.

Quick reference commands:

```bash
# Preview local context for AI research
python3 tools/semester_mapping.py preview papers/artificial-intelligence-and-data-science/te/2019_pattern

# Create an unresolved draft for a pattern folder
python3 tools/semester_mapping.py review papers/artificial-intelligence-and-data-science/te/2019_pattern

# Stage researched results (after AI agent fills semester_no values)
python3 tools/semester_mapping.py stage /tmp/semester-stage.json

# Apply after human review of changelog/semester.md
python3 tools/semester_mapping.py apply

# Discard pending semester changes
python3 tools/semester_mapping.py discard

# Patch already-generated manifests with new semester data
python3 tools/semester_mapping.py fix-manifest --dry-run
python3 tools/semester_mapping.py fix-manifest
```

---

## Manifest Behavior

`tools/upload_pipeline.py manifest` writes frontend JSON to `manifest/`. It reads from `mapping/semester_mapping.yml` for semester data.

**Standard branch year nodes include:**
- `yearName` — short code: `SE`, `TE`, `BE`
- `yearFullName` — full label: `Second Year`, `Third Year`, `Fourth Year`
- `semesterIncluded` — `true` only when every subject in that year has a numeric semester or `other`

**First Year node includes:**
- `semesterIncluded` — `true` only when every First Year subject in that pattern has a numeric semester or `other`

**MBA nodes:**
- Keep `semesterName` (not `yearFullName`)
- Do not get `semesterIncluded`

**Honors nodes:**
- Do not get `semesterIncluded`

**Subject lookup entries:**
- May include numeric `semesterNo` or `semesterNo: "other"`
- `unresolved`, missing, or invalid semester values make `semesterIncluded` false
- Review sources are never written to manifest JSON

---

## Typical Upload Workflow

```bash
# 1. Sanity check credentials
python3 tools/upload_pipeline.py preflight

# 2. Refresh upload tracking
python3 tools/upload_pipeline.py scan

# 3. Upload PDFs
python3 tools/upload_pipeline.py sync --workers 4

# 4. Check progress
python3 tools/upload_pipeline.py summary

# 5. Generate manifests
python3 tools/upload_pipeline.py manifest
```

Or in one command:

```bash
python3 tools/upload_pipeline.py all
```
