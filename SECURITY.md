# Security policy

> **⚠ Prototype — pre-release.** This software is under active development. Security review and threat modeling are partial. Expect changes to the security posture as the prototype matures. Do not deploy outside the invited Passport to Wealth pilot.

## Reporting a vulnerability

If you have found a security issue in the installer, the skill, or the published dashboard, please **do not** open a public GitHub issue.

Instead, contact Passport to Wealth privately via [https://www.passporttowealth.com/](https://www.passporttowealth.com/) and reference "Finance Clarity security report" in your message.

We aim to acknowledge reports within 5 business days.

## What this project handles

- Client-side storage of financial transactions, paystubs, and tax documents on the client's own laptop.
- Generation and storage of a passcode that protects the client's published dashboard.
- Transmission of dashboard content (filtered to bank-transaction data only by default) to the publishing host.
- Local logs that are redacted before any support bundle is created.

## What this project does **not** do

- It does not transmit raw transaction data, payslips, or tax documents anywhere.
- It does not store any credentials in plaintext that aren't permission-locked (`chmod 600`) on the client's laptop.
- It does not phone home with telemetry in v1. (v2 plans an opt-in error-reporting channel — see `engagement/development/backlog.md`.)

## Operating principles

The skill enforces twelve hard operating rules covering privacy, sensitive-data gating, publish-flow safety, secret handling, and pre-flight environmental checks. Full list in [`engagement/development/finance-clarity-build-spec.md`](engagement/development/finance-clarity-build-spec.md) §2.

If a vulnerability would cause any of those operating rules to be violated, treat it as high-severity and report it via the contact above.
