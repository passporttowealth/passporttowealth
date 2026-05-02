# `finance-clarity-build` — Skill Specification

> **⚠ Prototype — pre-release.** This spec describes a v1 design under active construction. Sections may move, behaviors may change, and acceptance criteria evolve as the prototype is exercised against real client folders. Until v1.0.0 ships, treat as design intent, not a frozen contract.

Implementation spec for the skill that takes a non-technical user from a pile of unsorted financial files to a published, password-protected dashboard. This document is the source of truth for the skill's behavior. Companion docs: `demo-script.md` (user journey), `backlog.md` (delivery sequencing).

---

## 1. Purpose & scope

### 1.1 What it does

The skill provides a single, conversational interface that:

1. Ingests an arbitrary folder of financial files (CSV, XML, PDF, ZIP, mixed).
2. Sorts, dedupes, and normalizes them into a canonical structure.
3. Categorizes transactions with rule-based logic the user can correct.
4. Detects and excludes self-transfers so income/spend totals are accurate.
5. Builds a branded HTML dashboard from a locked template.
6. Publishes the dashboard to here.now behind a server-side passcode, with a publish flow that is safe by construction (never serves real content over an unprotected slug).
7. Supports an idempotent monthly refresh: drop new files, say "refresh," same URL, same passcode.

### 1.2 What it does not do

- Bank API integration (no Plaid, no Open Banking).
- Investment portfolio analytics (positions, performance, allocation).
- Tax computation. (Tax docs are read-only reference material.)
- Multi-user / multi-tenant. One workspace, one user, one site.
- Forecasting beyond the visual calculator slot (Phase 4.6 of the kickoff calculator pick).
- Anything that requires the data to leave the user's laptop, except the act of publishing the rendered site.

### 1.3 Audience

Non-technical end users running macOS, supported by an advisor (Arielle) who is also non-technical. Both interact with the skill in plain English. The only Terminal interaction is double-clicking `.command` files.

---

## 2. Operating principles (hard rules)

These are non-negotiable. The skill enforces them; they are not advisory.

| # | Rule | Enforcement |
|---|---|---|
| OP-1 | **Never read sensitive content without per-file consent. Enforcement is content-aware, not folder-based.** Before any file open, run a sensitivity check on filename **and** first-page text-layer keywords (`Brutto`, `Net Pay`, `Social Security`, `Steuer-ID`, `Tax Identification`, `Lohnsteuer`, `1099`, `W-2`, `Passport No`, etc.). If the file matches **or** lives in `02_payslips/` / `04_reference_docs/`, abort the read and ask the user — regardless of how it was classified. | Single `is_sensitive(path)` gate function. Every reader (classifier preview, normalizer, categorizer) calls it. Misclassification cannot route around it. |
| OP-2 | **Never publish real content to an unprotected slug.** Two-step publish (placeholder → password → real content) is the only allowed path. | Skill refuses to call the content-push step until a `passwordProtected: true` response is in hand for the target slug. |
| OP-3 | **Never put the passcode on a command line.** Read from interactive prompt or `--password-file`, never argv. | Skill refuses to accept `--password` flags. |
| OP-4 | **Never publish numbers the user hasn't confirmed.** Sanity gate is mandatory before site build. | Site builder refuses to run unless `pipeline/output/sanity_confirmed.json` is present and recent (≤ 1 hour old). |
| OP-5 | **Never silently overwrite user-edited files.** Anything in `rules.yaml`, `.passcode`, or `site/custom/` is treated as user property. | All writes to those paths back up first to `.bak.{timestamp}`. |
| OP-6 | **Never sync the workspace folder to a third-party cloud without explicit consent.** | Bootstrap detects iCloud-synced Desktop/Documents and prompts to relocate. Skill warns on every startup if the workspace is inside a synced root. |
| OP-7 | **Never include API keys, passcodes, or transaction descriptions in logs.** | Logger applies a redaction pass on every write. Patterns: account numbers (≥6 contiguous digits with optional hyphens), `.passcode` content, credentials file content. |
| OP-8 | **Minimize user exposure to third-party service names, credentials, and technical plumbing.** The agent owns every third-party interaction it can. **v1 exception:** the user signs in to Claude during install, and (only if they choose to share their dashboard) signs up with the publishing host on first publish via the in-agent email-code flow. Users who never share never sign up — the dashboard stays purely local. After signup, the user never sees the service name, the key, slugs, venv paths, or package names again. | User-facing strings outside the install + share dialogs reviewed against a banned-words list: `here.now`, `API key`, `credential`, `slug`, `Homebrew`, `Python`, `pip`, `venv`, `npx`, `OFX`, `webhook`. Permitted: "your site", "your passcode", "your folder", "your dashboard". The full "agent owns the publishing host signup with no user involvement" path is a v2 backlog item (per-client signed install links, scoped credentials, handshake endpoint). |
| OP-9 | **Never ask the user to invent secrets.** Passcodes, tokens, and any other secret material are generated by the skill, written to a local `.env` the user can read, and recited to the user once on creation. The user can rotate or replace them later, but the default path requires no thought. | Skill refuses any "choose a passcode" interaction. Passcodes are 4-word diceware (memorable, ~50 bits entropy) by default, with `random-alphanumeric-16` and `user-supplied` as opt-in alternatives surfaced only if the user objects. |
| OP-10 | **Every failure must be diagnosable from off-laptop.** The skill writes a structured error envelope (§17.2) for every error, redacted per OP-7, to a local errors folder. On a single user request ("something's broken"), the agent zips the envelopes into a support bundle and (a) uploads it to a fresh, password-protected publishing-host slug and (b) saves it to `~/Desktop/` as a fallback, then opens the user's mail client with URL + passcode pre-filled and copies the same to the clipboard. The user is never asked to interpret logs, run diagnostics, or take screenshots. **v2 backlog:** auto-transmission to an advisor-controlled error inbox. | Every `raise` and every non-zero exit path in the skill must produce an envelope before propagating. Linter check on PRs. |
| OP-11 | **Refuse to run in environments where the skill cannot uphold its own guarantees.** Pre-flight checks at install and on the first `claude` launch each session: managed-device (MDM) detection, free-disk minimum (5 GB), Mac architecture, network reachability for FX + publishing host, Claude Code authentication state, Anthropic subscription status (Pro/Max) **or** valid `ANTHROPIC_API_KEY`. Any failed check aborts with a plain-English explanation and the support bundle path. | Single `preflight()` function callable from installer + skill startup. Returns structured failures mapped to FCB-00xx codes. |
| OP-12 | **Hard sanity floors are non-negotiable.** Pipeline output must pass programmatic floors (savings rate within [-50%, +90%], month-over-month income variance < 100%, transfers < 40% of gross flow, uncategorized < 50%) before the user is even shown the sanity gate. Floor violations surface as "I'm worried about this" with the specific numbers, **before** the "does this look right?" question. | `sanity.py` runs floors first; gate UX changes if any floor trips. User cannot say "looks right" past a floor violation without explicitly acknowledging each one. |
| OP-13 | **Anthropic data-terms consent is required before any install action runs.** The installer presents a plain-English explanation of what Claude is, what data is sent to Anthropic during normal use, and links to Anthropic's privacy hub (`https://privacy.anthropic.com/`), privacy policy (`https://www.anthropic.com/legal/privacy`), consumer/commercial terms, and trust center (`https://trust.anthropic.com/`). The user must type explicit acceptance (`I accept` / `accept` / `agree` / `yes`) — anything else cancels the install with no side effects. Acceptance is logged with timestamp. | First gate in `install.sh`, before pre-flight (OP-11). Refusal exits cleanly with zero file-system writes outside `install.log`. The same consent message and link list are surfaced again as a one-time read-back when the skill first launches. |

Violating any of these is a skill defect. The skill should fail loudly rather than work around them.

---

## 3. System layout

### 3.1 On-disk structure

```
~/Documents/my-finances/
  inbox/                      ← User dumps anything here. Auto-emptied on each run.
  01_bank_transactions/       ← Sorted bank exports (CSV, XML, OFX, QIF, PDF text-layer).
  02_payslips/                ← Sorted payslips. SKIPPED by default (OP-1).
  03_amazon_orders/           ← Sorted Amazon order summaries.
  04_reference_docs/          ← Tax docs, identity docs. SKIPPED by default (OP-1).
  05_other/                   ← Anything that didn't classify cleanly.
  pipeline/
    output/
      transactions_raw.csv          ← One row per source-file row, pre-normalization.
      transactions_normalized.csv   ← After currency/sign/date normalization.
      transactions_tagged.csv       ← After categorization + transfer detection.
      monthly_actuals.csv           ← Pivot: month × category → amount.
      finance_summary.xlsx          ← Branded Excel summary.
        sanity_confirmed.json         ← Written after user confirms totals.
      run.log                       ← Redacted per OP-7.
      errors/                       ← One JSON envelope per error (§17.2). Cleared on successful next run.
  rules.yaml                  ← User-editable categorization rules.
  fx_cache/                   ← Skill-managed FX rate cache (daily ECB rates). Never edited by user.
  fx_overrides.yaml           ← Optional user overrides for specific dates/pairs. Empty by default; the user only touches it if they want to override the auto-sourced rate (rare).
  site/
    index.html                ← Published artifact root.
    assets/                   ← Inlined-or-bundled JS/CSS, fonts, logo.
    downloads/                ← CSV, XLSX, rules.yaml — bundled for download from site.
    custom/                   ← User overrides (CSS, copy). Never overwritten.
  .env                        ← chmod 600. Auto-generated by the skill (OP-9). Holds DASHBOARD_PASSCODE, SITE_URL, CLIENT_ID. The user can read it but never has to.
  .env.bak.{timestamp}        ← Rotation backups.
  .herenow/state.json         ← Slug + claim token. Skill-managed; not user-facing.
  install.log                 ← From bootstrap.
```

### 3.2 External dependencies

| Dependency | Where | Purpose | Required? |
|---|---|---|---|
| `uv` | `~/.local/bin/uv` (single binary, ~10 MB, installed via `curl -LsSf https://astral.sh/uv/install.sh | sh`) | Python toolchain — handles managed-Python install, venv creation, and dep resolution in one binary. Replaces the previous brew/python/venv/pip chain. | Yes |
| Python 3.11+ | `uv python install 3.11` (managed install in `~/.local/share/uv/python/`) | Pipeline runtime | Yes |
| `openpyxl`, `pdfplumber`, `pyyaml`, `chardet`, `reportlab` | venv inside `my-finances/.venv/`, populated via `uv pip install --python` | Pipeline libraries | Yes |
| Claude Code | per official installer | The CLI the user interacts with | Yes |
| `jq` | `brew install jq` (Homebrew is the only remaining brew dep — invoked lazily, only if jq is missing) | Required by `here-now` publish script | Yes |
| Homebrew | `/opt/homebrew` (Apple Silicon) or `/usr/local` (Intel) | Only needed to fetch jq if it's not already present. Skipped entirely if `command -v jq` succeeds. | Conditional |
| `here-now` skill | Auto-installed via `npx skills add heredotnow/skill --skill here-now -g` | Publishing | Yes |
| `~/.herenow/credentials` | `chmod 600` | here.now API key | Yes |

No CDN dependencies. No npm install at runtime. The site template's chart library and fonts are bundled at skill-install time.

---

## 4. Bootstrap installer (v1)

The user downloads one file from a link the advisor sends, double-clicks it, and the agent walks them through the rest in plain English. Two third-party touchpoints in v1: signing in to Claude (or pasting an Anthropic API key), and signing up for the publishing host. Both are walked through with browser-handoff and paste-back. Everything else — runtime, dependencies, FX cache, workspace layout — is provisioned silently.

### 4.0 Prerequisites the advisor confirms before sending the install link

These are the advisor's job (not the installer's job to fix). The advisor's pre-flight checklist:

1. **Mac running macOS 13 (Ventura) or later.** Apple Silicon or Intel both fine.
2. **At least 10 GB free disk space.** (Realistic install is 3–6 GB; 10 GB cushion absorbs the FX cache, the workspace, and a year of refreshes.)
3. **Personal laptop, not corporate-managed.** The skill detects MDM and refuses to install on managed devices in v1.
4. **One of:** an active Claude Pro subscription, an active Claude Max subscription, **or** an Anthropic API key with billing set up (for the API-key auth path).
5. **Comfortable installing things from a link the advisor sent.** If the client has malware paranoia, the advisor offers to drive the install live during the kickoff session.

### 4.1 Distribution

Source of truth: **GitHub — `github.com/passporttowealth/passporttowealth`** (public).

The repo holds the skill, the installer, the templates, and the docs. The user-facing artifacts (the things the client touches) are:

- `installer/install.sh` — the bootstrap script. Streamed via curl (no file lands on disk → no Gatekeeper). Source-of-truth at `https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh`.
- `installer/install.ps1` — Windows equivalent. Streamed via PowerShell `irm | iex`.
- `installer/index.html` — the product landing page deployed to here.now (slug `sandy-delta-dc3r`) and served at `https://passporttowealth.app/`. Hero is the curl one-liner with a copy button. Egregore-style minimalism; no download buttons (they were the Gatekeeper-trip surface).
- `installer/legacy/` — archived `Welcome.command`/`.bat`/`.ps1` for the small slice of clients who genuinely won't open Terminal. Sunset after a few clean curl-path onboardings.

The advisor shares: **`https://passporttowealth.app/`** (apex; `www.passporttowealth.app` 301s to it). The landing page lives at here.now slug `sandy-delta-dc3r` and is served at the apex via a here.now custom-domain link. Updates to the slug propagate globally in ≤60s.

The landing page shows:

- A copy-button install command (one for macOS using `curl ... | bash`; one for Windows using `irm ... | iex`). OS-detection auto-selects the right tab; the user can switch.
- A first-time-Terminal hint (`⌘+Space` → `Terminal` → `Enter`) right under the command.
- A "what this does" section, a "how it works" 3-card grid (local / opens-in-browser / sharing-is-opt-in), and a privacy block explaining why no third-party server is contacted by default.
- A footer link to the GitHub repo and a fallback pointer to `installer/legacy/` for users who can't use Terminal.

**No Gatekeeper instructions** are needed because curl-pipe-bash never lands a file on disk for the OS to gate. This was the v1's #1 abandonment surface.

#### 4.1.1 Why this split (here.now for the landing page, GitHub for the install script)

The landing page lives on here.now (`https://passporttowealth.app/`) because:

- Brand-friendly URL with no `github.io` subdomain leakage in client-facing comms.
- The here-now skill makes "publish a new copy" a one-liner; no GitHub Pages build wait.
- Survives if the GitHub repo is renamed/transferred.

The install script + skill code live in GitHub because:

- Versioned: every change is auditable in commit history.
- Curl can pull `install.sh` directly from `raw.githubusercontent.com` — the user reads exactly what they're about to run before pasting (`curl ... | less`).
- The skill self-update path (§18.1) reads from the same repo.
- The skill is fetched via `npx skills add passporttowealth/passporttowealth --skill finance-clarity-build` at install time (B9.8) — the same pattern used for the here-now skill.
- The advisor can fork or template the repo for other practices later without rebuilding distribution infra.

The repo is **public** so the curl one-liner (and `npx skills add`) can fetch without auth. No client data, no credentials, and no client-specific config live in the repo. Per-client config lives entirely on the client's laptop, populated at install time.

### 4.2 Installer behavior

When the client pastes the install one-liner (`curl -fsSL https://passporttowealth.app/install | bash`) into Terminal:

1. **Re-bind stdin to the controlling terminal.** With curl-pipe-bash, bash reads the script from the pipe and stdin is at EOF — `read` prompts would auto-fire empty. The first thing install.sh does is `exec </dev/tty` so consent gates and option pickers actually receive user input. If `/dev/tty` doesn't exist (CI, headless), AUTO_MODE is auto-enabled.
2. **Show the time estimate** based on Xcode CLT presence:
   - Xcode CLT already installed → "about 10 minutes."
   - Xcode CLT missing → "30 to 60 minutes (Mac needs to download some developer tools first)."
3. **Run pre-flight (OP-11)** before touching anything:
   - macOS version ≥ 13. Abort with FCB-0001 if not.
   - Free disk space ≥ 5 GB. Abort with FCB-0002 if not, with plain-English instruction to free space.
   - Mac architecture detected (Apple Silicon vs Intel; affects Homebrew prefix).
   - MDM detection (`profiles status -type enrollment`). If managed, abort with FCB-0003: "Your Mac is managed by your employer. This skill is for personal laptops. Talk to your advisor."
   - Network reachability for `api.frankfurter.app` and `here.now`.
4. **Show a plain-language progress log only.** No package names, no shell commands, no version strings. The user sees, e.g., "Installing the tools your dashboard needs… ✓".
5. **Provision the runtime** (technical steps hidden, each one logged to `install.log` for support):
   - Install Xcode Command Line Tools if absent (Mac shows its native consent dialog — unavoidable but Apple-native).
   - Install `uv` (Astral's Python toolchain) — replaces Homebrew + brew Python + venv + pip. One install, one toolchain.
   - Install `jq` (only if missing) via Homebrew — sole remaining brew dep.
   - Install the AI assistant CLI (Claude Code).
   - Install both companion skills via `npx skills add` — the publishing-host skill (`heredotnow/skill`) and `passporttowealth/passporttowealth` (this repo, with the `finance-clarity-build` skill).
6. **Authenticate the AI assistant** (§4.3) — the only third-party touchpoint required at install time. The publishing-host signup that used to live here has moved to `publish.sh` and runs on first share (see §4.4) — most installs never trigger it. For API-key auth: install.sh appends an `export ANTHROPIC_API_KEY=…` line to the user's shell rc (with idempotent guards) so `claude` picks it up from any new Terminal — replaces the role START-HERE used to play for that auth mode.
7. **Finalize:**
   - Write `~/Documents/my-finances/config.yaml` (advisor name, support email, primary currency, calculator choice — all defaulting if not configured).
   - Create the workspace folder and subfolders.
   - Pre-warm the FX cache: silently fetch the last 24 months of business-day exchange rates (§10.5.5).
   - Detect iCloud-synced Desktop/Documents (OP-6) and prompt: "Your Desktop syncs to iCloud. For your privacy, I'll put your finance folder somewhere that doesn't sync. OK?" If yes, relocate to `~/finance-workspace/` (outside any sync root).
   - **No Desktop shortcut, no app bundle, no other artifacts on the user's laptop.** Re-entry is `claude` from any Terminal — `refresh.sh` defaults `PYTHON` to `$WS/.venv/bin/python` so the pipeline runs correctly without venv activation.
8. **Verify** end-to-end with the diagnostic (§4.5) and report green. Failures are surfaced as warnings, not blockers — the skill itself catches real problems when the user runs it.
9. **Done message:** Three-line "what to do next" — open Terminal, type `claude`, ask for a report. The install Terminal session stays open (it's the user's own terminal — no auto-close that would yank away their other tabs).

### 4.3 Authenticating the AI assistant

The user has one of three auth modes (per §4.0). The installer asks once:

```
The AI assistant I use can sign you in three ways. Which do you have?

  1. Claude Pro (~$17/month) — sign in with your email
  2. Claude Max — sign in with your email
  3. An Anthropic API key — paste the key

(If you don't have any of these, stop now and call your advisor —
they'll get you set up. This step is the only one I can't do without you.)
```

#### 4.3.1 Pro / Max path
Installer launches `claude` once, which opens a browser tab to Anthropic OAuth. User signs in, browser redirects with success. Installer detects auth completion and continues. If the user closes the browser tab without completing, installer waits 5 minutes then prompts retry.

#### 4.3.2 API key path
Installer prompts: "Paste your Anthropic API key — it starts with `sk-ant-`. I'll save it locked so only you can read it."

The pasted key is written to two places: the workspace's `.env` (so the skill scripts can read it if needed), AND a guarded `export ANTHROPIC_API_KEY=…` block appended to the user's shell rc (`~/.zshrc` on modern macOS, `~/.bash_profile`/`~/.bashrc` for bash). Idempotent — re-running the installer strips the previous block before adding the new one. This way `claude` picks up the key from any new Terminal session without the user thinking about it. Verified with a test API call (`POST /v1/messages` with `max_tokens: 1`) before continuing. Failure → plain message "that key didn't work — paste it again, or check your Anthropic billing."

#### 4.3.3 Auth verified
Either way, before continuing, installer runs `claude --version` and a one-shot prompt to confirm the assistant responds. Failure → FCB-0004 with the support bundle path.

### 4.4 Publishing-host signup — deferred to first share (Strategic #2)

**The installer no longer signs up for the publishing host.** Many users only ever want their dashboard for themselves (local view, no sharing) — for them, the third-party signup is friction with no payoff. The signup has moved to `skill/scripts/publish.sh` and runs only when the user explicitly chooses to share their dashboard with an advisor or family member.

When `publish.sh` runs and `~/.herenow/credentials` is missing, the script:

1. Prompts for the user's email.
2. POSTs to `https://here.now/api/auth/agent/request-code` with that email — here.now sends a one-time code (`ABCD-2345` format).
3. Reads the code from the user.
4. POSTs to `https://here.now/api/auth/agent/verify-code` with `{email, code}`. Response includes `apiKey`.
5. Saves the key to `~/.herenow/credentials` with `chmod 600`.

Two user actions: type email, type code from inbox. Both happen in Terminal — no browser handoff. Manual paste (sign up via browser + paste key) stays available as an explicit fallback (`paste` at the code prompt) for when email delivery fails.

If the user never publishes, the credential file never gets created and they never sign up. The privacy story is strictly stronger: dashboards stay 100% local for users who don't share.

#### 4.4.1 Common failure modes the agent catches
- **User typed an email at the API key prompt** → "That looks like an email address. The key is a long random string."
- **User typed a URL** → "That looks like a web address. Find 'API Keys' on the page, not the URL bar."
- **Key rejected as invalid** → "The service says that key isn't recognized. Did you confirm your email?"
- **Code didn't verify** → "That code didn't verify. Try again, or type 'paste' to do it manually."

After signup, future publishes are silent — the credential persists.

### 4.5 Re-entry: `claude` from any Terminal

There is **no Desktop shortcut, no app bundle, no `.command` file** on the user's laptop. Re-entry is two steps:

1. Open Terminal (`⌘+Space` → type `Terminal` → Enter).
2. Type `claude` and hit Enter.

That's it. The `finance-clarity-build` skill is registered globally at `~/.claude/skills/finance-clarity-build/` and auto-loads inside Claude Code. The skill's pipeline scripts use `FCB_WORKSPACE` (default: `~/Documents/my-finances/`) so they find the workspace from any cwd. `refresh.sh` defaults `PYTHON` to `$WS/.venv/bin/python` so the venv doesn't need to be activated. For the API-key auth path, `ANTHROPIC_API_KEY` is exported from the user's shell rc by the installer — `claude` picks it up from any new Terminal session automatically.

Why no Desktop shortcut: a `.command` file cluttered the user's Desktop and surfaced a generic Terminal icon they didn't recognize. The "open Terminal, type claude" path is one extra step (open Terminal vs. double-click a Desktop icon) but ships zero artifacts. Trade made deliberately on the principle "no visible changes to the user's laptop."

The diagnostic (per OP-11) runs at the end of install. The skill itself surfaces health issues at runtime (e.g., "Claude Code can't reach the network" → support bundle path §17.6).

### 4.6 Cross-platform parity (Mac is reference; Windows is a parallel target)

The canonical installer is `installer/install.sh` (Bash, curl-pipe-bash). Windows mirror is `installer/install.ps1` (PowerShell, `irm | iex`). Same behavior contract; Windows port tracked separately as backlog item #60. Legacy double-click installers (`installer/legacy/Welcome.{command,bat,ps1}`) are kept as a fallback for users who can't open Terminal.

**Sync rule:** any user-facing string change in `install.sh` lands in `install.ps1` in the same PR. CI lint will eventually enforce this; for now it's a code-review check. Linux is out of scope until a real customer asks for it.

### 4.7 v2 hardenings (Sprint 2 — see backlog.md)

The following are intentionally out of scope for v1 to keep the install simple:

- **Per-client signed install links** + **advisor-onboarding tool** that provisions scoped credentials and a one-time bootstrap token, so the user never sees the publishing host even once.
- **Handshake endpoint** the installer calls to fetch credentials silently.
- **Auto-transmitted error envelopes** to an advisor-controlled error inbox (§17 v2).
- **Heartbeats** so silent clients are distinguishable from healthy ones.
- **Signed and notarized `Welcome.app`** + **signed Windows MSIX** so neither OS shows an unsigned-binary warning.
- **macOS Keychain** + **Windows Credential Manager** for credential storage instead of locked files.
- **Linux installer.**

---

## 5. The skill itself

### 5.1 Skill structure

```
finance-clarity-build/
  SKILL.md                    ← Frontmatter + behavior contract (this spec, condensed)
  config.yaml                 ← Per-client: advisor name, support email, calculator choice (no secrets)
  prompts/
    greeting.md               ← First-run greeting (§6.1)
    sanity_gate.md            ← Mandatory pre-build confirmation prompt
    refresh.md                ← Monthly refresh prompt
    user_facing_strings.md    ← Single source of truth for all user-visible language; OP-8 reviewed
  scripts/
    classify.py               ← File classifier (§7)
    dedupe.py                 ← Hash-based deduper (§8)
    normalize.py              ← Currency, sign, date normalizer (§9)
    fx_fetch.py               ← Auto-sources daily FX rates, manages cache, applies overrides (§10.5)
    categorize.py             ← Rule engine + transfer detector (§10)
    sanity.py                 ← Pre-build totals report (§11)
    build_site.py             ← Template populator (§12)
    publish.sh                ← Two-step publish wrapper around the publishing-host skill (§13)
    refresh.sh                ← End-to-end monthly update (§14.2)
    delete-site.sh            ← Recovery: take site down (§15)
    rotate-passcode.sh        ← Recovery: change passcode (§15)
    reset-rules.sh            ← Recovery: restore starter rules (§15)
    find-my-site.sh           ← Recovery: locate user's site after laptop change (§15)
    support-bundle.sh         ← Diagnostic upload, auto-sent to advisor (§17)
  templates/
    site/
      index.html              ← The locked dashboard template
      assets/
        app.css               ← Tokens + layout + components
        app.js                ← Chart wiring + filters + table sort
        chart.min.js          ← Bundled Chart.js (or uPlot, see §12.3)
        fonts/                ← Bundled woff2 (no Google Fonts)
        logo.svg              ← Passport to Wealth logo
    rules-starter.yaml        ← ~100-merchant EU/US starter rule set
  references/
    DESIGN_TOKENS.md          ← Color, type, spacing, motion tokens
    CALCULATOR_INTERFACE.md   ← Plug-in contract for the visual calculator slot
    EDGE_CASES.md             ← Bank-format quirks observed in the wild
```

### 5.2 Skill invocation

Auto-triggers on:

- First prompt after the user runs `claude` post-install (greeting flow).
- User mentions: "build my report", "refresh", "publish", "delete my site", "rotate passcode", "reset rules", "find my site", "fix my site", "something's wrong".

Does not trigger on: general finance questions, code questions unrelated to this workspace.

---

## 6. End-to-end workflows

### 6.1 Greeting (first run, empty inbox)

The greeting prompts the user to open a Finder window at the inbox if they haven't already (Spotlight: ⌘+Space → `my-finances` → Enter, or `open ~/Documents/my-finances/inbox` from the same Terminal). With START-HERE removed, the skill no longer relies on a pre-opened Finder window — the greeting tells the user where to drop files explicitly:

```
Hi — I'm here to turn your financial files into a private dashboard
only you can see.

I just opened a folder window for you called "inbox" (look for it
on your screen — it might be behind this Terminal). Drag your files
into it from anywhere on your computer:

  • Bank statements (CSVs, PDFs — whatever your bank gives you)
  • Paystubs (I won't read them unless you ask)
  • Tax documents (same)
  • Receipts, Amazon order history, anything else

Don't worry about sorting, deduplicating, or fixing anything first —
I'll do all that. When you're ready, come back here and say
"build my report".

A few things upfront:
  • Your files stay on this laptop. I only put a private web page
    online at the end, locked with a passcode I'll create for you.
  • I won't open paystubs or tax documents unless you tell me to.
  • If anything goes wrong, I'll tell you what to do — you don't
    need to know any of the technical bits.
```

If `inbox/` already has files: skip the greeting, jump to §6.2.

If the user types something other than "build my report" / "I'm done" / "go" — e.g., "what now?", "I'm confused", "help" — the agent re-explains in shorter form, with the option to "let me show you a 30-second video" (link to a hosted screen-recording, optional v1.x).

### 6.2 Build flow (cold start)

The user types one sentence at a time. Every other step is the agent. No service names, no file paths, no commands appear in user-facing text.

| Step | What the skill does | What the user sees |
|---|---|---|
| 1 | `classify.py` runs on `inbox/` | "I found 47 files. Sorting them now." |
| 2 | Sort report shown, ambiguous files listed | "I sorted 41 of them. Can you tell me what these 6 are?" |
| 3 | `dedupe.py` runs across sorted folders | "Three of these were saved twice — I kept one of each." |
| 4 | Privacy gate (OP-1) | "I see paystubs and tax docs. I'll skip them by default — your dashboard doesn't need to read them. OK?" |
| 5 | `normalize.py` runs, surfaces decisions | "Your German bank uses day/month dates and shows charges as positive numbers. Your US card does the opposite. I'll line them up — sound right?" |
| 6 | `categorize.py` runs | (silent unless new merchants) "I'm not sure how to categorize these 5 stores — what kind of place is each?" |
| 7 | `sanity.py` shows totals | Mandatory gate (OP-4). Awaits "looks right". |
| 8 | `build_site.py` populates template | "Your dashboard is ready — opening it in your browser now." |
| 9 | User reviews, light iteration | (rename category, hide calculator, swap charts) |
| 10 | User says "publish" → §13 | "I'll put it online behind a passcode I'll create for you. Saving everything now…" Then: "Done. Your dashboard is at `{url}`. Your passcode is `{4-word-passphrase}`. Both are also saved in a file called `.env` inside your finance folder, so you can always look them up — I'll remind you of them whenever you ask." |

### 6.3 Refresh flow (monthly)

Triggered by "refresh", "I added new files", "update my report".

1. `classify.py` on `inbox/` only (existing folders untouched).
2. `dedupe.py` across all folders (catches re-downloaded statements).
3. `normalize.py` on new files; existing normalized rows unchanged.
4. `categorize.py` incremental: only new rows scored. New uncategorized merchants surfaced for user input.
5. `sanity.py` shows month-over-month delta: "you added 47 transactions, totals through March now: ..."
6. After confirmation, `build_site.py` rebuilds.
7. `publish.sh` re-publishes to the existing slug with the existing passcode (read from `.passcode`).

The user types one sentence. Everything else is the skill.

### 6.4 Recovery flows

See §15. Each recovery action is a single user sentence or a `.command` double-click. None require the user to remember the slug, passcode, or folder layout.

---

## 7. File classifier (`classify.py`)

### 7.1 Inputs

Recursive walk of `inbox/`. Handles:
- ZIPs (auto-extract to a temp dir, classify contents).
- Nested folders (flattens for sorting; preserves source path in the report).
- Mac metadata files (`.DS_Store`, `__MACOSX/`) — skipped silently.

### 7.2 Classification heuristics

Order matters. First match wins.

| Bucket | Filename patterns | Content patterns (first-page text layer only, no OCR) |
|---|---|---|
| `01_bank_transactions/` | `*statement*`, `*activity*`, `*transactions*`, `*chase*`, `*deutsche*`, `*schwab*`, `*amex*`, `*.ofx`, `*.qif`, `*.qfx` | Header keywords: "Date", "Description", "Amount", "Balance", "Posting Date" |
| `02_payslips/` | `*payslip*`, `*paystub*`, `*payroll*`, `*VA_*`, `*SV_*`, `*LB_*`, `*Lohn*`, `*gehalt*` | "Gross Pay", "Net Pay", "YTD", "Brutto", "Netto", "Sozialversicherung" |
| `03_amazon_orders/` | `*amazon*`, `*order*summary*` | "Order Placed", "Shipping Address", "Order #" |
| `04_reference_docs/` | `*tax*`, `*1099*`, `*W2*`, `*W-2*`, `*SSN*`, `*passport*`, `*ID*`, `*Bescheinigung*`, `*Steuer*` | "Internal Revenue Service", "Finanzamt", "Tax ID" |
| `05_other/` | (fallback) | (fallback) |

### 7.3 Output

A proposed sort report:

```yaml
sorted:
  - file: Chase6055_Activity20250101_20260323.CSV
    bucket: 01_bank_transactions
    reason: filename matches *Activity*, content has "Date,Description,Amount" header
  - file: Rafael David Fernandez Valdes (1).pdf
    bucket: 02_payslips
    reason: filename matches Spanish-name pattern, first page has "Brutto"
ambiguous:
  - file: scan001.pdf
    reason: no filename pattern, first page text layer empty
duplicates:
  - kept: Chase6055_Activity20250101_20260323.CSV
    dropped: Chase6055_Activity20250101_20260323 (1).CSV
    reason: SHA-256 match
```

Surfaced to the user verbatim. Files only move after confirmation. Ambiguous files prompt one user question per file (or batch: "all of these are old utility bills — put them in 04_reference_docs").

### 7.4 Strict no-OCR rule

Classification reads PDF **text layers** only via `pdfplumber`. If text layer is empty, the file goes to `05_other/` with a note. OCR is a separate, opt-in path the user must explicitly request.

### 7.5 Sensitivity check (OP-1 enforcement)

Before any other reader touches a file, `is_sensitive(path)` runs on every file in every folder. The check uses both:

- **Filename patterns:** `*tax*`, `*1099*`, `*W2*`, `*W-2*`, `*SSN*`, `*passport*`, `*ID*`, `*identity*`, `*Steuer*`, `*Lohn*`, `*Bescheinigung*`, `*payslip*`, `*paystub*`.
- **First-page text-layer keywords** (PDFs only): `Brutto`, `Netto`, `Net Pay`, `Gross Pay`, `Social Security Number`, `Tax Identification`, `Steuer-ID`, `Internal Revenue Service`, `Finanzamt`, `1099`, `W-2`, `YTD Earnings`.

Any match → file is sensitive. The pipeline refuses to read it. The user is asked per-file (or per-batch) before any sensitive file is opened. Misclassification into `01_bank_transactions/` cannot bypass this — the gate runs on every read regardless of folder.

### 7.6 Disambiguation protocol for ambiguous files

When the classifier reports ambiguous files, the agent asks one **structured** question per file or batch — not free-form "what is this?". Structure:

```
This file:  scan001.pdf
What is it?
  (a) Money you spent or earned (bank transaction, receipt, statement)
  (b) Paystub, payroll, or income document — I'll skip reading it
  (c) Tax document — I'll skip reading it
  (d) Something else (I'll set it aside without reading it)
  (e) I don't know — set it aside

Type a, b, c, d, or e. (Or describe several files at once:
"a, b for files 2 and 3, e for the rest")
```

Free-text fallback only if the user objects to the structure ("can't I just tell you?"). If user says "I don't know" or "skip", file goes to `05_other/` with a deferred-classification flag. If the user says "I'll deal with it later" → flag and continue.

### 7.7 Account aliasing

For each unique account detected across bank files (by combining bank name + last-4 of any account number found), the agent asks during the first sanity gate (§11):

```
I see these accounts in your data. What would you like to call them
on your dashboard? (You don't have to use the bank's name or your
account number — pick whatever's clear to you.)

  1. Deutsche Bank, account ending 0916  →  [Joint Checking]
  2. Chase, card ending 6055             →  [Travel Card]
  3. Schwab, account ending 2378         →  [Brokerage]
```

Defaults shown in `[brackets]` come from the bank type (Joint, Travel Card, etc.). User can edit any. Aliases stored in `config.yaml`. Account numbers (even last-4) are **never** displayed on the published dashboard — only the alias.

---

## 8. Deduper (`dedupe.py`)

### 8.1 Algorithm

1. SHA-256 hash every file in the sorted folders.
2. Group by hash. Keep the file with the shortest path; move others to `inbox/.duplicates/`.
3. For CSVs: also run a content-level dedupe (parse, hash sorted rows). Catches statements re-exported with different filenames but identical data.
4. For overlapping date ranges (same account, same bank, partial row overlap): flag for user, do not auto-merge.

### 8.2 Output

```
Removed 3 exact duplicates. 1 partial overlap needs your call:

  Chase Statement Jan-Mar 2025.CSV (covers 2025-01-01 to 2025-03-31)
  Chase Statement Q1 2025.CSV       (covers 2025-01-15 to 2025-03-15)

  These overlap. Should I (a) keep both and dedupe row-by-row,
  (b) keep only the longer one, or (c) keep both as-is?
```

Default suggestion: (a). Behavior on user choice is recorded for next refresh.

---

## 9. Normalizer (`normalize.py`)

Produces `transactions_normalized.csv` with the canonical schema:

```
date           ISO 8601, YYYY-MM-DD
description    UTF-8 text, trimmed
amount         signed decimal, negative = money out
currency       ISO 4217 code (EUR, USD, ...)
account        stable identifier (e.g. "Deutsche Bank Joint", "Chase 6055")
source_file    relative path from workspace root
source_row     integer, 1-indexed
```

### 9.1 Per-file detection

For each source file, before parsing rows:

| Decision | Heuristic | Surfaced to user? |
|---|---|---|
| Currency | Account name keyword (Chase → USD, DB → EUR), or CSV column header (`Amount EUR`), or symbol prefix (`$`, `€`) | Only if ambiguous |
| Sign convention | Salary-shaped row (recurring, monthly, large positive) — if positive, debits-negative; if negative, debits-positive | Always |
| Date format | If any day field > 12 → DD/MM. If month field > 12 → MM/DD. Otherwise → ask user | Always when ambiguous |
| Encoding | `chardet`; if confidence < 0.8 → UTF-8 with replace, log warning | Never (handled silently) |

### 9.2 Output

The normalized CSV plus a `normalize_report.yaml` recording every per-file decision so refreshes are deterministic. User can edit the report to override decisions.

---

## 10. Categorization & transfer detection (`categorize.py`)

### 10.1 Rule engine

Rules live in `rules.yaml`:

```yaml
- match: "REWE|EDEKA|ALDI|LIDL|KAUFLAND|DM|ROSSMANN"
  type: regex
  category: Groceries
  subcategory: Supermarket

- match: "DB Vertrieb|Deutsche Bahn"
  type: regex
  category: Transport
  subcategory: Train

- match: "AMAZON"
  type: regex
  category: SPLIT_AMAZON       # special token, see §10.4
```

Rules apply in file order. First match wins. Unmatched rows → `Uncategorized`.

### 10.2 Starter rule set

Ship `templates/rules-starter.yaml` with ~100 EU + US merchant patterns derived from `finance_ops/custom-build/pipeline/categorize.py`. Categories:

```
Groceries, Restaurants, Transport, Travel, Housing, Utilities, Childcare,
Healthcare, Personal Care, Shopping, Subscriptions, Entertainment, Gifts,
Cash, Income, Tax, Investment, Insurance, Fees, Other
```

User-extensible. Adding a rule is one line in `rules.yaml`; refresh re-categorizes affected rows.

### 10.3 Transfer detection

Self-transfers (e.g. moving USD from Chase to Schwab) must not count as income or spend.

Algorithm:
1. For each negative row, look for a positive row in another account with the same FX-converted amount within ±3 days and ±2% FX tolerance.
2. Match → tag both as `Transfer`, exclude from category totals.
3. Surface unmatched single-side transfers for user review (often = real outflows the user forgot about).

### 10.4 Special tokens

| Token | Behavior |
|---|---|
| `SPLIT_AMAZON` | If `03_amazon_orders/` was parsed, allocate the row across categories using the proportions from parsed orders. Else: tag as `Shopping`. |
| `SPLIT_ATM` | Configurable split (default 70% household services, 30% misc). User edits split in `rules.yaml`. |
| `EXCLUDE` | Drop from all totals. Keep in raw data with the tag. Use for work reimbursements, etc. |

### 10.5 FX (auto-sourced, no user maintenance)

The skill sources its own exchange rates. The user never types a rate, never edits a YAML file, never cares which API was called. `fx_overrides.yaml` exists only as an escape hatch — the user can override a specific date+pair if they have a reason (e.g. they want to use a credit-card statement's actual conversion), but the default path requires no input.

#### 10.5.1 Source

Primary: **Frankfurter** (`api.frankfurter.app`) — wraps the European Central Bank reference rates, no API key, no rate limit for personal-scale use. Daily rates, business days only.

Fallback chain, in order:
1. Frankfurter direct.
2. ECB Statistical Data Warehouse XML (same data, different transport) — used if Frankfurter is unreachable.
3. `exchangerate.host` — broader pair coverage if a non-EUR-anchored pair is needed.
4. Local cache only — if all three are unreachable, use the most recent cached rate within ±7 days of the transaction date and tag the run with a "stale FX" warning visible at the sanity gate.

The skill does **not** fall back to a hardcoded rate. If no source has data within 7 days of a transaction date, the pipeline blocks at the sanity gate with FCB-1101 ("FX rate unavailable for `{date}` `{pair}`; advisor has been notified") and emits an envelope.

#### 10.5.2 Granularity: per-transaction daily rates

Conversion uses the **rate for the transaction's date**, not a monthly average. This matches what banks actually do and avoids end-of-month distortion.

Algorithm per transaction:
1. If `transaction.currency == reporting_currency`, no conversion.
2. Look up the rate in `fx_cache/{year}/{date}.json`.
3. If absent, fetch a window covering the transaction date and the surrounding ±5 business days; cache the whole window.
4. If the exact date is a non-business day (weekend/holiday), use the most recent prior business-day rate (consistent with ECB convention).
5. Apply: `amount_in_reporting = amount_in_native × rate(native → reporting, date)`.
6. Store both `amount` (native) and `amount_eur` (EUR equivalent) in `transactions_normalized.csv`. EUR is the canonical reporting currency; the dashboard can re-present in any other currency by applying a current snapshot rate (§10.5.4).

#### 10.5.3 Cache layout

```
fx_cache/
  meta.json                  ← Last fetch timestamp per pair, source used, schema version.
  2025/
    2025-01-02.json          ← One file per business day, all pairs in one file.
    2025-01-03.json
    ...
  2026/
    ...
```

Cache file shape:

```json
{
  "date": "2025-01-02",
  "base": "EUR",
  "rates": {"USD": 1.0432, "GBP": 0.8294, "CHF": 0.9311},
  "source": "frankfurter",
  "fetched_at": "2025-01-03T07:14:22Z"
}
```

Cache is append-only; old entries never invalidated. New pairs lazily added when first requested.

#### 10.5.4 Current-snapshot rate (for dashboard presentation)

The published dashboard supports a "show me in {currency}" toggle for the user's primary currencies. This uses the **latest available rate** (single snapshot, refreshed on each publish), not the per-transaction historical rates. The footer notes the snapshot date so the user knows totals are at-time-of-publish FX, not at-time-of-transaction.

Per-transaction historical conversion remains the source of truth for analytics; the snapshot is only for re-presentation.

#### 10.5.5 Refresh behavior

- **Bootstrap**: silently fetch the last 24 months of business-day rates for EUR↔USD (the most common cross-border pair). Adds ~3 KB × 250 days = ~750 KB to the install. Hidden from the user.
- **Each pipeline run**: fetch any missing dates in the cache that the current dataset needs. Almost always a tiny incremental fetch.
- **Each refresh (§14)**: also pull the most recent business-day rate so the snapshot toggle (§10.5.4) is current.
- **Offline / source-unreachable**: pipeline continues with cached data, marks the run with a "FX cache N days old" warning at the sanity gate, emits an FCB-1102 envelope so the advisor knows.

#### 10.5.6 Overrides (escape hatch only)

`fx_overrides.yaml` (empty by default):

```yaml
# Empty unless you have a reason to override the automatic rate.
# Format: date (or date range) + pair + rate. Highest precedence — wins over the cache.
# Example:
#   - date: 2025-03-15
#     from: USD
#     to: EUR
#     rate: 0.9234
#     reason: "matches my credit card statement"
```

Surfaced in user-facing flows only if the user mentions FX accuracy ("the conversion looks off", "I want to use my statement's rate"). The agent walks them through adding an override in conversation, then re-runs the pipeline.

#### 10.5.7 What the user sees

Nothing, in the normal case. If the sanity gate detects stale FX or an unavailable rate, the agent surfaces it in plain English: "I couldn't get an exchange rate for {date} from any of my sources. Using the closest one I have, from {n} days earlier. My advisor has been notified."

---

## 11. Sanity check (`sanity.py`)

Mandatory gate (OP-4) between pipeline and site build, with hard floors (OP-12) running before the user is even shown the gate.

### 11.0 Hard floors (run first; surface failures before the gate)

| Floor | Threshold | What surfaces if violated |
|---|---|---|
| Savings rate | within [-50%, +90%] of income | "Your savings rate looks like {x}%. That's unusual — usually means I miscounted transfers. Want me to investigate before we go on?" |
| MoM income variance | < 100% (excluding first/last partial months) | "Your income jumped {x}× between {month-a} and {month-b}. Often this means I misread a transfer as income. Want me to look?" |
| Transfers as % of gross flow | < 40% | "Almost half of what I see is transfers between your own accounts. I might be missing a real expense or counting one twice." |
| Uncategorized rows | < 50% of total | "Half your transactions don't have a category yet. Worth fixing the rules first — your dashboard will be more useful." |
| FX cache freshness | snapshot ≤ 7 days old | "I couldn't get fresh exchange rates today. Using rates from {n} days ago — your numbers might be slightly off." |

User cannot say "looks right" past a floor violation without typing "I understand the warning about {floor-name} and want to continue anyway." Each acknowledgement is logged in `sanity_confirmed.json` so the advisor can see what was waved through.

### 11.1 What it shows

```
=== Sanity check — please confirm before I build the site ===

Period covered: 2025-01-01 through 2026-03-31 (15 months)
Accounts: Deutsche Bank Joint, Chase 6055, Schwab Brokerage

Monthly totals (EUR equivalent):
  Income (avg/month):    €X,XXX
  Spend  (avg/month):    €X,XXX
  Net    (avg/month):    €X,XXX

Top 10 merchants by spend:
  1. {merchant}  €X,XXX  ({count} transactions)
  ...

Largest 5 single transactions:
  1. {date} {description}  €X,XXX  ({account})
  ...

Transfers excluded:    {count} ({total} EUR)
Uncategorized rows:    {count} ({pct}% of total)

Does this look right? (yes / no, what's wrong)
```

### 11.2 Behavior on "no"

User describes what's off in plain English. Skill investigates the specific item, reports back, offers a fix (add a transfer pair, add an exclusion, fix a category). Re-runs sanity. Loops until "yes".

### 11.3 On "yes"

Writes `pipeline/output/sanity_confirmed.json`:

```json
{
  "confirmed_at": "2026-05-01T14:32:00Z",
  "totals_hash": "sha256:...",
  "row_count": 3847
}
```

Site builder checks this file's `totals_hash` matches the current pipeline output and is < 1 hour old. If not, re-runs sanity.

---

## 12. Site builder (`build_site.py`)

### 12.1 Template-first, not generation

The skill **populates** `templates/site/index.html` — it never generates HTML from scratch. The template has named slots (`<div data-slot="kpi-cards">`, `<div data-slot="cashflow-chart">`, etc.). The builder fills slots with data; layout, brand, and components are fixed.

### 12.0 Primary currency

Primary (reporting) currency is set in `config.yaml` and asked at the first sanity gate if not yet set: "What currency do you want your dashboard to show totals in? (EUR, USD, GBP, …)". Default is the most-frequent currency observed across the user's accounts. All "EUR equivalent" language elsewhere in the spec applies to the user's chosen primary currency.

### 12.2 Brand & design tokens

Defined in `references/DESIGN_TOKENS.md`. Required tokens:

```
--color-bg, --color-surface, --color-text, --color-text-muted
--color-accent, --color-positive, --color-negative
--color-chart-1 through --color-chart-8
--font-display, --font-body, --font-mono (all bundled woff2)
--space-1..8 (4/8/12/16/24/32/48/64 px)
--radius-sm, --radius-md, --radius-lg
--shadow-sm, --shadow-md
```

Final values TBD with Arielle. Until confirmed, use a neutral default palette that meets WCAG AA.

### 12.3 Component library

| Component | Purpose | Notes |
|---|---|---|
| `KpiCard` | Top-of-page metrics (income, spend, net, savings rate) | 4-up on desktop, 2x2 on mobile |
| `CategoryBar` | Horizontal bar chart, spend by category | Horizontal because labels fit; sortable |
| `CashflowLine` | Monthly net, 15-month window | Two series: income (positive), spend (negative) |
| `TransactionTable` | Filterable, sortable, paginated | Defaults to last 90 days; filter by category, account, search |
| `DownloadsBlock` | Links to CSV, XLSX, rules.yaml, fx.yaml | Each with one-line description |
| `CalculatorSlot` | Plug-in slot per `references/CALCULATOR_INTERFACE.md` | Whichever calculator picked at kickoff. **Default if none picked yet:** placeholder card reading "Your advisor will turn this into your chosen visual tool." Site is publish-eligible without a picked calculator. |
| `PrivacyFooter` | One-line "what here.now sees" disclosure | Same wording for every site |

### 12.4 Chart library

Bundled `Chart.js` (latest LTS) inlined into `assets/chart.min.js`. No CDN reference. If site weight becomes an issue, swap to `uPlot` — same plug-in interface from the builder's perspective.

### 12.5 Accessibility & responsiveness baseline

- WCAG AA contrast on all text and interactive elements.
- 16px minimum body text.
- `<meta name="viewport">` present.
- `prefers-reduced-motion` respected (no chart entrance animation).
- All tables semantic (`<table><thead><tbody>`).
- Filters keyboard-navigable; focus rings visible.
- Lighthouse score ≥ 90 on Performance, Accessibility, Best Practices. Build fails below 90.

### 12.6 User customization (`site/custom/`)

User-writable folder. Two files honored:

```
site/custom/overrides.css     ← Loaded last, can override tokens
site/custom/copy.yaml         ← Override page title, KPI labels, footer text
```

Never overwritten by the builder. Survives every refresh.

### 12.7 Local view by default (`view-local.sh`)

After every successful build, `refresh.sh` invokes `view-local.sh`, which opens `$WS/site/index.html` in the user's default browser via a `file://` URL. No third-party server, no signup, no passcode — the dashboard lives only on the user's laptop and is gated by the OS lock screen.

This is the default first experience and the experience for users who never share. The publishing flow (§13) is opt-in and runs only when the user explicitly chooses to share their dashboard.

CI / scripted runs of `refresh.sh` can pass `--no-open` to skip the auto-open.

---

## 13. Publisher (`publish.sh`) — opt-in, only when sharing

Two-step flow that closes the publish-then-protect race (OP-2). All third-party calls are made by the skill using the credentials the bootstrap stored in the keychain. The user never sees the publishing host's name, the slug, the API endpoint, or the credential.

**Triggered only by an explicit user action** ("share my dashboard with X"). Local view (§12.7) is the default — most users never reach this section. On first publish, `publish.sh` runs the embedded email-code signup flow described in §4.4 to provision `~/.herenow/credentials`. Subsequent publishes are silent.

### 13.1 First publish

1. **Stage placeholder:** Generate `templates/placeholder/index.html` (single page: "This site is being prepared.") and call the publishing-host skill against it. Capture slug + claim token internally.
2. **Generate passcode (OP-9).** If `.env` already has a `DASHBOARD_PASSCODE`, reuse it. Otherwise generate a 4-word diceware passphrase from a vetted, phone-friendly wordlist (lowercase only, no special characters except hyphens, all words ≤ 6 chars to fit a phone keyboard without autocorrect drama, no homophone pairs). Example: `paper-orchid-stove-vine`. Write `DASHBOARD_PASSCODE`, `SITE_URL` (set after step 5), and `CLIENT_ID` to `.env` with `chmod 600`. Never echo the passcode to logs.
3. **Set passcode** on the host via the metadata-patch endpoint. Read the response.
4. **Verify** `passwordProtected: true` in the response. Abort if not.
5. **Push real content** to the now-protected slug. Update `.env` with `SITE_URL`.
6. **Verify** with a fresh, unauthenticated request that the response is the password challenge, not site content. Abort and roll back (delete site) if not.
7. **Report to user:** Recite the URL and passcode once, with explicit phone-access guidance:

   ```
   ✓ Your dashboard is live at:
       {url}

   ✓ Your passcode is:
       {paper-orchid-stove-vine}

   Both are saved in a file called .env in your finance folder.
   Ask me "what's my passcode?" any time and I'll read it back.

   ⚠ Save the passcode somewhere you can reach from your phone:
       • Your phone's password manager (1Password, iCloud Keychain,
         Bitwarden, etc.) — I'll wait if you want to do that now.
       • OR I can email both the URL and the passcode to your own
         email so you have them on every device.

   Type "save", "email", or "done".
   ```

   On `email`: agent uses `mailto:` with the user's own address (asked once, stored in `config.yaml`) pre-filled with subject "Your finance dashboard" and the URL + passcode in the body. Falls back to clipboard + Terminal print per §17.6.

8. **Scrollback hygiene:** After the user confirms they've saved the passcode, agent offers to clear Terminal scrollback (`printf '\033[2J\033[H'`) so the passcode doesn't sit visibly on the screen. If the user keeps saying "ask me later" three times, agent stops asking — they get the implication.

Slug, claim URL, and host credential are stored silently — not surfaced.

### 13.2 Refresh publish

1. Read `slug` from `.herenow/state.json`.
2. Read passcode from `.passcode`.
3. Verify the slug is still password-protected (HEAD request shape). If not, treat as first-publish path.
4. Push new content with `--slug {slug}`.
5. Spot-check that the re-published site is still gated.

### 13.3 Failure handling

| Failure | Behavior |
|---|---|
| API returns 5xx during placeholder publish | Retry 3x with backoff. Then abort, no site exists yet. |
| API returns 5xx during password set | Retry 3x. Then call delete-site on the placeholder. Abort. |
| `passwordProtected: true` not in PATCH response | Call delete-site on the placeholder. Abort with explicit error. |
| Real content push fails | Site stays as placeholder. Tell user to retry "publish". Slug is preserved. |
| Verification HEAD shows content without auth | Call delete-site immediately. Abort. Treat as defect, log full context. |

---

## 14. Refresh (`refresh.sh`)

### 14.1 Triggers

User says: "refresh", "I added new files", "update my report".

### 14.2 Steps

1. `classify.py` on `inbox/` only.
2. `dedupe.py` across all sorted folders.
3. `normalize.py` on new files; honor decisions in `normalize_report.yaml`.
4. `fx_fetch.py` incremental: fetch any FX dates the new transactions need + today's snapshot rate (§10.5.5). Silent unless a source is unreachable.
5. `categorize.py` incremental: score only rows missing a category. Surface new uncategorized merchants.
6. `sanity.py` with month-over-month deltas: "since last refresh on {date}, you added N transactions; new totals: ...". Includes a "FX cache N days old" warning if the snapshot fetch failed.
7. After confirmation: `build_site.py`.
8. `publish.sh` refresh path.

### 14.3 Idempotency

Running refresh twice with no new files is a no-op (no re-publish). The skill compares the content hash before pushing.

---

## 15. Recovery flows

Primary interaction is conversational. The user says one sentence; the agent does everything. The `.command` files exist as a fallback if the assistant won't start (e.g. catastrophic install corruption), but the user is never told about them upfront — they're surfaced only by support if needed.

| What the user says | What the agent does |
|---|---|
| "Take my site down" / "delete my dashboard" | Confirm in plain English ("This will remove the page at `{url}`. You'll keep the data on your laptop. Confirm?"). Call delete on the publishing host. Clear local state. Tell user it's done. |
| "Change my passcode" / "I shared my passcode by mistake" | Generate a new passcode (OP-9: same diceware default). Back up `.env` → `.env.bak.{timestamp}`. Update on the host, update locally. Tell user: "Done. Your new passcode is `{phrase}` — also saved in your `.env`. The old one no longer works." |
| "What's my passcode?" / "What's my dashboard URL?" | Read from `.env`. Recite. Remind the user they can open `.env` themselves at any time. |
| "Start my categories over" / "the categories are wrong" | Back up current rules. Restore the starter set. Re-run categorization. Re-run sanity gate. Rebuild + republish. |
| "I'm on a new laptop, where's my dashboard?" | Walk through reinstalling the workspace via a fresh install link from the advisor. Once running, locate the existing site under the advisor's account and re-link it to the new workspace. The user types nothing technical. |
| "Something's wrong, I need help" | Run support bundle (§17.6). Upload to a fresh password-protected site. Open user's mail client with URL + one-time passcode pre-filled to `{advisor-email}`. Tell user: "Review and send when ready." |
| "Show me what you've remembered about me" | Print a plain-language summary of what's stored locally (categories, rules, calculator choice, last refresh date). Offer to wipe individual items. |
| "Back up my workspace" / "save my settings" | Bundle `rules.yaml`, `fx_overrides.yaml`, `config.yaml`, `.env` into an encrypted zip (user supplies a one-time password the agent verifies). Save to `~/Desktop/finance-workspace-backup-{date}.zip`. Tell user to keep it somewhere safe (iCloud, Dropbox, USB). |
| "Restore from backup" / "I have my old workspace file" | Walk through unzipping with the password. Restore files. Re-link to the existing dashboard via the recovered slug. Run a refresh to validate. |
| "Share my dashboard with my accountant" / "send to my advisor" | Confirm recipient email. Open `mailto:` with the URL + passcode + a short cover note pre-filled. Also copies the same to the clipboard and prints in Terminal so the user can paste manually if their email client doesn't intercept `mailto:`. |
| "Start completely over" / "wipe everything" | Hard-confirm twice (this deletes local data and the published site). On second yes: delete the published site, clear local data folders, keep the install itself so the user can drop new files in fresh. |
| "I have feedback" / "I have a suggestion" / "this could be better" / "I love this" | Distinct from support bundle (which is for failures). Agent prompts for a free-text message, asks whether to attach optional anonymous context, then runs the **feedback flow** (§15.1). |

Underlying scripts (`delete-site.sh`, `rotate-passcode.sh`, `reset-rules.sh`, `find-my-site.sh`, `support-bundle.sh`, `redact-logs.sh`, `feedback.sh`) are skill internals, not user surface. They're invoked by the agent in response to the natural-language requests above.

### 15.1 Feedback flow

A first-class channel for non-bug input — suggestions, frustrations, "this is great", "I wish it did X". Different from the support bundle (which is reactive to a failure) and from the error envelope (which is a structured machine record). Feedback is human-to-human.

#### 15.1.1 What the user types

```
You:  "I have feedback"
Agent: "Tell me what's on your mind. I'll send it to your advisor.
        Anything from a one-line note to a longer message — whatever
        you want to say."

[user types message]

Agent: "Want me to attach any anonymous context? Either makes it
        easier for your advisor to act on:
          (a) just the message
          (b) message + skill version, OS, last refresh date
          (c) message + (b) + last sanity-gate summary
                       (only top-level totals, no transactions)
        Type a, b, or c."
```

#### 15.1.2 What's transmitted

The user's free-text message verbatim, plus any opted-in context. **Never** transmitted regardless of opt-in:
- Transaction descriptions, amounts, account numbers (even partial).
- File contents from any folder.
- The passcode, the publishing-host credential, the Anthropic API key (if any).
- Merchant names (only category labels, and only at level c).

Same OP-7 redaction whitelist as the error envelope (§17.2).

#### 15.1.3 Three-path delivery (mirrors §17.6 support-bundle)

Whatever the user opts into, the agent delivers via three parallel paths so no single failure traps them:

1. **Local save:** every feedback message saved to `~/Documents/my-finances/feedback/{timestamp}.txt`. Always works, requires nothing. Acts as the user's own audit log.
2. **Email via mailto:** opens default mail client pre-filled with subject `Finance Clarity feedback`, body containing the message + opted-in context, To: `{advisor-feedback-email}` from `config.yaml`.
3. **Optional HTTP POST** to `feedback_endpoint_url` in `config.yaml`, if set. The endpoint receives a JSON body and is expected to forward / file appropriately. The skill ships **no default endpoint** — the advisor configures one (recommended pattern: a Cloudflare Worker that creates a GitHub issue; recipe in `docs/feedback-channel.md`). If the field is unset, the skill skips this path silently.

The agent reports back:

> "Done. I saved your feedback locally, and I've also opened your email
> client with it ready to send. {if endpoint configured: 'I also sent it
> directly to your advisor.'} Click send when you're ready."

#### 15.1.4 POST schema (for `feedback_endpoint_url`)

```json
{
  "v": 1,
  "ts": "2026-05-08T14:32:00Z",
  "client_id": "stable-hash-no-pii",
  "advisor_id": "passporttowealth",
  "skill_version": "0.4.2",
  "platform": "macOS 14.5 (arm64)" or "Windows 11 (build 22631)",
  "message": "the user's verbatim message",
  "context_level": "a" | "b" | "c",
  "context": {
    "last_refresh_at": "2026-05-01T10:14:00Z",   // level b+
    "transactions_total": 3847,                  // level c only
    "categories_in_use": ["Groceries", ...],     // level c only, no merchants
    "currencies_seen": ["EUR", "USD"]            // level c only
  }
}
```

Bearer token: optional. If `feedback_endpoint_token` is set in `config.yaml`, included as `Authorization: Bearer {token}`. The token's purpose is preventing third-party abuse of the endpoint — not authenticating the user.

Endpoint failure (5xx, timeout, DNS) is non-blocking: the local save and mailto: paths still succeed, the user is told, and the next refresh retries the queued POSTs from `pipeline/output/feedback/_pending/`.

#### 15.1.5 Why a Cloudflare Worker is a natural fit (recommended)

The advisor doesn't want their GitHub credentials on every client laptop. A Cloudflare Worker — server-side, holds the credential as a Worker secret — accepts the POST and creates an issue via the GitHub REST API. Same Worker can fan out to email, Slack, Linear, etc. depending on how the advisor wants feedback to flow.

Step-by-step deploy recipe in [`docs/feedback-channel.md`](../../docs/feedback-channel.md). Keeps the implementation off the hot path of the v1 ship — zero clients are blocked if the Worker isn't deployed yet (mailto: still works).

#### 15.1.6 Out of scope

- In-app screenshots / annotated dashboards (Sprint 2).
- Voice / video feedback (no).
- Auto-detection of frustration ("you sighed in your prompts") — no.

---

## 16. Privacy guardrails (cross-cutting)

In addition to the seven hard rules in §2:

### 16.1 Default behaviors

- The pipeline runs against `01_bank_transactions/` only. `02_payslips/` and `04_reference_docs/` are untouched unless the user explicitly asks the skill to read a specific file from them, in which case the skill prompts per-file before opening.
- The published site shows aggregates and transactions. It does **not** show: full account numbers (always last-4), identity fields, payslip data, or tax data — even if those somehow ended up in `transactions_tagged.csv` (the builder strips them).
- The privacy footer on the site is mandatory and not user-removable. Wording fixed in the template.

### 16.2 What the user is told upfront

The greeting and the first sanity gate both include a one-liner about what stays local, what reaches here.now, and what the passcode does and doesn't protect. Plain English, no security jargon.

### 16.3 What we do not do

- No analytics on the site. No third-party scripts.
- No silent telemetry. Errors **are** auto-reported to the advisor (§17.2) so the user doesn't need to debug their own laptop, but the user is told this upfront at install time and shown the redacted payload on request. Routine activity (successful runs, file counts, category labels, transaction content) is **never** transmitted.
- No automatic backup to any cloud.
- No "share with us" anonymized data collection.

---

## 17. Diagnostics & support

The advisor must be able to diagnose ≥80% of failures from a support bundle the user emails them — without ever asking the client for screenshots, raw logs, or remote-access. In v1, transmission is user-triggered (one sentence, one email). v2 (§4.5, backlog) automates transmission to an advisor-controlled inbox.

### 17.1 Local logs

| File | Purpose | Redaction |
|---|---|---|
| `install.log` | Bootstrap output, every step. | OP-7 redaction on save (account-number patterns, secrets). |
| `pipeline/output/run.log` | Every pipeline run, structured (one JSON line per step). | OP-7 + merchant-name stripping for any line above DEBUG. |
| `pipeline/output/errors/{ts}-{code}.json` | One envelope per error (§17.2). | Pre-redacted at write time. |
| `.claude/` | AI assistant logs (third-party). | `redact-logs.sh` runs an OP-7 sweep on demand. |

Logs rotate at 5 MB. Last 5 generations kept. Older ones deleted, not archived.

### 17.2 Error envelope (local in v1, auto-transmitted in v2)

Every error path in the skill emits a structured envelope before propagating. In v1 the envelope is written to `pipeline/output/errors/` only. The user is told: "Something didn't work. Want me to put together a report for my advisor?" — on yes, the agent runs the support bundle path (§17.6) and uploads it to a fresh, password-protected publishing-host slug; the user emails the URL + one-time passcode to the advisor.

In v2 (backlog) the same envelope is also POSTed to an advisor-controlled inbox endpoint configured at install time, eliminating the "want me to send it?" turn.

Envelope schema (`v: 1`):

```json
{
  "v": 1,
  "ts": "2026-05-01T14:32:00Z",
  "client_id": "stable-hash-no-pii",
  "advisor_id": "passporttowealth",
  "skill_version": "0.4.2",
  "publish_skill_version": "1.8.3",
  "platform": "macOS 14.5 (arm64)",
  "runtime": "Python 3.11.5",
  "correlation_id": "uuid-for-this-session",
  "error": {
    "code": "FCB-0312",
    "category": "normalize",
    "step": "detect_sign_convention",
    "message": "no salary-shaped row found in {account_id}; cannot infer sign",
    "stack": "redacted-stack-trace",
    "user_visible_message": "I'm not sure how to read your German bank file. My advisor is looking into it."
  },
  "context": {
    "workflow": "build",
    "last_user_action_verb": "said: build my report",
    "file_counts": {"01_bank_transactions": 4, "02_payslips": 12, "03_amazon_orders": 0, "04_reference_docs": 3, "05_other": 1, "inbox": 0},
    "transaction_count_pre_error": 0,
    "categories_in_use": ["Groceries", "Transport", "Housing"],
    "rules_count": 117,
    "currencies_seen": ["EUR", "USD"],
    "date_range_seen": ["2025-01-01", "2026-03-31"],
    "run_log_tail": ["...last 50 redacted lines..."]
  }
}
```

What's **never** in the envelope:
- Transaction descriptions or amounts
- Merchant names (only category labels in `categories_in_use`)
- Account numbers (only stable account aliases like "DB-Joint")
- File names from `02_payslips/` or `04_reference_docs/`
- The passcode, the site URL, any credentials
- File contents of any kind

Redaction is **whitelist-based**: the envelope builder constructs each field from sanitized values; it never serializes raw exceptions or raw log lines into the payload.

### 17.3 Stable error code ranges

| Range | Subsystem |
|---|---|
| FCB-0001..0049 | Pre-flight / environment (OP-11): macOS version, disk, MDM, network, AI-assistant auth, publishing-host credential validation |
| FCB-0050..0099 | Bootstrap / install (Homebrew, Xcode CLT, runtime, dependencies) |
| FCB-0100..0199 | File classifier |
| FCB-0200..0299 | Deduper |
| FCB-0300..0399 | Normalizer |
| FCB-0400..0499 | Categorizer + transfer detector |
| FCB-0500..0599 | Sanity gate |
| FCB-0600..0699 | Site builder |
| FCB-0700..0799 | Publisher |
| FCB-0800..0899 | Refresh |
| FCB-0900..0999 | Recovery |
| FCB-1000..1099 | Telemetry / envelope itself |
| FCB-1100..1199 | FX fetching / cache (Frankfurter unreachable, ECB fallback failed, no rate within 7 days, override-file parse error) |

Every code maps 1:1 to a documented entry in `references/ERROR_CODES.md` with: probable cause, advisor remediation steps, whether it's safe to retry, whether it requires client cooperation.

### 17.4 Advisor inbox (v2 — backlog)

Out of scope for v1. Spec retained for forward-compatibility:

- `POST {endpoint}/v1/errors` with the envelope as JSON body.
- `Authorization: Bearer {scoped-token}` (issued at handshake, §4.5).
- Response: `{ "received": true, "ack_id": "..." }` within 5 seconds.
- If unreachable: queue in `pipeline/output/errors/_pending/`, retry with exponential backoff. User not blocked.

When v2 ships, v1 envelopes already on disk get a one-time backfill upload.

### 17.5 Heartbeats (v2 — backlog)

Out of scope for v1. In v2: once per successful run, POST a `heartbeat` envelope so the advisor can distinguish a silent client from a healthy one.

### 17.6 Support bundle (the v1 transmission path)

The primary way the advisor sees anything from a client's laptop in v1. Triggered by:

- Conversation: "something is broken", "I need help", or after any error envelope is written (the agent offers).
- `Welcome.command` falling back to `support.command` if install fails before the skill is wired up.

`support-bundle.sh` produces a sanitized ZIP containing:

- All envelopes from `pipeline/output/errors/` since last bundle.
- `install.log`
- `pipeline/output/run.log` (redacted)
- File counts per folder (no contents, no filenames).
- `rules.yaml`, `fx.yaml` (not sensitive).
- Skill versions, runtime versions, OS version.
- `check.command` output.

Excluded explicitly: `.env`, `~/.herenow/credentials`, anything from `01_bank_transactions/`, `02_payslips/`, `04_reference_docs/`, the rendered site, any `transactions_*.csv`, all merchant names.

In v1, the bundle is delivered through three parallel paths so no single failure traps the user:

1. **Upload** to a fresh, password-protected publishing-host site using the user's credentials (§4.4). If this fails (most likely cause: the credentials themselves are broken — a Catch-22 the user can't escape on their own), skip silently and proceed.
2. **Save** the zip to `~/Desktop/finance-support-bundle-{ts}.zip` unconditionally — always works, requires nothing.
3. **Share** the resulting URL (or filename, if upload failed) and one-time passcode through:
   - `mailto:` opens the default mail client with subject/body pre-filled to the advisor email from `config.yaml`.
   - Same content copied to the system clipboard.
   - Same content printed in Terminal in a clearly-marked block.

The agent says, in conversation:

> "Done. Three ways to get this to your advisor — pick whichever works:
> - I just opened your email with everything filled in. Click send.
> - I copied the same text to your clipboard — paste it into any email or message.
> - It's also on your screen below in case you want to type it yourself.
> - The bundle is also saved at `~/Desktop/finance-support-bundle-{ts}.zip` if you'd rather attach the file directly."

The bundle URL (when upload succeeded) is set to expire after 7 days. The Desktop zip stays until the user deletes it.

In v2 (backlog) the bundle uploads directly to the advisor inbox with no email turn.

### 17.7 Consent disclosure (at install time)

The install dialog shows once:

> "If something goes wrong, I'll write a small report on your laptop with what step failed and how many files you have — never your transactions, account numbers, or names. I'll only send it to your advisor when you tell me to. You can see exactly what's in any report by asking 'show me what you've written'."

No transmission consent needed in v1 (nothing transmits without the user's "yes"). v2 adds a transmission consent here.

### 17.8 Transparency: "show me what you've written"

Conversational request. Agent prints the most recent N envelopes from `pipeline/output/errors/`, in plain-English summaries with the JSON visible on request. Lets the user verify OP-7 / OP-8 are honored before they send anything.

---

## 18. Skill lifecycle & test fixtures

### 18.1 Skill self-update

On every START-HERE launch, the skill checks (in the background, no blocking) for a newer version of itself. If a newer version exists, the user is told once at the top of the session: "I have an update available. Want me to install it now? It'll take about 30 seconds." On `yes`, the skill updates in place via the same publishing-host CDN that distributes `Welcome.command`. On `not now`, the prompt is suppressed for 7 days. Updates never run without user consent.

### 18.2 AI assistant rate limits

Claude Pro and Max have usage limits. If the assistant returns a rate-limit error mid-flow, the agent surfaces it in plain English:

> "I've used a lot of AI capacity today and need to pause. Try again in about an hour — your work is saved. (If this happens often, your advisor can look at upgrading your plan.)"

API-key users see the equivalent for billing/quota errors with guidance to check their Anthropic billing dashboard.

### 18.3 Test fixtures

For Rafa to test the skill end-to-end without using real client data:

- `references/test-fixtures/` — three pre-built unsorted "client folders" of fictional data (single-currency US household, dual-currency EU household, complex cross-border household). Each ≤ 50 files mixing CSV, OFX, PDF, ZIP, with deliberate edge cases (duplicates, ambiguous classifications, sensitive PDFs that should trip OP-1, transactions that should trip each sanity floor).
- `scripts/run_fixture.sh` — runs a fixture end-to-end (install, ingest, build, publish to a sandbox publishing-host slug, take down) and asserts: zero OP violations, all expected sanity floors trip, expected error codes emitted for injected failures.
- Fixtures derive from the existing `finance_ops/custom-build/demo/` generator, extended with the new edge cases.

CI runs `run_fixture.sh` on every PR.

### 18.4 PDF parsing isolation

`pdfplumber` runs in a subprocess with a 30-second wall-clock limit and a 256 MB memory cap (resource limits via `setrlimit`). PDFs that exceed either limit are skipped with FCB-0150 ("PDF parser hit a safety limit") rather than allowed to consume the parent process. Never invoke any PDF tooling that supports JS execution or external resource loading.

### 18.5 FX time-zone disclosure

ECB rates publish in CET. The site footer shows the FX snapshot date in both CET and the user's local time so a user in PT or EST doesn't see "yesterday's" rate and assume staleness.

---

## 19. Out of scope (v1)

Explicitly not in this skill, even if asked:

- Bank API connections (Plaid, Yodlee, Open Banking).
- iOS / Android client.
- Multi-user collaboration on a single workspace.
- Real-time updates (the model is "drop files + refresh", not streaming).
- Custom report layouts beyond `site/custom/` token + copy overrides.
- Automated tax categorization or filing.
- Investment performance tracking.
- Budgeting / goal-setting workflows.
- Notifications (email, push, SMS).
- Windows / Linux installers (Sprint 2).

---

## 20. Acceptance criteria (v1)

The skill is "done" for the May milestone when a non-technical tester (assumed to have Claude Pro, Max, or an Anthropic API key per §4.0), given only the install link and no other instructions, can:

1. Get past macOS Gatekeeper to launch `Welcome.command` using only the on-page instructions (right-click → Open).
2. Complete install in the time the installer told them up front (10 min if Xcode CLT is present; 30–60 min if not). Pre-flight aborts cleanly with a plain-English message if the Mac is MDM-managed, low on disk, or on an unsupported macOS version.
3. Sign in to Claude (Pro/Max OAuth) **or** paste an Anthropic API key. The agent verifies authentication before continuing. After install, only one third-party-service name (the publishing host) ever appears in any user-facing string, and only during install.
4. Never be asked to invent or type a passcode. The agent generates a phone-friendly diceware passphrase (lowercase, hyphens, no homophones), recites it once, and saves it to `.env` (OP-9). The agent prompts the user to save it to a phone password manager or email it to themselves.
5. Drop an unsorted folder of mixed-format finance files into `inbox/` (or onto the Finder window the skill opens for them) and produce a published, passcode-protected dashboard in under 30 minutes of live time.
6. Re-open the published URL on a phone and load the site after typing the passcode without autocorrect mangling it.
7. A week later, drop new files, say "refresh", and see updated totals at the same URL with the same passcode without any other interaction.
8. Take the site down by saying "delete my dashboard" — confirmed in under 60 seconds.
9. When something breaks, say "I need help" and have the agent (a) save a redacted support bundle to Desktop, (b) upload it to a fresh password-protected slug if credentials are working, (c) open a pre-filled email AND copy to clipboard AND print in Terminal so at least one path delivers it.

Tests the skill must survive without OP violations:

10. **Misclassified sensitive PDF:** a payslip filename-tricked into `01_bank_transactions/` is detected by content-aware OP-1 and **not** read.
11. **10x-off pipeline:** an injected duplicate-transfer that inflates income 10× trips an OP-12 sanity floor before the user is asked to confirm anything.
12. **Calculator not picked yet:** dashboard publishes successfully with a placeholder card.
13. **Brand assets missing:** site builder fails the build (does not fall back to generic AI styling) and surfaces the missing-assets error to the advisor.
14. **iCloud-synced Documents:** workspace is auto-relocated to `~/finance-workspace/` outside the sync root.
15. **Concurrent START-HERE double-click:** second instance focuses the first and exits.
16. **Mailto handler not configured:** clipboard + Terminal-print fallbacks both work; the user can deliver the support bundle without `mailto:`.
17. **Publishing-host credentials broken:** support bundle still saves to Desktop and the user is told how to send it.

In parallel, the advisor (Rafa) must be able to:

18. Diagnose ≥80% of injected failures (one per error code class FCB-00xx through FCB-11xx) from a support bundle alone — without contacting the tester, without requesting screenshots, without opening anything on the tester's laptop.

A passing run produces zero violations of OP-1 through OP-12 in any envelope, log, or user-visible string.

**Out of scope for v1 acceptance** (covered by v2 / `backlog.md`): per-client install links, auto-transmitted error envelopes, heartbeats, advisor-onboarding tool, signed/notarized installer, Windows/Linux installers.
