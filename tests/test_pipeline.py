#!/usr/bin/env python3
"""End-to-end regression tests for the Finance Clarity pipeline.

Locks in everything that works today against the demo kit, so future
enhancements (chart libraries, analytics, design changes) can ship without
silently breaking categorization, sanity floors, or the publish flow.

Run:
    python3 tests/test_pipeline.py

Exit 0 on success, non-zero on any failure. CI runs this on every PR.

Tests, in order:
  1. Demo kit generates expected files.
  2. classify.py sorts demo files into the right buckets, OP-1 catches the
     payslip even though it's named in a way that could go to bank-transactions.
  3. dedupe.py finds the Q3 100% overlap.
  4. normalize.py produces the canonical CSV with expected row counts +
     correctly-signed brokerage rows.
  5. categorize.py applies starter rules + transfer detector pairs all 4
     quarterly transfers.
  6. sanity.py runs hard floors (none should trip on demo data) and writes
     sanity_confirmed.json.
  7. build_site.py renders index.html with all expected DOM markers + the
     dashboard JSON payload has the expected schema and totals.
  8. OP-4 invariant: build_site.py refuses to run without sanity_confirmed.

The publish step (which makes real network calls) is NOT exercised here.
That's a separate manual step.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "skill" / "scripts"
DEMO_DATA = REPO / "demo-kit" / "data"


def run_script(script: str, *args: str, env_extra: dict | None = None,
               check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Invoke a skill script in a subprocess. Auto-adds FCB_WORKSPACE if set."""
    cmd = [sys.executable if script.endswith(".py") else "/bin/bash",
           str(SCRIPTS / script), *args]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd, capture_output=capture, text=True, check=check, env=env, timeout=180,
    )


# ── Test base: every test gets a fresh tmp workspace pre-loaded with demo ────
class PipelineTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fcb-test-"))
        cls.workspace = cls.tmpdir / "workspace"
        cls.workspace.mkdir()
        (cls.workspace / "inbox").mkdir()
        # Seed inbox with the demo kit
        if not DEMO_DATA.exists():
            raise RuntimeError(f"demo-kit data missing at {DEMO_DATA} — run demo-kit/build_demo.py first")
        for f in DEMO_DATA.iterdir():
            if f.is_file():
                shutil.copy2(f, cls.workspace / "inbox" / f.name)
        cls.env = {"FCB_WORKSPACE": str(cls.workspace)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)


# ── 0. Demo kit sanity ────────────────────────────────────────────────────────
class TestDemoKit(unittest.TestCase):
    def test_expected_files_exist(self):
        expected = {
            "demo_checking_2025.csv", "demo_brokerage_2025.csv",
            "duplicate_q3_checking.csv", "paystub_jan_2025.pdf",
            "tax_assessment_2024.pdf", "amazon_orders_2025.pdf",
            "mystery_scan.pdf",
        }
        actual = {p.name for p in DEMO_DATA.iterdir() if p.is_file()}
        self.assertEqual(expected, actual,
            f"demo-kit files mismatch: missing={expected - actual}, extra={actual - expected}")


# ── 1. Classify ───────────────────────────────────────────────────────────────
class TestClassify(PipelineTestBase):
    def test_classify_routes_files_correctly(self):
        run_script("classify.py", env_extra=self.env)
        ws = self.workspace
        # Bank transactions
        bank = {p.name for p in (ws / "01_bank_transactions").iterdir()}
        self.assertIn("demo_checking_2025.csv", bank)
        self.assertIn("demo_brokerage_2025.csv", bank)
        self.assertIn("duplicate_q3_checking.csv", bank)
        # Payslips
        payslips = {p.name for p in (ws / "02_payslips").iterdir()}
        self.assertIn("paystub_jan_2025.pdf", payslips,
            "OP-1: payslip should land in 02_payslips, not be opened by the pipeline")
        # Tax
        ref = {p.name for p in (ws / "04_reference_docs").iterdir()}
        self.assertIn("tax_assessment_2024.pdf", ref)
        # Amazon
        az = {p.name for p in (ws / "03_amazon_orders").iterdir()}
        self.assertIn("amazon_orders_2025.pdf", az)
        # Mystery scan → 05_other (no text layer)
        other = {p.name for p in (ws / "05_other").iterdir()}
        self.assertIn("mystery_scan.pdf", other,
            "no-OCR rule: image-only PDFs land in 05_other, not auto-OCRed")

    def test_inbox_emptied_after_classify(self):
        leftovers = [p for p in (self.workspace / "inbox").iterdir() if p.is_file() and not p.name.startswith(".")]
        self.assertEqual(leftovers, [], "inbox should be empty after classify")


# ── 2. Dedupe ─────────────────────────────────────────────────────────────────
class TestDedupe(PipelineTestBase):
    def test_dedupe_catches_q3_overlap(self):
        run_script("classify.py", env_extra=self.env)
        result = run_script("dedupe.py", "--json", env_extra=self.env)
        report = json.loads(result.stdout)
        overlap = report["dedup_content_overlap"]
        self.assertEqual(len(overlap), 1, "expected exactly 1 overlap pair")
        files = sorted([overlap[0]["file_a"], overlap[0]["file_b"]])
        self.assertEqual(files, ["demo_checking_2025.csv", "duplicate_q3_checking.csv"])
        self.assertEqual(overlap[0]["overlap_pct"], 100.0)


# ── 3. Normalize ──────────────────────────────────────────────────────────────
class TestNormalize(PipelineTestBase):
    def test_normalize_produces_canonical_csv(self):
        run_script("classify.py", env_extra=self.env)
        run_script("normalize.py", env_extra=self.env)
        out = self.workspace / "pipeline" / "output" / "transactions_normalized.csv"
        self.assertTrue(out.exists(), "transactions_normalized.csv should exist")
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        self.assertGreater(len(rows), 400, "expected ~519 rows from demo data")
        self.assertLess(len(rows), 600)
        self.assertEqual(set(rows[0].keys()),
            {"date", "description", "amount", "currency", "account", "source_file", "source_row"})

    def test_brokerage_signs_correct(self):
        """Brokerage: dividends + transfers in are POSITIVE; buys are NEGATIVE."""
        run_script("classify.py", env_extra=self.env)
        run_script("normalize.py", env_extra=self.env)
        out = self.workspace / "pipeline" / "output" / "transactions_normalized.csv"
        brk = [r for r in csv.DictReader(out.open()) if r["account"] == "Brokerage"]
        self.assertGreaterEqual(len(brk), 10, "expected ≥10 brokerage rows")
        pos = sum(1 for r in brk if float(r["amount"]) > 0)
        neg = sum(1 for r in brk if float(r["amount"]) < 0)
        self.assertGreater(pos, neg, "brokerage should have more positives (dividends + transfers) than negatives (buys)")
        # Dividends should be positive
        divs = [r for r in brk if "DIVIDEND" in r["description"]]
        self.assertTrue(divs and all(float(r["amount"]) > 0 for r in divs),
            "DIVIDEND rows must be positive (inflow)")
        # Buys should be negative
        buys = [r for r in brk if r["description"].startswith("BUY")]
        self.assertTrue(buys and all(float(r["amount"]) < 0 for r in buys),
            "BUY rows must be negative (outflow)")


# ── 4. Categorize ─────────────────────────────────────────────────────────────
class TestCategorize(PipelineTestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        run_script("classify.py", env_extra=cls.env)
        run_script("normalize.py", env_extra=cls.env)
        run_script("categorize.py", env_extra=cls.env)

    def test_tagged_csv_has_expected_categories(self):
        out = self.workspace / "pipeline" / "output" / "transactions_tagged.csv"
        self.assertTrue(out.exists())
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        cats = {r["category"] for r in rows}
        # A few categories we know should appear from the demo data
        for expected in ("Income", "Housing", "Groceries", "Restaurants", "Transport",
                         "Subscriptions", "Insurance"):
            self.assertIn(expected, cats, f"expected category {expected!r} not found")

    def test_uncategorized_rate_below_15pct(self):
        out = self.workspace / "pipeline" / "output" / "transactions_tagged.csv"
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        relevant = [r for r in rows if r["category"] not in ("EXCLUDE", "TRANSFER")]
        uncat = sum(1 for r in relevant if r["category"] == "Uncategorized")
        pct = uncat / len(relevant) * 100
        self.assertLess(pct, 15.0,
            f"Uncategorized rate {pct:.1f}% — starter rules should cover ≥85% of demo data")

    def test_all_four_quarterly_transfers_paired(self):
        """Demo kit has 4 quarterly transfers (Mar, Jun, Sep, Dec). All should pair."""
        out = self.workspace / "pipeline" / "output" / "transactions_tagged.csv"
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        transfers = [r for r in rows if r["category"] == "TRANSFER"]
        # 4 outflows from checking + 4 inflows to brokerage = 8 paired rows
        self.assertEqual(len(transfers), 8, f"expected 8 paired transfer rows, got {len(transfers)}")

    def test_monthly_actuals_pivot_exists(self):
        out = self.workspace / "pipeline" / "output" / "monthly_actuals.csv"
        self.assertTrue(out.exists())
        rows = list(csv.reader(out.open(encoding="utf-8")))
        self.assertEqual(len(rows), 13, "expected header + 12 months for 2025 demo data")


# ── 5. Sanity floors (OP-12) + gate (OP-4) ────────────────────────────────────
class TestSanity(PipelineTestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        run_script("classify.py", env_extra=cls.env)
        run_script("normalize.py", env_extra=cls.env)
        run_script("categorize.py", env_extra=cls.env)

    def test_no_floors_trip_on_demo_data(self):
        result = run_script("sanity.py", "--json", env_extra=self.env)
        report = json.loads(result.stdout)
        self.assertEqual(report["violations"], [],
            f"demo data should produce no floor violations; got: {report['violations']}")

    def test_sanity_summary_has_expected_shape(self):
        result = run_script("sanity.py", "--json", env_extra=self.env)
        report = json.loads(result.stdout)
        s = report["summary"]
        for k in ("rows_total", "income_avg_per_month", "spend_avg_per_month",
                  "net_avg_per_month", "savings_rate_pct", "top_10_categories",
                  "biggest_5_transactions", "n_months", "date_range"):
            self.assertIn(k, s, f"summary missing key {k!r}")
        self.assertEqual(s["n_months"], 12)
        self.assertEqual(s["date_range"], ["2025-01-01", "2025-12-31"])

    def test_op4_build_refuses_without_sanity_confirmed(self):
        """OP-4: build_site.py must refuse to run without sanity_confirmed.json."""
        # Make sure the file is NOT present
        confirmed = self.workspace / "pipeline" / "output" / "sanity_confirmed.json"
        if confirmed.exists():
            confirmed.unlink()
        result = run_script("build_site.py", env_extra=self.env, check=False)
        self.assertNotEqual(result.returncode, 0,
            "build_site should fail without sanity_confirmed.json")
        self.assertIn("sanity", (result.stderr + result.stdout).lower())


# ── 6. Build site ─────────────────────────────────────────────────────────────
class TestBuildSite(PipelineTestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        run_script("classify.py", env_extra=cls.env)
        run_script("normalize.py", env_extra=cls.env)
        run_script("categorize.py", env_extra=cls.env)
        run_script("sanity.py", "--auto-confirm", env_extra=cls.env)
        run_script("build_site.py", env_extra=cls.env)

    def test_site_artifacts_present(self):
        site = self.workspace / "site"
        self.assertTrue((site / "index.html").exists())
        self.assertTrue((site / "downloads" / "transactions_tagged.csv").exists())
        self.assertTrue((site / "downloads" / "monthly_actuals.csv").exists())
        self.assertTrue((site / "assets" / "brand" / "logo-blue.png").exists(),
            "brand assets should be copied (symlink dereferenced)")

    def test_no_unreplaced_template_placeholders(self):
        html = (self.workspace / "site" / "index.html").read_text()
        unreplaced = re.findall(r"\{\{[^}]+\}\}", html)
        self.assertEqual(unreplaced, [],
            f"every {{{{ ... }}}} placeholder should be rendered; leftover: {unreplaced}")

    def test_dashboard_data_payload_schema(self):
        html = (self.workspace / "site" / "index.html").read_text()
        m = re.search(r'<script id="dashboard-data"[^>]*>(.+?)</script>', html, re.DOTALL)
        self.assertIsNotNone(m, "dashboard-data <script> block missing")
        d = json.loads(m.group(1))
        for k in ("currency", "months", "by_month_in", "by_month_out",
                  "category_totals", "kpis", "transactions"):
            self.assertIn(k, d, f"dashboard JSON missing key {k!r}")
        # KPI sanity
        kpis = d["kpis"]
        self.assertEqual(kpis["n_months"], 12)
        self.assertGreater(kpis["income_total"], 50000)
        self.assertGreater(kpis["spend_total"], 50000)
        # Category totals don't include Income (excluded so it doesn't dwarf the chart)
        cats = {c for c, _ in d["category_totals"]}
        self.assertNotIn("Income", cats, "Income should be excluded from spend-by-category")

    def test_site_has_required_dom_sections(self):
        """Lock in the dashboard structure so chart-library swaps don't break the build."""
        html = (self.workspace / "site" / "index.html").read_text()
        for marker in [
            'class="brand"',                # branded header
            'kpi-grid',                     # KPI cards
            'id="chart-cashflow"',          # cashflow chart container
            'id="chart-category"',          # category chart container
            'id="chart-monthly"',           # monthly stacked chart
            'id="tx-table"',                # transactions table
            'class="downloads"',            # downloads block
            'rel="icon"',                   # favicon
            "Passport to Wealth",            # brand name
            'aria-labelledby="insights-h"', # insights section
            'class="methodology"',          # methodology section
            'github.com/rafaeldavid/passporttowealth',  # GitHub footer link
            'passporttowealth.com',         # main site footer link
        ]:
            self.assertIn(marker, html, f"required DOM marker missing: {marker!r}")

    def test_chartjs_bundled_inline(self):
        """Chart.js must be bundled, not referenced via CDN (OP — works offline)."""
        html = (self.workspace / "site" / "index.html").read_text()
        self.assertIn('src="assets/js/chart.umd.min.js"', html, "chart.js script src missing")
        chart_js = self.workspace / "site" / "assets" / "js" / "chart.umd.min.js"
        self.assertTrue(chart_js.exists(), "chart.umd.min.js must be copied to site/")
        # Sanity-check it's actually Chart.js
        head = chart_js.read_text(encoding="utf-8", errors="ignore")[:200]
        self.assertIn("Chart.js", head, "expected Chart.js header in bundled file")

    def test_no_external_cdn_references(self):
        """Site must work offline — no external CSS/JS pulls."""
        html = (self.workspace / "site" / "index.html").read_text()
        # Scripts/links pointing to external hosts (excluding mailto:, the
        # noopener external links in the footer, and inline data: URIs)
        import re as r
        srcs = r.findall(r'(?:src|href)="(https?://[^"]+)"', html)
        # GitHub + passporttowealth.com footer links are intentional (external nav).
        cdn_only = [u for u in srcs
                    if not u.startswith(("https://github.com", "https://www.passporttowealth.com"))]
        self.assertEqual(cdn_only, [], f"unexpected external resources: {cdn_only}")

    def test_dashboard_data_includes_polish_fields(self):
        """The new payload fields the polished template depends on."""
        html = (self.workspace / "site" / "index.html").read_text()
        m = re.search(r'<script id="dashboard-data"[^>]*>(.+?)</script>', html, re.DOTALL)
        d = json.loads(m.group(1))
        for k in ("cashflow_3mo_avg", "monthly_by_category", "top_categories_for_monthly",
                  "insights", "methodology", "accounts"):
            self.assertIn(k, d, f"polished dashboard JSON missing key {k!r}")
        # Rolling avg has the same length as months
        self.assertEqual(len(d["cashflow_3mo_avg"]), len(d["months"]))
        # Insights is a list of HTML-safe strings
        self.assertIsInstance(d["insights"], list)
        self.assertGreater(len(d["insights"]), 2,
            "expected at least 3 auto-generated insights from demo data")
        # Methodology is a list of [label, value] pairs
        self.assertIsInstance(d["methodology"], list)
        self.assertGreater(len(d["methodology"]), 5)
        # KPIs include per-month averages
        for k in ("income_avg_per_month", "spend_avg_per_month", "net_avg_per_month"):
            self.assertIn(k, d["kpis"])

    def test_dashboard_polish_p0_markers(self):
        """Lock in the P0 visual lifts from the design audit so a casual edit
        can't quietly walk them back. These are the floor of perceptual polish."""
        html = (self.workspace / "site" / "index.html").read_text()
        # P0-1: KPI value uses a confident clamp() — min ≥ 24px (lifted from
        # the original 24px-min/32px-max). Max capped at 36px after the first
        # iteration overflowed at 44px on a $XX,XXX value in a 220px grid cell.
        self.assertRegex(html, r"\.kpi \.value \{[^}]*font-size:\s*clamp\(2[4-9]px",
            "P0-1: KPI value font-size should clamp from ≥24px")
        # KPI overflow guards: tabular-nums + nowrap + min-width:0 on .kpi.
        self.assertRegex(html, r"\.kpi\s*\{[^}]*min-width:\s*0",
            "min-width:0 on .kpi prevents grid-item overflow")
        self.assertRegex(html, r"\.kpi \.value \{[^}]*white-space:\s*nowrap",
            ".kpi .value should be white-space:nowrap so $-prefixed numbers don't wrap")
        # P0-2: hero-band wraps hero+KPI strip outside <main>.
        self.assertIn('class="hero-band"', html, "P0-2: hero-band wrapper missing")
        self.assertIn(".hero-band", html, "P0-2: hero-band CSS rule missing")
        self.assertIn('class="kpi-band"', html, "P0-2: kpi-band markup missing")
        # P0-3: section eyebrows — every <section> > h2 gets the navy tab.
        self.assertIn("section > h2", html, "P0-3: section eyebrow rule missing")
        self.assertIn("section > h2::before", html,
            "P0-3: section eyebrow ::before tab missing")
        # P0-4: thousand-suffix formatter for chart axes.
        self.assertIn("const fmShort", html,
            "P0-4: fmShort formatter for axis ticks missing")
        # All three charts use fmShort (cashflow, category, monthly stacked).
        self.assertGreaterEqual(html.count("fmShort(v)"), 3,
            "P0-4: all 3 charts should use fmShort for axis ticks")

    def test_no_scrollintoview_in_observer_paths(self):
        """REGRESSION: Element.scrollIntoView from inside an IntersectionObserver
        callback (or any auto-scroll loop) caused a feedback loop where the
        page kept fighting the user's scroll. Lock it out — use scrollLeft on
        a specific element instead. See dev/SMOKE_CHECKS.md.

        If you have a legitimate need for scrollIntoView (e.g. user-initiated
        click handler), wrap it with a comment containing 'scrollIntoView OK'."""
        html = (self.workspace / "site" / "index.html").read_text()
        # Allow occurrences explicitly marked as audited; allow comment-only
        # mentions (// or /* prefix). We only fail on actual function calls
        # (.scrollIntoView( or scrollIntoView( with no comment prefix).
        suspicious_lines = []
        call_pattern = re.compile(r'\bscrollIntoView\s*\(')
        for i, line in enumerate(html.splitlines(), 1):
            stripped = line.strip()
            # Skip lines whose meaningful content is just a comment
            if stripped.startswith(("//", "*", "/*")):
                continue
            if "scrollIntoView OK" in line:
                continue
            if call_pattern.search(line):
                suspicious_lines.append((i, stripped))
        self.assertFalse(suspicious_lines,
            f"scrollIntoView call(s) without 'scrollIntoView OK' marker — "
            f"these caused the scroll-fighting bug. Lines: {suspicious_lines}")

    def test_no_overflow_hidden_on_html_or_body(self):
        """REGRESSION: an overflow:hidden on html/body fully disables scroll.
        Lock it out — only descendants may use overflow."""
        html = (self.workspace / "site" / "index.html").read_text()
        # Allow occurrences in selectors targeting children (e.g. .table-card { overflow: hidden })
        for pattern in (r"\bhtml\s*\{[^}]*overflow\s*:\s*hidden",
                        r"\bbody\s*\{[^}]*overflow\s*:\s*hidden"):
            self.assertIsNone(re.search(pattern, html),
                f"found overflow:hidden on html/body — kills page scroll: pattern {pattern!r}")

    def test_feedback_widget_framed_as_product_feedback(self):
        """REGRESSION: feedback was reframed from 'send to your advisor' to
        'help improve the product'. Lock in the new framing so future copy
        edits don't slip back to advisor-communication framing."""
        html = (self.workspace / "site" / "index.html").read_text()
        # Required new framing
        for required in ["Help improve this dashboard", "Help improve this",
                         "What could be better", "team that builds"]:
            self.assertIn(required, html, f"product-feedback framing missing: {required!r}")
        # Phrases that signal the OLD framing (drawer copy only — not the
        # privacy disclosure or footer where 'advisor' is still correct).
        # We extract the drawer body specifically.
        drawer = re.search(r'<aside[^>]*id="fb-drawer"[^>]*>(.+?)</aside>', html, re.DOTALL)
        self.assertIsNotNone(drawer, "feedback drawer markup missing")
        drawer_html = drawer.group(1)
        for banned in ["your advisor will see", "Send feedback to your advisor",
                       "send to your advisor"]:
            self.assertNotIn(banned, drawer_html,
                f"old advisor-communication framing snuck back into the drawer: {banned!r}")

    def test_section_nav_present_and_anchors_match_section_ids(self):
        """Every nav link must point to an actual section id on the page."""
        html = (self.workspace / "site" / "index.html").read_text()
        self.assertIn('<nav class="sections"', html, "sticky section nav missing")
        # Extract nav hrefs (#anchor) and section IDs
        nav_anchors = set(re.findall(r'<nav class="sections"[^>]*>(.*?)</nav>', html, re.DOTALL)[0]
                          .__class__.__call__('').join([]))  # noop placeholder, replaced below
        nav_block = re.search(r'<nav class="sections"[^>]*>(.*?)</nav>', html, re.DOTALL).group(1)
        nav_anchors = set(re.findall(r'href="#([\w-]+)"', nav_block))
        section_ids = set(re.findall(r'<section[^>]*\bid="([\w-]+)"', html))
        section_ids |= set(re.findall(r'<\w+[^>]*\bid="([\w-]+)"\s+aria-labelledby', html))
        section_ids |= set(re.findall(r'\bid="(overview)"', html))
        missing = nav_anchors - section_ids
        self.assertFalse(missing, f"nav links point at nonexistent section IDs: {missing}")
        # Common-sense floor: at least 6 nav items
        self.assertGreaterEqual(len(nav_anchors), 6, f"expected ≥6 nav items; got {nav_anchors}")

    def test_inter_font_bundled(self):
        """Inter woff2 files must be in site/assets/fonts and referenced by @font-face."""
        html = (self.workspace / "site" / "index.html").read_text()
        for w in (400, 500, 600, 700):
            f = self.workspace / "site" / "assets" / "fonts" / f"Inter-{w}.woff2"
            self.assertTrue(f.exists(), f"missing bundled font: {f.name}")
            self.assertGreater(f.stat().st_size, 5000, f"{f.name} suspiciously small ({f.stat().st_size} bytes)")
            self.assertIn(f"Inter-{w}.woff2", html, f"@font-face for weight {w} not referenced in HTML")

    def test_feedback_widget_present(self):
        """Floating button + drawer + form."""
        html = (self.workspace / "site" / "index.html").read_text()
        for marker in ['id="fb-open"', 'id="fb-drawer"', 'id="fb-text"', 'id="fb-submit"',
                       'class="fb-fab"', 'aria-modal="true"']:
            self.assertIn(marker, html, f"feedback widget marker missing: {marker!r}")

    def test_feedback_config_in_dashboard_data(self):
        """Dashboard JSON exposes the feedback endpoint config (so the
        in-page form knows where to POST). REGRESSION: at least one of
        (endpoint_url, advisor_email) must be set, otherwise the widget
        shows 'no delivery channel configured' and the user can't send
        anything. The skill's config.example.yaml is the floor."""
        html = (self.workspace / "site" / "index.html").read_text()
        m = re.search(r'<script id="dashboard-data"[^>]*>(.+?)</script>', html, re.DOTALL)
        d = json.loads(m.group(1))
        self.assertIn("feedback", d, "dashboard JSON missing 'feedback' block")
        fb = d["feedback"]
        for k in ("advisor_id", "skill_version", "endpoint_url"):
            self.assertIn(k, fb)
        # At least one delivery channel must exist so the widget never
        # shows the "no channel configured" error to a real user.
        self.assertTrue(
            fb.get("endpoint_url") or fb.get("advisor_email"),
            "feedback widget would have no delivery channel — at least one of "
            "endpoint_url or advisor_email must be set in config.example.yaml")

    def test_transactions_table_default_pagesize_10(self):
        """Default page size is 10 rows + show-more flow."""
        html = (self.workspace / "site" / "index.html").read_text()
        # The select has '10 rows' selected by default
        self.assertRegex(html, r'<option value="10"\s+selected', "default page size should be 10")
        # Time-period filter present with the expected values
        for v in ('30d', '90d', '6mo', 'ytd'):
            self.assertIn(f'value="{v}"', html, f"time-period filter missing value {v}")
        # Show-more button + per-table download button present
        self.assertIn('id="tx-more"', html)
        self.assertIn('id="tx-download"', html)
        self.assertIn('id="tx-pagesize"', html)

    def test_insights_are_factual_not_advisory(self):
        """OP — insights section must never give advice. Catch common advisory phrasing."""
        html = (self.workspace / "site" / "index.html").read_text()
        m = re.search(r'<script id="dashboard-data"[^>]*>(.+?)</script>', html, re.DOTALL)
        d = json.loads(m.group(1))
        banned_phrases = ["you should", "you must", "you ought", "we recommend",
                          "I recommend", "consider", "think about", "try to", "stop"]
        for insight in d["insights"]:
            lower = insight.lower()
            for phrase in banned_phrases:
                self.assertNotIn(phrase, lower,
                    f"insight contains advisory phrasing {phrase!r}: {insight!r}")


# ── 7. Total transactions across all the test classes ────────────────────────
class TestPipelineHealth(unittest.TestCase):
    """Smoke-level sanity that the pipeline scripts themselves are importable
    and the shared lib doesn't have basic syntax errors."""

    def test_lib_importable(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import _lib  # noqa: F401
        finally:
            sys.path.remove(str(SCRIPTS))

    def test_all_scripts_executable(self):
        for name in ("classify.py", "dedupe.py", "normalize.py", "fx_fetch.py",
                     "categorize.py", "sanity.py", "build_site.py"):
            p = SCRIPTS / name
            self.assertTrue(p.exists(), f"script missing: {name}")
            self.assertTrue(os.access(p, os.X_OK), f"script not executable: {name}")

    def test_installer_no_more_stub_markers(self):
        """The installer used to emit '[STUB]' lines for the actual install
        actions (Homebrew, Python, Claude Code, workspace, etc). After
        finishing the end-to-end implementation, none of those should remain."""
        cmd = (REPO / "installer" / "Welcome.command").read_text(encoding="utf-8")
        # Two specific stub lines we want to confirm are gone:
        for banned in ("[STUB] This step would install",
                       "[STUB] Would launch",
                       "[STUB] Would write key",
                       "[STUB] Would open https://here.now/signup",
                       "[STUB] Would create",
                       "[STUB] Would run the diagnostic"):
            self.assertNotIn(banned, cmd, f"installer still has stub: {banned!r}")

    def test_installer_auth_choice_is_two_options(self):
        """User feedback: Claude Pro and Max are both subscriptions —
        collapse the auth picker to 2 options (paid subscription vs API key)
        instead of 3 (Pro vs Max vs API key)."""
        cmd = (REPO / "installer" / "Welcome.command").read_text(encoding="utf-8")
        # The simplified prompt
        self.assertIn("Type 1 or 2:", cmd, "auth prompt should be 2-choice now")
        self.assertNotIn("Type 1, 2, or 3:", cmd, "old 3-choice prompt should be gone")
        # The new copy frames choice 1 as 'Paid subscription' (covers Pro AND Max)
        self.assertIn("Paid subscription", cmd, "choice 1 should say 'Paid subscription'")
        # The case dispatch should be on (1, 2) not (1, 2, 3)
        self.assertNotIn("1|2)", cmd, "old Pro/Max combined branch should be gone")

    def test_installer_creates_launcher_and_desktop_shortcut(self):
        """Step 5 must write .skill-launcher.sh into the workspace (used by the
        B9.2 seamless handoff) AND drop START-HERE.command on the Desktop."""
        cmd = (REPO / "installer" / "Welcome.command").read_text(encoding="utf-8")
        self.assertIn('LAUNCHER="$WS/.skill-launcher.sh"', cmd,
            "Step 5 must write the workspace launcher")
        self.assertIn('DESKTOP_SHORTCUT="$HOME/Desktop/START-HERE.command"', cmd,
            "Step 5 must drop the Desktop shortcut")
        self.assertIn('chmod +x "$LAUNCHER"', cmd, "launcher must be executable")
        self.assertIn('chmod +x "$DESKTOP_SHORTCUT"', cmd, "shortcut must be executable")
        # Launcher must activate the venv + export ANTHROPIC_API_KEY if set
        self.assertIn('source "\\$WS/.venv/bin/activate"', cmd,
            "launcher must source the workspace venv")
        self.assertIn('ANTHROPIC_API_KEY=', cmd,
            "launcher must export ANTHROPIC_API_KEY for the API-key auth path")

    def test_installer_step6_diagnostic_replaces_stub(self):
        """Step 6 used to be '[STUB] Would run the diagnostic'. Should now do
        actual checks, count failures, and exit non-zero on any red."""
        cmd = (REPO / "installer" / "Welcome.command").read_text(encoding="utf-8")
        self.assertIn("DIAGNOSTIC_FAILS=0", cmd,
            "Step 6 should track diagnostic failure count")
        # At least 8 distinct diagnostic checks
        self.assertGreaterEqual(cmd.count("check ") + cmd.count("check_file "), 8,
            "Step 6 should run at least 8 diagnostic checks")
        # And exit non-zero on red
        self.assertIn("if [ \"$DIAGNOSTIC_FAILS\" -gt 0 ]", cmd,
            "Step 6 should branch on diagnostic-fail count")

    def test_installer_offers_start_now_handoff(self):
        """B9.2 invariant: at end of install, ask 'Want to start now?'
        and exec/launch the workflow if user says yes — instead of forcing
        them to find and double-click START-HERE on the Desktop. Desktop
        shortcut still exists for re-entry sessions 2+; just not the first-
        run handoff."""
        cmd = (REPO / "installer" / "Welcome.command").read_text(encoding="utf-8")
        ps1 = (REPO / "installer" / "Welcome.ps1").read_text(encoding="utf-8")
        self.assertIn("Want to start now?", cmd,
            "Welcome.command must offer the seamless start-now prompt (B9.2)")
        self.assertIn("Want to start now?", ps1,
            "Welcome.ps1 must offer the seamless start-now prompt (B9.2)")
        # Mac: must close fd 3 before exec to release the install-log handle
        self.assertIn("exec 3>&-", cmd,
            "Welcome.command must release log fd before exec to avoid leak")
        self.assertIn('exec "$WORKSPACE_LAUNCHER"', cmd,
            "Welcome.command must exec into the workspace launcher")
        # Windows: must Start-Process the launcher
        self.assertIn("Start-Process -FilePath $WorkspaceLauncher", ps1,
            "Welcome.ps1 must Start-Process the workspace launcher")

    def test_installer_has_pause_gates_and_auto_flag(self):
        """B9.3 invariant: paced output + Press-Enter gates between sections.
        Without these, pre-flight ✓s flash by faster than humans can read.
        Both Mac (.command, bash) and Windows (.ps1) installers must:
        - define paced sub-step helper (ok_paced / Write-OkPaced)
        - define a pause helper that's TTY-guarded
        - support an --auto / -Auto flag to skip pacing for CI
        - actually CALL the pause helper at least 2× between major sections."""
        cmd = (REPO / "installer" / "Welcome.command").read_text(encoding="utf-8")
        ps1 = (REPO / "installer" / "Welcome.ps1").read_text(encoding="utf-8")

        # Mac: helpers + gates + --auto
        self.assertIn("ok_paced()", cmd, "Welcome.command missing ok_paced helper")
        self.assertIn("pause_for_user()", cmd, "Welcome.command missing pause_for_user helper")
        self.assertGreaterEqual(cmd.count("pause_for_user"), 4,
            "Welcome.command should INVOKE pause_for_user at ≥2 transition points "
            "(plus the function definition + check, that's ≥4 occurrences)")
        self.assertIn("--auto", cmd, "Welcome.command must support --auto flag")
        self.assertIn("AUTO_MODE", cmd, "Welcome.command must implement --auto bypass")

        # Windows: helpers + gates + -Auto
        self.assertIn("Write-OkPaced", ps1, "Welcome.ps1 missing Write-OkPaced helper")
        self.assertIn("Pause-ForUser", ps1, "Welcome.ps1 missing Pause-ForUser helper")
        self.assertGreaterEqual(ps1.count("Pause-ForUser"), 4,
            "Welcome.ps1 should INVOKE Pause-ForUser at ≥2 transition points")
        self.assertTrue("-Auto" in ps1 or "--auto" in ps1,
            "Welcome.ps1 must support -Auto / --auto flag")
        self.assertIn("AutoMode", ps1, "Welcome.ps1 must implement Auto bypass")

    def test_installer_uses_working_herenow_url(self):
        """B9.7 regression: here.now has no /signup path — that URL 404s.
        The signup is via the homepage's 'Sign in' button (which doubles as
        sign-up). Don't direct users to a 404."""
        cmd = (REPO / "installer" / "Welcome.command").read_text(encoding="utf-8")
        self.assertNotIn("here.now/signup", cmd,
            "https://here.now/signup is a 404 — link the homepage instead")
        self.assertNotIn("here.now/sign-up", cmd,
            "/sign-up also 404s")
        self.assertNotIn("here.now/login", cmd,
            "/login also 404s")
        # The homepage IS valid (200)
        self.assertIn('open "https://here.now/"', cmd,
            "installer should open here.now/ (the working homepage)")

    def test_installer_does_not_auto_open_privacy_hub(self):
        """B9.1 regression: auto-opening privacy.anthropic.com in the browser
        mid-consent-gate snaps focus away from Terminal and confuses users.
        Terminal/Windows-Terminal linkify URLs — let the user click if they
        want to read first."""
        cmd_path = REPO / "installer" / "Welcome.command"
        ps1_path = REPO / "installer" / "Welcome.ps1"
        cmd = cmd_path.read_text(encoding="utf-8")
        ps1 = ps1_path.read_text(encoding="utf-8")
        self.assertNotIn('open "https://privacy.anthropic.com', cmd,
            "Welcome.command must not auto-open the privacy hub (B9.1)")
        self.assertNotIn('Start-Process "https://privacy.anthropic.com', ps1,
            "Welcome.ps1 must not auto-open the privacy hub (B9.1)")
        # Both files must still mention the URL so users know where to look:
        self.assertIn("privacy.anthropic.com", cmd,
            "URL should still be PRINTED for the user to click")
        self.assertIn("privacy.anthropic.com", ps1,
            "URL should still be PRINTED for the user to click")

    def test_progress_helper_silent_when_not_tty(self):
        """B9.5 invariant: the progress() helper must produce zero output
        when stderr isn't a TTY. Tests, CI, and JSON-pipe consumers all
        capture stderr — any \\r-spam would corrupt logs and break parsers."""
        result = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); "
             "from _lib import progress; progress('x', 1, 10); "
             "progress('x', 5, 10); progress('x', 10, 10)"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        self.assertEqual(result.stderr, "",
            f"progress() leaked output to non-TTY stderr: {result.stderr!r}")
        self.assertEqual(result.stdout, "",
            f"progress() should never write to stdout: {result.stdout!r}")

    def test_progress_helper_handles_zero_total(self):
        """progress() with total=0 must be a no-op (no div-by-zero)."""
        sys.path.insert(0, str(SCRIPTS))
        try:
            from _lib import progress
            progress("x", 0, 0)  # should not raise
        finally:
            sys.path.remove(str(SCRIPTS))

    def test_no_utcnow_in_pipeline_scripts(self):
        """B9.6 regression: datetime.utcnow() is deprecated in Python 3.12+ and
        prints a DeprecationWarning that confuses non-technical users running
        the pipeline. Use datetime.now(timezone.utc) instead."""
        for name in ("fx_fetch.py", "sanity.py", "build_site.py", "categorize.py",
                     "normalize.py", "dedupe.py", "classify.py", "_lib.py"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertNotIn(".utcnow(", text,
                f"{name}: datetime.utcnow() is deprecated — use datetime.now(timezone.utc)")


if __name__ == "__main__":
    # Pretty-print the run
    print(f"\nFinance Clarity pipeline regression suite")
    print(f"  repo: {REPO}")
    print(f"  python: {sys.version.split()[0]}")
    print(f"  ts: {datetime.now(timezone.utc).isoformat()}\n")
    unittest.main(verbosity=2)
