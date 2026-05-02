# Passport to Wealth — Finance Clarity

> **⚠ Prototype — pre-release.** A pilot tool for clients of Passport to Wealth, under active development. Use as a complement to your existing financial records, not a replacement. Always keep your original bank exports.

A private financial dashboard you build on your own laptop in under 30 minutes — from a folder of bank statements to clarity. **Your data never leaves your computer unless you choose to share it.**

**Want to see the output before installing?** [View the live demo dashboard](https://passporttowealth.app/dashboard-demo/) — built from synthetic data by the real pipeline.

## Install

**macOS** — open Terminal (`⌘ Space` → `Terminal` → `Enter`) and paste:

```bash
curl -fsSL https://passporttowealth.app/install | bash
```

**Windows** — open PowerShell (`Win` → `PowerShell` → `Enter`) and paste:

```powershell
irm https://passporttowealth.app/install.ps1 | iex
```

Or visit [passporttowealth.app](https://passporttowealth.app/) for the same with a copy button.

> The Windows installer (v0) shipped in B9.16. Same overall flow as Mac — Anthropic terms gate, paced sections, visible prompts, all tools via winget (Node, uv, jq) + npm (Claude Code) + npx (skills). Test coverage is structural rather than end-to-end since we don't have a Windows test box; ship-then-dry-run the first few clients.

> The short URL is a tiny shim that exec-fetches the canonical script at [`installer/install.sh`](installer/install.sh) on this repo's `main` branch. If you want to read what you're about to run, `curl https://passporttowealth.app/install | less` first.

> **Can't open Terminal or PowerShell?** A file-download fallback lives in [`installer/legacy/`](installer/legacy/). Slower to onboard (you'll hit your OS's "unidentified developer" warning) but works without typing anything.

## What you get

After install completes, you have a `~/Documents/my-finances/` folder and that's it — **no Desktop shortcut, no app icon, no other artifacts on your laptop**. To use it:

1. Open Terminal, type `claude`, hit Enter.
2. Drop your bank statements / payslips / tax docs into `~/Documents/my-finances/inbox/`.
3. Tell the assistant *"build my report."*
4. It sorts, dedupes, normalizes currencies, fetches exchange rates, categorizes, and shows the totals back for confirmation.
5. Once you approve, the dashboard opens in your browser. Local file. No third-party server.
6. (Optional.) Want to share with your advisor? Say *"share my dashboard."* That puts it on a private URL behind a passcode.

Refreshes are *"I added new files. Refresh."* No need to be in any particular folder when you run `claude` — the skill knows where your workspace is.

## Privacy

- **Local by default.** The pipeline runs entirely on your laptop. Files never leave unless you publish.
- **Sharing is opt-in.** No third-party host is contacted unless you choose to share. Users who never publish never sign up for anything.
- **Sensitive files are skipped.** Paystubs and tax returns are not fed into the pipeline by default — you opt in per file.
- **The published URL is gated.** When you do share, content is protected by a server-side passcode the skill generates. The HTML never reaches a visitor's browser without it.

Full privacy operating principles in [`dev/finance-clarity-build-spec.md`](dev/finance-clarity-build-spec.md) §3.

## How the install command works

The one-liner streams a shell script over HTTPS and pipes it to bash (or PowerShell). Same pattern as Homebrew, Rust, uv, and Claude Code itself. Nothing lands in your `Downloads` folder, so no Gatekeeper / SmartScreen warnings to dismiss.

The script provisions: `uv` (Python toolchain), Python 3.11, `jq`, Node.js (Apple doesn't ship it; required for `npx skills add`), Claude Code, the [`here-now`](https://github.com/heredotnow/skill) publishing skill, the `finance-clarity-build` skill (this repo, fetched via [`npx skills add`](https://github.com/vercel-labs/skills)), and the workspace at `~/Documents/my-finances/`. Logs to `~/Library/Logs/passport-to-wealth-install.log` (macOS) or `%LOCALAPPDATA%\PassportToWealth\Logs\` (Windows).

The full source of `install.sh` is right here in this repo for inspection — `curl ... | less` first if you want to read before running.

## What's in this repo

| Path | What's there |
|---|---|
| [`installer/install.sh`](installer/install.sh) | The canonical Mac install script (curl-piped). |
| [`installer/install.ps1`](installer/install.ps1) | The canonical Windows install script (irm-piped). |
| [`installer/index.html`](installer/index.html) | The product landing page, deployed to [passporttowealth.app](https://passporttowealth.app/). |
| [`installer/dashboard-demo/`](installer/dashboard-demo/) | Public live demo of the dashboard at [passporttowealth.app/dashboard-demo](https://passporttowealth.app/dashboard-demo/), built from `demo-kit/` synthetic data by the real pipeline. |
| [`installer/publish-landing.sh`](installer/publish-landing.sh) | Wrapper that publishes the landing page with `{{BUILD_STAMP}}` substituted. **Use this, not the bare here-now skill.** |
| [`installer/legacy/`](installer/legacy/) | Archived `Welcome.command` / `.bat` / `.ps1` for the file-download fallback path. |
| [`skill/`](skill/) | The `finance-clarity-build` Claude Code skill: prompts, scripts, dashboard templates, error-code reference. |
| [`docs/`](docs/) | Advisor-facing operational docs (onboarding, troubleshooting, design system, privacy notes). |
| [`dev/`](dev/) | Product / dev planning — demo script, full skill spec, backlog, repo layout doc. |
| [`cloudflare-worker/`](cloudflare-worker/) | The Worker that turns "I have feedback" into a GitHub issue. |
| [`.github/`](.github/) | CI workflows. |

## For advisors

See [`docs/advisor-onboarding.md`](docs/advisor-onboarding.md) for the kickoff playbook — what to confirm before sending a client the install link, what to walk through live, and how to read incoming support bundles.

## Status

Pre-v1. Structure exists; implementation in progress per [`dev/backlog.md`](dev/backlog.md). Open issues tracked at [github.com/passporttowealth/passporttowealth/issues](https://github.com/passporttowealth/passporttowealth/issues).

## License

Proprietary. See [`LICENSE`](LICENSE). Copyright © 2026 Passport to Wealth. All rights reserved.
