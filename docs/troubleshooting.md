# Troubleshooting playbook

> **⚠ Prototype.** Per-error-code playbook for the advisor. Read this against an incoming support bundle's error envelopes (`pipeline/output/errors/*.json`). Each entry below tells you what to say to the client, not just what the code means — `skill/references/ERROR_CODES.md` has the technical detail.

When a client says *"something's broken"* the skill produces a support bundle (spec §17.6) delivered three ways: as an email attachment, as a one-time password-protected URL, and as a saved zip on their Desktop. Each bundle contains one or more JSON error envelopes. Find the `code` field, look it up here.

---

## Quick triage flow

1. **Open the most recent envelope** in the support bundle (`pipeline/output/errors/{ts}-{code}.json`).
2. **Find `error.code`** — it's an `FCB-XXXX` value.
3. **Look up the code in this doc** (Cmd-F).
4. **Reply to the client** using the suggested phrasing under that code.
5. **If the code is one I don't recognize** — file a GitHub issue using the `bug` template; the catch-all rule below applies in the meantime.

---

## Pre-flight / install (FCB-0001 – FCB-0099)

These fire before any pipeline runs. The client never built a dashboard yet; they bounced off install.

### FCB-0001 — Unsupported macOS / Windows version

**What it means:** Their OS is too old (macOS < 13 or Windows build < 18362).

**What to say to the client:**
> "Your computer's operating system is older than what the installer needs. On Mac: open *System Settings → General → Software Update*; on Windows: *Settings → Windows Update*. Once you've updated, try the install link again. If your computer can't update that far, let me know — we'll find another way."

**Action:** None on your side; client-side OS upgrade.

---

### FCB-0002 — Insufficient disk space

**What it means:** Less than 5 GB free on their home volume.

**What to say to the client:**
> "Your computer's running low on disk space — I need at least 5 GB free for the workspace. The fastest cleanup is usually emptying *Downloads* and *Trash* on Mac, or *Recycle Bin* on Windows. Once you've got room, run the installer again — it'll pick up where it left off."

**Action:** None on your side.

---

### FCB-0003 — MDM-managed device

**What it means:** Their machine is enrolled in an organization's mobile-device-management (corporate / school / employer device).

**What to say to the client:**
> "Your computer is managed by an organization (looks like an employer or school). For privacy reasons the skill is personal-laptops-only in this version. Do you have a personal computer we could use instead?"

**Action:** None — by design. Help them find a personal machine.

---

### FCB-0004 — Anthropic auth failed

**What it means:** Either their API key is invalid, their Pro/Max session didn't authenticate, or there's a billing issue.

**What to say to the client:**
> "The AI assistant didn't accept the sign-in. Common causes: the API key was copied with a typo, your Claude subscription needs renewing, or your Anthropic account needs payment-method confirmation. Could you log in to https://www.anthropic.com/ and check that everything's active? Then run the installer again."

**Action:** Confirm with them which auth path they're on (Pro / Max / API key) before troubleshooting further.

---

### FCB-0010 — FX source unreachable (warning, not blocker)

**What it means:** The skill couldn't reach the exchange-rate service during install. Install continued anyway; FX cache will populate on first use instead of pre-warming.

**What to say to the client:**
> "Heads-up — your install couldn't pre-load exchange-rate data because of a network blip. It'll catch up the first time you build your report. No action needed."

**Action:** None unless this repeats — then check whether their network blocks `api.frankfurter.app`.

---

### FCB-0050..0099 — Bootstrap / install failures

Brew install failed, Xcode CLT install failed, dependency install failed, etc.

**Generic playbook:**
1. Ask them to send the install log (`~/Library/Logs/passport-to-wealth-install.log` on Mac; `%LOCALAPPDATA%\PassportToWealth\Logs\passport-to-wealth-install.log` on Windows).
2. Read the last 100 lines for the actual command that failed.
3. Most fixes: clean state and re-run (the installer is idempotent). For deeper Homebrew/Python problems, walk them through `brew doctor` (Mac) or `winget` reset (Windows) on a screen-share.

**What to say to the client:**
> "The install hit a snag with one of the tools it needs to set up. Could you send me the install log? It's at `{path}` — just attach it to a reply. I'll look at it and get back to you with the next step."

---

## Pipeline (FCB-0100 – FCB-0599)

These mean the client has a working install but the pipeline failed mid-run. Their data is fine — nothing was published or overwritten.

### FCB-0100..0199 — File classifier

**What it means:** Couldn't read or sort an input file.

**What to say to the client:**
> "I couldn't make sense of one of the files you dropped in — usually a corrupted PDF or an unusual format. Could you open the file yourself first to confirm it works, then drop it back in? If it's a bank statement that opens fine but the skill still chokes, send me the file name (NOT the file itself) and I'll add support for that format."

**Action:** If a specific bank format keeps failing, add a row to `skill/references/EDGE_CASES.md` and update `classify.py` accordingly.

---

### FCB-0150 — PDF parser hit a safety limit

**What it means:** A PDF took longer than 30 seconds or used more than 256 MB of memory to parse — either malformed or unusually large.

**What to say to the client:**
> "One of your PDFs is larger or more complex than I can safely process — usually means it's a scanned image (no text layer) rather than a real text PDF. Could you ask your bank for a CSV export of the same data? CSV is much more reliable than PDF for this."

**Action:** None unless they can't get CSV — then we look at OCR as an opt-in path (out of scope v1).

---

### FCB-0200..0299 — Deduper

**What it means:** Found overlapping date ranges across statements that need their judgement to merge.

**What to say to the client:**
> "I noticed you have two bank exports that cover overlapping months — I want to make sure I don't double-count those days. Could you tell me whether to (a) keep both files and dedupe row-by-row, (b) keep only the longer one, or (c) keep both as-is? Most people pick (a)."

**Action:** None.

---

### FCB-0300..0399 — Normalizer

**What it means:** Currency, sign convention, or date format detection failed for one of the input files.

**What to say to the client:**
> "I couldn't tell whether the {bank-name} file uses day-month or month-day dates (or which way the plus/minus signs work). Could you look at any one transaction in that file and tell me: (1) was it a charge or a deposit, (2) what date is the bank showing, and (3) is the amount listed as positive or negative?"

**Action:** Use the answer to manually pre-set the convention in the workspace's `normalize_report.yaml` if needed.

---

### FCB-0400..0499 — Categorizer / transfers

**What it means:** Either rule parse error in their `rules.yaml`, or transfer-pair detection ambiguity.

**What to say to the client:**
> "The categorization rules tripped on something. If you've edited `rules.yaml` recently, could you say 'reset my rules' to the assistant? That'll restore the starter set and we can rebuild from there. If you haven't edited it, send me the support bundle — it's a bug on my side."

**Action:** If user hasn't edited rules, look at the envelope `error.message` for the specific rule line.

---

### FCB-0500..0599 — Sanity gate

**What it means:** Either a hard floor tripped without acknowledgement or `sanity_confirmed.json` was rejected as stale.

**What to say to the client:**
> "The numbers I came up with don't pass the basic sanity checks I run before showing you anything. Most often this is because I missed a transfer between two of your accounts — could you walk me through your accounts so I can see what I should treat as transfers?"

**Action:** Read the envelope to see which floor tripped.

---

## Site builder + publisher (FCB-0600 – FCB-0799)

### FCB-0600..0699 — Site builder

**What it means:** Something went wrong populating the dashboard template.

**Most common cause:** brand assets missing or template slot mismatch.

**What to say to the client:**
> "I hit a snag building your dashboard page. This is usually a bug on my side rather than something with your data. Could you send me the support bundle? I'll fix it and ping you back."

**Action:** Investigate. If it's missing brand assets, see if `assets/brand/` was correctly synced from the repo.

---

### FCB-0700..0799 — Publisher

**What it means:** Something went wrong with the publishing-host (the service that hosts the dashboard URL).

**Critical sub-codes:**
- `FCB-0701` — placeholder publish failed (likely host outage or expired credentials).
- `FCB-0702` — passcode set on host but didn't take effect (host bug; rare).
- `FCB-0703` — verification request returned site content without auth — **rolled back, site deleted**. This is the publish-time race-condition guard (OP-2). Should never fire in production; if it does, treat as a security defect.
- `FCB-0704` — push of real content failed but placeholder remains.

**What to say to the client (FCB-0701, FCB-0704):**
> "The dashboard host had a hiccup. Want to try again in a few minutes? Just say 'publish' to the assistant. If it keeps failing I'll check the service status."

**What to say to the client (FCB-0702 / FCB-0703):**
> "Something unexpected happened on the host side. To be safe I rolled back what I'd uploaded. Don't worry — nothing was exposed. I'm looking into it now."

**Action (FCB-0703 specifically):** This is a security event. File an internal bug, mark P0, root-cause before any further client publishes.

---

## Refresh + recovery (FCB-0800 – FCB-0999)

### FCB-0800..0899 — Refresh failures

**What it means:** Same shape as FCB-01xx through 06xx but happened during an incremental refresh rather than a cold build. Slug + passcode preserved.

**What to say:** Same playbook as the corresponding cold-build code, plus: "Your existing dashboard is still up at the same URL — this only affected the new run."

---

### FCB-0900..0999 — Recovery flow failures

**What it means:** A recovery action (delete, rotate, reset, find, support-bundle, feedback) didn't complete.

**What to say:** Depends on which one. Generic: "The {action} didn't finish. Let's try it once more — if it still fails I'll do it from my side."

---

## Telemetry + FX (FCB-1000+)

### FCB-1000..1099 — Telemetry / envelope itself

**What it means:** The skill failed to write or transmit an error envelope. Highly meta — usually a disk-write or permissions issue.

**Action:** If you only see one of these in a bundle, you may be missing the originating error. Ask the client whether anything else seemed to go wrong around that time.

---

### FCB-1101 — FX rate unavailable for transaction date

**What it means:** No exchange-rate source had data within ±7 days of one of their transaction dates.

**What to say to the client:**
> "I couldn't find an exchange rate for {date}. Most likely your network was offline when I tried to fetch it. Are you online now? If yes, just say 'refresh' and I'll try again."

**Action:** If repeats, check whether their network blocks `api.frankfurter.app`.

---

### FCB-1102 — FX cache stale

**What it means:** Couldn't refresh today's snapshot rate during a refresh; using cached rates older than 7 days. Surfaced as a sanity-gate warning.

**What to say:** "Your rates are a bit out of date — totals on your dashboard may differ from current FX by a few percent. I'll catch up on the next refresh."

**Action:** None.

---

## Codes I don't recognize (catch-all)

If the envelope has a code not listed above:

1. **Reply to the client immediately** so they're not waiting:
   > "Got your support bundle. Looks like a new failure mode — let me dig in and get back to you within 24 hours. In the meantime your existing dashboard (if you have one) is still up at the same URL with the same passcode."
2. **File a GitHub issue** using `bug` template, attach the redacted envelope.
3. **Add a row to `skill/references/ERROR_CODES.md`** + a section here once you understand the cause.

---

## What you should NEVER do

- **Never ask the client to send you their actual data files** (CSVs, PDFs, etc.). The support bundle has everything you need; if it doesn't, fix the bundle, not the policy.
- **Never ask for the passcode.** It's locally generated and locally stored — you don't need it to help them, and asking would create a credential-handling habit we don't want.
- **Never advise the client to run shell commands you sent them.** If a fix needs that, do it on a screen-share where you can see what they're doing.
- **Never close a support thread without writing down what fixed it** — even one line in your own notes. Patterns emerge over the first 20 clients.
