# `passporttowealth` — Repo Layout

Proposed structure for `github.com/passporttowealth/passporttowealth`. Everything in `installer/` and `skill/` is what the client touches (directly or indirectly); everything else is for the advisor and the build process.

```
passporttowealth/
├── README.md                          ← Public-facing: what this is, who it's for, link to the install page
├── LICENSE                            ← Pick one (MIT keeps options open)
├── SECURITY.md                        ← How to report a security issue (private email, not public issues)
├── CHANGELOG.md                       ← Version notes per release tag (read by the self-update flow)
│
├── installer/                         ← What the client streams + the public landing
│   ├── install.sh                     ← Canonical Mac installer (curl-piped from passporttowealth.app/install)
│   ├── install.ps1                    ← Canonical Windows installer (irm-piped from passporttowealth.app/install.ps1)
│   ├── install                        ← Tiny bash shim served at the short URL; exec-fetches install.sh from GitHub raw
│   ├── index.html                     ← Landing page (here.now slug sandy-delta-dc3r → https://passporttowealth.app/)
│   ├── publish-landing.sh             ← USE THIS to publish the landing page. Substitutes {{BUILD_STAMP}} in a temp dir.
│   ├── dashboard-demo/                ← Live public demo at /dashboard-demo (built from demo-kit by the real pipeline)
│   ├── assets/                        ← Landing imagery + brand pack (real files, no symlinks)
│   ├── legacy/                        ← Archived Welcome.{command,bat,ps1} for file-download fallback
│   └── README.md                      ← How to publish, regenerate the demo, sync brand assets
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
├── docs/                              ← What the advisor reads
│   ├── advisor-onboarding.md          ← How Rafa hands a client the install link, what to confirm first
│   ├── client-quickstart.md           ← The three-paragraph "what to expect" the advisor can paste into an email
│   ├── troubleshooting.md             ← Per-error-code playbook the advisor reads against incoming support bundles
│   ├── design-system.md               ← Brand pack reference once Arielle delivers it
│   └── privacy-and-security.md        ← What's local, what's transmitted, what the passcode protects
│
├── dev/                              ← Product / dev planning docs (no commercial / engagement details)
│   ├── demo-script.md                ← User-journey walkthrough for the product
│   ├── finance-clarity-build-spec.md ← Full implementation spec for the skill (source of truth)
│   ├── backlog.md                    ← Prioritized work items / epic plan
│   └── github-repo-layout.md         ← This file
│
├── releases/                          ← Tagged versions; self-update flow reads from these
│   └── (managed via GitHub Releases — not a real folder)
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                     ← Run `scripts/run_fixture.sh` against the test fixtures on every PR
│   │   ├── lint-user-strings.yml      ← OP-8 banned-words check on every PR
│   │   └── pages.yml                  ← Backup deploy of `installer/` to GitHub Pages (canonical landing is here.now)
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug.md                     ← For Rafa / dev only, not advertised to clients
│   │   └── feature.md
│   └── CODEOWNERS                     ← Rafa owns everything for now
│
└── .gitignore                         ← Excludes test-fixture outputs, .venv, .DS_Store
```

---

## Distribution mechanics

### What the client sees
`https://passporttowealth.app/` (also reachable via `www.passporttowealth.app`, which 301s to the apex). The landing page is `installer/index.html`, deployed to here.now via the here-now skill. The `installer/Welcome.{command,bat,ps1}` files are bundled into the same publish, so the download buttons on the landing page point at relative paths (`Welcome.command`, etc.) on the same origin — no GitHub raw URL dependency.

### How the landing page gets there
The here-now publish slug behind `passporttowealth.app` is `sandy-delta-dc3r`. To update:

```bash
bash installer/publish-landing.sh
```

That wrapper handles two regressions that bit us before:
1. **`{{BUILD_STAMP}}` substitution** — the landing footer has a build-stamp placeholder. Without the wrapper, it renders literally on the live page.
2. **Symlink dereferencing** — `installer/assets/brand/` was once a symlink. The here-now skill walks files with `find -type f` (skips symlinks), so the brand PNGs disappeared from the bundle and the live logo 404'd. The brand assets are now real files (and a test guards against re-introducing a symlink), but `publish-landing.sh` also runs `rsync -aL` to dereference anything new just in case.

Propagation is ≤60s globally via Cloudflare KV. The `.github/workflows/pages.yml` workflow also builds a backup mirror to GitHub Pages on every push to `main` — same content, second URL, used only if here.now is unreachable.

### The live demo dashboard
`https://passporttowealth.app/dashboard-demo/` is a public mirror of the dashboard, built from the synthetic `demo-kit/` fixture by the real pipeline (classify → ... → build_site). Lives at `installer/dashboard-demo/` and ships in the same publish bundle as the landing page. No passcode (it's marketing). To regenerate, see [`installer/README.md`](../installer/README.md#the-demo-dashboard).

### What the installer pulls down
At install time, `Welcome.command` `git clone`s the repo (or `curl`s a tarball of the latest release) into `~/Documents/my-finances/.skill/`, then symlinks the skill into the right Claude Code skills directory. This way the workspace contains its own pinned copy of the skill and self-update is just a `git fetch && git checkout {new-tag}`. The skill code itself stays in GitHub (auditable, versioned); only the landing page + installer launchers are mirrored to here.now for the brand-friendly download URL.

### Self-update
On every START-HERE launch, the skill checks `https://api.github.com/repos/passporttowealth/passporttowealth/releases/latest` against the local pinned version. If newer, prompts the user once: "I have an update. Install now? (~30 seconds)". Updates only run on consent.

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

1. **Initialize the repo** with `README.md`, `LICENSE`, `SECURITY.md`, `.gitignore` (using the patterns above). ✅ done
2. **Publish the landing page to here.now** at slug `sandy-delta-dc3r` (see *Distribution mechanics* above for the publish command). ✅ done
3. **Attach `passporttowealth.app` (apex + www)** as a custom domain on the here.now slug via `POST /api/v1/domains` and `POST /api/v1/links` (see `~/.claude/skills/here-now/SKILL.md`). ✅ done — live at `https://passporttowealth.app/`
4. **Stub the landing page** (`installer/index.html`) with placeholder copy + the Gatekeeper instructions block. ✅ done — real screenshots in `installer/assets/`
5. **Move the planning docs** from `finance_services/dev/` into the repo's `dev/` folder so everything lives in one place. ✅ done
6. **Wire the CI workflows** (lint, fixture run, Pages backup deploy) before any meaningful skill code lands — keeps the door closed on regressions from day one.

After that, items in `backlog.md` Epic order: bootstrap installer (B1.x), then file ingestion (E2.x), and so on.
