# `passporttowealth` — Repo Layout

Proposed structure for `github.com/rafaeldavid/passporttowealth`. Everything in `installer/` and `skill/` is what the client touches (directly or indirectly); everything else is for the advisor and the build process.

```
passporttowealth/
├── README.md                          ← Public-facing: what this is, who it's for, link to the install page
├── LICENSE                            ← Pick one (MIT keeps options open)
├── SECURITY.md                        ← How to report a security issue (private email, not public issues)
├── CHANGELOG.md                       ← Version notes per release tag (read by the self-update flow)
│
├── installer/                         ← What the client downloads
│   ├── Welcome.command                ← The bootstrap script. Has to be raw-downloadable.
│   ├── index.html                     ← GitHub Pages landing page (download button + Gatekeeper instructions + screenshot)
│   ├── assets/
│   │   ├── gatekeeper-step-1.png      ← Screenshot of the "cannot be opened" dialog
│   │   ├── gatekeeper-step-2.png      ← Screenshot of right-click → Open
│   │   ├── gatekeeper-step-3.png      ← Screenshot of the "Open Anyway" confirmation
│   │   └── ptw-logo.svg               ← Passport to Wealth logo for the landing page
│   └── README.md                      ← Notes for the advisor on how to share the install link
│
├── skill/                             ← The `finance-clarity-build` skill itself
│   ├── SKILL.md                       ← Frontmatter + behavior contract (condensed spec)
│   ├── config.example.yaml            ← Per-client config template (no secrets)
│   ├── prompts/
│   │   ├── greeting.md
│   │   ├── sanity_gate.md
│   │   ├── refresh.md
│   │   └── user_facing_strings.md     ← Single source of truth for user-visible copy; OP-8 reviewed
│   ├── scripts/
│   │   ├── classify.py
│   │   ├── dedupe.py
│   │   ├── normalize.py
│   │   ├── fx_fetch.py
│   │   ├── categorize.py
│   │   ├── sanity.py
│   │   ├── build_site.py
│   │   ├── publish.sh
│   │   ├── refresh.sh
│   │   ├── delete-site.sh
│   │   ├── rotate-passcode.sh
│   │   ├── reset-rules.sh
│   │   ├── find-my-site.sh
│   │   ├── support-bundle.sh
│   │   ├── redact-logs.sh
│   │   ├── backup-workspace.sh
│   │   └── restore-workspace.sh
│   ├── templates/
│   │   ├── site/                      ← The locked dashboard template (HTML, CSS, JS, fonts, logo)
│   │   ├── placeholder/               ← The "site coming soon" page used in the publish race-fix
│   │   └── rules-starter.yaml         ← ~100-merchant EU/US starter rule set
│   └── references/
│       ├── DESIGN_TOKENS.md           ← Color, type, spacing, motion tokens
│       ├── CALCULATOR_INTERFACE.md    ← Plug-in contract for the visual calculator slot
│       ├── EDGE_CASES.md              ← Bank-format quirks observed in the wild
│       ├── ERROR_CODES.md             ← FCB-00xx through FCB-11xx with cause + remediation
│       └── test-fixtures/             ← Three pre-built unsorted "client folders" for end-to-end tests
│
├── docs/                              ← What the advisor reads (and what's hosted via GitHub Pages for the landing)
│   ├── advisor-onboarding.md          ← How Rafa hands a client the install link, what to confirm first
│   ├── client-quickstart.md           ← The three-paragraph "what to expect" the advisor can paste into an email
│   ├── troubleshooting.md             ← Per-error-code playbook the advisor reads against incoming support bundles
│   ├── design-system.md               ← Brand pack reference once Arielle delivers it
│   └── privacy-and-security.md        ← What's local, what's transmitted, what the passcode protects
│
├── engagement/                        ← Project / planning docs (the contents currently in finance_services/engagement/)
│   ├── project-overview.md
│   ├── kickoff-agenda.md
│   ├── mnda-template.md
│   └── development/
│       ├── demo-script.md
│       ├── finance-clarity-build-spec.md
│       ├── backlog.md
│       └── github-repo-layout.md      ← This file
│
├── releases/                          ← Tagged versions; self-update flow reads from these
│   └── (managed via GitHub Releases — not a real folder)
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                     ← Run `scripts/run_fixture.sh` against the test fixtures on every PR
│   │   ├── lint-user-strings.yml      ← OP-8 banned-words check on every PR
│   │   └── pages.yml                  ← Build + deploy `installer/index.html` to GitHub Pages
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug.md                     ← For Rafa / dev only, not advertised to clients
│   │   └── feature.md
│   └── CODEOWNERS                     ← Rafa owns everything for now
│
└── .gitignore                         ← Excludes test-fixture outputs, .venv, .DS_Store
```

---

## Distribution mechanics

### What the client downloads
`https://raw.githubusercontent.com/rafaeldavid/passporttowealth/main/installer/Welcome.command`

But they don't see that URL — they see the GitHub Pages landing page (with the screenshots) and click "Download for Mac." The href under that button is the raw URL above.

### What the installer pulls down
At install time, `Welcome.command` `git clone`s the repo (or `curl`s a tarball of the latest release) into `~/Documents/my-finances/.skill/`, then symlinks the skill into the right Claude Code skills directory. This way the workspace contains its own pinned copy of the skill and self-update is just a `git fetch && git checkout {new-tag}`.

### Self-update
On every START-HERE launch, the skill checks `https://api.github.com/repos/rafaeldavid/passporttowealth/releases/latest` against the local pinned version. If newer, prompts the user once: "I have an update. Install now? (~30 seconds)". Updates only run on consent.

---

## Branching & release model (lean for v1)

- `main` is always-shippable. CI must pass, fixtures must pass, OP-8 lint must pass.
- Feature work in branches named `epic/{epic-id}-{short-name}` matching the backlog (e.g. `epic/E2.1-auto-sort`).
- Releases tagged `v0.x.0` (or `v1.0.0` for the May milestone). GitHub Releases page becomes the changelog.
- No staging branch, no protected-branch rules beyond "PRs must pass CI." Single-maintainer simplicity.

---

## What stays private (NOT in the repo)

These never get committed:

- Real client data (any real CSV, PDF, or transaction)
- The advisor's here.now API key (lives only on the advisor's machine, used only by the v2 `advisor-onboard` tool when that ships)
- Test fixtures derived from real data — only fully-synthetic fixtures live in `references/test-fixtures/`

`.gitignore` covers `*.csv`, `*.pdf`, `*.xlsx`, `*.env`, `.venv/`, `.DS_Store`, `pipeline/output/`, `inbox/`, `01_bank_transactions/`, `02_payslips/`, `03_amazon_orders/`, `04_reference_docs/`, `05_other/`, `fx_cache/`, `.herenow/`.

---

## What to set up in the repo first (before any code)

1. **Initialize the repo** with `README.md`, `LICENSE`, `SECURITY.md`, `.gitignore` (using the patterns above).
2. **Enable GitHub Pages** on `main` branch, source `installer/` (or `/docs` if Pages prefers that) so the landing page goes live at `https://rafaeldavid.github.io/passporttowealth/`.
3. **Buy + configure the brand domain** (`passporttowealth.studio` or whichever Arielle prefers per `kickoff-agenda.md`) and point a CNAME at the GitHub Pages URL.
4. **Stub the landing page** (`installer/index.html`) with placeholder copy + the Gatekeeper instructions block. Real screenshots can come once Arielle's brand pack is in.
5. **Move the planning docs** from `finance_services/engagement/` into the repo's `engagement/` folder so everything lives in one place.
6. **Wire the CI workflows** (lint, fixture run) before any meaningful skill code lands — keeps the door closed on regressions from day one.

After that, items in `backlog.md` Epic order: bootstrap installer (B1.x), then file ingestion (E2.x), and so on.
