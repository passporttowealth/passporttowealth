# Installer

> **⚠ Prototype.** Both Mac and Windows installers are v0 skeletons — they print the planned flow but the actual installs are stubbed. Track real implementation in `dev/backlog.md` Epic 1.

What the client downloads. Everything else in the repo (the skill, the templates, the docs) is provisioned silently by the installer once the user double-clicks it.

## Files

| File | Platform | Purpose |
|---|---|---|
| `Welcome.command` | macOS | Bash bootstrap script. Self-relaunches in Terminal when double-clicked from Finder. |
| `Welcome.bat` | Windows | Tiny CMD wrapper that hands off to `Welcome.ps1` with execution-policy bypass for that one process. |
| `Welcome.ps1` | Windows | The real Windows installer logic, in PowerShell. Mirrors the macOS flow step-for-step. **Must live in the same folder as `Welcome.bat`.** |
| `index.html` | both | GitHub Pages landing page. Detects the visitor's OS and shows the right download button + the right "OS will warn you" instructions (Gatekeeper for Mac, SmartScreen for Windows). |
| `assets/` | both | Screenshots for the landing page (Gatekeeper steps, SmartScreen steps), Passport to Wealth logo. |

## Why two files for Windows

Batch (`.bat`) is what double-clicks reliably from File Explorer; PowerShell (`.ps1`) is what we want for actual installer logic. The pair-of-files pattern is industry standard:

- The `.bat` is a 30-line wrapper that does one thing: launches `powershell.exe -ExecutionPolicy Bypass -File Welcome.ps1`. This bypasses the system-wide PowerShell execution-policy lockdown for **this one process only** without changing any user setting.
- The `.ps1` does all real work and gets all the structured-data, error-handling, and UX affordances we'd otherwise lack in batch.

The landing page makes this clear: Windows users are told to download both files into the same folder.

## Distribution URLs

- **Landing page** (what the advisor shares — same URL for everyone, OS-detected): `https://rafaeldavid.github.io/passporttowealth/`
- **Direct downloads** (what the landing buttons point to):
  - Mac: `https://raw.githubusercontent.com/rafaeldavid/passporttowealth/main/installer/Welcome.command`
  - Windows: `https://raw.githubusercontent.com/rafaeldavid/passporttowealth/main/installer/Welcome.bat`
  - Windows (companion): `https://raw.githubusercontent.com/rafaeldavid/passporttowealth/main/installer/Welcome.ps1`
- **Brand-friendly URL** (recommended): point a CNAME from `passporttowealth.studio/welcome` (or similar) to the GitHub Pages URL. See [`docs/advisor-onboarding.md`](../docs/advisor-onboarding.md).

## Sharing with a client

Send the brand-friendly URL. The landing page handles platform detection — the client doesn't need to know whether they're on Mac or Windows. Tell them to expect their OS's "unknown developer" warning; the landing page shows them how to get past it.

Do **not** send the raw download URL directly; the landing page is what walks them through the OS warning, and that step is the most common abandonment point on both platforms.

## Updating the installer

Edit `Welcome.command`, `Welcome.bat`, or `Welcome.ps1` on a feature branch, open a PR, let CI verify it (lint + fixture run), merge to `main`. The next client to click the download URL gets the new version automatically. Existing clients pick up updates via the skill's self-update flow on their next START-HERE launch (see spec §18.1).

**Keep the two installers in sync.** Any user-facing string change in `Welcome.command` should land in `Welcome.ps1` in the same PR, and vice versa. CI lint will eventually enforce this; for now it's a code-review check.

Bump `CHANGELOG.md` and tag a `v0.x.0` release on each meaningful update.

## Reference v1 vs full parity

Per `dev/finance-clarity-build-spec.md` and `dev/backlog.md`:

- **macOS is the v1 reference implementation.** Every behavior described in the spec is targeted at Mac first.
- **Windows is a parallel target with the same behavior contract.** The PowerShell installer will reach feature parity per backlog item B1.3, ahead of v1.0.0 ship if possible, otherwise immediately after.
- **Linux is out of scope until a real customer asks for it.** No third stub.
