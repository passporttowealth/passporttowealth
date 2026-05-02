# refresh.md

Triggered by user saying "refresh", "I added new files", "update my report" (spec §14, §6.3).

The agent runs `refresh.sh` which:
1. Classifies new files in `inbox/` only (existing folders untouched).
2. Dedupes across all sorted folders.
3. Normalizes new rows.
4. Fetches missing FX dates + today's snapshot rate.
5. Incrementally categorizes only new rows; surfaces new uncategorized merchants.
6. Runs sanity gate with month-over-month deltas.
7. Rebuilds the dashboard at `$WS/site/`.

After refresh.sh completes, the agent **opens the rebuilt dashboard locally**
(`view-local.sh` → `file://$WS/site/index.html`) by default. **Republishing
to a shared URL only happens if the user has previously published** — i.e.
`$HOME/.herenow/credentials` exists. New users see the local view and are
asked once whether they want to share.

The user types one sentence; the agent does everything else.

---

## Acknowledgement on receipt

```
Refreshing your dashboard. Give me a minute or two — I'll let you know
what changed.
```

---

## Per-step status (printed inline as steps complete)

```
✓ Found {n_new} new files in your inbox
✓ Sorted them: {n_bank} bank exports, {n_payslips} paystubs (skipped),
    {n_other} other
✓ Dedupe: {n_dropped} were already in your data
✓ FX rates updated through {date}
{conditional: "→ Asking you about {n_new_merchants} new merchants..."}
✓ Sanity check passed
✓ Dashboard rebuilt
{conditional, only if credentials present: "✓ Published to your existing URL"}
```

---

## Completion summary — first build (no credentials yet)

```
=== Done ===

Your dashboard is open in your browser. It lives only on your laptop —
no third-party server, no passcode needed (your laptop's lock screen
already protects it).

  • {n_transactions} transactions
  • Through {latest_transaction_date}
  • Net cashflow this period: {primary_currency_symbol}{net_change}

Want to share it with anyone (advisor, family)? I can put it on a
private URL with a passcode — that's also how you'd see it on your
phone. Just say "share my dashboard" and I'll set it up.

Otherwise, refresh any time by dropping new files in your inbox and
saying "refresh".
```

---

## Completion summary — incremental refresh, already shared

```
=== Done ===

Compared to your last refresh on {previous_refresh_date}:
  • Added {n_new_transactions} transactions
  • {n_new_categories_added} new merchants categorized
  • Totals now run through {latest_transaction_date}
  • Net cashflow this period: {primary_currency_symbol}{net_change}

Your dashboard is at the same URL with the same passcode:
  {url}

Open it on any device to see the new data. Want to share with someone
new? Just say "share my dashboard with {name}" and I'll handle it.
```

---

## "Nothing changed" (idempotent re-run)

If the user says "refresh" but no new files exist and dedupe drops everything:

```
Nothing new to refresh — your inbox is empty, or everything you dropped
in is already in your dashboard.

Want to:
  • Drop new files into the inbox folder (it's the one I opened earlier)
  • See your current dashboard URL ("what's my URL?")
  • Send me feedback ("I have feedback")
```
