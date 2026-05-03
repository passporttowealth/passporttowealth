# Demo Backlog — Items to Make `demo-script.md` Robust for Non-Technical Users

> **⚠ Prototype — pre-release.** Backlog represents the work needed to reach v1 for the May advisor meeting. Items marked P0 are blockers for the prototype to ship at all; P1/P2 are sequenced behind that.

Companion to `demo-script.md`. Each item closes a gap surfaced during red-team. Priority is set against the end-of-May advisor meeting and the 20-hour sprint cap.

**Priority key:** P0 = demo can't ship without it · P1 = demo ships but feels fragile · P2 = Sprint 2 / post-May
**Size key:** S = <2h · M = 2–6h · L = 6h+

---

## Epic 1 — Bootstrap & install

The whole `demo-script.md` Phase 0 assumes the user already has Terminal literacy, Claude Code, Python, and a here.now account. They don't. The user can copy-paste **one** thing into Terminal — that's the entire ceiling.

### B1.1 — Single bootstrap installer · **P0 · M**
**Problem:** Five separate installs (Claude Code, Python, `openpyxl`, here.now creds, folder scaffold) each with their own failure mode. Non-technical users abandon at install #2.
**Recommendation:** Ship one shell script — `Welcome.command` (Mac double-clickable) — that:
1. Installs `uv` via `curl -LsSf https://astral.sh/uv/install.sh | sh` (single 10MB binary; replaces what used to be Homebrew + brew Python + venv + pip — four prompts collapsed to one)
2. `uv python install 3.11` + `uv venv` + `uv pip install` (one toolchain owns Python provisioning)
3. `brew install jq` *only if jq is missing* — Homebrew is now a conditional dep, not mandatory (jq is the only thing left that needs it)
4. Installs Claude Code via the official one-liner
5. Creates `~/Documents/my-finances/` with the four canonical subfolders empty
6. Prompts for the here.now API key (paste once) and writes it to `~/.herenow/credentials` with `chmod 600`
7. Drops a `START-HERE.command` into `my-finances/` that opens Terminal in that folder and runs `claude`
8. Logs every step to `install.log` so failures are debuggable remotely

User experience: download one file, double-click it, paste two things (Mac password, here.now key), done. **Distribute via a here.now-hosted page** so the link itself is shareable.

### B1.2 — Pre-flight check command · **P0 · S**
**Problem:** When something breaks mid-demo, neither the user nor Rafa knows which dependency is the culprit.
**Recommendation:** A `check.command` that prints a green/red table for: Claude Code installed, Python version, `openpyxl` importable, here.now key present and valid, `my-finances/` folder exists, internet reachable. First diagnostic step for every support request.

### B1.3 — Windows + Linux variants · **P2 · M**
**Problem:** B1.1 is Mac-only. Arielle's audience may include both.
**Recommendation:** Defer to Sprint 2. For now, document Mac-only and confirm Arielle's team is on Mac before the demo.

### B1.4 — Idempotent re-install · **P1 · S**
**Problem:** If the bootstrap is run twice (user panics, runs again), it should skip what's already done, not duplicate or corrupt.
**Recommendation:** Every step in B1.1 wrapped in `if not exists`. End with a "✓ everything is ready" message either way.

---

## Epic 2 — File ingestion (the messy folder problem)

Users will dump everything into one folder — bank PDFs, screenshots, tax returns, recipes — and expect Claude to figure it out. The current script assumes pre-sorted input.

### E2.1 — Auto-sort routine · **P0 · M**
**Problem:** `01_bank_transactions/`, `02_payslips/` etc. don't exist in the user's reality.
**Recommendation:** A Claude routine triggered by "I dropped my files in, what now?" that:
1. Lists every file in the folder (recursively)
2. Classifies each by filename + first-page heuristics (without OCR — just filename patterns and PDF text-layer keywords like "Statement", "Paystub", "1099")
3. Shows the user a proposed sort with a one-line reason per file ("`Chase_Activity_2025.csv` → `01_bank_transactions/` because filename contains 'Activity' + .csv")
4. Asks for batch confirmation, not file-by-file
5. Moves files (doesn't copy — keeps single source of truth)
6. Lists "I wasn't sure about these" separately and asks the user

### E2.2 — Deduplication · **P0 · S**
**Problem:** Users re-download the same statement 3x. Pipeline double-counts. Numbers look 3x higher than reality.
**Recommendation:** Hash-based dedupe inside the auto-sort. If two files have identical content, keep one and tell the user. If two CSVs have overlapping date ranges from the same account, flag for review before merging.

### E2.3 — PDF-statement support · **P1 · L**
**Problem:** Many retail banks (especially European) only give PDF statements, not CSV exports. Current script bans PDF parsing.
**Recommendation:** Use a deterministic PDF text extractor (`pdfplumber`) for text-layer PDFs only — *not* OCR, *not* AI extraction. If the PDF is a scan with no text layer, tell the user "this bank doesn't give us machine-readable data, here's how to ask them for a CSV export." Keep AI-based extraction as an explicit opt-in per file.

### E2.4 — Multi-currency + sign-convention normalization · **P1 · M**
**Problem:** EUR/USD mixing, debits-positive vs debits-negative, DD/MM vs MM/DD all silently corrupt the totals.
**Recommendation:** A normalization step Claude runs after sort. Detects currency from the file/account, detects sign convention from a sample of known-direction transactions (e.g. salary should be positive), detects date format from unambiguous samples (day > 12 anywhere → DD/MM). Surfaces all three decisions to the user before continuing.

### E2.5 — Sanity-check gate · **P0 · S**
**Problem:** Pipeline can produce numbers that are 10x off (double-counted transfers, wrong sign) and the script publishes them anyway.
**Recommendation:** Mandatory checkpoint after pipeline, before site build. Claude shows: total in/out per month, top 10 merchants, biggest 5 transactions, transfers detected and excluded. User must respond "looks right" before site builds. If anything looks off, Claude offers to investigate the specific item.

---

## Epic 3 — Update workflow (drop-in new files over time)

The current Phase 5 is two sentences. Real users will return monthly with new exports, expect the site to update, and have forgotten the slug, the passcode, and the folder location.

### E3.1 — Single update command · **P0 · M**
**Problem:** Phase 5 requires the user to re-prompt Claude through 4 steps. They won't.
**Recommendation:** A `refresh.command` (or a single Claude prompt: "refresh my report") that:
1. Auto-sorts any new files in the inbox (Epic 2)
2. Re-runs the pipeline incrementally
3. Reports new uncategorized merchants and asks for rules
4. Rebuilds Excel + site
5. Republishes to the **same slug** read from `.herenow/state.json`
6. Keeps the same passcode (no re-PATCH unless the user asks)
7. Reports what changed: "added 47 transactions, 3 new merchants categorized, totals updated through March 2026"

### E3.2 — "Inbox" folder convention · **P1 · S**
**Problem:** User doesn't know which subfolder to drop new files into.
**Recommendation:** A single `inbox/` folder at the top of `my-finances/`. Drop anything here. Auto-sort empties it on every refresh. One folder to remember.

### E3.3 — Slug + passcode recovery · **P1 · S**
**Problem:** `.herenow/state.json` lives in the project folder. Lose the laptop, lose the slug. User creates a duplicate site instead of updating, leaving the old one orphaned and live.
**Recommendation:** On first publish, Claude emails the user (via a here.now hosted "your site is ready" page they can bookmark) the slug, the claim URL, and a reminder of the passcode location. Add a `find-my-site.command` that lists all sites under their here.now account.

### E3.4 — Categorization-rule persistence + sharing · **P1 · S**
**Problem:** Rules built in Session 1 should persist to Session 2. If Arielle wants to share a starter rule set across her clients, there's no mechanism.
**Recommendation:** Rules live in `my-finances/rules.yaml`, version-controlled by the user (or just backed up). Ship a starter `rules.yaml` with the 100 most common merchants for the EU/US cross-border audience, derived from `finance_ops/custom-build/pipeline/categorize.py`.

### E3.5 — Diff view between refreshes · **P2 · M**
**Problem:** User can't tell what changed month-over-month.
**Recommendation:** Site shows "since last refresh on {date}: +47 transactions, category X up 12%, new recurring charge detected." Sprint 2 — not needed for first demo.

---

## Epic 4 — Design system / front-end quality

The current Phase 2 prompt ("bar chart, line chart, table") will produce something visually generic and inconsistent run-to-run. For a brand-aligned demo to ~35 advisors, that's not enough.

### E4.1 — Branded HTML template · **P0 · M**
**Problem:** Every run produces a different-looking site. Arielle can't show a consistent product to advisors.
**Recommendation:** A pre-built `site-template/` with locked-in:
- Color tokens (Passport to Wealth palette — confirm with Arielle)
- Typography (one display, one body, one mono — system fonts to keep it offline-safe)
- Layout grid (12-col, mobile-first)
- Component library (KPI card, chart container, transaction row, downloads block)
- Inlined chart library — pick one (Chart.js or uPlot) and ship it inlined, not via CDN
- Empty data slots Claude fills in, rather than Claude generating HTML from scratch

Claude's job is to populate the template, not invent the design.

### E4.2 — `frontend-design` skill or local equivalent · **P0 · M**
**Problem:** Without a skill, Claude defaults to its generic AI aesthetic. The `frontend-design` skill exists in this environment — leverage it.
**Recommendation:** Either (a) invoke the existing `frontend-design` skill in the build prompt, or (b) write a project-local skill `finance-clarity-build` that bundles the template (E4.1), the publish flow (Epic 5), and the design constraints into one invocation. Option (b) is cleaner because it also encodes the safety and publish-flow rules in the same place.

### E4.3 — Accessibility + mobile baseline · **P1 · S**
**Problem:** Advisors will open the demo on phones. Generic Claude HTML won't be responsive or accessible.
**Recommendation:** Template enforces: WCAG AA contrast, 16px min body text, viewport meta, prefers-reduced-motion, semantic HTML for tables, keyboard-navigable filters. Add a Lighthouse check in the build step that fails the build if score drops below 90.

### E4.4 — Chart selection guide · **P1 · S**
**Problem:** "Bar chart for spend by category" is the lazy default. Some questions are better answered by a treemap, a sparkline, or a calendar heatmap.
**Recommendation:** A short decision matrix Claude consults: "spend over time → line; spend by category → horizontal bar (more labels fit); recurring patterns → calendar heatmap; portfolio composition → treemap." Three or four named patterns, not unlimited creativity.

### E4.5 — Print/PDF stylesheet · **P2 · S**
**Problem:** Advisors will want to print or PDF-export the dashboard for client meetings.
**Recommendation:** A `@media print` block in the template. Sprint 2.

### E4.6 — Visual calculator slot · **P0 · M**
**Problem:** The sprint commits to "one visual calculator" (FIRE, FX risk, etc.) but there's no slot for it in the current site structure.
**Recommendation:** Template has a dedicated "Calculators" section with a plug-in pattern. Whichever calculator is picked at kickoff (see `skill/references/CALCULATOR_INTERFACE.md`) drops into that slot without changing the rest of the site.

---

## Epic 5 — Privacy & safety guardrails

Currently informal ("don't let Claude open the payslip PDFs"). For Claude-as-instructions, these need to be hard rules in the skill, not advice in a markdown doc.

### E5.1 — Default-deny on PDFs with sensitive content · **P0 · S**
**Problem:** Claude will silently OCR payslips, tax returns, anything PDF.
**Recommendation:** Skill enforces: never open `02_payslips/`, `04_reference_docs/`, or any file matching `*tax*`, `*1099*`, `*W2*`, `*SSN*` patterns without an explicit per-file confirmation from the user. The pipeline uses **only** bank transactions by default.

### E5.2 — Publish-then-protect race condition · **P0 · S**
**Problem:** here.now publish creates a live URL before PATCH adds the password. Window of seconds where financial data is publicly accessible.
**Recommendation:** Two-step publish baked into the skill:
1. Publish a single `index.html` placeholder that says "site coming soon"
2. PATCH the password
3. Verify password is set (response includes `passwordProtected: true`)
4. **Then** push the real content via update
The skill must refuse to push real content to an unprotected slug. No exceptions.

### E5.3 — Passcode handling hygiene · **P0 · S**
**Problem:** Passcode passed via CLI ends up in shell history and `.claude/` logs.
**Recommendation:** Skill reads passcode from a prompt or a `--password-file` flag, never as a CLI argument. Never echoed to logs. Stored in `my-finances/.passcode` with `chmod 600` so the refresh command can reuse it.

### E5.4 — Log audit + redaction · **P1 · S**
**Problem:** Claude Code logs in `.claude/` may contain raw transaction descriptions, account fragments, merchant names.
**Recommendation:** A `redact-logs.command` that scrubs `.claude/` of anything matching account-number patterns or anything from `02_payslips/`. Also: document log location so user can clear them themselves.

### E5.5 — `.gitignore` and cloud-sync warning · **P1 · S**
**Problem:** User puts `my-finances/` in iCloud/Dropbox/OneDrive without realizing it. Files leave the laptop.
**Recommendation:** Bootstrap (B1.1) warns if Desktop is iCloud-synced and offers to put `my-finances/` outside the sync root. Ship a `.gitignore` that excludes credentials, state, the inbox, and all data files — so if the user does git-init the folder they don't accidentally commit transactions.

### E5.6 — Plain-language privacy summary on the site · **P2 · S**
**Problem:** Anyone the user shares the site with should know what here.now sees.
**Recommendation:** A small footer on the site: "Hosted on here.now. Server sees the files; access is gated by a passcode you control. Source data on owner's laptop." Sprint 2.

---

## Epic 7 — Browser-level regression testing

### H7.1 — Headless browser test suite · **P1 · M**
**Problem:** Tests in `tests/test_pipeline.py` are static HTML inspection. They can't catch behavioral bugs (scroll loops, broken interactions, chart rendering failures). One such bug — `scrollIntoView` inside an IntersectionObserver creating a feedback loop — shipped through green CI in commit `9a87c0f`.
**Recommendation:** Add Playwright (Python flavor). New `tests/test_browser.py` runs the smoke checklist from `dev/SMOKE_CHECKS.md` headlessly: page scrolls, nav highlights as you scroll, charts hover, drawer opens, feedback submits. ~1 min total. Replaces the manual checklist for what can be automated.
**Why not now:** adds ~150 MB to CI (Playwright + Chromium), needs iteration to stabilize against flakiness. Worth doing once the prototype settles.

---

## Epic 8 — Landing page polish (research + critique from dry-run)

The `installer/index.html` landing page is the single most important page in the funnel — clients see it before they trust *anything* else about the product. It's currently functional but reads "engineer's prototype," not "polished product Arielle would proudly send to a client." Critique below is grounded in concrete comparable landing pages reviewed during the dry-run setup phase.

### Comparables reviewed

| Site | What's best-in-class | Gap vs. ours |
|---|---|---|
| **cursor.com** | Massive headline + interactive product mockup + named-individual social proof (Karpathy, Collison, Brockman) immediately above the fold. Footer has SOC 2 badge + 8-language selector. Trust comes from "look who already uses this," not from explanation. | We have no product visual above the fold and no social proof. Page is text-and-warning-heavy. |
| **raycast.com** | Single confident "Download for Mac" CTA, system requirement note (`v1.104.15 macOS 13+`) right below — frictionless. Inter typography. Zero install-warning language. Animated product visual (their keyboard) is the centerpiece. | Our prototype banner is the *first thing* you see — defensive opener. Our Mac warning callout dominates the page visually. |
| **(general best-practice patterns)** | Hero screenshot of the actual product. Inverted pyramid: most important first. Secondary trust signals (open-source badge, named maintainer, security policy). Sticky CTA on scroll. Single primary action per viewport. | We have many of the right ingredients but the **emphasis hierarchy is wrong**: warnings dominate, the actual product is invisible above the fold. |

### What's good about the current page (preserve)

- Brand color (`#0F1E33` navy) is right and matches the dashboard.
- OS auto-detection + appropriate fallback when JS is off.
- The Gatekeeper / SmartScreen workaround steps with SVG illustrations — these *exist* and that's better than 90% of indie installers. Just needs better placement.
- Privacy-aware language is already in the prototype banner — needs to be promoted, not buried.
- Single clear download CTA per platform.

### What needs to change (concrete list)

#### E8.1 — Lead with the product, not the warning · **P1 · M**
Above the fold currently: **prototype banner → headline → download button → text "what this does" → big yellow Mac-warning block**. This is engineer-think — defensive disclaimers first, product last. Industry pattern is **screenshot + headline + CTA + social proof**, then everything else.
**Recommendation:** Hero becomes a real screenshot of the populated dashboard (use the demo workspace render, lightly cropped). Headline + CTA sits beside or below it. Prototype banner moves to a smaller "About this prototype" strip after the hero, not blocking the first impression. Mac-warning block collapses behind a "Need help getting past Mac's warning?" expandable that opens after the user clicks Download (or stays open by default but visually de-emphasized — same yellow, half the size).

#### E8.2 — Add trust signals (Arielle's identity) · **P1 · S**
Currently the page says "Passport to Wealth" and shows the logo. That's a brand, not a person. Modern best-practice (Cursor with Karpathy, Linear with Anand, Raycast with Marques Brownlee) is to **put real names and faces** near the CTA so the visitor knows who's behind this.
**Recommendation:** Below the hero: a small "From Arielle Tucker, Passport to Wealth" line with her headshot (already on passporttowealth.com — needs her permission to reuse). Plus one sentence in her voice about why she built this. Optional: a "Source code on GitHub" link as a tertiary trust signal for the technically curious.

#### E8.3 — Visual "how it works" instead of the text block · **P1 · S**
Current "What this does" section is a paragraph + bullet list. Modern landing pages use **3-step visual sequences** with tiny icons or screenshots: `[1. Install] → [2. Drop your files in] → [3. See your dashboard]`. Each step is a small card with one sentence, no paragraph. Faster to scan, more confidence.
**Recommendation:** Replace the bullet list with a 3-card grid (mobile: vertical stack). Each card: number, mini-icon, one-line title, one-line description. Total: 9 lines of text instead of a paragraph.

#### E8.4 — Promote privacy / data handling to its own section · **P1 · S**
"Your data, on your laptop" is buried inside the prototype banner. For a financial tool, this is the #1 thing prospects care about. Should be its own section with **3-4 short bullets** under a clear heading like "Your data, your laptop, your control".
**Recommendation:** New section between "How it works" and the OS-warning callout. Bullets: (1) files never leave your laptop except the rendered dashboard; (2) dashboard locked with a passcode you control; (3) sensitive docs (paystubs, tax) skipped by default; (4) Anthropic data terms link upfront. Each bullet: one line, no jargon.

#### E8.5 — Rework the prototype banner · **P1 · S**
The yellow box up top sets a "this might break" mood before the visitor knows what "this" is. Better pattern: a smaller "About this prototype" strip after the hero, with the same content but in a less alarming visual treatment. Or: a tasteful "Beta" badge on the download button itself, with the explanation in a hover/tap tooltip.
**Recommendation:** Move the prototype banner down. Replace the yellow alarm-treatment with a calmer info box (light-navy tint instead of warning yellow). Keep the wording — just change where the eye lands first.

#### E8.6 — Bundle Inter font on the landing page · **P0 · XS**
Dashboard already bundles Inter (4 weights). Landing page relies on the system font stack — looks great on Mac, mediocre on Windows. Trivial port: copy the `@font-face` block + woff2 files. Closes a gratuitous cross-platform polish gap that prospects judge us on instantly.

#### E8.7 — Sticky download CTA on scroll · **P2 · XS**
Long landing pages (this one will be after E8.1-E8.5) lose the CTA when the user scrolls. Industry standard is a small "Download for Mac" button that sticks to the top right (or bottom on mobile) once the hero CTA scrolls out of view. ~30 lines of CSS + an IntersectionObserver.

#### E8.8 — Footer enrichment · **P2 · S**
Current footer: copyright + main site link. Industry norm has 3-5 columns: product, security, company, legal. We have legitimate things to put there: link to the GitHub repo (transparency), link to `docs/feedback-channel.md` summary or a "How feedback works" page (process transparency), security contact email (`SECURITY.md` reference), Anthropic terms link, the brand main site. Builds credibility without adding noise above the fold.

#### E8.9 — Replace the "Watch a 30-second video" placeholder · **P2 · M**
Modern best practice: a Loom or 30-sec MP4 above the fold showing the product in motion. We don't have one. Out-of-scope until v1 ships, but reserve a slot in the design so it can drop in.

### Summary of design hierarchy change

**Currently (top to bottom on first viewport):**
1. Logo + brand
2. ⚠ Yellow prototype banner (large)
3. Headline + lede
4. Download button (small text link)
5. Description fineprint
6. "What this does" text bullet list
7. ⚠ Big yellow "Mac will warn you" block with screenshots

**Target:**
1. Logo + brand
2. **Hero with dashboard screenshot + headline + confident CTA + system req note**
3. **Trust strip**: "From Arielle Tucker / Passport to Wealth" + headshot + one-line why
4. 3-step "How it works" visual cards
5. "Your data, your laptop" privacy section
6. Calmer prototype info strip (not a yellow alarm)
7. Collapsible "Need help getting past Mac's warning?" — opens after download click
8. Enriched footer

**Total scope:** the content stays ~95% the same. The reorganization, hierarchy, and one new screenshot do the heavy lifting.

---

## Epic 9 — Bugs surfaced during the dry-run walkthrough

### B9.1 — `Welcome.command` opens browser before user reads the consent text · ✅ **DONE** (Issue A in commit 72ded60)
**Status:** Auto-open removed. URL is printed for the user to click — Terminal linkifies it. Same fix in legacy/Welcome.ps1.
**Found by:** dry-run, Phase 1 of `dev/SMOKE_CHECKS.md`-style walkthrough.
**Symptom:** During the Anthropic data-terms consent gate, the script prints the explanatory text *and* calls `open https://privacy.anthropic.com/` in the same flow before prompting for `I accept` / `no`. The browser snaps focus, the user loses their place in the Terminal, doesn't know what to type next.
**Root cause:** Lines in `installer/Welcome.command`:
```bash
say "If you do not accept Anthropic's terms, please ${BOLD}stop here${RESET}..."
say
# Open the privacy hub in the user's browser so it's one click away.
if command -v open >/dev/null 2>&1; then
  open "https://privacy.anthropic.com/" 2>/dev/null || true
fi
while true; do
  read -r -p "..." consent
```
Browser opens between the info print and the prompt — focus shift kills the moment.
**Fix:** Three options, in order of preference:
  1. **Don't auto-open at all.** Print the URL, let the user click it (Terminal makes URLs clickable on Mac). Removes the focus-shift entirely.
  2. **Ask first**: print info → prompt "Would you like me to open the privacy hub in your browser? (yes/skip)" → open if yes → then the accept/no prompt.
  3. **Open AFTER prompt**: open only on `I accept` so the user reads the terms BEFORE the browser opens (less useful but easy).
Recommend option 1 — least surprising, fewest moving parts.
**Mirror in `Welcome.ps1`** — same bug exists there, same fix.

### B9.2 — Seamless install → first-run handoff · ✅ **DONE** (commit 475513e, then superseded by B9.10)
**Status:** Originally shipped as a "Want to start now?" prompt that exec'd into the workspace launcher (commit 475513e). B9.10 then removed START-HERE entirely + the launcher wrapper, so the seamless-handoff prompt is also gone. Re-entry is now just "open Terminal, type claude" (printed at end of install).
**Found by:** dry-run user-interview phase.
**Symptom (the surface complaint):** The installer ends with "Double-click START-HERE on your Desktop whenever you want to use it." This forces a context switch right when momentum is highest — Terminal → minimize/cmd-tab → find Desktop icon → double-click → wait for new Terminal → resume. The user just spent 10+ minutes installing and now has to *find a thing*.
**The deeper need (what user-interview surfaced):** First-run should feel like ONE coherent flow, not two disjointed events stitched by a Desktop shortcut. The shortcut is fine for *next time*; it's wrong as the first-run handoff.
**Comparables:**
  - **`npm create vue` / `npx create-react-app`**: end with `cd <dir> && npm install` printed — they point but don't launch. (Acceptable for dev tools where the user is technical and probably wants to look around first.)
  - **Cursor / VS Code installer**: auto-opens the app at the end. Zero friction. Implicit assumption: the user installed it because they want to use it.
  - **GitHub CLI `gh auth login`**: ends with "✓ Logged in. Try `gh repo list` to see your repos." — points without launching, but the next thing IS a one-line CLI command, not a Desktop hunt.
  - **Stripe CLI / Vercel CLI install**: end with the "what to run next" line.
  - **Modern interactive installers** (rustup, fnm, deno-install): explicit "Run `source ~/.bashrc` or restart your terminal to start using it" — equivalent of the Desktop double-click, BUT they understood at install time the user couldn't be auto-relaunched into a new shell.
**The right pattern for our audience:** **ask, default-yes, launch in place**. We're not constrained the way `rustup` is — we can re-exec from the install script directly into the workflow.
```
✓ Your workspace is ready.

Want to start now? [Y/n]: _

  [Y or Enter] → script execs straight into the workflow
                 (same Terminal window, no Desktop hunt, no context switch)
  [n]          → "OK — double-click START-HERE on your Desktop whenever you're ready."
                 (the shortcut still exists for re-entry next time)
```
**Implementation sketch:** at the end of `Welcome.command`, after the diagnostic green-✓ block:
```bash
read -r -p "Want to start now? [Y/n]: " ANSWER
case "$(echo "$ANSWER" | tr '[:upper:]' '[:lower:]' | xargs)" in
  ""|y|yes) exec "$WS/.skill-launcher.sh" ;;     # the same thing START-HERE points at
  *)        say "OK — double-click START-HERE on your Desktop whenever you're ready." ;;
esac
```
~10 lines. Mirror in `Welcome.ps1` (PowerShell `Start-Process` instead of exec).
**Bonus:** for the first-ever install, the user could go straight from the install script into the workflow without ever needing the Desktop shortcut. The shortcut is then only for sessions 2+, where it actually makes sense.

### B9.3 — Pace the CLI output so a human can actually read it · ✅ **DONE** (commits 92b0a4a, 72ded60)
**Status:** `say_paced` / `ok_paced` / `pause_for_user` helpers + section-by-section pre-consent pacing. `--auto` bypasses for CI. Visible-prompt fix in commit 544f749 (printf prompt as line then read, sidesteps read -p invisibility on some Mac terminals).
**Found by:** dry-run user-interview phase.
**Symptom (the surface complaint):** "The terminal responses were really quick and it didn't let me read through each of the progress process." Pre-flight checks (4 sequential ✓s) appear in under a second. The user feels processed, not guided.
**The deeper need (what user-interview surfaced):** The user wants to FEEL competent — like they're following along with what's happening, not watching a robot do work TO them. Pacing is a trust-building mechanism.
**How best-in-class CLI tools handle this:**
  - **Stripe CLI / Vercel CLI / npm**: use the `ora` library — every step gets a unicode spinner (`⠋ ⠙ ⠹ ⠸`) that runs for at least the actual work duration. If a step completes in <500ms, the spinner is held for a forced minimum so the user can read the label before it flashes to ✓.
  - **rustup**: massive vertical spacing between steps, color-coded statuses, generous use of bold text — slow visual rhythm even when work is fast.
  - **GitHub CLI `gh auth login`**: pauses for input at every major milestone (URL display → "Press Enter to open browser" → wait for OAuth → "Authentication complete"). The user can't get ahead of the script.
  - **Charm.sh tools (`gum`, `vhs`)**: full TUI with animation timings; nothing renders faster than human reading speed.
  - **Homebrew `install`**: doesn't need pacing tricks because the actual `git clone` + `make install` work takes minutes — pacing is automatic.
  - **Anthropic `claude install`**: clean, but does pause for input at decision points.
**Three patterns to lift, in order of impact:**
  1. **Explicit "Press Enter to continue" gates between major sections.** Highest leverage. Converts a firehose into a conversation. Place between: pre-flight summary → consent gate; consent → runtime install; auth choice → publishing-host signup; publishing-host → workspace creation; final summary → "want to start now?" (B9.2). Adds 4-5 keypresses to the install. For a 10+ min install, that's worth it for the sense of agency.
  2. **Forced minimum display time per sub-step.** Add a `say_paced()` helper that wraps `say` with `sleep 0.4`. So the 4 pre-flight checks take ~1.6s instead of <1s. Gives the eye time to land on each line.
  3. **Real spinner during actual install work.** Once steps 2-4 of the installer become real (Homebrew + Python + Claude Code installs), use a unicode spinner (`spinner='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'`) with the task label. The spinner runs for the duration of the actual work; min display 500ms.
**Implementation sketch:**
```bash
# Helper: paced print
say_paced() { say "$@"; sleep 0.4; }

# Helper: gate
pause_for_user() {
  printf '\n'
  read -r -p "$(printf '%sPress Enter to continue%s ' "$DIM" "$RESET")" _
}

# Helper: spinner during long-running command
spin() {
  local label="$1"; shift
  local pid frame=0
  local frames=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
  "$@" >/dev/null 2>&1 &
  pid=$!
  while kill -0 $pid 2>/dev/null; do
    printf '\r  %s %s' "${frames[$((frame % 10))]}" "$label"
    frame=$((frame + 1))
    sleep 0.08
  done
  wait $pid; local rc=$?
  printf '\r  %s%s%s %s\n' "$GREEN" "✓" "$RESET" "$label"
  return $rc
}
```
**Trade-off:** the explicit gates add 4-5 keypresses. For non-technical users this is a clear win. Add `--auto` flag for technical users / CI / Rafa's own re-runs that skips the gates. Pacing the output (sleeps, spinners) costs ~3-5 seconds total per install — negligible against a 10+ min install.
**Mirror in `Welcome.ps1`** — PowerShell has `Write-Progress` for spinners and `Read-Host` for gates; same patterns translate cleanly.

### B9.4 — Re-evaluate the `START-HERE` shortcut as the primary re-entry method · ✅ **DONE** (commit 6ec981d, B9.10)
**Status:** START-HERE removed entirely. Re-entry is `claude` from any Terminal — no Desktop artifact. refresh.sh defaults PYTHON to the workspace venv so the pipeline runs from any cwd. API-key auth users get an idempotent `export ANTHROPIC_API_KEY=…` block in their shell rc.
**Found by:** B9.2 follow-on thinking.
**Question:** If B9.2 lets the user go straight from install to first run without ever touching the Desktop, do we still need the Desktop shortcut at all? Or is there a better re-entry pattern for sessions 2+?
**Alternatives to investigate:**
  - **CLI command**: `passport-clarity` or `pclarity` on PATH — like `gh`, `stripe`, `vercel`. Works for the technical-curious 5%; doesn't help the 95% non-technical audience.
  - **Menu bar app** (Mac) / **system tray** (Windows): always-visible, one click to open. Adds significant install complexity (needs a real signed `.app`).
  - **Dock pin**: same as Desktop shortcut, slightly less visible-on-boot but more discoverable than the Desktop for users who keep a clean Desktop.
  - **Status quo Desktop shortcut**: lowest-tech, most visible, requires zero packaging work. Not glamorous but works.
**Recommendation:** keep the Desktop shortcut for v1 (it works, costs nothing). Promote it from "the only way to start" to "the re-entry shortcut after the first run." Revisit when v1 ships if a real signed app is on the table.

### B9.5 — Pipeline operations need ongoing-progress signals (FX fetch is the worst offender) · ✅ **DONE** (commit 72ded60)
**Status:** `progress()` helper added to `skill/scripts/_lib.py` (TTY-guarded, writes to stderr). FX prewarm in install.sh redirects stderr to /dev/tty so the bar reaches the user during install. Issue C in the original quick-wins commit.
**Found by:** dry-run user-interview phase. "Output felt like it got stuck when it was fetching the exchange rate."
**Symptom (the surface complaint):** During step 4/7 of the pipeline, the user sees:
```
▸ 4/7 Fetching exchange rates for 2025-01-01 → 2025-12-31
                                                                    ← long silent gap (~30-60s)
FX cache warmed: 261 fetched, 0 already cached, 0 failed
```
~261 sequential HTTP requests to Frankfurter, no intermediate output, no signal of life. Looks frozen.
**The deeper need (what user-interview surfaced):** This is the **same principle as B9.3** (the user wants to feel like the pilot, not the passenger) but on the Python skill side, not the bash installer side. The previous fix targets the installer; this one targets the pipeline scripts.
**Where this hurts in the current skill:**
  - **`fx_fetch.py`** — the worst case. Hundreds of HTTP requests, single line at start, single line at end, nothing in between. ← bit the user.
  - **`build_site.py`** — silent until "✓ Site built". Asset copies (Inter font woff2 × 4, Chart.js bundle, brand assets, downloads) could lag for a half-second; user sees nothing.
  - **`publish.sh`** — already has stepped output (▸ Setting passcode → ✓ passwordProtected → etc), pacing is fine.
  - **`categorize.py`, `normalize.py`, `dedupe.py`, `classify.py`, `sanity.py`** — all print summaries at the end. Fast enough on demo data that users don't notice silence. Could become a problem at 10× scale.
**How best-in-class Python CLI tools handle this:**
  - **`tqdm`**: industry standard for batch-progress bars. Wrap any iterable: `for d in tqdm(dates, desc="FX rates")`. Free progress bar, ETA, rate. ~50 KB dep.
  - **`rich`** (library): full TUI with `Progress`, `Spinner`, `Status`, `Live`. Beautiful but ~10 MB transitive dep — heavy for our needs.
  - **`click` + `click-spinner`**: simple integration if we used click for CLI parsing. We don't.
  - **Stdlib-only**: `sys.stderr.write("\r" + msg); flush()` to update one line in place. No deps, ~30 lines for a reusable helper. Less polished than tqdm but works fine for a non-technical audience that just wants to see something moving.
**Recommendation: stdlib helper, not a new dep.**
Add to `skill/scripts/_lib.py`:
```python
def progress(label: str, current: int, total: int, width: int = 24) -> None:
    """Print a single-line progress bar that updates in place. Goes to
    stderr (non-disruptive to JSON-on-stdout consumers). Newline auto-printed
    when current >= total so subsequent output appears below."""
    pct = current * 100 // total if total else 0
    filled = width * current // total if total else 0
    bar = "█" * filled + "·" * (width - filled)
    sys.stderr.write(f"\r  {label}: {bar} {current:>4}/{total} ({pct:>3}%)")
    sys.stderr.flush()
    if current >= total:
        sys.stderr.write("\n")
```
Then in `fx_fetch.py:warm_cache()`:
```python
from _lib import progress
total = sum(1 for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5)
done = 0
# ...inside the loop, after each business-day iteration...
done += 1
progress("FX rates", done, total)
```
Same pattern in `build_site.py` for the asset copy loop. Skip `categorize`/`normalize`/etc. for now — they're fast enough on demo data; revisit at scale.
**Trade-off:** None worth speaking of. Stdlib-only, no dep weight, ~30 lines added across the skill, pure UX improvement. Could later upgrade to `tqdm` if we want polish (single-line change at each call site).
**Bonus:** the `progress()` helper writes to stderr, which means our `--json` output paths (used by tests) keep emitting clean JSON to stdout. Tests don't break.

### B9.6 — Suppress `DeprecationWarning` noise in user-facing pipeline output · ✅ **DONE** (commit 72ded60)
**Status:** Replaced `datetime.utcnow()` with `datetime.now(timezone.utc)` in `fx_fetch.py` and `sanity.py`. No more deprecation noise mid-pipeline.
**Found by:** dry-run user-interview phase. The output during the FX fetch included this:
```
/path/to/skill/scripts/fx_fetch.py:99: DeprecationWarning: datetime.datetime.utcnow() is
deprecated and scheduled for removal in a future version. Use timezone-aware objects ...
```
**Symptom:** Non-technical users may read "DeprecationWarning" as an error or a bug — undermines confidence in the tool.
**Root cause:** Two places use `datetime.utcnow()` (deprecated in Python 3.12+, hard error in some future Python). `fx_fetch.py:99` and `sanity.py:152`.
**Fix (preferred — addresses the warning at source):** Replace with `datetime.now(timezone.utc)`. One-line edit per occurrence; no behavior change. Already imported `timezone` in `_lib.py`; trivial to do same in the two scripts.
**Fallback fix (suppress, don't address):** Add `import warnings; warnings.filterwarnings("ignore", category=DeprecationWarning)` at the top of pipeline scripts. Hides the noise but masks future deprecations too. Not recommended.
**Recommendation:** preferred fix. ~3 lines changed total. Run regression suite after.

### B9.7 — Replace publishing-host signup with the in-agent email-code flow · ✅ **DONE** (commits 925ecea, 3cb16bf)
**Status:** Email-code flow shipped. Then moved out of the installer entirely (commit 3cb16bf) — local-first means most users never see this. The flow now lives in `skill/scripts/publish.sh` and runs only on first share. Uses `POST /api/auth/agent/request-code` + `/verify-code` — two user actions instead of six.
**Found by:** dry-run + investigation when the user reported the broken `here.now/signup` URL.
**Surface complaint:** "the page https://here.now/signup doesn't exist... so user gets blocked."
**Immediate fix (already shipped):** point at the homepage `https://here.now/` instead and walk the user through clicking "Sign in" → email signup → API key copy → paste back. Works, but requires 6+ user actions and a context switch into the browser.
**Better path (this backlog item):** the here.now docs describe an **in-agent flow** at `POST /api/auth/agent/request-code` and `POST /api/auth/agent/verify-code` designed specifically for installer-style flows. Replaces 6 user actions with 2 (type your email, type the code from your inbox).
**Proposed flow in `Welcome.command` Step 4:**
```
Email address (we'll send you a one-time code): _____
  → POST /api/auth/agent/request-code  { "email": "..." }
  → "Check your inbox for a 6-character code (subject: 'here.now sign-in')"
  → block with read for the code:
Code from email: ______
  → POST /api/auth/agent/verify-code   { "email": "...", "code": "..." }
  → response includes the API key
  → save to ~/.herenow/credentials chmod 600
```
**Trade-off:** depends on the here.now in-agent endpoints staying stable. They're documented but new; could change shape. Mitigation: keep the manual paste flow as a fallback ("if the in-agent flow fails, paste your key here instead").
**Bonus:** completely closes OP-8 for the publishing-host concern — the user never sees the brand "here.now" in any clickable surface.
**Implementation:** ~50 lines in Welcome.command Step 4 + matching mirror in Welcome.ps1. New regression test asserting the email-code POST pattern is present.

### B9.8 — Migrate skill distribution from `git clone` to `npx skills add` · ✅ **DONE**
**Shipped together with the curl-pipe-bash bypass (B9.9). Both depended on the repo being public + on the `passporttowealth` GitHub org existing.**
**What changed:**
- `installer/install.sh` Step 2h now runs `npx -y skills add passporttowealth/passporttowealth --skill finance-clarity-build --agent claude-code -g -y` instead of `git clone $SKILL_REPO_URL`.
- All in-script `$SKILL_INSTALL_DIR/skill/...` paths flattened to `$SKILL_INSTALL_DIR/...` because npx-installed skills land with the SKILL.md at the top level (vs the git-clone path which dropped the entire repo as a working tree under `~/.claude/skills/finance-clarity-build/`).
- The `skill` CLI walks the repo for any `SKILL.md` and matches by the `name:` frontmatter field — so our existing `skill/SKILL.md` layout works without restructuring.
- `--agent claude-code -g -y` flags make the install non-interactive (without them, the CLI prompts for which agent platform to install to, which would hang in a piped-from-curl context).
**Spike findings (kept for the record):**
- `skills` is an npm package by vercel-labs. MIT-style open distribution. No registry account needed.
- `heredotnow/skill` is a **GitHub `owner/repo` shorthand**. The CLI clones the repo, walks for `SKILL.md`, installs them. No `package.json`, no npm publish, no proprietary backend.
- Updates: `npx skills update <name>` re-pulls from `main` (no semver discipline yet on our side — track if this becomes a problem).
- Privacy: public-repo only as a first-class flow. We made the repo public as part of the org migration.

### B9.10 — Egregore-style landing page + START-HERE removal + short-URL shim · ✅ **DONE**
**Found by:** user feedback — "no .command files is better for now... add a command on the website that does the same thing etc."
**What changed:**
- `installer/index.html` rewritten as a single-page product site in egregore.xyz aesthetic. Hero is the install command with copy button. Mac/Windows OS toggle. Navy/white minimalism with brand `#0F1E33` accent. No download buttons (curl-pipe is the only path the page advertises). No Gatekeeper instructions (curl-pipe never triggers it).
- `installer/install` (no extension) is a 2-line shim that exec-fetches the canonical `install.sh` from raw.githubusercontent.com. Mirrored into the here.now publish bundle so users can paste the short URL: `curl -fsSL https://passporttowealth.app/install | bash`. Single source of truth on GitHub.
- **START-HERE.command and `.skill-launcher.sh` removed entirely.** Re-entry is `claude` from any Terminal — no Desktop shortcut, no app icon, no other artifacts on the user's laptop besides `~/Documents/my-finances/`.
- `skill/scripts/refresh.sh` defaults `PYTHON` to `$WS/.venv/bin/python` so the pipeline runs from any cwd without venv activation.
- For API-key auth, install.sh appends an `export ANTHROPIC_API_KEY=…` block (with idempotent guards) to the user's shell rc — claude finds the key from any new Terminal.
- `install.sh` early `exec </dev/tty` fixes the curl-pipe-bash gotcha where `read` prompts auto-fire empty (because bash's stdin = the drained pipe). With this fix, the consent gate and option pickers actually receive user input under `curl ... | bash`.
- Diagnostic-failure handling simplified: warnings, not blockers. The skill catches real problems at runtime.
- Step 6 became Step 5 (5-step install: pre-flight, tools, Claude auth, workspace, diagnostics).
- README.md rewritten to match the landing page + new re-entry pattern.
- Spec §4.2 (installer behavior) and §4.5 (re-entry) rewritten. Greeting prompt no longer assumes a pre-opened Finder window.
- Demo script Phase 0 updated: paste the curl one-liner; Phase 1 walks through opening Claude from any Terminal.
- Advisor onboarding playbook updated: kickoff verifies the workspace folder + `claude` works, not the Desktop shortcut.

### B9.9 — Curl-pipe-bash install bypass + repo migration to `passporttowealth` org · ✅ **DONE**
**Shipped together with B9.8.**
**What changed:**
- Repo migrated from `rafaeldavid/passporttowealth` (private) → `passporttowealth/passporttowealth` (public). GitHub auto-redirects the old URL for ~6 months so anything inflight survives the move.
- New `installer/install.sh` is the canonical install path. Streamed via `curl -fsSL https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh | bash` — no file lands in `~/Downloads`, so macOS Gatekeeper never intervenes. Removes the #1 dry-run abandonment surface (Gatekeeper warning + right-click → Open dance).
- `installer/Welcome.command`, `Welcome.bat`, `Welcome.ps1` archived to `installer/legacy/` with an explanatory README. Kept (not deleted) as a fallback for users who genuinely won't open Terminal — sunset after 2-3 successful curl-path onboardings.
- All in-repo URL references updated (`cloudflare-worker/README.md`, `skill/templates/site/index.html`, `tests/test_pipeline.py`, `docs/feedback-channel.md`, `dev/github-repo-layout.md`, `dev/finance-clarity-build-spec.md`).
- New regression tests pin the npx-skills-add invocations + the absence of `git clone $SKILL_REPO_URL` in `install.sh`.
**Follow-up (still TODO):**
- Landing page (`installer/index.html`) needs the redesign to lead with the curl one-liner instead of download buttons (egregore-style; B9.10). ✅ done in B9.10.
- The Cloudflare Worker's GitHub PAT was scoped to `rafaeldavid/passporttowealth`. After the migration the PAT was rotated (a new fine-grained PAT scoped to `passporttowealth/passporttowealth`) and the Worker re-deployed. ⚠ The user pasted that new PAT in chat as part of the rotation — track-#63 to rotate it again.
- README.md still describes the old download-and-double-click flow; rewrite as part of B9.10. ✅ done.

### B9.11 — Brew-install Node.js so npx works on fresh Macs · ✅ **DONE** (commit b84af60)
**Surface complaint:** "Is it possible a user can't run `curl ... | bash` because of a missing dependency?"
**Root cause:** Apple doesn't ship Node. Steps 2g/2h of install.sh use `npx skills add` to fetch the here-now and finance-clarity-build skills. Without Node, the script dead-ended at "npx: command not found" before reaching workspace setup.
**Fix:** install.sh Step 2b's `NEED_BREW` gate now triggers on missing jq OR missing node. Step 2e brew-installs Node alongside jq with a "Installing Node.js (~10s, gives us npx for the next steps)" message. Step 5 diagnostic checks `command -v npx` to verify. Spec §4.2 dependency table updated to list Node as a required dep with conditional Homebrew install.
**Tests:** new `test_installer_brew_installs_node_for_npx`. Existing `test_installer_uses_uv_for_python_provisioning` updated for the dual jq+node NEED_BREW gating.

### B9.12 — Bulletproof TTY rebind + visible prompts + non-cancelling consent gate · ✅ **DONE** (commits dfff5e8, 544f749)
**Surface complaint:** "I still can't see the press enter to continue or similar text" after running the curl one-liner on a real Mac terminal.
**Root cause (compound):**
- `exec </dev/tty` early in install.sh could fail silently or succeed but then bash 3.2 (Apple's default) returned the pre-redirect TTY state from `[ -t 0 ]` later — pause_for_user's re-test wrongly skipped every pause.
- The consent gate's case-statement treated empty input as "cancel" (`"no"|"cancel"|"quit"|"stop"|""`), so when read returned empty (the rebind silently failed), the install exited saying "install cancelled" before the user understood what happened.
- Even when the rebind worked + `read -p` triggered, bash's `read -p PROMPT` writes to stderr with quirky flushing on some macOS terminals — the prompt could fail to render. Plus the prompt used DIM ANSI which is borderline-invisible against several Mac Terminal default themes.
**Fix (4 changes):**
1. Capture INTERACTIVE flag once at the top, after the rebind attempt. pause_for_user gates on $INTERACTIVE instead of re-testing `[ -t 0 ]`. Eliminates the bash 3.2 stale-test-result class of bug.
2. Log the rebind diagnostic (`tty_state: <state> interactive=<0|1> auto_mode_forced=<0|1>`) to install.log. Post-mortem support can see exactly which branch fired without a re-run.
3. Empty input no longer matches the cancel branch. Now falls through to a dedicated "I didn't catch any input" re-prompt. After 5 consecutive empties, bail with a clear support pointer (catches genuinely-broken TTY without infinite loop).
4. All visible prompts now print as standalone bold lines via `printf '%s▶ Prompt%s\n' "$BOLD" "$RESET"` then `read -r VAR` with no `-p`. Sidesteps the read-p flushing quirk and makes the prompt unmissable.
**Tests:** `test_installer_curl_pipe_safe` extended for the new INTERACTIVE flag pattern + diagnostic log. New `test_installer_consent_gate_does_not_silently_cancel_on_empty`.

### B9.13 — Landing page polish: gold accent, left-gutter section nav, working watermark · ✅ **DONE** (commit 9561bfe)
**Found by:** ongoing landing-page iteration with the user.
**What changed:**
- New `--color-gold` (#C9A75D) brand accent. Sprinkled at <10% visual weight: section number badges, active section-nav indicator, latest month bar in the dashboard preview chart, pill dot.
- Egregore-style left-gutter section nav. Sticky, appears once the hero scrolls out of view, IntersectionObserver tracks the section currently in view, smooth-scroll on click. Hidden below 1100px viewport.
- Watermark fix: previous regex stripping had broken the SVG XML (orphan `</path>` tag); re-fetched + re-stripped using xml.etree.ElementTree (proper parser). Country shapes now render correctly. Switched from mask-image to background-image with fill baked into the SVG root. Opacity tuned to 5% / 7% mobile per "less prominent" feedback.
- H1 polish: "Your crossborder finances, **the easy way.**" with line-break + "the easy way" in gold.
- Floating prototype pill now only appears when the header pill scrolls out of view (IntersectionObserver pattern).

### B9.14 — Landing page narrative: Have a conversation + Ask for new analysis sections · ✅ **DONE** (commit 671f9cf)
**Found by:** user feedback that the page narrative was missing the conversational layer + a forward-looking "more is coming" beat.
**What changed:**
- New section 02 "Have a conversation" between "Drop your files" and "See your numbers". Frames the plain-English Q&A interaction (ask about a charge, propose a recategorization, apply a rule going forward). Terminal mockup shows the round-trip pattern.
- New section 04 "Ask for new analysis" between "See your numbers" and "Share if you want". Marked **Coming soon** via a small gold-on-cream pill in the heading. Terminal mockup shows three calculator examples (FIRE, FX exposure, year-over-year category compare) — communicates breadth without overpromising.
- New `.coming-soon-chip` CSS class (reusable for any future Coming-soon sections).
- Section IDs renumbered (sec-01..sec-06). Section nav updated. Prototype-modal Privacy anchor moved to #sec-06.

### B9.20 — Lean two-branch model + Tier 1 CI gates + agent orientation doc · ✅ **DONE** (lean) / 📋 **DEFERRED** (full staging + transparency surfaces)
**Found by:** user follow-up to B9.19 — "given we need constant feedback but want stable product, enable branch protection and some sort of staging/versioning. One that is public (and works) and one that is in development/testing."

**The shape that fits this product:** unlike a SaaS app with one production URL, this product has five surfaces (landing page, install scripts, demo dashboard, Cloudflare Worker, the skill itself distributed via `npx skills add`). Each surface needs its own production/staging story. Full table in `CLAUDE.md` if needed. Off-the-shelf "preview deployment" patterns (Vercel etc.) don't map cleanly because the surfaces use different distribution channels.

**Lean version shipped now:**
- New `next` branch — development trunk. Push directly here; promote to `main` via PR after soak.
- Branch protection on `main` with **admin bypass** — required status checks gate normal PRs (CI, lint, security, OP-8, pages); repo owner can still push direct in an emergency.
- New `.github/workflows/lint.yml` — shellcheck on `install.sh`, `install` shim, `publish-landing.sh`, and `skill/scripts/*.sh`; PSScriptAnalyzer on `install.ps1`.
- New `.github/workflows/security.yml` — `pip-audit` (Python pipeline deps) + `npm audit` (Worker deps). Runs on PR + push + weekly cron. Answers tester-question "are these installations safe?" with public CI runs.
- New `.github/dependabot.yml` — weekly pip + npm + github-actions updates.
- `pages.yml` updated: now substitutes `{{BUILD_STAMP}}` (so the Pages backup mirror has the same stamp the canonical here.now publish gets) and refuses to deploy if `{{` placeholders survive in HTML. Also drops the stale `Welcome.command/.bat/.ps1` copies that haven't existed at the top of `installer/` since B9.10.
- New `CLAUDE.md` at repo root — agent orientation. Covers branching model, required CI gates, test scope, publishing surfaces, recent regression classes that must not return, and a where-to-find-what map. Claude Code reads it automatically; other agents read it manually. README updated to point at it.

**Deferred — review after the prototype phase (late May 2026):**

*Full staging (B9.20a):* per-surface staging environment.
- Separate here-now slug for landing-page staging (e.g. `passport-staging.here.now/`); CI publishes from `next` to staging slug, from `main` to prod slug.
- Cloudflare Worker `[env.staging]` block in `wrangler.toml` with separate KV namespace (`wrangler kv:namespace create FCB_METRICS_STAGING`); CI deploys from `next` → staging Worker, `main` → prod Worker.
- `?channel=next` query param on the install shim → routes testers to `install.sh` from `next` branch instead of `main`. Lets specific testers opt into bleeding edge.
- `staging-publish.yml` workflow on push to `next`; `prod-publish.yml` workflow on merge to `main` (also tags `vX.Y.Z` from CHANGELOG).
- ~4-6 hours of work; ~95% of value vs lean's ~70%. Not warranted at 5-10 testers; revisit at ~20+ or after a regression that lean version would have missed.

*Transparency / safety surfaces (B9.20b — open questions, see "User asked about" below):*
- Public `/docs/security` or `/docs/install-explained` page, auto-generated from `install.sh` + `install.ps1`. Lists every package, every URL fetched, every system permission required, in plain English. Doesn't drift because it regenerates from source. Linked from landing-page footer + included in tester onboarding emails.
- `passporttowealth.app/llms.txt` — agent-discoverable index of canonical sources (install command, demo dashboard, security page, skill spec). Per Jeremy Howard / Answer.ai's emerging convention.
- Both deferred pending user approval of scope (open question raised in same session).

**User asked about (deferred to next decision):**
1. Automated security review beyond pip-audit + shellcheck — could add SBOM generation (CycloneDX), Sigstore/cosign signing, or a public SLSA provenance claim. Each is 4-8 hours. Diminishing returns at this scale.
2. The `/docs/security` page above.
3. The `llms.txt` above.

### B9.19 — Prototype-phase test scope cut + deferred CI roadmap · ✅ **DONE** (cut) / 📋 **PARTIAL** (CI roadmap deferred)
**Found by:** user request — multi-agent assessment of "are these tests useful or fake or slop?", followed by scoping to "5-10 tester clients over the next 2 weeks; iterate fast, minimize impact on new customers, defer the rest until end-of-month."
**The diagnosis (from two parallel audits):** the 69-test suite was ~38% behavioral / ~49% source-grep / ~10% snapshot / ~3% slop. The behavioral tests pulled real weight; the source-grep tests were useful as living documentation but many pinned copy phrases or implementation details that paid maintenance cost without defending tester-impacting behavior. Critical structural blind spot: nothing exercised the publish/deploy paths (install.sh, install.ps1, publish-landing.sh, publish.sh, the Cloudflare Worker live). Every recent regression escaped through this gap.
**The cut (2026-05-03):**
- 69 → 39 tests (30 deletions + 3 consolidations whose load-bearing assertions were merged into surviving tests).
- Deleted: 2 slop (lib_importable, all_scripts_executable), 4 legacy bug classes (no-stub-markers, no-desktop-artifacts, no-auto-open-privacy-hub, legacy-installers-archived), 8 copy/UX/step-numbering pins (auth_choice_two_options, step5_diagnostic_runs_checks, ends_with_clear_reentry, has_pause_gates_and_auto_flag, traps_sigint_with_step_logging, diagnostic_failure_warns_does_not_block, pre_consent_block_is_paced, fx_prewarm_streams_progress_to_tty), 11 polish-era / impl-pinning (polish_p0_markers, no_scrollintoview, no_overflow_hidden, dashboard_data_includes_polish_fields, transactions_table_default_pagesize_10, feedback_widget_framed, feedback_widget_present, feedback_config_in_dashboard_data, insights_are_factual_not_advisory, inter_font_bundled, monthly_actuals_pivot_exists), 2 micro unit tests on tiny helpers (progress_helper_silent_when_not_tty, progress_helper_handles_zero_total).
- Consolidated: inbox-emptied check merged into routing test; curl-pipe-friendly assertions merged into curl_pipe_safe; python311 absolute-path check merged into uses_uv test.
- Kept everything that defends: pipeline data correctness (classify/dedupe/normalize/categorize/sanity), template placeholder-substitution, dashboard JSON schema, privacy footer honesty, CDN-free / chartjs-bundled, landing-page asset resolution, dashboard-demo bundle completeness, install.sh curl-pipe safety, consent-gate-doesn't-silently-cancel, install→publish flow continuity (view-local, refresh-invokes-view, publish-runs-email-code), telemetry (install_started ping + Worker schema), Windows installer parity (install.ps1 winget), recent regression classes.

**Why this is the right scope for the prototype phase:**
- Iteration speed > defense in depth. With 5-10 testers over 2 weeks, every failed test on a legitimate refactor costs PR cycle time and burns trust in the suite.
- Real defense comes from CI gates on the publish path (next phase), not unit tests on source-grep patterns.
- The cut suite still catches every recent regression class (verified — the brand-symlink, BUILD_STAMP, privacy-footer, dashboard-demo guards all survived).

**Deferred CI/CD roadmap — review late May 2026 after the prototype phase closes:**

*Tier 1 — minimum viable, ship before going wider than 10 testers:*
1. Pre-publish guard inside `pages.yml` — fail the workflow if `{{` survives in any HTML it's about to deploy. (One-line grep; mirrors what `installer/publish-landing.sh` already does locally.)
2. Shellcheck `installer/install.sh` in CI via `ludeeus/action-shellcheck@master`. Catches POSIX bugs, unquoted vars, non-portable constructs.
3. PSScriptAnalyzer on `installer/install.ps1` via PowerShell action. Same idea, Windows side, no Windows test box yet so static analysis is the only gate.
4. Branch protection on `main` — require `ci.yml` + `lint-user-strings.yml` + the two new lint jobs to pass before merge. Repo setting via `gh repo edit`.
5. Dependabot — `.github/dependabot.yml` for `pip` (Python deps) and `npm` (Worker / wrangler).

*Tier 2 — solid, ship before 1.0:*
6. `wrangler deploy --dry-run` on Worker PRs. Needs `CLOUDFLARE_API_TOKEN` repo secret. Catches schema/syntax errors before they reach prod.
7. Container smoke-test of `install.sh` in Ubuntu — `bash -x install.sh` with mocked stdin + network stubs, asserts script reaches end without exit-non-zero. Catches "doesn't even start" bugs.
8. HTML lint + relative-link check on `installer/index.html` (htmlhint + ~10-line Python link checker). Catches dead asset references before they reach prod.
9. Pre-commit hooks — local shellcheck + JSON validity + end-of-file-fixer via `pre-commit` framework. Stops devs from pushing things CI will reject.

*Tier 3 — luxury, defer past 1.0:*
10. Lighthouse CI on landing page (perf/SEO/a11y).
11. Live HTTP integration test against staged Worker (with isolated KV namespace).
12. Auto-generated CHANGELOG from commit messages (release-drafter).
13. Signed commits, OWASP Top-10 review.

**Verdict from the audits:** "Tests are not slop, but mis-scoped — they defended the source code's claims about itself, not the deployed artifacts users see. Every recent regression escaped through that gap. Tier 1 closes the gap cheaply." Re-evaluate after late May, when we know which classes of issue actually surfaced in the tester pilot vs. were predicted.

### B9.18 — Live public demo dashboard at /dashboard-demo + 3 supporting fixes · ✅ **DONE**
**Found by:** user request "add a link to view a dashboard example in the landing page under 'See your numbers' section, and link out to a demo dashboard without a passcode mounted via here.now at passporttowealth.app/dashboard-demo using the template simulation data."
**Why this exists:** Prospects need to see the actual output before committing to the install command. A static `<div class="dash-preview">` in the landing page is a sketch, not the real thing. A live mirror — built by the real pipeline against the synthetic demo-kit fixture — answers "what am I getting?" in one click.
**What changed:**
- New `installer/dashboard-demo/` (~530KB, 12 files, no symlinks). Built end-to-end by `refresh.sh --auto-confirm` against `demo-kit/data/*` (fully synthetic, deterministic random.seed(42)). Ships in the same publish bundle as the landing page → resolves at `https://passporttowealth.app/dashboard-demo/` automatically. No passcode (it's the marketing site by design).
- Two demo-only patches applied to the bundled copy:
  - Gold "Demo dashboard — synthetic data" banner right after `<body>` so visitors aren't confused.
  - Footer override (the per-client passcode framing doesn't apply to a public demo).
- Link added in section 03 of `installer/index.html` under the styled preview: "View the full live demo dashboard ↗", gold underline.
- Considered alternative: run `publish.sh` end-to-end → separate slug → metadata-PATCH the passcode off → here-now link API to map `/dashboard-demo`. Rejected — same dashboard files either way, much more state to babysit.

**Three fixes shipped in the same commit because they kept tripping each other:**
- **Fix #1 — privacy footer was misleading.** `skill/templates/site/index.html` claimed "the host never received your transactions, only the rendered numbers." Reality: `publish.sh` uploads the full `site/` directory which includes `downloads/transactions_tagged.csv` (every row) AND embeds the per-transaction list in `<script id="dashboard-data">` JSON. New copy is specific: source files stay local; categorized transactions and CSV exports DO get uploaded behind the passcode. Spec §16.1 updated to require this honest framing for any future template edits.
- **Fix #2 — `{{BUILD_STAMP}}` placeholder was rendering literally on the live page.** Was never wired up to a substitution mechanism. New `installer/publish-landing.sh` wrapper builds `installer/` to a temp dir, substitutes the stamp (UTC `yyyymmddHHMMSS`, same format as install-telemetry build_stamp), then publishes from temp. Source file keeps the placeholder — no per-publish git churn. **All future landing publishes must go through this wrapper, not the bare here-now skill.**
- **Fix #3 — `installer/dashboard-demo/downloads/*.csv` were blocked by the global `*.csv` gitignore.** Force-added; they're synthetic fixtures, the ignore rule is for real client data.

**Tests:** `test_dashboard_demo_bundle_complete` (banner + footer override + no symlinks anywhere) and `test_privacy_footer_is_honest_about_what_publishes` (old phrasing must not creep back; new phrasing must be present). 69 tests pass.

**Docs synced:** root `README.md`, `installer/README.md` (full refresh — was still describing Welcome.command flow), `dev/github-repo-layout.md`, `dev/demo-script.md`, `dev/finance-clarity-build-spec.md` §16.1, `CHANGELOG.md`.

### B9.17 — Install-start telemetry (anonymous, opt-out): Cloudflare Worker /install + KV counters · ✅ **DONE**
**Found by:** user question "is it possible to track number of installations? how do other software products manage this?" — investigated three layers, shipped Layer 1 (dashboards we already had) + Layer 2 (this), deferred Layer 3 (success/failure outcomes) to future work.
**Why this exists:** Without telemetry we can't tell the difference between "no one installed today" and "ten people installed but six quit at the consent gate." We need the install-start count to size the next problem.
**What changed:**
- New Cloudflare KV namespace `FCB_METRICS` (id `26eca96d62724b968eeefb17f7cd51e4`) bound in `cloudflare-worker/wrangler.toml`. 90-day TTL per key keeps it bounded.
- Worker rewritten to URL-route: `POST /` (existing feedback path), `POST /install` (new — anonymous telemetry), `GET /install/stats?days=N` (new — admin-gated read). Two new functions: `handleInstallEvent` (validates schema, sanitizes platform to mac/win/unknown, increments daily counter `installs:{platform}:{day}` in KV) and `handleInstallStats` (sums counters across N days, returns totals + by-day breakdown).
- Both installers POST after the consent gate, in background (so the install isn't blocked on telemetry network):
  - `install.sh`: backgrounded `curl ... &` with stderr → install log.
  - `install.ps1`: `Start-Job` so it runs in a background PowerShell job.
- Opt-out: set `FCB_NO_ANALYTICS=1` (mac) or `$env:FCB_NO_ANALYTICS = "1"` (win) before running.
- Disclosed in the Anthropic data-terms consent block on both sides — the same gate that already exists for the AI data-terms consent.
**Privacy guarantees (this is the whole point):**
- The Worker never reads `cf-connecting-ip` (the only IP-like header Cloudflare exposes). Verified by absence in source.
- The Worker never reads user-agent.
- `[observability]` is `enabled = false` in `wrangler.toml` so Cloudflare doesn't cache request bodies in its own logs.
- The body has exactly four fields: `v`, `event`, `platform`, `build_stamp`, `advisor_id`. No name. No machine ID. No file paths. No IP.
- KV stores integers only — `installs:mac:2026-05-02 = 7`. The advisor sees aggregate counts, not events.
**Tests:** `test_installer_posts_anonymous_install_started_ping` (both installers POST, both honor opt-out, both disclose, both background) + `test_worker_install_endpoint_validates_schema` (Worker routes correctly, validates schema, sanitizes platform, writes to KV with TTL, never reads IP/UA, admin gate on /install/stats). 66 tests pass.
**Verified live:** Worker deployed, all four cases tested with curl (good POST → 200 with key, bad schema → 400, wrong bearer → 401, GET with admin token → counts back). Test KV entries deleted after.
**Layer 3 (deferred):** outcome tracking — `install_succeeded` / `install_failed` with the `failed_step` label. Wait until we have ≥10 active clients so the failure modes are real, not theoretical. The Worker already routes to `/install`, so adding `/install/outcome` is additive when the time comes.

### B9.16 — Windows installer v0 (install.ps1) · ✅ **DONE**
**Found by:** task #60 (originally "Port real install logic + B9.7 email-code flow to Welcome.ps1") + user request to ship the first Windows-compatible install.
**What changed:**
- New `installer/install.ps1` — ~720 lines, parity with `install.sh`'s current shape (post-B9.10/B9.11/B9.12). Designed for `irm https://passporttowealth.app/install.ps1 | iex`.
- All UX patterns mirror the Mac side: Anthropic data-terms gate (OP-13), section-by-section pacing via `Pause-ForUser`, visible printf-style prompts via new `Read-VisiblePrompt` helper (Read-Host -Prompt has the same render-quirk as bash's read -p — same fix), Ctrl+C trap via `trap` block, install log to `%LOCALAPPDATA%\PassportToWealth\Logs\`, INTERACTIVE_DIAG state captured + logged.
- Tools provisioned via **winget** (Microsoft's official package manager, ships with Win 10 1809+): Node.js (`OpenJS.NodeJS.LTS`), uv (`astral-sh.uv`), jq (`jqlang.jq`). Claude Code via npm (`@anthropic-ai/claude-code` — Anthropic's distribution channel for non-Mac).
- Skills installed via the same `npx skills add ... --agent claude-code -g -y` invocations as the Mac side. The here-now and finance-clarity-build skills land at `%USERPROFILE%\.claude\skills\`.
- Workspace at `%USERPROFILE%\Documents\my-finances\`. Same canonical subfolders. FX prewarm runs through the workspace venv. Diagnostics pin tool presence + workspace shape.
- API-key auth: persists the key in two places — workspace `.env` AND a User-scope environment variable (`[Environment]::SetEnvironmentVariable($name, $val, "User")`). Mirrors the Mac shell-rc append pattern so `claude` finds the key from any new PowerShell window.
- Empty input at the consent gate doesn't silently cancel (mirrors B9.12). After 5 consecutive empties → bail with support pointer.
- Landing-page Windows tab updated: removed "coming soon" treatment, copy button enabled, command active.
**What's deferred to v1.1:**
- OneDrive sync detection + workspace relocation (Windows equivalent of Mac's iCloud check).
- Self-elevation if winget needs admin (winget usually runs without — defer until reported).
- WSL detection (the bash path would work better there; v0 assumes native PowerShell).
- End-to-end test on a real Windows box. Test coverage is structural only (`test_install_ps1_exists_with_winget_provisioning`); we ship-then-dry-run the first few clients.
- Legacy/Welcome.ps1 stays a stub. Curl/irm path is the canonical onboarding.
**Tests:** new `test_install_ps1_exists_with_winget_provisioning` — pins winget package IDs, UX-pattern presence, diagnostic checks, no [STUB] markers, end-message shape. 64 tests pass.

## Epic 6.5 — v2 hardening: zero-touch advisor onboarding (deferred from v1)

Items pulled out of `finance-clarity-build-spec.md` v1 to keep the first ship simple. Together they remove the one remaining moment of third-party-service exposure (the publishing-host signup during install) and let the advisor diagnose failures without the user having to email a support bundle.

### H6.5.1 — Per-client signed install links · **P2 · M**
**Problem:** v1 ships one generic `Welcome.command`. Every client signs up for the publishing host themselves during install, which violates the spirit of OP-8 (only justified in v1 by simplicity).
**Recommendation:** Replace the generic installer with a per-client signed link the advisor generates. The link embeds a single-use bootstrap token. Installer hits a handshake endpoint to fetch a scoped publishing-host credential. User never sees the service.

### H6.5.2 — `advisor-onboard` companion tool · **P2 · M**
**Problem:** No tool today for the advisor to provision a client.
**Recommendation:** Small advisor-only script (run from advisor's own Claude Code) that takes a client name + email, provisions a scoped credential under the advisor's publishing-host account, generates a one-time bootstrap token, builds the install URL, and optionally drafts the welcome email. Records the client in a local registry so the advisor can later see who's onboarded, take a site down, or rotate a credential.

### H6.5.3 — Handshake endpoint · **P2 · M**
**Problem:** Bootstrap token has nothing to redeem against.
**Recommendation:** Small advisor-controlled HTTPS endpoint (initial implementation: a here.now-hosted serverless function). Accepts the token, returns scoped credentials + advisor identity, marks the token consumed. Dependency for H6.5.1 and H6.5.2.

### H6.5.4 — Auto-transmitted error envelopes + advisor inbox · **P2 · L**
**Problem:** v1 requires the user to say "I need help" before the advisor sees anything. Quiet failures stay invisible.
**Recommendation:** Same envelope schema (§17.2 of the spec) but POSTed to an advisor-controlled inbox endpoint on every failure. Queued retry on transmission failure so the user is never blocked. Browseable per-client log on the advisor side. Closes acceptance criteria #6/#7 from the original spec.

### H6.5.5 — Heartbeats · **P2 · S**
**Problem:** Advisor can't distinguish a silent (broken / abandoned) client from a healthy one.
**Recommendation:** Once per successful run, post a `heartbeat` envelope. Disclosed in install consent. Disable-able by the user.

### H6.5.6 — Signed and notarized `Welcome.app` · **P2 · M**
**Problem:** Mac shows an unsigned-binary warning on `Welcome.command`, which can scare non-technical users into bailing.
**Recommendation:** Bundle the installer as a signed and notarized `.app`. Requires an Apple Developer account ($99/yr — confirm with Arielle whether her org or Rafa absorbs this).

### H6.5.7 — macOS Keychain for credential storage · **P2 · S**
**Problem:** v1 stores the publishing-host credential in `~/.herenow/credentials` with `chmod 600`. Fine, but Keychain is the OS-blessed path.
**Recommendation:** Move credentials to Keychain unconditionally. Read via `security find-generic-password`.

---

## Epic 6 — Recovery & operations

What does the user do when they break it.

### E6.1 — `delete-my-site.command` · **P0 · S**
**Problem:** No documented way to take the site down.
**Recommendation:** One command that calls `DELETE /api/v1/publish/:slug` and confirms. Critical for "I changed my mind" moments and for a clean demo reset.

### E6.2 — Passcode rotation · **P1 · S**
**Problem:** User shares passcode with the wrong person. No way to rotate.
**Recommendation:** `rotate-passcode.command` that prompts for a new passcode, PATCHes the metadata, and updates `.passcode`. Existing sessions invalidate automatically (per here.now docs).

### E6.3 — "Start over" reset · **P1 · S**
**Problem:** Bad categorization rules cascade. User wants to wipe and try again.
**Recommendation:** `reset-rules.command` that backs up `rules.yaml` to `rules.yaml.bak.{date}` and restores the starter set.

### E6.4 — Support handoff doc · **P1 · S**
**Problem:** When the user emails Rafa "it doesn't work," there's no diagnostic to attach.
**Recommendation:** A `support-bundle.command` that zips `install.log`, the output of `check.command` (B1.2), the contents of `pipeline/output/` (without raw transactions — just file names and counts), and uploads to a here.now URL Rafa can open. No PII leaves the laptop.

---

## Sequencing recommendation

**Before kickoff (week of May 4):**
- B1.1, B1.2, B1.4 — bootstrap installer + pre-flight + idempotency
- E5.1, E5.2, E5.3 — the three privacy hard rules
- E4.1, E4.2 — branded template + skill
- E2.1, E2.2, E2.5 — auto-sort, dedupe, sanity gate
- E3.1, E3.2 — single update command + inbox

**During sprint, before the May meeting:**
- E2.3, E2.4 — PDF support, normalization
- E3.3, E3.4 — slug recovery, rule starter set
- E4.3, E4.4, E4.6 — accessibility, chart guide, calculator slot
- E5.4, E5.5 — log audit, gitignore + sync warning
- E6.1, E6.2, E6.3, E6.4 — recovery commands

**Sprint 2 (post-May):**
- B1.3 — Windows/Linux installers
- E3.5 — diff view between refreshes
- E4.5 — print stylesheet
- E5.6 — public privacy footer
- H6.5.1 through H6.5.7 — full Epic 6.5 (zero-touch advisor onboarding + auto-telemetry)

---

## Two structural decisions to make this week

These don't fit as line items but block multiple items above:

1. **Build as a Claude skill or as a set of shell scripts?** A skill (`finance-clarity-build/`) bundles the template, the prompts, and the safety rules in one place that Claude auto-invokes. Shell scripts are more legible to the user but force the user to remember which command to run. **Recommendation: skill + a minimal set of shell entry points** (`install`, `start`, `refresh`, `delete`) so the user has 4 things to remember and Claude does the rest behind the scenes.

2. **Where does the template live?** If `site-template/` lives in the bootstrap installer, every install gets the same version — but updates require re-installing. If it lives in the skill, Claude can update it without re-installing. **Recommendation: skill owns the template**, installer just provisions Claude Code which loads the skill on first run.
