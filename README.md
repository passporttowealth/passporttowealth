# Passport to Wealth — Finance Clarity

> **⚠ PROTOTYPE — pre-release. Not for production use.**
>
> This software is under active development by Passport to Wealth. Expect bugs, incomplete behaviors, and breaking changes. It is intended for invited test users working directly with their advisor — **not** for general distribution and **not** as a system of record for your finances. Always keep your original bank exports and statements; never delete a source file because the dashboard shows it.

A private, passcode-protected financial dashboard a Passport to Wealth client can build on their own laptop in under 30 minutes — from a folder of bank statements to a shareable URL — without sorting files, learning a tool, or signing up for anything beyond the AI assistant they already use.

This repository holds the installer, the skill that drives the workflow, the dashboard templates, and the project planning docs.

## For clients

You should have received an install link from your advisor. Open it on the computer you want to use this on (Mac or Windows). The page detects your operating system and gives you the right download. Follow the on-page instructions for getting past your OS's "unrecognized developer" warning, and the installer will walk you through the rest.

If you don't have an install link yet, contact your advisor at Passport to Wealth.

## For the advisor

See [`docs/advisor-onboarding.md`](docs/advisor-onboarding.md) for how to send a client the install link, what to confirm before they install, and how to read incoming support bundles.

## What's in this repo

| Path | What's there |
|---|---|
| `installer/` | What the client downloads — `Welcome.command` and the landing page (served at `https://passporttowealth.app/` via here.now) that hosts it. |
| `skill/` | The `finance-clarity-build` Claude Code skill: prompts, scripts, dashboard templates, error-code reference. |
| `docs/` | Advisor-facing operational docs (onboarding, troubleshooting, design system, privacy notes). |
| `dev/` | Product / dev planning — demo script, full skill spec, backlog, this repo's layout doc. |
| `.github/` | CI workflows (lint, fixture run, Pages backup deploy) and issue templates. |

## How it works (in one paragraph)

The client downloads `Welcome.command`, double-clicks it, and the installer provisions everything silently — runtime, AI assistant, the dashboard skill, the publishing-host credentials, and the client's workspace folder. The client then drops their financial files into one inbox folder and says *"build my report"*. The skill sorts them, dedupes, normalizes currency and date formats, fetches FX rates, categorizes transactions, runs sanity floors, and shows the totals back for confirmation. Once confirmed, it builds a branded dashboard from a locked template and publishes it to a private URL behind a passcode the skill generates. Future updates are *"I added new files. Refresh."*

For the full design see [`dev/finance-clarity-build-spec.md`](dev/finance-clarity-build-spec.md).

## Status

Pre-v1. The structure exists; implementation is in progress per [`dev/backlog.md`](dev/backlog.md). Not ready for client distribution yet.

## License

Proprietary. See [`LICENSE`](LICENSE). Copyright © 2026 Passport to Wealth. All rights reserved.
