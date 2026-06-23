# Final `sppupyqs` Cloudflare Migration Plan

## Summary
Keep the existing Flask app untouched as reference:

```text
sppupyqs-flask/
```

Create the migrated static Cloudflare version in a new folder:

```text
sppupyqs/
```

Do not delete, rename, or overwrite `sppupyqs-flask`. It remains useful context while building and comparing behavior.

Target architecture:

```text
sppupyqs/
  Cloudflare Pages static site

shared/workers/sppu-pyqs-db/
  Cloudflare Worker + D1 for contact and download analytics

shared/workers/sppu-pyqs/
  existing PDF/R2 Worker, untouched
```

No Pages Functions. No automatic deployment. Build and README commands only.

## Folder Strategy
Create a new app folder from scratch/copying only what is needed:

```text
sppupyqs/
  build.py
  README.md
  manifest/
  pyqs-metadata/
  static/
  templates/
  src/
  dist/
```

Use `sppupyqs-flask` as the source of truth during migration:
- copy/adapt templates,
- copy/adapt manifest loading logic,
- copy static assets,
- copy SEO/rendering behavior,
- copy metadata hydration logic,
- then remove Flask runtime dependencies from the new `sppupyqs` implementation.

`src/` in the new folder should be build-time utilities only, not a Flask runtime app.

## Static Build Strategy
Make this the local workflow:

```bash
cd sppupyqs
python build.py
cd dist
npx serve .
```

`python build.py` should:
- hash/minify CSS and JS,
- render all HTML pages into `dist/`,
- copy static assets, fonts, images, PDF.js, manifest/search assets,
- generate `sitemap.xml`,
- generate `_headers`,
- generate `_redirects`,
- copy `robots.txt`, `ads.txt`, and verification txt files.

Do not pre-generate `.gz` or `.br`; Cloudflare edge compression is enough.

## Route Migration
| Current route | New result |
|---|---|
| `/` | Static page |
| `/2019`, `/2015`, `/2012` | Static pattern pages |
| `/<pattern>/<subject>` | Static viewer pages |
| `/honors/<subject>` | Static viewer pages |
| legacy `/<subject>` | `_redirects` 301 |
| `/contact` | Static page |
| `POST /contact` | `shared/workers/sppu-pyqs-db` |
| `POST /api/notify-download` | `shared/workers/sppu-pyqs-db` |
| `/api/question-papers/list` | Remove if possible; use `/static/search.1.json` |
| `/api/pdf-proxy` | Remove if direct Cloudflare PDF loading works |
| `/static/*`, `/images/*`, SEO files | Cloudflare Pages static assets |

## New Worker
Create:

```text
shared/workers/sppu-pyqs-db/
```

Do not use or modify:
```text
shared/workers/sppucodes-db
shared/workers/sppu-pyqs
```

Worker responsibilities:
- contact form submission,
- Discord notification via hidden `DISCORD_WEBHOOK_URL` secret,
- download analytics,
- D1 writes.

Use a new D1 database, for example:

```text
sppu-pyqs-db
```

## Download Analytics Schema
Use `client_id`, not `fingerprint_id`.

Browser behavior:

```js
localStorage.setItem("client_id", crypto.randomUUID())
```

Tables:
- `contact_messages`
- `download_clients`
- `paper_download_events`

Track:
- subject downloaded,
- exam type downloaded,
- file count,
- branch/pattern/semester,
- `client_id`,
- timestamp.

This answers:
- most downloaded subject,
- most downloaded exam type,
- most active browser/client,
- downloads by day/week/month,
- downloads by branch or pattern.

## PDF Strategy
- First test direct PDF loading from the existing R2/PDF URLs on Cloudflare Pages.
- If direct loading works, remove `/api/pdf-proxy`.
- If it fails, use the existing `shared/workers/sppu-pyqs` public endpoint or binding as the PDF path.
- Do not modify `shared/workers/sppu-pyqs`.

## README Requirements
Create README files with commands for:
- local static build,
- local static preview,
- Worker local development,
- D1 creation/migration,
- secret setup,
- manual deployment commands.

Deployment commands should be documented only, not run automatically.

## Implementation Priority
1. Create new `sppupyqs/` folder.
2. Copy/adapt only needed files from `sppupyqs-flask`.
3. Build the static renderer in `sppupyqs/build.py`.
4. Generate `dist/` with pages, assets, sitemap, headers, redirects.
5. Replace `/api/question-papers/list` with `/static/search.1.json`.
6. Replace FingerprintJS naming/logic with `client_id`.
7. Create `shared/workers/sppu-pyqs-db`.
8. Add README instructions.
9. Test locally with:

```bash
cd sppupyqs
python build.py
cd dist
npx serve .
```

## Acceptance Tests
- `sppupyqs-flask/` remains unchanged.
- `sppupyqs/` contains the new static site.
- `python build.py` creates full `dist/`.
- Local preview works with `npx serve .`.
- Search uses `/static/search.1.json`.
- Download tracking sends `client_id`.
- Contact/download Worker code exists but is not deployed automatically.
- No Pages Functions are introduced.
- Existing `shared/workers/sppu-pyqs` is untouched.
