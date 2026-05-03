# user_facing_strings.md

Single source of truth for every user-visible string the skill emits, outside the install dialog. Reviewed against OP-8 (banned-words list) on every PR via `.github/workflows/lint-user-strings.yml`.

OP-8 banned in any value below: `here.now`, `API key`, `credential`, `slug`, `Homebrew`, `Python`, `pip`, `venv`, `npx`, `OFX`, `webhook`. Permitted: "your site", "your passcode", "your folder", "your dashboard." <!--OP8-OK: this line is the canonical banned-words list itself, intentionally enumerating them-->

The full prompt copy lives in the dedicated files (`greeting.md`, `sanity_gate.md`, `refresh.md`). This file is the lexicon for **everything else** — short messages the agent emits during the flow.

```yaml
# ─── Sort + ingest ──────────────────────────────────────────────────
sort_summary: |
  I found {n_total} files. I sorted {n_sorted} of them: {breakdown}.
  I wasn't sure about these {n_ambiguous} — can you tell me what they are?

dedupe_summary: |
  {n_dropped} of these were the same statement saved twice. I kept one of each.

privacy_skip_default: |
  I see paystubs and tax documents in the folder. By default I'll skip them —
  your dashboard doesn't need to read them. Tell me if you want me to include
  any specific ones (I'll ask file-by-file before opening anything).

# ─── Disambiguation per file ────────────────────────────────────────
disambiguate_one: |
  This file: {filename}
  What is it?
    (a) Money you spent or earned (bank transaction, receipt, statement)
    (b) Paystub, payroll, or income document — I'll skip reading it
    (c) Tax document — I'll skip reading it
    (d) Something else (I'll set it aside without reading it)
    (e) I don't know — set it aside
  Type a, b, c, d, or e. (Or describe several at once: "a, b for files 2 and 3, e for the rest")

# ─── Account aliases ────────────────────────────────────────────────
account_alias_prompt: |
  I see these accounts in your data. What would you like to call them on your
  dashboard? You don't have to use the bank's name or your account number —
  pick whatever's clear to you.
  {numbered_account_list_with_default_aliases_in_brackets}

# ─── Currency primary ──────────────────────────────────────────────
primary_currency_prompt: |
  What currency do you want your dashboard to show totals in?
  I see these in your data: {observed_currencies}.
  Default would be {most_frequent_currency}. Type one, or hit enter to accept.

# ─── Normalization decisions ────────────────────────────────────────
normalize_confirm: |
  Your {bank_name} file uses {date_format} dates and shows charges as
  {sign_convention} numbers. {other_bank_name_if_different} does the opposite.
  I'll line them up. Sound right? (yes/no)

# ─── Publishing ─────────────────────────────────────────────────────
publish_announce: |
  I'll put it online behind a passcode I'll create for you. Saving everything
  now…

publish_done: |
  ✓ Your dashboard is live at:
      {url}

  ✓ Your passcode is:
      {passcode}

  Both are saved in a file called .env in your finance folder.
  Ask me "what's my passcode?" any time and I'll read it back.

  ⚠ Save the passcode somewhere you can reach from your phone:
      • Your phone's password manager (1Password, iCloud Keychain,
        Bitwarden, etc.) — I'll wait if you want to do that now.
      • OR I can email both the URL and the passcode to your own email
        so you have them on every device.

  Type "save", "email", or "done".

scrollback_prompt: |
  Want me to clear what's on your screen so the passcode isn't sitting visibly?
  (yes/no/ask later)

# ─── Recovery ───────────────────────────────────────────────────────
delete_confirm: |
  This will remove your dashboard at {url}. Your data here on this laptop
  stays put — only the public page goes away. Confirm? (yes/no)

delete_done: |
  ✓ Done. Your dashboard is no longer online. Your local data is untouched —
  you can publish a new one any time by saying "publish".

rotate_announce: |
  Generating a new passcode for you now…

rotate_done: |
  ✓ Your new passcode is:
      {new_passcode}
  
  The old one no longer works. Anyone using your dashboard right now will be
  asked for the new one.

reset_rules_confirm: |
  This will replace your current categorization rules with the starter set.
  I'll back up your current ones first, so we can put them back if needed.
  Confirm? (yes/no)

reset_rules_done: |
  ✓ Done. Starter rules restored. I backed up your old ones to {backup_path}.
  Re-running categorization now — give me a moment.

what_passcode: |
  Your passcode is: {passcode}
  Saved in .env in your finance folder. Your dashboard URL is: {url}

what_url: |
  Your dashboard is at: {url}
  Type "what's my passcode?" if you need that too.

share_with_email_prompt: |
  Got it — what's their email address?

share_with_done: |
  ✓ I've opened your email with the URL and passcode pre-filled to {recipient}.
  I also copied the same to your clipboard if you'd rather paste it somewhere
  else. Click send when you're ready.

backup_announce: |
  Backing up your settings (categorization rules, account names, dashboard
  link). I'll lock the backup with a one-time password — pick something you'll
  remember.

backup_done: |
  ✓ Saved to your Desktop: {backup_path}
  Keep this somewhere safe (cloud drive, USB stick, etc.). To use it on a
  new computer, install the workspace there first, then say "restore from
  backup" and point me at this file.

restore_announce: |
  Where's your backup file? Drag it into this window or paste the path.

restore_done: |
  ✓ Restored your settings. Reconnecting to your existing dashboard…

wipe_confirm_first: |
  This will:
    • Delete your dashboard at {url}
    • Erase your sorted files, categorization rules, FX cache, and dashboard
      link from this computer
    • Keep the install itself, so you can drop new files in fresh

  Your original files in your inbox folder are NOT touched. You'll need to
  re-drop them if you want to start over.

  Are you sure? (Type "yes I'm sure" to continue.)

wipe_confirm_second: |
  Last chance — this can't be undone. Type "yes wipe everything".

wipe_done: |
  ✓ Done. Your dashboard is offline and your local data is cleared.
  Drop new files into the inbox folder and say "build my report" to start
  fresh.

# ─── Feedback ───────────────────────────────────────────────────────
feedback_prompt: |
  Tell me what's on your mind. I'll send it to your advisor. Anything from
  a one-line note to a longer message — whatever you want to say.

feedback_context_prompt: |
  Want me to attach any anonymous context? Either makes it easier for your
  advisor to act on:
    (a) just the message
    (b) message + skill version, OS, last refresh date
    (c) message + (b) + last sanity-gate summary (only top-level totals,
        no transactions)
  Type a, b, or c.

feedback_done: |
  ✓ Done. Your feedback has been:
      • Saved on your laptop at {local_path}
      • Sent to your advisor's email (your email client should have opened)
      {if_endpoint_set: "      • Sent directly to your advisor's feedback channel"}
  Click send in your email if you want it to go that way too.

# ─── Support bundle ────────────────────────────────────────────────
support_bundle_announce: |
  Putting together what your advisor needs to help. Give me a moment.

support_bundle_done: |
  ✓ Done. Three ways to get this to your advisor — pick whichever works:

    • I just opened your email with everything filled in. Click send.
    • I copied the same text to your clipboard — paste it into any email
      or message.
    • The bundle is also saved at {desktop_path} if you'd rather attach
      the file directly.

  The link expires in 7 days, so don't sit on it too long.

# ─── Errors (generic) ──────────────────────────────────────────────
error_generic: |
  Something didn't work. I've written a report on this laptop with what
  failed and what step we were on (no transactions, no account numbers,
  no names — just the technical bits).
  
  Want me to put together what your advisor needs? It'll take 30 seconds.
  (yes/no)

error_offering_support: |
  Saying yes will:
    • Save a redacted report to your Desktop
    • Upload it as a one-time password-protected link
    • Open your email with the link + temporary passcode pre-filled to
      your advisor

  You can review it before sending.
```
