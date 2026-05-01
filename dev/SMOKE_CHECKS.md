# Smoke checks — manual UI tests CI cannot run

Why this exists: our regression suite (`tests/test_pipeline.py`) is **static analysis** — it inspects the rendered HTML, asserts markup is correct, asserts JSON payloads have the right shape. It does not load the page in a browser. That gap let a scroll-fighting bug slip into `9a87c0f` (a `scrollIntoView` call inside an IntersectionObserver callback created a feedback loop).

Until we add headless-browser tests (Playwright / Selenium — see `dev/backlog.md`), every change to the dashboard template, charts, navigation, or any piece of front-end JS must be smoke-checked manually before commit. **30 seconds, every time.**

---

## The 30-second smoke check

Run after **any** change to:
- `skill/templates/site/*.html`
- `skill/templates/site/assets/js/*.js`
- `skill/scripts/build_site.py`
- The CSS / chart / interactive code in any of the above

Steps:

1. **Build:** `python3 demo-kit/build_demo.py` (if not already done) → `FCB_WORKSPACE=/tmp/smoke mkdir -p /tmp/smoke/inbox && cp demo-kit/data/* /tmp/smoke/inbox/ && FCB_WORKSPACE=/tmp/smoke bash skill/scripts/refresh.sh --auto-confirm`
2. **Open:** `open /tmp/smoke/site/index.html` (Mac) or `xdg-open` (Linux)
3. **Scroll:** Scroll the whole page top to bottom with the mouse wheel and the trackpad. **The page should scroll smoothly, in one direction, with no fighting.** The nav-strip pill should highlight the section you're on; the strip itself can scroll horizontally to follow but the page should never jump or rebound.
4. **Mobile width:** Resize the browser to 375px wide. Repeat #3. Tap each nav link — it should smooth-scroll to the right section.
5. **Charts:** Hover each chart. Tooltips should appear, formatted as currency. Mobile width: tap to show tooltip.
6. **Transactions table:** Type in the search box, change the time-period dropdown, change a category, click a column header to sort, click "Show more", click "Download CSV" — all should respond instantly without breaking the page.
7. **Feedback widget:** Click the floating "Help improve this" button. Drawer slides in (right on desktop, up from bottom on mobile). Click backdrop to close. Reopen, type a message, hit Send. Status message should appear; if no endpoint is configured the failure message should be honest, not silent.
8. **Methodology section:** Click "How was this dashboard built?" — should expand to show details, click again to collapse.

If any step is wrong, **don't commit until it's fixed.**

---

## Specific anti-patterns that broke the page in past commits

Each of these has a regression test in `tests/test_pipeline.py`. If you find yourself reaching for one of these, add a comment marker explaining why and the test will let it through.

| Pattern | Why it broke things | Test that catches it |
|---|---|---|
| `Element.scrollIntoView` from inside an IntersectionObserver | Vertical-scroll feedback loop — page fights the user. Use manual `scrollLeft` on a specific scrollable element instead. | `test_no_scrollintoview_in_observer_paths` |
| `overflow: hidden` on `html` or `body` | Disables page scroll entirely. Only descendants may use overflow. | `test_no_overflow_hidden_on_html_or_body` |
| Reframing the product-feedback drawer as advisor-communication ("send to your advisor") | The drawer feeds product-improvement signals; advisor questions go through email, not this widget. | `test_feedback_widget_framed_as_product_feedback` |

If you have a legitimate reason to use `scrollIntoView` (e.g. user-initiated click handler), put `// scrollIntoView OK — {reason}` on the same line and the lint will let it through.

---

## What CI runs vs what only the human can see

| Check | Where |
|---|---|
| HTML structure (slots, IDs, links) | `tests/test_pipeline.py` (CI) |
| JSON payload schema | `tests/test_pipeline.py` (CI) |
| Operating-principle invariants (OP-1, OP-4, etc.) | `tests/test_pipeline.py` (CI) |
| **Page actually scrolls** | This doc — manual |
| **Charts actually render** | This doc — manual |
| **Hover tooltips appear** | This doc — manual |
| **Drawer animation feels right** | This doc — manual |
| **Mobile layout doesn't break** | This doc — manual |
| **Filter dropdowns close cleanly** | This doc — manual |

The right long-term fix is Playwright (or a Bun/Puppeteer equivalent) running this checklist as code. Tracked as `H7.1` in the backlog. Until then: this checklist, every time, no exceptions.
