# SPPU PYQs R2 File Server

Cloudflare Worker that serves SPPU Previous Year Question Paper PDFs (and other static assets) from a Cloudflare R2 bucket. Files are immutable exam papers, so the worker uses aggressive multi-layer caching to minimise R2 reads and deliver files as fast as possible.

## Base URL

```
https://sppu-pyqs.albatrossc.workers.dev
```

## URL Structure

The worker maps the URL path directly to the R2 object key. The `canonicalPath` field from the manifest JSON files is used as the key.

```
GET https://sppu-pyqs.albatrossc.workers.dev/<canonicalPath>
```

### Examples

```
GET /papers/artificial-intelligence-and-data-science/be/2019_pattern/big_data_analytics_ele_V_aids/insem_mar_2024_aids_bdaa_eV_2019p.pdf
GET /papers/computer-engineering/se/2019_pattern/data_structures_and_algorithms_comp/endsem_may_jun_2024_comp_dsaa_2019p.pdf
```

### Path Breakdown

```
papers/<branch-slug>/<year-key>/<pattern>/<subject_key>/<exam>_<month>_<year>_<branch>_<shortcode>_<pattern>.pdf
```

| Segment         | Example                                      |
|-----------------|----------------------------------------------|
| `branch-slug`   | `artificial-intelligence-and-data-science`   |
| `year-key`      | `se`, `te`, `be`                             |
| `pattern`       | `2019_pattern`, `2015_pattern`               |
| `subject_key`   | `data_structures_and_algorithms_aids`        |
| `filename`      | `endsem_may_jun_2024_aids_dsaa_2019p.pdf`    |

## Architecture

```
Client  →  Cloudflare Edge PoP  →  Cache API (per-PoP)  →  R2 Bucket
                │                        │                      │
                │  cache HIT ◄───────────┘                      │
                │  cache MISS ──────────── fetch from R2 ◄──────┘
                │                          cache full 200 GET
                └───────────────────────────────────────────────
```

1. Request arrives at the nearest Cloudflare edge PoP.
2. Worker builds a **normalized cache key** (origin + pathname only, no query strings).
3. On **cache hit**: returns the cached response with `X-Worker-Cache: HIT`.
4. On **cache miss**: fetches the object from R2, serves it with `X-Worker-Cache: MISS`, and stores the full 200 GET response in the Cache API for future requests at this PoP.

> **Important**: The Cloudflare Cache API (`caches.default`) is **per data center / PoP**, not globally replicated. The first request from a new PoP will always be a cache miss and will hit R2. Once cached at a PoP, subsequent requests from the same PoP are served instantly without R2 reads.

## Caching Strategy

Since exam papers are **immutable** (never modified after upload), the worker uses aggressive caching:

| Layer                   | TTL           | Header / Mechanism                                                  |
|-------------------------|---------------|---------------------------------------------------------------------|
| **Browser cache**       | 1 year        | `Cache-Control: public, max-age=31536000, immutable`                |
| **Cloudflare edge**     | 30 days       | `CDN-Cache-Control: public, max-age=2592000`                        |
| **Worker Cache API**    | Per-PoP       | `caches.default.put()` — only full 200 GET responses are cached     |
| **ETag support**        | Conditional   | R2 `httpEtag` forwarded; supports `If-None-Match` → 304             |

### What is NOT cached

- `206 Partial Content` (range requests) — always fetched from R2
- `HEAD` responses — not stored, but existing cached GET headers are reused
- `404` and `405` error responses
- Requests with cache bypass (`Cache-Control: no-cache`, `Pragma: no-cache`, or `?bypassCache=1`)

### Cache bypass

The worker explicitly checks for bypass signals:

| Signal                        | Effect                                        |
|-------------------------------|-----------------------------------------------|
| `Cache-Control: no-cache`     | Skips `cache.match()` and `cache.put()`       |
| `Pragma: no-cache`            | Same                                          |
| `?bypassCache=1` query param  | Same                                          |

Bypassed responses include the header `X-Worker-Cache-Bypass: true`.

## Debug Headers

Every file response includes a cache debug header:

| Header                     | Value     | Meaning                                    |
|----------------------------|-----------|--------------------------------------------|
| `X-Worker-Cache`           | `HIT`    | Served from Worker Cache API (no R2 read)  |
| `X-Worker-Cache`           | `MISS`   | Fetched from R2                            |
| `X-Worker-Cache-Bypass`    | `true`   | Cache was explicitly bypassed              |

## Range Requests

The worker supports RFC 7233 `Range` requests for all files:

- Parses `Range: bytes=start-end`, `bytes=start-`, and `bytes=-suffix` formats.
- Returns `206 Partial Content` with `Content-Range` and correct `Content-Length`.
- Returns `416 Range Not Satisfiable` for invalid ranges.
- Range requests always read from R2 (never cached/served from Cache API).
- All responses include `Accept-Ranges: bytes`.

## Conditional Requests

The worker supports `If-None-Match` for conditional GET:

- `ETag` from R2 is included in all file responses.
- If client sends `If-None-Match` matching the `ETag`, the worker returns `304 Not Modified`.
- 304 responses include `ETag`, `Cache-Control`, CORS, and debug cache headers.
- This works both on cache hits (fast) and cache misses (checks R2 ETag).

## HEAD Requests

`HEAD` requests never download the file body:

1. First checks the Worker Cache API for a cached GET response — if found, returns its headers with `X-Worker-Cache: HIT`.
2. If not cached, calls `env.BUCKET.head()` to get metadata only (no body transfer).
3. Returns the same headers as a GET (including `Content-Length`, `ETag`, etc.) but no body.

## Folder Structure

```text
shared/workers/sppu-pyqs/
├── src/
│   ├── index.ts          # Worker entry point — routing, R2 fetch, caching, range support
│   └── env.ts            # Environment type definitions (R2Bucket binding)
├── wrangler.toml         # Wrangler config with R2 binding
├── package.json          # Scripts and dependencies
├── tsconfig.json         # TypeScript configuration
└── README.md             # This file
```

## Setup

### 1. Install dependencies

```bash
cd shared/workers/sppu-pyqs
npm install
```

### 2. Create the R2 bucket (first time only)

```bash
npm run r2:create
```

### 3. Upload files to R2

Upload PDFs to R2 using their `canonicalPath` as the object key:

```bash
# Single file
wrangler r2 object put sppu-pyqs/papers/computer-engineering/se/2019_pattern/dsa_comp/endsem_may_jun_2024.pdf --file=./path/to/local.pdf

# Bulk upload (use a script or rclone)
rclone sync ./papers r2:sppu-pyqs/papers
```

### 4. Run locally

```bash
npm run dev
```

For remote R2 access during development:

```bash
npm run dev:remote
```

## Commands Reference

| Command               | Description                                    |
|-----------------------|------------------------------------------------|
| `npm run dev`         | Start local dev server (local R2 emulation)    |
| `npm run dev:remote`  | Start local dev server with remote R2 access   |
| `npm run deploy`      | Deploy worker to Cloudflare                    |
| `npm run typecheck`   | Run TypeScript type checking                   |
| `npm run r2:create`   | Create the `sppu-pyqs` R2 bucket               |
| `npm run r2:list`     | List objects in the R2 bucket                  |

## Deployment

```bash
npm run deploy
```

The worker deploys to:

```
https://sppu-pyqs.albatrossc.workers.dev
```

## API Endpoints

### `GET /`

Health check / service info.

```json
{
  "service": "sppu-pyqs",
  "status": "ok",
  "description": "SPPU PYQ file server backed by Cloudflare R2",
  "usage": "GET /<canonicalPath>"
}
```

### `GET /<canonicalPath>`

Returns the file from R2 with appropriate `Content-Type`, caching headers, and CORS support.

**Success (200)**:
Returns file body with headers:
- `Content-Type`: based on file extension (e.g. `application/pdf`)
- `Cache-Control: public, max-age=31536000, immutable`
- `ETag`: from R2 for conditional requests
- `Accept-Ranges: bytes`
- `X-Worker-Cache: HIT` or `MISS`

**Partial Content (206)** — on valid `Range` request:
- `Content-Range: bytes start-end/total`
- `Content-Length`: size of the partial content
- `X-Worker-Cache: MISS` (range requests always hit R2)

**Not Modified (304)** — on valid `If-None-Match`:
- `ETag`, `Cache-Control`, CORS headers, `X-Worker-Cache`

**Not Found (404)**:
```json
{ "error": "Object not found: papers/..." }
```

**Range Not Satisfiable (416)** — on invalid `Range`:
- `Content-Range: bytes */totalSize`

### `HEAD /<canonicalPath>`

Same as GET but returns only headers (no body). Uses cached GET headers when available, otherwise calls `BUCKET.head()`.

### `OPTIONS`

CORS preflight. Returns `204` with appropriate `Access-Control-*` headers.

## Environment Variables

| Variable         | Required | Default | Description                       |
|------------------|----------|---------|-----------------------------------|
| `ALLOWED_ORIGIN` | No       | `*`     | CORS `Access-Control-Allow-Origin`|

## R2 Binding

Defined in `wrangler.toml`:

```toml
[[r2_buckets]]
binding = "BUCKET"
bucket_name = "sppu-pyqs"
```

## Integration with Manifest

The manifest JSON files (e.g., `sppupyqs/manifest/2019_subjects.json`) reference this worker via the `r2BaseUrl` provider:

```json
{
  "providers": {
    "r2BaseUrl": "https://sppu-pyqs.albatrossc.workers.dev"
  },
  "subjects": {
    "some_subject": {
      "papers": [
        {
          "canonicalPath": "papers/branch/year/pattern/subject/exam_month_year.pdf"
        }
      ]
    }
  }
}
```

The full download URL is: `r2BaseUrl + "/" + canonicalPath`

## Testing Examples

### Cold GET (first request at this PoP)

```bash
curl -I "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf"
# Expect: X-Worker-Cache: MISS
```

### Warm GET (subsequent request at same PoP)

```bash
curl -I "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf"
# Expect: X-Worker-Cache: HIT
```

### Different browser / no local cache

A different browser or incognito window will still get `X-Worker-Cache: HIT` because Worker Cache API is server-side and per-PoP, independent of browser cache.

### HEAD request

```bash
curl -I -X HEAD "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf"
# Expect: Content-Length, ETag, no body
```

### Range request

```bash
curl -H "Range: bytes=0-1023" "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf" -o /dev/null -w "%{http_code}\n"
# Expect: 206
```

### Conditional request (If-None-Match)

```bash
# First, get the ETag:
ETAG=$(curl -sI "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf" | grep -i etag | tr -d '\r' | cut -d' ' -f2)

# Then send conditional request:
curl -I -H "If-None-Match: $ETAG" "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf"
# Expect: 304 Not Modified
```

### Bypass cache

```bash
# Via header:
curl -I -H "Cache-Control: no-cache" "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf"
# Expect: X-Worker-Cache: MISS, X-Worker-Cache-Bypass: true

# Via query param:
curl -I "https://sppu-pyqs.albatrossc.workers.dev/papers/it-engineering/be/2012_pattern/software_modeling_and_design_ie/insem_aug_2015_ie_smdi_2012p.pdf?bypassCache=1"
# Expect: X-Worker-Cache: MISS, X-Worker-Cache-Bypass: true
```

## Troubleshooting

- **404 for a file that exists in R2**
  Verify the R2 object key exactly matches the `canonicalPath` from the manifest. Keys are case-sensitive.

- **CORS errors in browser**
  Set `ALLOWED_ORIGIN` in `wrangler.toml` to your site's origin instead of `*`.

- **Stale cached response**
  The Cache API caches aggressively. Use `?bypassCache=1` or `curl -H "Cache-Control: no-cache"` to skip the Worker Cache API. Note: these only work because the worker explicitly implements bypass logic — Cloudflare does not automatically honor `Cache-Control: no-cache` for `caches.default`.

- **Cache appears inconsistent across locations**
  The Worker Cache API is **per Cloudflare PoP** (data center), not globally replicated. A file cached in Mumbai may not be cached in Frankfurt. The first request from any new PoP will be a cache miss and will read from R2.

- **R2 bucket not found**
  Run `npm run r2:create` and ensure the `bucket_name` in `wrangler.toml` matches.

- **Browser shows old version despite R2 update**
  Since `Cache-Control: immutable` is set, browsers will not revalidate. Users need to hard-refresh or clear cache. For server-side, use `?bypassCache=1`. If you need to invalidate globally, purge via the Cloudflare dashboard or update the canonical path.

- **Range request returns 416**
  The requested byte range is outside the file size. Verify the file exists and the range is valid with a `HEAD` request first.
