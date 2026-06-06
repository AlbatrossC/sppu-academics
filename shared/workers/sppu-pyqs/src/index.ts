import type { Env } from "./env";

// ---------------------------------------------------------------------------
// MIME types
// ---------------------------------------------------------------------------

const MIME_TYPES: Record<string, string> = {
  ".pdf": "application/pdf",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".gif": "image/gif",
  ".css": "text/css",
  ".js": "application/javascript",
  ".html": "text/html",
  ".txt": "text/plain",
  ".xml": "application/xml",
};

function getMimeType(path: string): string {
  const dotIndex = path.lastIndexOf(".");
  if (dotIndex === -1) return "application/octet-stream";
  const ext = path.substring(dotIndex).toLowerCase();
  return MIME_TYPES[ext] || "application/octet-stream";
}

// ---------------------------------------------------------------------------
// Cache constants  (files are immutable — cache as aggressively as possible)
// ---------------------------------------------------------------------------

const CACHE_MAX_AGE = 31536000; // 1 year
const CF_EDGE_TTL = 2592000;    // 30 days

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a normalized cache key: origin + pathname only, always GET.
 * Strips query strings so `?v=1` or `?bypassCache=1` don't fragment the cache.
 */
function buildCacheKey(requestUrl: string): Request {
  const url = new URL(requestUrl);
  url.search = "";
  return new Request(url.toString(), { method: "GET" });
}

/**
 * Check whether the request explicitly asks to bypass cache.
 */
function shouldBypassCache(request: Request, url: URL): boolean {
  const cc = request.headers.get("Cache-Control") || "";
  const pragma = request.headers.get("Pragma") || "";
  if (cc.includes("no-cache") || cc.includes("no-store")) return true;
  if (pragma.includes("no-cache")) return true;
  if (url.searchParams.has("bypassCache")) return true;
  return false;
}

/**
 * Parse an RFC 7233 `Range: bytes=start-end` header.
 * Returns `{ offset, length }` for R2, or null if the header is absent.
 * Throws on malformed ranges so we can return 416.
 */
function parseRangeHeader(
  header: string | null,
  totalSize: number,
): { offset: number; length: number; start: number; end: number } | null {
  if (!header) return null;

  const match = header.match(/^bytes=(\d*)-(\d*)$/);
  if (!match) throw new Error("Malformed range");

  let start: number;
  let end: number;

  if (match[1] === "" && match[2] !== "") {
    // suffix range: bytes=-500  →  last 500 bytes
    const suffix = parseInt(match[2], 10);
    start = Math.max(0, totalSize - suffix);
    end = totalSize - 1;
  } else if (match[1] !== "" && match[2] === "") {
    // open-ended: bytes=500-
    start = parseInt(match[1], 10);
    end = totalSize - 1;
  } else {
    start = parseInt(match[1], 10);
    end = parseInt(match[2], 10);
  }

  if (start > end || start < 0 || end >= totalSize) {
    throw new Error("Range not satisfiable");
  }

  return { offset: start, length: end - start + 1, start, end };
}

/**
 * Standard response headers shared across all file responses.
 */
function baseHeaders(origin: string, contentType: string, etag?: string): Headers {
  const h = new Headers({
    "Content-Type": contentType,
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Range, If-None-Match",
    "Access-Control-Expose-Headers":
      "Content-Length, Content-Range, Accept-Ranges, ETag, X-Worker-Cache, X-Worker-Cache-Bypass",
    "Cache-Control": `public, max-age=${CACHE_MAX_AGE}, immutable`,
    "CDN-Cache-Control": `public, max-age=${CF_EDGE_TTL}`,
    "Accept-Ranges": "bytes",
    "X-Content-Type-Options": "nosniff",
  });
  if (etag) h.set("ETag", etag);
  return h;
}

/** CORS preflight response. */
function handleOptions(env: Env): Response {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
      "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Range, If-None-Match",
      "Access-Control-Max-Age": "86400",
    },
  });
}

/** JSON error — never cached. */
function errorResponse(status: number, message: string, origin: string): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": origin,
      "Cache-Control": "no-store",
    },
  });
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const origin = env.ALLOWED_ORIGIN || "*";

    // --- Preflight --------------------------------------------------------
    if (request.method === "OPTIONS") {
      return handleOptions(env);
    }

    // --- Method gate ------------------------------------------------------
    if (request.method !== "GET" && request.method !== "HEAD") {
      return errorResponse(405, "Method not allowed", origin);
    }

    const url = new URL(request.url);
    const objectKey = decodeURIComponent(url.pathname.slice(1));

    // --- Root / health check ----------------------------------------------
    if (!objectKey) {
      return new Response(
        JSON.stringify({
          service: "sppu-pyqs",
          status: "ok",
          description: "SPPU PYQ file server backed by Cloudflare R2",
          usage:
            "GET /<canonicalPath>  —  e.g. /papers/computer-engineering/se/2019_pattern/dsa_comp/endsem_may_jun_2024.pdf",
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
            "Cache-Control": "public, max-age=3600",
          },
        },
      );
    }

    const isHead = request.method === "HEAD";
    const hasRange = request.headers.has("Range");
    const bypass = shouldBypassCache(request, url);

    // --- Normalized cache key ---------------------------------------------
    const cache = caches.default;
    const cacheKey = buildCacheKey(request.url);

    // ------------------------------------------------------------------
    // 1. HEAD requests
    //    • Try cached GET first (headers only).
    //    • Fall back to R2 HEAD (no body download).
    // ------------------------------------------------------------------
    if (isHead) {
      if (!bypass) {
        const cached = await cache.match(cacheKey);
        if (cached) {
          const headers = new Headers(cached.headers);
          headers.set("X-Worker-Cache", "HIT");
          return new Response(null, { status: cached.status, headers });
        }
      }

      // R2 HEAD — metadata only, no body transfer
      const headObj = await env.BUCKET.head(objectKey);
      if (!headObj) return errorResponse(404, `Object not found: ${objectKey}`, origin);

      const mimeType = getMimeType(objectKey);
      const headers = baseHeaders(origin, mimeType, headObj.httpEtag);
      headers.set("Content-Length", headObj.size.toString());
      headers.set("X-Worker-Cache", "MISS");
      if (bypass) headers.set("X-Worker-Cache-Bypass", "true");

      return new Response(null, { status: 200, headers });
    }

    // ------------------------------------------------------------------
    // 2. Conditional request — If-None-Match
    // ------------------------------------------------------------------
    const ifNoneMatch = request.headers.get("If-None-Match");

    // ------------------------------------------------------------------
    // 3. Try Cache API (skipped on bypass and range requests)
    // ------------------------------------------------------------------
    if (!bypass && !hasRange) {
      const cached = await cache.match(cacheKey);
      if (cached) {
        // Conditional: compare ETag
        if (ifNoneMatch) {
          const cachedEtag = cached.headers.get("ETag");
          if (cachedEtag && (ifNoneMatch === cachedEtag || ifNoneMatch === `W/${cachedEtag}`)) {
            const h304 = new Headers({
              ETag: cachedEtag,
              "Cache-Control": `public, max-age=${CACHE_MAX_AGE}, immutable`,
              "Access-Control-Allow-Origin": origin,
              "X-Worker-Cache": "HIT",
            });
            return new Response(null, { status: 304, headers: h304 });
          }
        }

        const headers = new Headers(cached.headers);
        headers.set("X-Worker-Cache", "HIT");
        return new Response(cached.body, { status: 200, headers });
      }
    }

    // ------------------------------------------------------------------
    // 4. Fetch full object metadata from R2 (needed for size + ETag)
    // ------------------------------------------------------------------
    // For range requests we still need the total size first.
    // We fetch the full object when no range, or use head + ranged get.

    if (hasRange) {
      // --- Range request path -------------------------------------------
      const headObj = await env.BUCKET.head(objectKey);
      if (!headObj) return errorResponse(404, `Object not found: ${objectKey}`, origin);

      const totalSize = headObj.size;
      const mimeType = getMimeType(objectKey);

      let range: ReturnType<typeof parseRangeHeader>;
      try {
        range = parseRangeHeader(request.headers.get("Range"), totalSize);
      } catch {
        return new Response("Range Not Satisfiable", {
          status: 416,
          headers: {
            "Content-Range": `bytes */${totalSize}`,
            "Access-Control-Allow-Origin": origin,
          },
        });
      }

      if (!range) {
        // Range header was present but empty — treat as full request
        // Fall through to full-object path below (shouldn't happen, but safe)
        return errorResponse(400, "Invalid Range header", origin);
      }

      const rangedObj = await env.BUCKET.get(objectKey, {
        range: { offset: range.offset, length: range.length },
      });
      if (!rangedObj) return errorResponse(404, `Object not found: ${objectKey}`, origin);

      const headers = baseHeaders(origin, mimeType, headObj.httpEtag);
      headers.set("Content-Length", range.length.toString());
      headers.set("Content-Range", `bytes ${range.start}-${range.end}/${totalSize}`);
      headers.set("X-Worker-Cache", "MISS");
      if (bypass) headers.set("X-Worker-Cache-Bypass", "true");

      // Do NOT cache 206 responses
      return new Response(rangedObj.body, { status: 206, headers });
    }

    // ------------------------------------------------------------------
    // 5. Full GET — fetch from R2
    // ------------------------------------------------------------------
    const object = await env.BUCKET.get(objectKey);
    if (!object) return errorResponse(404, `Object not found: ${objectKey}`, origin);

    const mimeType = getMimeType(objectKey);
    const headers = baseHeaders(origin, mimeType, object.httpEtag);
    headers.set("Content-Length", object.size.toString());
    headers.set("X-Worker-Cache", "MISS");
    if (bypass) headers.set("X-Worker-Cache-Bypass", "true");

    // Conditional: compare ETag even on cache miss (R2 source of truth)
    if (ifNoneMatch && object.httpEtag) {
      const etag = object.httpEtag;
      if (ifNoneMatch === etag || ifNoneMatch === `W/${etag}`) {
        const h304 = new Headers({
          ETag: etag,
          "Cache-Control": `public, max-age=${CACHE_MAX_AGE}, immutable`,
          "Access-Control-Allow-Origin": origin,
          "X-Worker-Cache": "MISS",
        });
        return new Response(null, { status: 304, headers: h304 });
      }
    }

    const response = new Response(object.body, { status: 200, headers });

    // Cache only full 200 GET responses, and never when bypassing
    if (!bypass) {
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
    }

    return response;
  },
};
