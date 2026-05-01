// passport-feedback — Cloudflare Worker
// Receives product-feedback POSTs from published dashboards and creates a
// GitHub issue under the configured repo. One deployment serves all clients.
//
// Secrets (set via `wrangler secret put`):
//   GITHUB_TOKEN           — fine-grained PAT, Issues: read/write on the repo
//   FEEDBACK_BEARER_TOKEN  — shared anti-abuse gate (visible in dashboard HTML
//                            by design; the real defense is the GitHub PAT
//                            being server-side only)
//
// Vars (in wrangler.toml):
//   GITHUB_OWNER, GITHUB_REPO, ALLOWED_ADVISOR_ID, ISSUE_LABEL,
//   ALLOWED_ORIGIN_SUFFIX
//
// Privacy: this Worker sees feedback message bodies. Cloudflare observability
// is off in wrangler.toml so message bodies don't sit in Cloudflare logs.
// The Worker NEVER stores anything itself — every request is fire-and-forget.

const MAX_MESSAGE_LEN = 10_000;

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const corsHeaders = buildCorsHeaders(origin, env);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (request.method !== "POST") {
      return jsonResponse(405, { error: "method_not_allowed" }, corsHeaders);
    }

    // Bearer-token gate
    if (env.FEEDBACK_BEARER_TOKEN) {
      const auth = request.headers.get("Authorization") || "";
      const presented = auth.startsWith("Bearer ") ? auth.slice(7) : "";
      if (presented !== env.FEEDBACK_BEARER_TOKEN) {
        return jsonResponse(401, { error: "unauthorized" }, corsHeaders);
      }
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return jsonResponse(400, { error: "invalid_json" }, corsHeaders);
    }

    // Schema validation (envelope spec §15.1.4)
    if (!body || body.v !== 1 || typeof body.message !== "string") {
      return jsonResponse(400, { error: "invalid_schema" }, corsHeaders);
    }
    if (env.ALLOWED_ADVISOR_ID && body.advisor_id !== env.ALLOWED_ADVISOR_ID) {
      return jsonResponse(403, { error: "advisor_mismatch" }, corsHeaders);
    }
    if (body.message.length > MAX_MESSAGE_LEN) {
      return jsonResponse(413, { error: "message_too_long" }, corsHeaders);
    }
    if (body.message.trim().length < 1) {
      return jsonResponse(400, { error: "message_empty" }, corsHeaders);
    }

    // Build the GitHub issue
    const firstLine = body.message.split("\n")[0].trim();
    const issueTitle = `[client-feedback] ${truncate(firstLine, 80)}`;
    const issueBody = renderIssueBody(body);

    const ghResp = await fetch(
      `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/issues`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
          "Accept": "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "passport-feedback-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title: issueTitle,
          body: issueBody,
          labels: [env.ISSUE_LABEL || "client-feedback"],
        }),
      }
    );

    if (!ghResp.ok) {
      const text = await ghResp.text();
      return jsonResponse(502, {
        error: "github_create_failed",
        status: ghResp.status,
        detail: text.slice(0, 500),
      }, corsHeaders);
    }

    const issue = await ghResp.json();
    return jsonResponse(201, {
      received: true,
      issue_url: issue.html_url,
      issue_number: issue.number,
    }, corsHeaders);
  },
};

// ── helpers ──────────────────────────────────────────────────────────────────

function buildCorsHeaders(origin, env) {
  // Allow any *.here.now origin (the dashboards live there) plus the GitHub
  // Pages landing if it ever wants to POST. Reject everything else by NOT
  // setting Access-Control-Allow-Origin → browsers will block.
  const allowedSuffix = env.ALLOWED_ORIGIN_SUFFIX || ".here.now";
  const headers = {
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  };
  let originHost;
  try { originHost = new URL(origin).host; } catch { originHost = ""; }
  const isHereNow = originHost.endsWith(allowedSuffix);
  const isLocal = originHost === "localhost" || originHost.startsWith("localhost:") || originHost.startsWith("127.0.0.1");
  if (isHereNow || isLocal) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return headers;
}

function jsonResponse(status, data, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function renderIssueBody(b) {
  const lines = [
    `**Message from client (${b.client_id || "unknown-id"}):**`,
    "",
    "> " + b.message.replace(/\n/g, "\n> "),
    "",
    "---",
    "**Context**",
    `- Advisor: \`${b.advisor_id || "?"}\``,
    `- Skill version: \`${b.skill_version || "?"}\``,
    `- Platform: \`${b.platform || "?"}\``,
    `- Timestamp: \`${b.ts || "?"}\``,
    `- Context level: \`${b.context_level || "a"}\``,
  ];
  if (b.context && Object.keys(b.context).length > 0) {
    lines.push("", "**Anonymous context (opted in):**", "```json", JSON.stringify(b.context, null, 2), "```");
  }
  lines.push("", "_Created by `passport-feedback` Cloudflare Worker._");
  return lines.join("\n");
}
