export interface Env {
  DB: D1Database;
  DISCORD_WEBHOOK_URL?: string;
  ALLOWED_ORIGIN?: string;
}

const DEFAULT_ALLOWED_ORIGIN = "*";

function corsHeaders(env: Env): HeadersInit {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || DEFAULT_ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Requested-With",
    "Access-Control-Max-Age": "86400",
  };
}

function json(env: Env, body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: corsHeaders(env),
  });
}

function getRequestContext(request: Request): {
  ipAddress: string;
  userAgent: string;
  sourceUrl: string;
} {
  return {
    ipAddress: request.headers.get("CF-Connecting-IP") || "",
    userAgent: request.headers.get("User-Agent") || "",
    sourceUrl: request.headers.get("Referer") || request.url,
  };
}

function cleanString(value: unknown, maxLength: number): string {
  return String(value || "").trim().slice(0, maxLength);
}

async function readPayload(request: Request): Promise<Record<string, unknown> | null> {
  const contentType = request.headers.get("Content-Type") || "";

  try {
    if (contentType.includes("application/json")) {
      const payload = await request.json();
      return payload && typeof payload === "object" ? payload as Record<string, unknown> : null;
    }

    const formData = await request.formData();
    const payload: Record<string, unknown> = {};
    formData.forEach((value, key) => {
      payload[key] = typeof value === "string" ? value : value.name;
    });
    return payload;
  } catch {
    return null;
  }
}

async function handleContact(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const payload = await readPayload(request);
  if (!payload) return json(env, { ok: false, message: "Invalid request body." }, 400);

  const name = cleanString(payload.name, 100);
  const email = cleanString(payload.email, 150);
  const message = cleanString(payload.message, 2000);
  if (!name || !email || !message) {
    return json(env, { ok: false, message: "Name, email, and message are required." }, 400);
  }

  const requestContext = getRequestContext(request);
  await env.DB.prepare(
    `INSERT INTO contact_messages (name, email, message, ip_address, user_agent, source_url)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6)`
  )
    .bind(name, email, message, requestContext.ipAddress, requestContext.userAgent, requestContext.sourceUrl)
    .run();

  ctx.waitUntil(sendDiscordNotification(env, "contact", {
    name,
    email,
    message,
    ...requestContext,
  }));

  return json(env, { ok: true, message: "Your message has been sent successfully!" });
}

async function handleDownload(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const payload = await readPayload(request);
  if (!payload) return json(env, { ok: false, message: "Invalid request body." }, 400);

  const clientId = cleanString(payload.client_id, 120);
  const subjectLink = cleanString(payload.subject_link, 300);
  const subjectName = cleanString(payload.subject_name, 250);
  const examType = cleanString(payload.exam_type, 40).toLowerCase();
  const fileCount = Math.max(0, Number.parseInt(String(payload.file_count || "0"), 10) || 0);
  const branch = cleanString(payload.branch, 160);
  const pattern = cleanString(payload.pattern, 40);
  const semester = cleanString(payload.semester, 80);

  if (!clientId || !subjectLink || !subjectName || !examType) {
    return json(env, { ok: false, message: "Missing required download fields." }, 400);
  }

  const requestContext = getRequestContext(request);
  ctx.waitUntil(recordDownload(env, {
    clientId,
    subjectLink,
    subjectName,
    examType,
    fileCount,
    branch,
    pattern,
    semester,
    ...requestContext,
  }));

  return json(env, { ok: true });
}

async function recordDownload(
  env: Env,
  event: {
    clientId: string;
    subjectLink: string;
    subjectName: string;
    examType: string;
    fileCount: number;
    branch: string;
    pattern: string;
    semester: string;
    ipAddress: string;
    userAgent: string;
  },
): Promise<void> {
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO download_clients (client_id, user_agent, download_count)
       VALUES (?1, ?2, 1)
       ON CONFLICT(client_id)
       DO UPDATE SET last_seen_at = datetime('now'),
                     user_agent = excluded.user_agent,
                     download_count = download_count + 1`
    ).bind(event.clientId, event.userAgent),
    env.DB.prepare(
      `INSERT INTO paper_download_events (
         client_id, subject_link, subject_name, exam_type, file_count,
         branch, pattern, semester, ip_address, user_agent
       )
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)`
    ).bind(
      event.clientId,
      event.subjectLink,
      event.subjectName,
      event.examType,
      event.fileCount,
      event.branch || null,
      event.pattern || null,
      event.semester || null,
      event.ipAddress || null,
      event.userAgent || null,
    ),
  ]);
}

async function sendDiscordNotification(
  env: Env,
  kind: "contact",
  payload: Record<string, string>,
): Promise<void> {
  if (!env.DISCORD_WEBHOOK_URL) return;

  const content = [
    "**New SPPU PYQs contact message**",
    `Name: ${payload.name}`,
    `Email: ${payload.email}`,
    `Message: ${payload.message}`,
    `Source: ${payload.sourceUrl}`,
  ].join("\n");

  const response = await fetch(env.DISCORD_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    console.error(JSON.stringify({
      event: "discord_notification_failed",
      status: response.status,
      kind,
    }));
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(env) });
    }

    if (request.method !== "POST") {
      return json(env, { ok: false, message: "Method not allowed." }, 405);
    }

    const pathname = new URL(request.url).pathname;
    try {
      if (pathname === "/contact" || pathname === "/api/contact") {
        return await handleContact(request, env, ctx);
      }
      if (pathname === "/api/notify-download" || pathname === "/notify-download") {
        return await handleDownload(request, env, ctx);
      }
      return json(env, { ok: false, message: "Not found." }, 404);
    } catch (error) {
      console.error(JSON.stringify({
        event: "request_failed",
        path: pathname,
        error: error instanceof Error ? error.message : String(error),
      }));
      return json(env, { ok: false, message: "An error occurred. Please try again." }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
