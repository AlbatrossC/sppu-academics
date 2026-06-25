# sppupyqs static site

Static Cloudflare Pages version of SPPU PYQs.

`sppupyqs-flask/` remains the reference Flask app. This folder contains the static build target only.

## Local build

```bash
cd sppupyqs
python -m pip install -r requirements.txt
python build.py
```

The build writes the full site to `dist/`.

Optional build-time values can be placed in `sppupyqs/.env`. Use `.env.example` as the pattern:

```text
PDF_SOURCE=r2
EXAM_TYPE=endsem
PATTERN_YEAR=2019
MAINTENANCE_MODE=false
```

Defaults are `PDF_SOURCE=r2`, `EXAM_TYPE=endsem`, `PATTERN_YEAR=2019`, and `MAINTENANCE_MODE=false`. `PDF_SOURCE` accepts `r2` or `cloudinary`; `EXAM_TYPE` accepts `insem` or `endsem`. When `MAINTENANCE_MODE=true`, the build skips the normal HTML routes and writes only the maintenance page.

To change the generated base URL for canonical links, sitemap URLs, Open Graph URLs, and `robots.txt`, set `SPPUPYQS_SITE_URL` before running the build:

```powershell
$env:SPPUPYQS_SITE_URL="https://sppupyqs.pages.dev"
python build.py
```

If `SPPUPYQS_SITE_URL` is not set, the build uses `https://sppupyqs.pages.dev`.

To override the contact/download backend target used in generated `_redirects`, set `SPPUPYQS_DB_WORKER_URL` before the build. If not set, the build uses `https://sppu-pyqs-db.albatrossc.workers.dev`.

## Local preview

```bash
cd sppupyqs/dist
npx serve .
```

## Cloudflare Pages

Use these settings:

- Build command: `python build.py`
- Build output directory: `dist`
- Root directory: `sppupyqs`

Manual deploy command:

```powershell
cd sppupyqs
$env:SPPUPYQS_SITE_URL="https://sppupyqs.pages.dev"
python build.py
npx wrangler pages deploy dist --project-name=sppupyqs --branch=pages
```

## Backend Worker

Contact form and download analytics are handled by:

```text
shared/workers/sppu-pyqs-db/
```

Set up D1 and secrets from that Worker README. No Pages Functions are required.

## Generated files

`python build.py` generates:

- static HTML routes
- hashed/minified CSS and JS in `dist/static/dist/`
- `dist/static/asset-manifest.json`
- current versioned search index such as `dist/static/search.1.json`
- `dist/url-phases.md`
- `dist/sitemap.xml`
- `dist/_headers`
- `dist/_redirects`
