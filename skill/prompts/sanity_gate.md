# sanity_gate.md

Mandatory pre-build confirmation prompt (spec §11). The agent runs `sanity.py`, which produces a structured JSON summary; the agent renders it using the templates below.

OP-12 hard floors run **first**. If any tripped, present the warning template and require explicit per-floor acknowledgement before the user can say "looks right."

---

## Standard sanity gate (no floors tripped)

```
=== Quick check before I build your dashboard ===

Period covered: {start_date} through {end_date} ({n_months} months)
Accounts: {account_aliases_comma_separated}

Monthly totals (in {primary_currency}):
  Income (avg/month):    {primary_currency_symbol}{income_avg}
  Spend  (avg/month):    {primary_currency_symbol}{spend_avg}
  Net    (avg/month):    {primary_currency_symbol}{net_avg}

Top 10 categories by spend:
  1. {cat_1_name}  {primary_currency_symbol}{cat_1_total}  ({cat_1_count} transactions)
  2. {cat_2_name}  ...
  ...

Largest 5 single transactions:
  1. {date}  {description}  {primary_currency_symbol}{amount}  ({account_alias})
  ...

Transfers excluded:    {n_transfers} ({primary_currency_symbol}{transfers_total})
Uncategorized rows:    {n_uncategorized} ({uncategorized_pct}% of total)
FX cache freshness:    {fx_age_days} days old

Does this look right?

  • Type "looks right" or "yes" to build the dashboard.
  • Tell me what looks wrong (e.g. "the income looks too high in March")
    and I'll dig into that specific item.
  • Or "show me {category}" / "show me {account}" to drill in first.
```

---

## Floor-violation warning template

For each floor that tripped, prepend this block before the standard gate. The user cannot say "looks right" until each violation is acknowledged.

```
⚠ I'm worried about this — {floor_name}:

  {plain_english_explanation_of_the_specific_violation_with_numbers}

  This often means: {most_common_root_cause_for_this_floor}.

  • If you'd like me to investigate, type "look into {floor_name}".
  • If you've checked and the number is correct, type:
    "I understand the warning about {floor_name} and want to continue anyway"
    (I'll keep going but log it so your advisor can see what we waved through.)
```

### Floor texts

**savings_rate**
> "Your average savings rate works out to {pct}% — that's outside what's typical [-50% to +90%]. Almost always means I miscounted a transfer between two of your accounts as income or spending."

**mom_income_variance**
> "Your income jumped {factor}x between {month_a} and {month_b}. Usually I'm misreading a transfer as income, or there's a one-off (bonus, refund) I should exclude from the monthly trend."

**transfers_pct**
> "About {pct}% of all the money I see is moving between your own accounts. That's high — I might be missing a real expense or counting one twice."

**uncategorized_pct**
> "{pct}% of your transactions don't have a category yet. The dashboard will be more useful if we fix the rules first — want me to walk through the most common ones?"

**fx_freshness**
> "I couldn't fetch fresh exchange rates today. Using cached rates from {n} days ago — your converted totals could be off by a percent or two. Want me to retry, or continue with the cached rates?"

---

## What "investigate" looks like

When the user types "look into {x}":

```
Looking into {floor_name}...

I checked: {what_I_checked}.
What I found: {what_I_found}.
Suggested fix: {suggested_fix}.

  • Apply this fix? (yes/no)
  • Or do you want to handle it differently?
```

After applying any fix, re-run sanity check. If the floor passes, the gate continues. If it still fails, ask again.
