# Feedback channel — Cloudflare Worker → GitHub issue

> **⚠ Prototype.** This doc explains how to deploy a Cloudflare Worker that receives client feedback POSTs and creates GitHub issues from them. Skip this if `feedback_endpoint_url` is unset in `config.yaml` — the skill still delivers feedback via local save + mailto: without any cloud setup.

## What this gives you

- Each time a client says *"I have feedback"* in the skill, an issue lands in your repo (or wherever the Worker forwards to). No manual triage of inbound emails, no GitHub PAT on client laptops.
- The client's GitHub-token-handling surface area is **zero**. The Worker holds the token as a Cloudflare secret; clients never see it.
- Same Worker pattern can be extended later to the v2 auto-error-inbox (`docs/troubleshooting.md`).

## Architecture

```
Client laptop                  Cloudflare Worker             GitHub
─────────────                  ─────────────────             ──────
"I have feedback"     POST /   ┌──────────────┐    POST /repos/.../issues
   feedback.sh   ────────────► │ Worker       │ ─────────────────────────►
                  Bearer token │ (no client   │   Authorization:           Issue
                  if you set   │  credentials)│   Bearer {GITHUB_PAT}      created
                  one         │              │
                              └──────────────┘
```

No client data ever passes through GitHub directly. The Worker is the only thing that holds your GitHub token.

## Deploy in ~10 minutes

Prerequisites:
- A Cloudflare account (free tier is fine for this).
- A GitHub fine-grained Personal Access Token scoped **only** to this repo, with `Issues: Read and write` permission.
- `wrangler` CLI installed (`npm install -g wrangler`) and logged in (`wrangler login`).

### 1. Create the Worker

```bash
mkdir -p ~/passport-feedback-worker && cd ~/passport-feedback-worker
npm init -y
npm install --save-dev wrangler
```

Create `wrangler.toml`:

```toml
name = "passport-feedback"
main = "src/index.js"
compatibility_date = "2026-01-01"

# Environment variables — non-secret
[vars]
GITHUB_OWNER = "rafaeldavid"
GITHUB_REPO = "passporttowealth"
ALLOWED_ADVISOR_ID = "passporttowealth"
```

Create `src/index.js`:

```javascript
// Cloudflare Worker: receive feedback, create GitHub issue.
// Secrets (set via `wrangler secret put`):
//   GITHUB_TOKEN           — fine-grained PAT, Issues: read/write on the target repo
//   FEEDBACK_BEARER_TOKEN  — optional shared secret to gate the endpoint

const ISSUE_LABEL = "client-feedback";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return json(405, { error: "method_not_allowed" });
    }

    // Optional bearer-token gate (matches feedback_endpoint_token in config.yaml)
    if (env.FEEDBACK_BEARER_TOKEN) {
      const auth = request.headers.get("Authorization") || "";
      const presented = auth.startsWith("Bearer ") ? auth.slice(7) : "";
      if (presented !== env.FEEDBACK_BEARER_TOKEN) {
        return json(401, { error: "unauthorized" });
      }
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json(400, { error: "invalid_json" });
    }

    // Sanity-check the schema (spec §15.1.4)
    if (!body || body.v !== 1 || typeof body.message !== "string") {
      return json(400, { error: "invalid_schema" });
    }
    if (env.ALLOWED_ADVISOR_ID && body.advisor_id !== env.ALLOWED_ADVISOR_ID) {
      return json(403, { error: "advisor_mismatch" });
    }
    if (body.message.length > 10_000) {
      return json(413, { error: "message_too_long" });
    }

    // Build the GitHub issue body in Markdown
    const issueTitle = `[client-feedback] ${truncate(body.message.split("\n")[0], 80)}`;
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
          labels: [ISSUE_LABEL],
        }),
      }
    );

    if (!ghResp.ok) {
      const text = await ghResp.text();
      return json(502, { error: "github_create_failed", status: ghResp.status, detail: text.slice(0, 500) });
    }

    const issue = await ghResp.json();
    return json(201, { received: true, issue_url: issue.html_url, issue_number: issue.number });
  },
};

function renderIssueBody(b) {
  const lines = [
    `**Message from client (${b.client_id || "unknown-id"}):**`,
    "",
    "> " + b.message.replace(/\n/g, "\n> "),
    "",
    "---",
    "**Context:**",
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

function truncate(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function json(status, data) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
```

### 2. Set the secrets

```bash
# GitHub fine-grained PAT, scoped to this repo, Issues: read/write
wrangler secret put GITHUB_TOKEN
# (paste the token when prompted)

# Optional bearer-token gate. Strongly recommended — prevents random
# scripts on the internet from creating issues in your repo.
# Generate any high-entropy string; share it with the skill via config.yaml.
wrangler secret put FEEDBACK_BEARER_TOKEN
# (paste a generated token when prompted)
```

### 3. Deploy

```bash
wrangler deploy
```

Wrangler prints the deployed URL, e.g. `https://passport-feedback.your-subdomain.workers.dev`.

### 4. Wire it into the skill

Edit each client's `~/Documents/my-finances/config.yaml` (or update the skill's `config.example.yaml` so new installs pick it up automatically):

```yaml
feedback:
  endpoint_url: "https://passport-feedback.your-subdomain.workers.dev"
  endpoint_token: "the-FEEDBACK_BEARER_TOKEN-you-generated-above"
```

That's it. Next time a client says *"I have feedback"*, an issue lands in `github.com/passporttowealth/passporttowealth/issues` labelled `client-feedback`.

## Costs

- Cloudflare Workers free tier: 100,000 requests/day. A pilot with ~50 clients sending ~1 feedback/week each = ~7 requests/day. **You will not hit any limits.**
- GitHub API (issue creation): unlimited for authenticated users on a personal/org repo.

## Safety

- The `ALLOWED_ADVISOR_ID` env var prevents another deployment of the skill from creating issues in your repo, even if someone copied your endpoint URL.
- The `FEEDBACK_BEARER_TOKEN` gates random POSTs to the URL. Rotate it via `wrangler secret put` if it ever leaks (no client-side change needed if you push the new token via a refreshed `config.yaml`).
- Worker logs in Cloudflare hold one entry per request. They are visible only to your Cloudflare account. Do not extend the Worker to log message bodies — they may contain personal context the client wrote.

## Extending later

Same Worker can:
- Forward feedback to email (Cloudflare Email Workers) or Slack (incoming webhook) in addition to GitHub.
- Receive auto-transmitted error envelopes (v2 — backlog Epic 6.5.4) by adding a second route.
- De-duplicate (close existing open issue with the same first-line title, comment instead of opening new) by adding a search-then-create flow.

Keep these as additive routes, not replacements — every channel still gets every message until the v2 acceptance work proves we can cut the email path.

## If you never deploy this

Totally fine. With `feedback.endpoint_url: null` in `config.yaml` (the default), the skill still:
- Saves every feedback message locally on the client's laptop.
- Opens the client's email client with the message pre-filled to your `advisor.feedback_email`.
- Copies it to the clipboard and prints in Terminal as fallbacks.

You'll get feedback by email instead of by GitHub issue. The Worker is an upgrade, not a requirement.
