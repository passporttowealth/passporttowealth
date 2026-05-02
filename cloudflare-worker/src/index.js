// passport-feedback — Cloudflare Worker
// Two endpoints, both POST, both bearer-gated:
//   /              feedback events from published dashboards (creates a
//                  GitHub issue under the configured repo).
//   /install       anonymous install_started telemetry from install.sh +
//                  install.ps1 (counts daily installs by platform in KV).
//   /install/stats GET — admin-gated read of the daily counters.
//
// Secrets (set via `wrangler secret put`):
//   GITHUB_TOKEN           — fine-grained PAT, Issues: read/write on the repo
//   FEEDBACK_BEARER_TOKEN  — shared anti-abuse gate (visible in dashboard HTML
//                            + install scripts by design; the real defense
//                            for sensitive ops is GITHUB_TOKEN being
//                            server-side only)
//
// Vars (in wrangler.toml):
//   GITHUB_OWNER, GITHUB_REPO, ALLOWED_ADVISOR_ID, ISSUE_LABEL,
//   ALLOWED_ORIGIN_SUFFIX
//
// KV bindings:
//   FCB_METRICS — install-event counters (daily rollup per platform).
//
// Privacy: feedback events see message bodies; install events see ZERO PII
// (no IP, no name, no machine ID — just platform + build_stamp + advisor_id).
// Cloudflare observability is off so neither stream sits in CF logs.

const MAX_MESSAGE_LEN = 10_000;

// 90-day retention on install counters keeps KV from growing unbounded.
const INSTALL_COUNTER_TTL_SECONDS = 90 * 24 * 60 * 60;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const origin = request.headers.get("Origin") || "";
    const corsHeaders = buildCorsHeaders(origin, env);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // Route: /install — anonymous telemetry POST
    if (path === "/install") {
      if (request.method !== "POST") {
        return jsonResponse(405, { error: "method_not_allowed" }, corsHeaders);
      }
      return handleInstallEvent(request, env, corsHeaders);
    }

    // Route: /install/stats — admin GET (requires GITHUB_TOKEN as bearer)
    if (path === "/install/stats") {
      if (request.method !== "GET") {
        return jsonResponse(405, { error: "method_not_allowed" }, corsHeaders);
      }
      return handleInstallStats(request, env, corsHeaders);
    }

    // Route: / (default) — feedback events
    if (request.method !== "POST") {
      return jsonResponse(405, { error: "method_not_allowed" }, corsHeaders);
    }

    // Bearer-token gate (feedback path)
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
  // Allow any *.here.now origin (the dashboards live there) + the
  // passporttowealth.app landing page (so the on-site feedback form can POST).
  // Reject everything else by NOT setting Access-Control-Allow-Origin →
  // browsers will block.
  const allowedSuffix = env.ALLOWED_ORIGIN_SUFFIX || ".here.now";
  const allowedHosts = ["passporttowealth.app", "www.passporttowealth.app"];
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
  const isAllowedHost = allowedHosts.includes(originHost);
  if (isHereNow || isLocal || isAllowedHost) {
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

// ── Install telemetry handlers ───────────────────────────────────────────────

// POST /install — anonymous install-start ping. Schema:
//   { v: 1, event: "install_started", platform: "mac"|"win",
//     build_stamp: "20260502214500", advisor_id: "passporttowealth" }
//
// PRIVACY: we store a daily counter per platform in KV. Nothing else.
// We deliberately do NOT log:
//   - client IP (cf-connecting-ip header is ignored)
//   - user-agent
//   - any PII fields
//   - the raw event body
async function handleInstallEvent(request, env, corsHeaders) {
  // Bearer-token gate (same anti-abuse token as feedback path; visible in
  // install.sh by design — it's a soft gate, not a secret).
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

  if (!body || body.v !== 1 || body.event !== "install_started") {
    return jsonResponse(400, { error: "invalid_schema" }, corsHeaders);
  }
  if (env.ALLOWED_ADVISOR_ID && body.advisor_id !== env.ALLOWED_ADVISOR_ID) {
    return jsonResponse(403, { error: "advisor_mismatch" }, corsHeaders);
  }

  // Sanitize platform to a fixed allowlist
  const platform = (body.platform === "mac" || body.platform === "win") ? body.platform : "unknown";
  const day = new Date().toISOString().slice(0, 10);  // "2026-05-02"
  const key = `installs:${platform}:${day}`;

  if (!env.FCB_METRICS) {
    return jsonResponse(500, { error: "kv_not_bound" }, corsHeaders);
  }

  const cur = parseInt((await env.FCB_METRICS.get(key)) || "0", 10);
  await env.FCB_METRICS.put(key, String(cur + 1), {
    expirationTtl: INSTALL_COUNTER_TTL_SECONDS,
  });

  return jsonResponse(200, { received: true, key }, corsHeaders);
}

// GET /install/stats?days=30 — admin-gated read of the daily counters.
// Auth: requires GITHUB_TOKEN as bearer (admin-only). Returns:
//   { days, totals: { mac: N, win: N }, by_day: { "2026-05-02": { mac: N, win: N }, ... } }
async function handleInstallStats(request, env, corsHeaders) {
  // Admin gate: must present the GITHUB_TOKEN to read aggregated stats.
  // (More restrictive than the install endpoint's anti-abuse bearer.)
  if (!env.GITHUB_TOKEN) {
    return jsonResponse(500, { error: "admin_token_not_configured" }, corsHeaders);
  }
  const auth = request.headers.get("Authorization") || "";
  const presented = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (presented !== env.GITHUB_TOKEN) {
    return jsonResponse(401, { error: "unauthorized" }, corsHeaders);
  }
  if (!env.FCB_METRICS) {
    return jsonResponse(500, { error: "kv_not_bound" }, corsHeaders);
  }

  const url = new URL(request.url);
  const days = Math.max(1, Math.min(90, parseInt(url.searchParams.get("days") || "30", 10)));

  const totals = { mac: 0, win: 0, unknown: 0 };
  const byDay = {};
  const now = new Date();

  for (let d = 0; d < days; d++) {
    const date = new Date(now);
    date.setUTCDate(date.getUTCDate() - d);
    const day = date.toISOString().slice(0, 10);
    byDay[day] = { mac: 0, win: 0, unknown: 0 };
    for (const platform of ["mac", "win", "unknown"]) {
      const v = parseInt((await env.FCB_METRICS.get(`installs:${platform}:${day}`)) || "0", 10);
      byDay[day][platform] = v;
      totals[platform] += v;
    }
  }

  return jsonResponse(200, { days, totals, by_day: byDay }, corsHeaders);
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
