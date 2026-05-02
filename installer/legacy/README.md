# Legacy installers

These are the v1 download-and-double-click installers. They've been
superseded by `installer/install.sh` (the curl-pipe-bash one-liner shown
on https://passporttowealth.app/) which avoids the macOS Gatekeeper /
Windows SmartScreen "unidentified developer" warning entirely.

| File | Platform | Status |
|---|---|---|
| `Welcome.command` | macOS | Functional. Distributed via direct file download from the old landing page. Triggers Gatekeeper. |
| `Welcome.bat` | Windows | Functional but Step 2-6 still stubs (real-install port pending — see backlog #60). |
| `Welcome.ps1` | Windows | Companion to `Welcome.bat`. Same status. |

## Why keep them

A small slice of clients won't or can't open Terminal. For them, downloading
a file and double-clicking it is the only path that works. We retain the
download flow as a fallback to avoid losing those users.

## When to delete

When at least 2-3 clients have onboarded successfully via the curl one-liner
(`installer/install.sh`) and there's been no fallback request, these can be
deleted. Until then, keep.

## Differences from `install.sh`

The legacy `Welcome.command` and `install.sh` differ in three places:

1. **Re-exec into Terminal:** legacy detects Finder-launch (no TTY) and
   re-execs itself inside Terminal.app via `open -a Terminal`. install.sh
   skips this — when curl-piped, we're already inside Terminal.
2. **Self-delete:** legacy deletes itself from `~/Downloads/` on success.
   install.sh has no file to delete.
3. **Skill fetch:** legacy uses `git clone` to pull the finance-clarity-build
   skill source. install.sh uses `npx skills add` (B9.8 — cleaner, matches
   the pattern already used for the here-now skill).

Otherwise the behavior contract is identical: same pre-flight, same uv
provisioning, same Claude Code install, same workspace, same diagnostics.
