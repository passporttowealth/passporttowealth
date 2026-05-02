# greeting.md

The skill prints this verbatim the first time the user runs `claude` post-install and the inbox is empty. If files are already in the inbox, jump straight to `prompts/sanity_gate.md` after running the build flow.

---

## Greeting (empty inbox)

```
Hi — I'm here to turn your financial files into a private dashboard
only you can see.

Your finance folder is at ~/Documents/my-finances/. Drag your files
into the inbox subfolder there (Spotlight: ⌘+Space → type
my-finances → Enter) — anything financial works:

  • Bank statements (CSVs, PDFs — whatever your bank gives you)
  • Paystubs (I won't read them unless you ask)
  • Tax documents (same)
  • Receipts, Amazon order history, anything else

Don't worry about sorting, deduplicating, or fixing anything first —
I'll do all that. When you're ready, come back here and say
"build my report".

A few things upfront:
  • Your files stay on this laptop. I only put a private web page
    online at the end, locked with a passcode I'll create for you.
  • I won't open paystubs or tax documents unless you tell me to.
  • If anything goes wrong, I'll tell you what to do — you don't
    need to know any of the technical bits.
  • Everything you write to me is also sent to Anthropic to power
    the assistant. You agreed to their terms during install — you
    can review or change those settings any time at
    https://privacy.anthropic.com/.

Got feedback or a suggestion at any point? Just say "I have feedback"
and I'll send it to your advisor.
```

---

## Re-prompt (user said "what now?" / "I'm confused" / "help")

```
No problem. The next step depends on where you are:

  • Haven't put files in yet?
       Drag bank statements, paystubs, anything financial into the
       inbox folder at ~/Documents/my-finances/inbox/. Then say
       "build my report".

  • Files are in but you want to see what I'd do first?
       Say "preview" and I'll list what I see without changing anything.

  • Something feels off?
       Say "I have feedback" or "something's broken" and I'll get help
       to your advisor without you having to debug anything.
```

---

## Inactivity nudge (after 5 minutes idle in greeting)

```
Still here whenever you're ready. There's no clock running. When you've
got files in the inbox, just say "build my report" and we'll go.
```
