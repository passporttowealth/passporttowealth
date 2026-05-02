# Advisor onboarding playbook

> **⚠ Prototype.** This is the v1 advisor-side playbook for getting a client from zero to a published dashboard. Updated as the install flow firms up.

How you (the advisor) hand a client an install link, what to verify before they install, what you do live during the kickoff session, and how to do the post-install handoff.

---

## Before sending the link

Confirm with the client (over email or call) that they have all four of these. Don't send the link until they do — every missing item is a much harder fix mid-install than pre-install.

| Item | What to ask | If missing |
|---|---|---|
| **Mac running macOS 13 (Ventura) or later, OR Windows 10 (build 1903+) / Windows 11** | "What computer will you use this on, and what version is it running? On Mac it's *About This Mac*; on Windows it's *Settings → System → About*." | Mac older than 13 → upgrade or use a different machine. Windows older than 1903 → same. The skill is personal-laptops-only in v1 — corporate-managed machines (MDM) are detected and refused. |
| **At least 10 GB free disk space** | "How much free space is on your computer? On Mac open *Storage* in System Settings; on Windows, *Settings → System → Storage*." | Walk them through clearing space (Downloads, Trash, large unused apps). |
| **A Claude account: Pro, Max, or an API key** | "Do you have a paid Claude account? If yes, Pro or Max? Or do you have an Anthropic API key?" | Walk them through signing up at `https://www.anthropic.com/claude`. Pro is fine for first install; Max if their usage grows. API key is for technical clients who already use the API. |
| **They're comfortable installing software you sent them** | "I'm going to send you a small installer. Mac/Windows will show a warning saying it's from an unknown developer — that's normal because we haven't paid for code-signing yet. The download page tells you exactly how to get past it." | If they're skittish, offer to drive the install live during the kickoff session (you screen-share, they share their screen, you walk through every click). |

If anything's a no, don't send the install link. Resolve first.

---

## Sending the link

The link is the same for every client (v1 — per-client signed links are v2; see `dev/backlog.md` Epic 6.5):

> `https://passporttowealth.app/`

(`www.passporttowealth.app` redirects to the apex, so either form works in client emails.)

Suggested email template (paste into your client mail):

```
Subject: Your Finance Clarity workspace — install link

Hi {name},

Here's the install link for the financial dashboard we discussed:

  https://passporttowealth.app/

The page shows a single command to copy. You'll open Terminal (on Mac:
press ⌘+Space, type "Terminal", hit Enter — the page walks you through
this if it's your first time), paste the command, and the installer
runs from there.

A few things upfront:

  • It takes about 10 minutes if you've installed developer tools on
    this computer before, or up to an hour on a fresh laptop (Mac
    needs to download some Apple developer tools first).

  • You'll be asked once how you sign in to Claude — paid subscription
    (Pro/Max) or an API key. Pick whichever you have.

  • The dashboard opens locally in your browser by default — your
    files don't leave your laptop. If you later want to share it with
    me or family, just tell the assistant "share my dashboard" and
    it walks you through a one-time email signup with the host.

If you'd rather we do this together — I'm happy to share my screen
and walk through every step on our kickoff call. Just let me know.

When you're ready, open the link.

— {your name}
```

---

## What you confirm during the kickoff session

If the client has installed already, walk through this together:

1. **`~/Documents/my-finances/` exists** with subfolders. If not, the install didn't complete — have them re-run the curl one-liner from passporttowealth.app, or check the install log.
2. **They can run `claude` from any Terminal** and see the AI assistant greeting. If `claude: command not found`, the Claude Code install didn't complete — re-run install. If claude opens but says "no API key" / "not authenticated", their auth didn't take — re-run install and pick the right option (paid subscription vs API key).
3. **They have files to drop in.** Confirm they have at minimum: bank statements as CSV exports (check they can actually export from their bank — some banks make this hard). Paystubs and tax docs are optional and won't be read by default.
4. **They've picked one calculator** (see `skill/references/CALCULATOR_INTERFACE.md`) — or they're comfortable shipping with the placeholder card.

Then walk through the demo per `dev/demo-script.md`.

---

## Post-install handoff

After the kickoff session ends, the client should leave with:

- Their dashboard URL bookmarked on phone + laptop.
- Their passcode saved in their phone's password manager (1Password, iCloud Keychain, Bitwarden — whatever they use).
- A copy of the URL + passcode in their own email (the agent can email it to them during the publish step).
- Knowledge that they can ask the agent any time:
  - *"What's my passcode?"* → recites it
  - *"What's my URL?"* → recites it
  - *"Refresh my report"* → drops new files in inbox + this prompt = updated dashboard
  - *"Delete my dashboard"* → takes the site down
  - *"I have feedback"* → opens the feedback channel (sends to your email, plus your Cloudflare Worker if configured per `docs/feedback-channel.md`)
  - *"Something's broken"* → sends you a redacted support bundle

Send a follow-up email with these prompts in writing so they have it saved.

---

## When things go wrong

Three failure surfaces, in order of how often they bite:

1. **Install never completed.** Client emails you saying nothing on their Desktop. Ask them to attach `~/Library/Logs/passport-to-wealth-install.log` (Mac) or `%LOCALAPPDATA%\PassportToWealth\Logs\passport-to-wealth-install.log` (Windows). Read against `docs/troubleshooting.md`.
2. **Install completed but the dashboard doesn't build.** Client says "I dropped files in and said build, but nothing's happening" or "my totals look wrong." Have them say *"Something's broken"* to the agent — you'll receive a redacted support bundle by email (or as a GitHub issue if your Cloudflare Worker is set up). Read against `docs/troubleshooting.md`.
3. **Dashboard built but the published URL doesn't load.** Likely a publishing-host issue. Have them say *"Find my site"* — the agent locates the slug. Then check the host's status page.

For everything else: the client has a feedback channel built into the skill (per spec §15.1). Encourage them to use it — it's how the prototype gets better fastest.

---

## Onboarding multiple clients

For now, each client gets the same install link. Their workspaces are independent on their own laptops. If you want a per-client view of who's onboarded:

- Keep a private spreadsheet or Notion page (advisor-side, not committed to the repo).
- Each row: client name, install date, dashboard URL (you only learn it if they share), most recent support bundle, calculator picked, status.

Per-client signed install links + an automated `advisor-onboard` registry are v2 (`dev/backlog.md` Epic 6.5).

---

## When the prototype matures past the May milestone

This playbook will need to evolve. Likely changes:

- Replace the manual link-sharing with `advisor-onboard` (Epic 6.5.2) — generates per-client signed links you send instead of the generic one.
- Replace the support-bundle email path with auto-transmitted error envelopes (Epic 6.5.4) — you see failures in your inbox before the client even reports them.
- Add heartbeats (Epic 6.5.5) so you know who's actively using it vs. stalled.
- Sign + notarize the installer (Epic 6.5.6) so the Mac/Windows warning goes away.

Until then, this manual flow is the contract.
