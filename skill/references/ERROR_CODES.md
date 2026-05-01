# Error Codes — FCB-00xx through FCB-11xx

> **⚠ Prototype.** Codes locked early so envelopes (spec §17.2) stay stable. Per-code remediation will fill in as the skill is built.

The advisor reads this against any incoming support bundle. Each code is **stable** — if a code's meaning changes, bump the code, don't reuse.

## Format

```
### FCB-XXXX — Short name
**Subsystem:** classify | normalize | … (per spec §17.3)
**Probable cause:** What usually triggers this.
**Safe to retry?** yes / no / yes-after-fix.
**Requires client cooperation?** yes / no.
**Remediation:** What the advisor should do or guide the client to do.
```

## Codes

### FCB-0001 — Unsupported macOS version
**Subsystem:** Pre-flight (OP-11)
**Probable cause:** Client is on macOS 12 or earlier.
**Safe to retry?** yes-after-fix (after Mac upgrade).
**Requires client cooperation?** yes.
**Remediation:** Walk client through `About This Mac → Software Update`. If they can't upgrade (older hardware), this skill won't work for them in v1.

### FCB-0002 — Insufficient disk space
**Subsystem:** Pre-flight (OP-11)
**Probable cause:** Less than 5 GB free on the home volume.
**Safe to retry?** yes-after-fix.
**Requires client cooperation?** yes.
**Remediation:** Ask client to clear space (Downloads, Desktop, Trash) and re-run the installer.

### FCB-0003 — MDM-managed device
**Subsystem:** Pre-flight (OP-11)
**Probable cause:** Client is on a corporate / employer-managed laptop.
**Safe to retry?** no (will fail again).
**Requires client cooperation?** yes.
**Remediation:** Skill is personal-laptops-only in v1. Advise client to use a personal Mac.

### FCB-0004 — Anthropic auth failed
**Subsystem:** Install (§4.3)
**Probable cause:** Invalid API key, expired session, or billing issue with Anthropic account.
**Safe to retry?** yes-after-fix.
**Requires client cooperation?** yes.
**Remediation:** Confirm Pro/Max subscription is active or API key is valid in Anthropic dashboard. Re-run install.

### FCB-0010 — FX source unreachable (warning)
**Subsystem:** Pre-flight (OP-11)
**Probable cause:** Network down, Frankfurter API outage, firewall.
**Safe to retry?** yes (often transient).
**Requires client cooperation?** sometimes.
**Remediation:** Install continues; FX pre-warm skipped. Client should be on a network that allows outbound HTTPS.

### FCB-1101 — FX rate unavailable for transaction date
**Subsystem:** FX fetch (§10.5)
**Probable cause:** No source has a rate within ±7 days of a transaction's date.
**Safe to retry?** yes (when network restored).
**Requires client cooperation?** no.
**Remediation:** Pipeline blocks at sanity gate. Advisor may need to manually add a rate to `fx_overrides.yaml`, or wait for network/source recovery.

### FCB-1102 — FX cache stale
**Subsystem:** FX fetch (§10.5)
**Probable cause:** Snapshot fetch failed during refresh; using cached rates older than 7 days.
**Safe to retry?** yes.
**Requires client cooperation?** no.
**Remediation:** Surfaced as a sanity-gate warning. Re-run refresh on a working network.

---

## Codes to be filled in (placeholder list)

```
FCB-0050..0099   Bootstrap / install (Homebrew, Xcode CLT, runtime install failures)
FCB-0100..0199   Classifier (file open errors, format detection failures, sensitive-content blocks)
FCB-0200..0299   Deduper (hash mismatches, content overlap detection)
FCB-0300..0399   Normalizer (currency detection, date format, sign convention)
FCB-0400..0499   Categorizer + transfer detector (rule parse errors, transfer-pair ambiguity)
FCB-0500..0599   Sanity gate (floor violations, user-acknowledgement mismatches)
FCB-0600..0699   Site builder (template slot mismatch, missing brand assets)
FCB-0700..0799   Publisher (host API errors, race-fix verification failures, site-down rollback)
FCB-0800..0899   Refresh (incremental run failures)
FCB-0900..0999   Recovery (delete, rotate, reset, find, support-bundle)
FCB-1000..1099   Telemetry / envelope itself
```

Each will get a full block above as we encounter and document the specific failure modes.
