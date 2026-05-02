> **⚠ Prototype — pre-release.** This script describes the intended demo flow against the v1 product. The product itself is under active development; some steps below depend on backlog items not yet shipped. Use this as the target experience, not a current capability.

## Audience

A first-time, non-technical client with a folder of their own financial files (bank exports, payslips, tax docs, receipts) who wants to see their money clearly without handing it to a third-party app. Walks away in under 30 minutes with a private, password-protected URL they can open from any device and share with a financial advisor.

> **Show, don't tell** — for prospects who want to see the output before committing to the install, send them `https://passporttowealth.app/dashboard-demo/`. It's the real dashboard rendered against the synthetic `demo-kit/` fixture; same layout, real charts, real categorization, fake numbers. Lives in `installer/dashboard-demo/` and is regenerated per the steps in [`installer/README.md`](../installer/README.md#the-demo-dashboard).

> Assumes the `finance-clarity-build` skill and the `install-finance-clarity` bootstrap installer (see `backlog.md`) are shipped. The client never types a Python command, never edits a config file, and never opens Terminal except by double-clicking.

---

## What the user will have at the end

1. A categorized view of their spending and income, populated into a branded site that looks the same for every client. **Opens locally in their browser by default** — lives only on their laptop, no third-party servers, no signup required.
2. **(Optional, opt-in)** A private URL at `{slug}.here.now`, gated by a server-side passcode they chose. Triggered only when the user explicitly chooses to share with their advisor or family. Content is never served until the passcode is verified.
3. A `Download your data` block on the site with the underlying CSV, Excel summary, and rule file — portable to any accountant.
4. A monthly refresh path that takes one drop-in and one sentence.

---

## Phase 0 — Install (10–60 min, before the call)

### What the advisor confirms before sending the link

Same checklist every client. If any of these aren't true, fix them before sending the install link:

1. **Mac running macOS 13 (Ventura) or later**, personal (not employer-managed), at least 10 GB free.
2. **One of:** active Claude Pro subscription, active Claude Max subscription, or Anthropic API key with billing set up. The installer will guide them through whichever they have.
3. **Heads-up sent** that the install takes ~10 minutes if they've installed developer tools before, up to an hour on a fresh Mac.

### What the client does

Send the client one link: `https://passporttowealth.app/`. They:

1. **Open the link.** A single-page site with a copy-button install command and a one-line "how to open Terminal" hint for first-timers.
2. **Open Terminal** (`⌘ Space` → type `Terminal` → `Enter`). The site walks them through this if they haven't done it before.
3. **Paste the one-liner and hit Enter:**
   ```
   curl -fsSL https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh | bash
   ```
   The installer runs in that Terminal window:
   - Runs pre-flight (disk, MDM, macOS version, network). Aborts cleanly with a plain-English message if anything is off.
   - Tells them realistic install time based on whether developer tools are present.
   - Asks for their Mac password once (system tools install).
   - **Asks how they sign in to Claude:** paid subscription (Pro/Max) or API key. Walks them through the right path.
   - Detects iCloud-synced Documents and offers to relocate the workspace outside the sync root.
   - Prints a final "✓ Done" with three lines of "what to do next" (open Terminal, type `claude`, ask for a report). **No Desktop shortcut, no app icon, no other artifacts on the user's laptop** beyond the workspace folder itself.
4. **No publishing-host signup at install time.** The dashboard is local-only by default. If they later choose to share with their advisor, the email-code signup runs then — once.
5. **No passcode for them to invent.** When they do choose to share, the skill generates one — phone-friendly, lowercase, no autocorrect-eating characters.

**Curl-piping the install bypasses macOS Gatekeeper entirely** because nothing lands on disk as a downloaded file. The previous file-download path (with the right-click → Open dance) is the v1 abandonment surface we removed; legacy `Welcome.command` lives at `installer/legacy/` as a fallback for clients who genuinely won't open Terminal.

If anything fails, the installer writes `install.log` and offers to bundle it for the advisor.

**No file sorting required.** The user can drop everything they have into the workspace `inbox/` in any structure — zipped, nested, duplicated, mixed-format. The skill handles the rest.

---

## Phase 1 — Open the workspace (2 min)

Live, screen-sharing.

1. **Open Terminal and type `claude`.** The AI assistant greets them. The skill (`finance-clarity-build`) auto-loads — it's globally registered under `~/.claude/skills/`. No need to be in any particular folder.
2. **Open Finder separately** at `~/Documents/my-finances/inbox/` so they have a visible drop target. (Spotlight: ⌘+Space → type `my-finances` → Enter.)
3. The assistant's greeting tells them, in plain English, what stays on their laptop, what they can ask, and that paystubs/tax docs are skipped by default.
4. Client drags their finance folder (or files) into the open `inbox/` Finder window from anywhere on their computer.

---

## Phase 2 — Sort, normalize, sanity-check (8 min, conversational)

The whole phase is one prompt from the user.

> **User says:** I dropped my files in. Build my report.

Claude runs the skill's ingestion routine and reports back in plain language:

1. **Sort:** "I found 47 files. I sorted 41 of them: 18 bank exports, 12 payslips, 8 tax docs, 3 Amazon orders. I wasn't sure about these 6 — can you tell me what they are?" Disambiguation is structured (a/b/c/d/e options), not free-text.
2. **Dedupe:** "Three of these were the same statement saved twice. I kept one copy of each."
3. **Privacy gate:** "I see payslips and tax returns in the folder. By default I'll skip them — your report doesn't need to read them. Tell me if you want me to include them." Detection is **content-aware** — even if a payslip is misclassified into the bank-transactions folder, the skill catches it on the read attempt.
4. **Account aliases:** "I see these accounts in your data. What would you like to call them on your dashboard? (Defaults: Joint Checking, Travel Card, …)" — account numbers never appear on the published site.
5. **Currency:** If primary currency isn't set yet, asks once: "What currency should your dashboard show totals in?" Defaults to the most-frequent currency observed.
6. **Normalize:** "Your Deutsche Bank file uses DD/MM dates and shows debits as positive. Your Chase file is the opposite. I'll convert everything to a common format. Confirm?"
7. **Hard sanity floors run first:** if savings rate is unbelievable, income jumps suspiciously month-over-month, transfers dominate the data, or > 50% is uncategorized, Claude flags it **before** asking "does this look right" — with the specific numbers and a one-line plain-English reason.
8. **Sanity gate:** Claude shows totals: monthly in/out, top 10 merchants, transfers excluded, biggest 5 transactions, FX cache freshness. Asks "does this look right?" The site does **not** build until the user says yes. Past a floor violation the user has to type the explicit acknowledgement so we know it was a deliberate choice.

Watchpoints:

- If the user says a number looks wrong, Claude investigates that line, not the whole pipeline. Common cause: a transfer between their own accounts mis-classified as income.
- If the user says "include the payslips," Claude asks per-file for confirmation and never silently OCRs.
- If a sanity floor trips, Claude does not let the user say "looks right" with a single yes — they have to acknowledge each warning explicitly. The acknowledgements get logged so we can review them later.

---

## Phase 3 — Build the site, view locally (5 min)

Once the user confirms the totals, Claude builds the site from the skill's locked template — same brand, same layout, same components for every client — and **opens it in their default browser via `file://`**. No third-party server, no signup, no passcode. The dashboard lives only on their laptop, gated by the laptop's lock screen.

> **Claude says:** Done. Your dashboard is open in your browser. It lives only on your laptop — no third-party server, no passcode needed (your laptop's lock screen already protects it).

The user sees the branded dashboard: KPI cards across the top, spend-by-category and monthly cashflow charts, sortable transactions table, the Download your data block, and the visual calculator slot (whichever calculator was picked at kickoff — FIRE, FX risk, etc.).

Iteration here is light: rename a category, hide a calculator, swap the order of the charts. The template constrains what can change so the result stays brand-consistent.

**Most clients stop here.** If they only want the dashboard for themselves, the install + build + view loop is the whole story. The publish step in Phase 4 is opt-in — only triggered when the user explicitly wants to share with someone.

---

## Phase 4 — Share it (optional, 5 min)

Skipped entirely if the user doesn't want to share. Surfaced by Claude after Phase 3:

> **Claude asks:** Want to share it with anyone (advisor, family)? I can put it on a private URL with a passcode — that's also how you'd see it on your phone. Just say "share my dashboard" and I'll set it up.

If the user says yes:

> **User says:** Share my dashboard.

The skill runs the safe publish flow:

1. **(First time only)** Runs the in-agent email-code signup with here.now: prompts for the user's email, sends a one-time code, verifies it, saves the API key to `~/.herenow/credentials`. Two user actions — email + code. After that it's silent on subsequent shares.
2. Publishes a placeholder page → a live URL exists but contains no data.
3. **Generates a phone-friendly passcode** (4-word lowercase passphrase, e.g. `paper-orchid-stove-vine` — the user is never asked to invent one) and saves it to `.env` in their workspace.
4. Sets the passcode on the host. Confirms it took.
5. Pushes the real site content to the now-protected slug.
6. Verifies in a fresh session that the passcode prompt appears before any content loads.

**Race condition closed by design.** The skill refuses to push real content to an unprotected slug.

Claude tells the user the URL and the passcode once, then asks how they want it preserved for phone access:

> "Save the passcode somewhere you can reach from your phone:
> - Your phone's password manager (1Password, iCloud Keychain, Bitwarden) — I'll wait if you want to do it now.
> - OR I can email both the URL and passcode to your own address.
>
> Either way, you can always ask me 'what's my passcode?' from your laptop and I'll read it back."

After they save it, Claude offers to clear the Terminal scrollback so the passcode isn't sitting visibly on the screen.

The client opens the URL in a private window on their phone, types the passcode (lowercase, hyphens — no characters autocorrect will mangle), sees the dashboard. Done.

---

## Phase 5 — Use it later (3 min walkthrough)

Same one-sentence loop, every month.

> **User says next month:** I dropped new files in. Refresh.

The skill auto-sorts the new files into the existing structure, dedupes against what's already there, re-runs the pipeline incrementally, asks about any new uncategorized merchants, rebuilds the site, and **opens the rebuilt site locally** in their browser. If the user previously shared (credentials present), it also republishes to the **same slug** with the **same passcode** so the URL their advisor bookmarked stays current. If they never shared, refresh stops at the local view. Reports what changed: "added 47 transactions, 3 new merchants categorized, totals now run through {month}."

The user never thinks about the slug, the passcode, the folder structure, or which command to run.

---

## Phase 6 — Recovery & undo (1 min walkthrough)

Five things the client can do without help. Each is a single sentence to Claude or a double-click of a `.command` file.


| What broke / changed                      | What they do                                                                                                                                        |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Want to take the site down                | "Delete my site" → Claude runs the delete command and confirms                                                                                      |
| Shared the passcode with the wrong person | "Rotate my passcode" → prompted for a new one, old sessions invalidated                                                                             |
| Categorization went sideways              | "Reset my rules" → restores the starter rule set, keeps a backup                                                                                    |
| Lost the URL or moved laptops             | "Find my site" → walks through reinstalling on the new laptop and re-linking to the existing dashboard. "Restore from backup" if they have a workspace backup file (Phase 4.5). |
| Forgot the passcode                       | "What's my passcode?" → Claude reads it from `.env` and recites it back. Same for "what's my URL?".                                                 |
| Want to share with their accountant       | "Share my dashboard with {name}" → opens email with URL + passcode + a one-line cover note pre-filled to the recipient. Clipboard fallback if `mailto:` isn't set up. |
| Want to back up their settings            | "Back up my workspace" → encrypted zip on their Desktop they can store anywhere safe (iCloud, Dropbox, USB).                                        |
| Something's broken and they need help     | "Something's broken" → Claude saves a sanitized diagnostic to their Desktop, uploads it as a one-time password-protected URL, and opens an email pre-filled to Rafa with both the URL and the file attached. Three delivery paths in case any one fails. No transaction data leaves the laptop. |


---

## What stays the same — privacy facts the client should know

- **The data lives on their laptop.** The `my-finances/` folder is the source of truth. Nothing syncs to the cloud unless they put the folder inside iCloud/Dropbox themselves (the installer warns if Desktop is iCloud-synced and offers to relocate).
- **here.now sees the published site.** Server-side passcode means the HTML never reaches a visitor's browser without verification — but here.now itself stores the files. This is access control, not zero-knowledge encryption. For anything they wouldn't trust to a hosting provider, share screenshots instead.
- **Payslips, tax returns, and identity docs are skipped by default.** Only bank transactions feed the pipeline. The client opts in per file if they want anything else included.
- **Logs are local and reviewable.** "Show me what you've written" prints recent error reports in plain English; "redact my logs" clears anything Claude saw during a session.
- **The passcode lives in `.env`** in their workspace, locked to their user account. They can read it any time, and they can ask Claude to recite or rotate it.

---

## Time budget


| Phase                                 | Target     | Hard stop  |
| ------------------------------------- | ---------- | ---------- |
| 0. Install (client solo, before call) | 10–60 min  | —          |
| 1. Open workspace                     | 2 min      | 5 min      |
| 2. Sort, normalize, sanity-check      | 10 min     | 18 min     |
| 3. Build the site                     | 5 min      | 10 min     |
| 4. Publish + save passcode for phone  | 5 min      | 8 min      |
| 5. Walk through monthly refresh       | 3 min      | 5 min      |
| 6. Walk through recovery options      | 2 min      | 4 min      |
| **Total live time**                   | **27 min** | **50 min** |


A 60-min slot leaves ~30 min for the conversation that actually matters: which patterns the client wants to see, which calculator they'd pick if we built a second one, who else they'd hand the URL to, and what would make them recommend this to another advisor.

---

## What this demo is *not*

- Not a production-grade tool. No SLA, no compliance certification, no support contract.
- Not a bank integration. Files come from the user's own exports.
- Not a full-featured app. One calculator, one dashboard, one publish target. Scope held tight on purpose.
- Not a replacement for an advisor. The output is meant to make the conversation with an advisor sharper, not to substitute for it.

