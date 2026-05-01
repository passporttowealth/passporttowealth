---
name: finance-clarity-build
description: >
  Turn a folder of unsorted financial files (bank statements, paystubs, tax docs)
  into a private, passcode-protected web dashboard. Use when the user says "build
  my report", "refresh my finances", "publish my dashboard", or after dropping
  files into the workspace inbox. Handles the entire pipeline — sort, dedupe,
  normalize currency and dates, fetch FX rates, categorize, run sanity floors,
  build a branded dashboard from a locked template, and publish behind a
  passcode the skill generates. Designed for non-technical users; agent owns
  every third-party interaction.
version: 0.0.1-stub
---

# `finance-clarity-build`

> **⚠ Prototype — pre-release skill.** Behavior, prompts, and on-disk layout will change. Pinned per-workspace via the bootstrap so individual clients aren't broken by upstream edits, but no API stability is guaranteed before `v1.0.0`.

This is a v0 stub. The implementation lands per the epic order in
[`engagement/development/backlog.md`](../engagement/development/backlog.md).

The full behavior contract lives in
[`engagement/development/finance-clarity-build-spec.md`](../engagement/development/finance-clarity-build-spec.md) —
this `SKILL.md` is a condensed pointer, not a duplicate.

## Hard rules (operating principles)

The skill enforces 13 hard operating rules — privacy, sensitive-data gating,
publish-flow safety, secret handling, environmental gates, sanity floors, and
Anthropic data-terms consent. Full table in spec §2.

A violation of any rule is a defect. The skill fails loudly rather than work
around them.

## Triggers

The agent invokes this skill when the user:

- Is in the workspace folder for the first time (greeting flow).
- Says: `build my report`, `refresh`, `publish`, `delete my dashboard`,
  `rotate passcode`, `reset rules`, `find my site`, `share with my accountant`,
  `back up my workspace`, `restore from backup`, `something is broken`,
  `I have feedback` / `I have a suggestion` / `this could be better`,
  `what's my passcode`, `what's my url`, `show me what you've remembered`,
  `start completely over`.
- Drops new files into `inbox/` after a previous build.

The skill does NOT trigger on general finance questions, code questions, or
anything outside the workspace.

## Layout

```
skill/
  SKILL.md                ← this file
  config.example.yaml     ← per-client config template (no secrets)
  prompts/
    greeting.md
    sanity_gate.md
    refresh.md
    user_facing_strings.md   ← OP-8 reviewed copy
  scripts/                ← see backlog Epic 2/3/5/6 for implementation order
  templates/
    site/                 ← locked dashboard template (HTML, CSS, JS, fonts, logo)
    placeholder/          ← "site coming soon" page used in the publish race-fix
    rules-starter.yaml    ← starter merchant categorization rules
  references/
    DESIGN_TOKENS.md      ← color, type, spacing, motion tokens
    CALCULATOR_INTERFACE.md
    EDGE_CASES.md
    ERROR_CODES.md        ← FCB-00xx through FCB-11xx with cause + remediation
    test-fixtures/        ← three pre-built unsorted client folders for end-to-end tests
```
