# Installer

> **⚠ Prototype.** Mac install path is the reference implementation; Windows is at v0 parity (B9.16). Track outstanding work in [`dev/backlog.md`](../dev/backlog.md).

What the client sees and runs. The full install is a one-line command they paste into their terminal — nothing lands in their `Downloads` folder.

## Files

| File | Purpose |
|---|---|
| `install.sh` | **Canonical Mac installer.** Streamed via `curl … \| bash` from `passporttowealth.app/install`. ~800 lines. Provisions uv, Python 3.11, jq, Node, Claude Code, here-now skill, finance-clarity-build skill, workspace at `~/Documents/my-finances/`. |
| `install.ps1` | **Canonical Windows installer.** Streamed via `irm … \| iex` from `passporttowealth.app/install.ps1`. Same flow as `install.sh`; tools via winget + npm. |
| `install` | Tiny bash shim served at `passporttowealth.app/install` that exec-fetches `install.sh` from GitHub raw. The branded short URL. |
| `index.html` | Landing page, deployed to here.now (slug `sandy-delta-dc3r`) at `https://passporttowealth.app/`. |
| `dashboard-demo/` | Live public mirror of the dashboard, built from the synthetic demo-kit fixture by the real pipeline. Served at `https://passporttowealth.app/dashboard-demo/`. See ["The demo dashboard"](#the-demo-dashboard) below. |
| `assets/` | Landing-page imagery: world-map watermark, the book cover, Gatekeeper/SmartScreen screenshots, and `assets/brand/` (real-file copies of the brand pack — see ["Brand assets"](#brand-assets-three-copies-keep-them-in-sync) below). |
| `publish-landing.sh` | **Use this to publish the landing page.** Substitutes `{{BUILD_STAMP}}` in a temp build dir, then publishes to here.now. Don't invoke the here-now skill against `installer/` directly — the timestamp would render literally. |
| `legacy/` | Archived `Welcome.command` / `.bat` / `.ps1` from the file-download era. Kept as a fallback for clients who absolutely cannot open Terminal/PowerShell. Not advertised on the landing page. |

## Distribution URLs

- **Landing page** (what advisors share): `https://passporttowealth.app/`
- **Install (Mac)**: `curl -fsSL https://passporttowealth.app/install | bash`
- **Install (Windows)**: `irm https://passporttowealth.app/install.ps1 | iex`
- **Live demo dashboard**: `https://passporttowealth.app/dashboard-demo/`
- **`www.passporttowealth.app`** redirects to the apex.
- **Backup mirror**: `.github/workflows/pages.yml` builds a copy of the landing page to GitHub Pages on every push to `main`. Belt-and-suspenders only — keep advertising `passporttowealth.app`.

## Publishing the landing page

```bash
bash installer/publish-landing.sh
```

That's it. The wrapper:
1. `rsync -aL` mirrors `installer/` to a temp dir, dereferencing any symlinks (here-now's `publish.sh` walks files with `find -type f`, which silently skips symlinks).
2. Substitutes `{{BUILD_STAMP}}` with the current UTC timestamp (format `yyyymmddHHMMSS`, matching the install-telemetry `build_stamp`).
3. Publishes to slug `sandy-delta-dc3r` via the here-now skill.
4. Carries `.herenow/` state in/out so claim tokens don't get lost.

**Don't publish `installer/` directly with the bare here-now skill** — `{{BUILD_STAMP}}` would land in the live HTML literally, and any future symlink would silently 404 in the bundle. Both regressions have happened; both are guarded by the wrapper.

The slug `sandy-delta-dc3r` is the original here.now slug behind `passporttowealth.app`; updates propagate to the apex automatically (≤60s via Cloudflare KV). Override with `LANDING_SLUG=...` env var if needed.

## The demo dashboard

`installer/dashboard-demo/` is a fully-rendered dashboard (synthetic data, real template, real pipeline). Linked from section 03 of the landing page so prospects can see the output before installing. Public — no passcode.

To regenerate (after the dashboard template changes, the demo-kit fixture changes, or the pipeline output shape changes):

```bash
# 1. Build a fresh dashboard from the demo-kit fixture
rm -rf /tmp/dashboard-demo-ws
mkdir -p /tmp/dashboard-demo-ws/inbox
cp demo-kit/data/* /tmp/dashboard-demo-ws/inbox/
FCB_WORKSPACE=/tmp/dashboard-demo-ws bash skill/scripts/refresh.sh --auto-confirm

# 2. Replace the bundled copy
rm -rf installer/dashboard-demo
cp -R /tmp/dashboard-demo-ws/site installer/dashboard-demo

# 3. Re-apply the two demo-only patches:
#    a) Add the gold "Demo dashboard — synthetic data" banner right after <body>
#    b) Override the privacy footer (the per-client passcode framing doesn't apply
#       to a public demo). Look at git history of installer/dashboard-demo/index.html
#       for the exact blocks; tests/test_dashboard_demo_bundle_complete asserts
#       both are present.

# 4. Force-add the synthetic CSV downloads (global *.csv ignore blocks them)
git add -f installer/dashboard-demo/downloads/*.csv

# 5. Republish
bash installer/publish-landing.sh
```

Tests guard the bundle: `test_dashboard_demo_bundle_complete` checks the banner, the footer override, and that all assets are real files (no symlinks).

## Brand assets — three copies, keep them in sync

Brand files (`logo-blue.png`, `logo-white.png`, `favicon.png`) live in three places:

1. `assets/brand/` — canonical
2. `installer/assets/brand/` — bundled into the landing page
3. `skill/templates/site/assets/brand/` — bundled into the user dashboard

**No symlinks** — here-now's `publish.sh` skips them. The `test_landing_page_assets_resolve_in_publish_bundle` test fails if a symlink is reintroduced under `installer/`.

When updating any brand file, run both `cp` lines from [`assets/brand/README.md`](../assets/brand/README.md).

## Sharing the install link with a client

Send `https://passporttowealth.app/`. The landing page handles platform detection and shows the right install command for Mac or Windows with a copy button. Tell them what to expect (Terminal/PowerShell, ~10 minutes on a fresh machine).

If the prospect wants to see the output first, send them `https://passporttowealth.app/dashboard-demo/` — that's why it's there.

## Updating the installer

Edit `install.sh` and/or `install.ps1` on a branch, open a PR, let CI lint + tests pass, merge to `main`. The next client to run the install one-liner gets the new version automatically — the install URL exec-fetches GitHub raw, so there's no separate publish step for the installer scripts themselves (only for the landing page).

**Keep the two installers in sync.** Any user-facing string in `install.sh` should land in `install.ps1` in the same PR. `tests/test_installer_*` enforces parity on key blocks (telemetry, consent gate, etc.).

Bump `CHANGELOG.md` on each meaningful update.

## Reference v1 vs full parity

Per `dev/finance-clarity-build-spec.md` and `dev/backlog.md`:

- **macOS** is the v1 reference. Every behavior in the spec targets Mac first.
- **Windows** reached v0 parity in B9.16 (winget for tools, npm for Claude Code, npx for skills, parity UX). Ship-then-dry-run remains the validation strategy until we have a real Windows test box. OneDrive sync detection deferred to v1.1.
- **Linux** is out of scope until a real customer asks for it.
