# `passport-feedback` — Cloudflare Worker

Receives product-feedback POSTs from published Finance Clarity dashboards and opens a GitHub issue under `passporttowealth/passporttowealth`. **One Worker deployment serves all clients** — they each post to the same URL using the same bearer token (which is shipped in `skill/config.example.yaml`).

## Architecture

```
Client dashboards (any *.here.now)
    │   POST /  with Authorization: Bearer <FEEDBACK_BEARER_TOKEN>
    ▼
Cloudflare Worker (this code)
    │   Validates bearer + advisor_id + schema
    │   Holds GITHUB_TOKEN as a Worker secret (clients never see it)
    ▼
GitHub Issues API
    └─▶ New issue under passporttowealth/passporttowealth labelled `client-feedback`
```

## Deploying

Prereqs:
- `wrangler` installed (`npm install -g wrangler`) and authenticated (`wrangler login`).
- A GitHub fine-grained PAT scoped to **only** `passporttowealth/passporttowealth` with `Issues: Read and write`.

From this directory:

```bash
# 1. Set both secrets (interactive — paste when prompted)
wrangler secret put GITHUB_TOKEN
wrangler secret put FEEDBACK_BEARER_TOKEN

# 2. Deploy
wrangler deploy
```

Wrangler prints the deployed URL on success. Wire it into `skill/config.example.yaml` (`feedback.endpoint_url`) and the bearer (`feedback.endpoint_token`) so future workspaces pick them up automatically.

## Verifying

A scripted smoke test lives at the repo root:

```bash
FEEDBACK_ENDPOINT_URL=https://passport-feedback.<your-subdomain>.workers.dev \
FEEDBACK_ENDPOINT_TOKEN=<the-bearer-you-set> \
python3 tests/test_feedback_endpoint.py
```

It asserts: 201 + issue_url on a valid envelope; 401 on a missing/wrong bearer; 4xx on an invalid schema.

## Rotating secrets

```bash
wrangler secret put GITHUB_TOKEN              # new PAT
wrangler secret put FEEDBACK_BEARER_TOKEN     # new bearer
```

After rotating the bearer, update `skill/config.example.yaml` and re-publish workspaces (their dashboards embed the bearer in HTML — old dashboards will start getting 401s until they refresh).

## Privacy

- Cloudflare observability is **off** in `wrangler.toml`. Cloudflare doesn't retain the request body. We rely on GitHub Issues as the durable record of what came through.
- The Worker doesn't log message bodies anywhere. Each request is fire-and-forget.
- The Worker forwards `client_id` (a hash of the workspace path, no PII) into the issue so different clients are distinguishable without being identifiable.

## Costs

Free tier covers this entirely at expected pilot scale (≤100k requests/day).
