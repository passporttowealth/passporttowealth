# CLAUDE.md — Agent orientation

> **You are picking up an active product with real testers.** Read this before making changes. The conventions below exist because each one closed a regression that hit production. Breaking them re-opens the regression.

This file is read automatically by Claude Code when working in this repo. If you are a different AI assistant, read it anyway — it's the fastest way to be useful here without breaking customer experience.

---

## What this project is (in one paragraph)

`passporttowealth/passporttowealth` is the Finance Clarity skill for [Passport to Wealth](https://passporttowealth.com/) — Arielle Tucker's expat-focused financial network of advisors and content. It's a Claude Code skill that turns a folder of bank statements into a private dashboard rendered on the user's laptop. Distribution is curl-pipe-bash on Mac (`curl -fsSL https://passporttowealth.app/install | bash`) and irm-pipe-iex on Windows. Pre-1.0 prototype. **5–10 testers actively using it during a 2-week pilot (started ~2026-05-03).** Every change you ship has a real chance of hitting a real tester within hours.

---

## The branching model (read this first)

Two branches:

- `**main`** — what testers' install commands resolve to. Must always work. Branch-protected with admin bypass: required status checks gate normal PRs, but the repo owner can push direct in an emergency. **Default: do not push direct to `main`.** Open a PR from `next` instead.
- `**next`** — development trunk. Push directly here. After changes have soaked (no tester complaints, CI green), fast-forward `main` to `next`.

Hotfix path: `hotfix/<short-name>` branch off `main`, PR back into `main`. Required checks still gate it.

**Workflow for any change:**

```bash
git checkout next
git pull
# … make changes, run tests …
git push origin next
# After soak (hours to a day, your judgment):
gh pr create --base main --head next --title "Promote next → main"
# Wait for CI. Merge.
```

---

## Required CI gates (don't merge if any of these fail)

Configured in `.github/workflows/`:


| Workflow                | What it gates                                                                                                                    | Why it exists                                                                                         |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `ci.yml`                | Python pipeline regression suite (39 tests, `tests/test_pipeline.py`)                                                            | Pipeline correctness on demo-kit fixture.                                                             |
| `lint.yml`              | shellcheck on `install.sh` + `install` shim + `publish-landing.sh` + `skill/scripts/*.sh`. PSScriptAnalyzer on `install.ps1`.    | Both installers are streamed and executed (`curl …                                                    |
| `security.yml`          | `pip-audit` (Python deps) + `npm audit` (Worker deps)                                                                            | Answers tester / advisor question: "are these installations safe?" Public, machine-verifiable result. |
| `lint-user-strings.yml` | OP-8 banned-words check (no third-party service names in user-facing copy)                                                       | Keeps "API key", "slug", "Homebrew" out of strings users see.                                         |
| `pages.yml`             | GitHub Pages backup mirror of the landing page; substitutes `{{BUILD_STAMP}}` and refuses to deploy if `{{` placeholders survive | Prevents the literal-`{{BUILD_STAMP}}`-on-live-site regression class.                                 |


If you add a new check to a workflow, also add it to the required-checks list via `gh api -X PUT /repos/passporttowealth/passporttowealth/branches/main/protection` (or the GitHub UI).

---

## Test scope is intentionally lean (`tests/test_pipeline.py`, ~40 tests)

The suite was cut from 69 → 39 on 2026-05-03 (B9.19) for the prototype phase. **The bar for adding a test:** would its failure tell us a real tester is about to have a bad experience? If yes (install breaks, dashboard shows wrong numbers, privacy claim drifts, recent regression class returns), add it. If no (it pins specific copy, CSS class names, default page sizes, file modes, or step-numbering), don't.

The full Tier 1/2/3 testing roadmap (container smoke-test of `install.sh`, live HTTP test against staged Worker, HTML lint + dead-link check, etc.) is in `dev/backlog.md` B9.19 / B9.20 for end-of-prototype review (late May 2026).

---

## Publishing surfaces — never break these without thinking

Five things visitors and testers depend on:

1. `**https://passporttowealth.app/`** — landing page, here-now slug `sandy-delta-dc3r`. Publish via `bash installer/publish-landing.sh` (NEVER the bare here-now skill — `{{BUILD_STAMP}}` would render literally and any new symlink would 404).
2. `**https://passporttowealth.app/install*`* — bash shim that exec-fetches `install.sh` from GitHub raw `main`. Updates on every push to `main` automatically.
3. `**https://passporttowealth.app/install.ps1**` — same for Windows.
4. `**https://passporttowealth.app/dashboard-demo/**` — public demo dashboard built from `demo-kit/` synthetic data by the real pipeline. Regenerate per the recipe in `installer/README.md`.
5. `**passport-feedback.rafaeldf2.workers.dev**` — Cloudflare Worker for feedback issues + install telemetry. Deploy via `wrangler deploy` from `cloudflare-worker/`. KV namespace `FCB_METRICS` (id `26eca96d62724b968eeefb17f7cd51e4`).

---

## Recent regression classes — DO NOT re-introduce

Each of these hit production undetected. Tests now guard them. If a test fails with one of these names, you are about to repeat history:

- `test_landing_page_assets_resolve_in_publish_bundle` — installer assets must be **real files, not symlinks**. here-now's `publish.sh` walks files with `find -type f` (skips symlinks). Brand assets live as real-file copies in **three** places now (canonical at `assets/brand/`, plus `installer/assets/brand/` and `skill/templates/site/assets/brand/`). When you update brand files, run both `cp` lines from `assets/brand/README.md`.
- `test_dashboard_demo_bundle_complete` — the demo dashboard needs the synthetic-data banner and the public-demo footer override. Re-applied after every regenerate.
- `test_privacy_footer_is_honest_about_what_publishes` — dashboard footer must NOT claim "the host never received your transactions, only the rendered numbers" (false; `publish.sh` uploads `downloads/transactions_tagged.csv` and embeds the per-transaction list in JSON). Honest framing required: source files (PDFs, statements) stay local; categorized transactions and CSV exports DO get uploaded behind the passcode.
- `pages.yml` placeholder guard — don't disable it. `{{BUILD_STAMP}}` in `installer/index.html` is intentional; substitution happens at publish time via `installer/publish-landing.sh` or the workflow.
- `test_installer_curl_pipe_safe` — install.sh must `exec </dev/tty` early, capture `INTERACTIVE=1` once, and never re-test `[ -t 0 ]` later. Bash 3.2 (Apple's default) returns stale results from `[ -t 0 ]` after redirect.
- `test_installer_consent_gate_does_not_silently_cancel_on_empty` — empty input at the consent gate must re-prompt, not silently cancel. Was a real bug.

---

## Where to find what


| You need to…                           | Look at                                                                                             |
| -------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Understand the product spec            | `dev/finance-clarity-build-spec.md` (long; see § for what you need)                                 |
| See what's left to build / what's done | `dev/backlog.md`                                                                                    |
| See what changed when                  | `CHANGELOG.md` (Unreleased + tagged versions)                                                       |
| Update the landing page                | `installer/index.html` + `bash installer/publish-landing.sh`                                        |
| Update what's listed at /docs          | `installer/build_docs.py` extracts packages/URLs/env-vars from install scripts; descriptions are curated. **Adding a new package or env var that's not in the curated maps fails CI.** |
| Add or change a legal page             | `installer/legal/{privacy,terms,dpa}.html` — drafts pending legal review. Keep the draft banner until counsel signs off. |
| Update the dashboard template          | `skill/templates/site/index.html` (regenerate demo via `installer/README.md` recipe)                |
| Run the pipeline manually              | `FCB_WORKSPACE=/tmp/ws bash skill/scripts/refresh.sh --auto-confirm` after seeding `/tmp/ws/inbox/` |
| Touch the install scripts              | `installer/install.sh` (Mac) + `installer/install.ps1` (Windows) — keep in sync                     |
| Touch the Worker                       | `cloudflare-worker/src/index.js` — `wrangler deploy` from that directory                            |
| Read advisor-facing docs               | `docs/advisor-onboarding.md`, `docs/troubleshooting.md`                                             |
| Check CI workflow definitions          | `.github/workflows/`                                                                                |


---

## Tone of voice in user-facing strings

- **Plain English.** No "API key", "slug", "Homebrew", "venv", "npx" in anything a non-technical user reads. The `lint-user-strings.yml` workflow enforces this.
- **No m-dashes in user-facing copy.** Use periods or "and" instead.
- **Specific over hedged.** "Your dashboard is ready" beats "Your dashboard should now be available."
- **Honest privacy claims.** Never overpromise. The product is "local by default, share if you choose"; don't escalate that to "your data never leaves your computer" if a code path uploads something.

---

## When in doubt

- Ask the user before destructive operations (`git reset --hard`, force-push, deleting tester data).
- Read `tests/test_pipeline.py` module docstring for the prototype-phase test philosophy.
- Read `installer/README.md` for publish + brand-sync mechanics.
- The auto-memory system at `~/.claude/projects/.../memory/` may have relevant context from prior sessions.
- If a recent regression class returns, the answer is in `CHANGELOG.md` under the matching B9.x entry.

---

*This file should be updated whenever a new convention is introduced that future agents should follow. Keep it under 300 lines so it stays scannable.*