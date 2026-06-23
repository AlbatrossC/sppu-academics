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

To change the generated base URL for canonical links, sitemap URLs, Open Graph URLs, and `robots.txt`, set `SPPUPYQS_SITE_URL` before running the build:

```powershell
$env:SPPUPYQS_SITE_URL="https://pages.sppupyqs.pages.dev"
python build.py
```

If `SPPUPYQS_SITE_URL` is not set, the build uses `https://sppupyqs.vercel.app`.

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
$env:SPPUPYQS_SITE_URL="https://pages.sppupyqs.pages.dev"
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
- `dist/static/search.1.json`
- `dist/sitemap.xml`
- `dist/_headers`
- `dist/_redirects`
