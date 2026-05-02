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
            'github.com/passporttowealth/passporttowealth',  # GitHub footer link
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
        """The macOS installer used to emit '[STUB]' lines for actual install
        actions (Homebrew, Python, Claude Code, workspace, etc). After
        finishing the end-to-end implementation, none of those should remain
        in install.sh. Welcome.ps1 (Windows) still has its [STUB]
        markers — the Windows real-install port is tracked separately;
        this test will be tightened once that lands.

        Cosmetic 'v0 skeleton' / 'engagement/development/' leftovers from
        when these files were stubs are banned in BOTH platforms — dry-run
        reported users seeing those lines and asking whether the installer
        was real."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        ps1 = (REPO / "installer" / "legacy" / "Welcome.ps1").read_text(encoding="utf-8")
        # macOS: no [STUB] markers, no cosmetic skeleton/dev-path leftovers
        for banned in ("[STUB] This step would install",
                       "[STUB] Would launch",
                       "[STUB] Would write key",
                       "[STUB] Would open https://here.now/signup",
                       "[STUB] Would create",
                       "[STUB] Would run the diagnostic",
                       "v0 skeleton", "v0 SKELETON", "v0 stub",
                       "engagement/development/"):
            self.assertNotIn(banned, cmd, f"install.sh still has: {banned!r}")
        # Windows: cosmetic-only enforcement until the real-install port lands
        for banned in ("v0 skeleton", "v0 SKELETON", "v0 stub",
                       "engagement/development/"):
            self.assertNotIn(banned, ps1, f"Welcome.ps1 still has: {banned!r}")

    def test_installer_auth_choice_is_two_options(self):
        """User feedback: Claude Pro and Max are both subscriptions —
        collapse the auth picker to 2 options (paid subscription vs API key)
        instead of 3 (Pro vs Max vs API key)."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The simplified prompt
        self.assertIn("Type 1 or 2:", cmd, "auth prompt should be 2-choice now")
        self.assertNotIn("Type 1, 2, or 3:", cmd, "old 3-choice prompt should be gone")
        # The new copy frames choice 1 as 'Paid subscription' (covers Pro AND Max)
        self.assertIn("Paid subscription", cmd, "choice 1 should say 'Paid subscription'")
        # The case dispatch should be on (1, 2) not (1, 2, 3)
        self.assertNotIn("1|2)", cmd, "old Pro/Max combined branch should be gone")

    def test_installer_leaves_no_desktop_artifacts(self):
        """B9.10 — START-HERE.command and the workspace launcher were removed.
        Re-entry is `claude` from any Terminal. The installer must NOT create
        anything on the Desktop or anywhere visible to the user beyond the
        workspace folder itself."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # No Desktop shortcut creation
        self.assertNotIn('"$HOME/Desktop/START-HERE.command"', cmd,
            "must not create a START-HERE shortcut on the Desktop")
        self.assertNotIn('cat > "$DESKTOP_SHORTCUT"', cmd,
            "must not write any Desktop shortcut")
        # No workspace launcher script
        self.assertNotIn('cat > "$LAUNCHER"', cmd,
            "must not create the .skill-launcher.sh wrapper")
        self.assertNotIn('LAUNCHER="$WS/.skill-launcher.sh"', cmd,
            "must not declare the launcher path")
        # The end-of-install message tells users how to re-enter
        self.assertIn("type:", cmd.lower().replace('  ', ' '),
            "end-of-install must tell users what to type to start")
        self.assertIn("claude", cmd,
            "end-of-install must mention the `claude` command")

    def test_installer_step5_diagnostic_runs_checks(self):
        """Step 5 (was Step 6 — renumbered after START-HERE removal in B9.10)
        runs actual diagnostic checks. Failures are warnings, not blockers —
        the skill catches real problems at runtime."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        self.assertIn("DIAGNOSTIC_FAILS=0", cmd,
            "Step 5 should track diagnostic failure count")
        # At least 8 distinct diagnostic checks
        self.assertGreaterEqual(cmd.count("check ") + cmd.count("check_file "), 8,
            "Step 5 should run at least 8 diagnostic checks")
        # Failures are warnings, not exit-1 blockers
        self.assertIn("warn \"$DIAGNOSTIC_FAILS diagnostic check(s) reported issues", cmd,
            "diagnostic failures should warn, not block")
        self.assertNotIn("exit 1\nfi\nelse\n  ok_paced \"All diagnostics passed\"", cmd,
            "must not exit 1 on diagnostic failure (B9.10 — warnings only)")

    def test_installer_ends_with_clear_reentry_instructions(self):
        """B9.10 — replaces the old 'Want to start now?' seamless handoff.
        With START-HERE removed, end-of-install just tells the user how to
        re-enter: open Terminal, type `claude`, ask for a report. No prompt,
        no exec into a launcher (because there is no launcher)."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The old prompt is gone
        self.assertNotIn("Want to start now?", cmd,
            "old 'Want to start now?' prompt should be removed")
        self.assertNotIn('exec "$WORKSPACE_LAUNCHER"', cmd,
            "old workspace-launcher exec should be removed")
        # The new instructions are present
        self.assertIn("Open ${BOLD}Terminal", cmd,
            "end-of-install must instruct user to open Terminal")
        self.assertIn("claude", cmd,
            "end-of-install must show the `claude` command")
        self.assertIn("build my report", cmd,
            "end-of-install must show an example prompt")
        # No exit auto-close (this is the user's own terminal in curl-pipe mode)
        self.assertNotIn("close_terminal_window_after_countdown", cmd,
            "auto-close terminal helper should be removed (B9.10)")

    def test_installer_has_pause_gates_and_auto_flag(self):
        """B9.3 invariant: paced output + Press-Enter gates between sections.
        Without these, pre-flight ✓s flash by faster than humans can read.
        Both Mac (.command, bash) and Windows (.ps1) installers must:
        - define paced sub-step helper (ok_paced / Write-OkPaced)
        - define a pause helper that's TTY-guarded
        - support an --auto / -Auto flag to skip pacing for CI
        - actually CALL the pause helper at least 2× between major sections."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        ps1 = (REPO / "installer" / "legacy" / "Welcome.ps1").read_text(encoding="utf-8")

        # Mac: helpers + gates + --auto
        self.assertIn("ok_paced()", cmd, "install.sh missing ok_paced helper")
        self.assertIn("pause_for_user()", cmd, "install.sh missing pause_for_user helper")
        self.assertGreaterEqual(cmd.count("pause_for_user"), 4,
            "install.sh should INVOKE pause_for_user at ≥2 transition points "
            "(plus the function definition + check, that's ≥4 occurrences)")
        self.assertIn("--auto", cmd, "install.sh must support --auto flag")
        self.assertIn("AUTO_MODE", cmd, "install.sh must implement --auto bypass")

        # Windows: helpers + gates + -Auto
        self.assertIn("Write-OkPaced", ps1, "Welcome.ps1 missing Write-OkPaced helper")
        self.assertIn("Pause-ForUser", ps1, "Welcome.ps1 missing Pause-ForUser helper")
        self.assertGreaterEqual(ps1.count("Pause-ForUser"), 4,
            "Welcome.ps1 should INVOKE Pause-ForUser at ≥2 transition points")
        self.assertTrue("-Auto" in ps1 or "--auto" in ps1,
            "Welcome.ps1 must support -Auto / --auto flag")
        self.assertIn("AutoMode", ps1, "Welcome.ps1 must implement Auto bypass")

    def test_installer_traps_sigint_with_step_logging(self):
        """Issue E3 — Ctrl-C used to exit silently with no log line, leaving
        advisors blind to where users abandoned. Now there's a SIGINT/SIGTERM
        trap that logs which step the user cancelled at, prints a friendly
        re-run message, and exits with conventional code 130.

        Also enforces that CURRENT_STEP is updated at each step heading
        (not stuck at 'pre-consent' for the whole install)."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The trap is wired
        self.assertIn("trap on_interrupt INT TERM", cmd,
            "install.sh must trap INT and TERM")
        self.assertIn("on_interrupt()", cmd,
            "install.sh must define the trap handler")
        # The handler logs + emits a re-run nudge
        self.assertIn('log "user_interrupt at step=', cmd,
            "trap handler must log which step was interrupted")
        self.assertIn("exit 130", cmd,
            "trap handler must exit with conventional Ctrl-C exit code")
        # CURRENT_STEP is updated at each Step heading. Strategic #2 dropped
        # the "publishing-host signup" step (moved to publish.sh), so steps
        # are now 1-of-5 instead of 1-of-6.
        for step_label in ("1/5 pre-flight", "2/5 installing tools",
                           "3/5 Claude sign-in",
                           "4/5 workspace setup", "5/5 final diagnostics"):
            self.assertIn(f'CURRENT_STEP="{step_label}', cmd,
                f"CURRENT_STEP should be set to '{step_label}…' at that step")

    def test_installer_diagnostic_failure_warns_does_not_block(self):
        """Issue E1 + B9.10 — diagnostic failures are warnings, period. The
        previous launcher-gate logic is gone (no launcher to gate on). The
        skill catches real problems at runtime."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # Failures emit a warn() call, no exit 1
        self.assertIn('warn "$DIAGNOSTIC_FAILS diagnostic check(s) reported issues', cmd,
            "diagnostic-fail must warn, not block")
        # The launcher-gate path is gone (B9.10 removed the launcher entirely)
        self.assertNotIn('if [ -x "$WS/.skill-launcher.sh" ]; then', cmd,
            "old launcher-presence gate should be gone")
        # Success path still says "All diagnostics passed"
        self.assertIn('ok_paced "All diagnostics passed"', cmd,
            "success path should still confirm")

    def test_installer_curl_pipe_safe(self):
        """B9.10 — install.sh must rebind stdin to /dev/tty early, otherwise
        curl-pipe-bash invocations can't read user input (bash drained the
        pipe to load the script body). Without this fix, the consent gate
        auto-fires empty and the install silently cancels."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The TTY rebind must happen before any read prompt
        self.assertIn("exec </dev/tty", cmd,
            "must rebind stdin to /dev/tty for curl-pipe-bash to work")
        # Headless fallback: if no /dev/tty, force AUTO_MODE
        self.assertIn("AUTO_MODE_FORCED=1", cmd,
            "must fall back to AUTO_MODE when no controlling tty")
        # The rebind must come BEFORE the consent gate's read
        rebind_idx = cmd.find("exec </dev/tty")
        consent_idx = cmd.find("Type %sI accept%s")
        self.assertLess(rebind_idx, consent_idx,
            "stdin rebind must happen before the consent prompt")

    def test_installer_pre_consent_block_is_paced(self):
        """Dry-run feedback: the opening (welcome + 3-step preview, prototype
        warning, Anthropic data-terms summary) was the most important block
        to actually read, but it dumped in <1 second because it lived above
        the consent gate where pacing helpers weren't called yet.

        Fix: split the pre-consent text into 3 logical sections, each
        followed by pause_for_user / Pause-ForUser. So the user sees:
        section → ENTER → section → ENTER → section → ENTER → consent.

        This test enforces ≥3 pause invocations BEFORE the consent prompt
        (vs. the older test which just counted total invocations across
        the whole script).
        """
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        ps1 = (REPO / "installer" / "legacy" / "Welcome.ps1").read_text(encoding="utf-8")

        # Mac: count pause_for_user calls BEFORE the consent read prompt.
        consent_idx = cmd.find("Type %sI accept%s to continue")
        self.assertGreater(consent_idx, 0, "consent prompt must exist")
        pre_consent = cmd[:consent_idx]
        # Subtract function definition (1) + auto-mode check inside the fn (1)
        invocations = pre_consent.count("pause_for_user") - 2
        self.assertGreaterEqual(invocations, 3,
            f"install.sh should pause ≥3 times before consent gate "
            f"(found {invocations} after subtracting fn-def + internal check)")

        # Windows: count Pause-ForUser calls before the consent Read-Host.
        consent_idx_ps1 = ps1.find("Type 'I accept' to continue")
        self.assertGreater(consent_idx_ps1, 0, "consent prompt must exist in ps1")
        pre_consent_ps1 = ps1[:consent_idx_ps1]
        # Subtract function definition (1) + auto-mode check inside the fn (1)
        invocations_ps1 = pre_consent_ps1.count("Pause-ForUser") - 2
        self.assertGreaterEqual(invocations_ps1, 3,
            f"Welcome.ps1 should pause ≥3 times before consent gate "
            f"(found {invocations_ps1} after subtracting fn-def + internal check)")

        # And: the section-1 emphasis lines (the 3 numbered preview steps)
        # should use the paced helper, not the instant one.
        self.assertIn('say_paced "  1. Type your Mac password', cmd,
            "Section 1 numbered preview steps should use say_paced")
        self.assertIn('Write-SayPaced "  1. Allow Windows', ps1,
            "Section 1 numbered preview steps should use Write-SayPaced")

    def test_installer_does_not_signup_for_publishing_host(self):
        """Strategic #2 — local-first. The publishing-host signup that used
        to live in install.sh Step 4 has moved to publish.sh and runs
        only when the user explicitly chooses to share. The installer must
        no longer reference any here.now signup endpoints, and Step 4 must
        no longer exist (steps are now 1-of-5)."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # Email-code endpoints must be GONE from the installer
        self.assertNotIn("/api/auth/agent/request-code", cmd,
            "request-code must move to publish.sh, not stay in installer")
        self.assertNotIn("/api/auth/agent/verify-code", cmd,
            "verify-code must move to publish.sh, not stay in installer")
        # And no more email prompt during install
        self.assertNotIn('read -r -p "Email: "', cmd,
            "installer must not ask for email — that happens on first share now")
        # Step numbering reflects the removal: 1-of-5, not 1-of-6
        self.assertIn("Step 1 of 5", cmd, "Step 1 should now read 'of 5'")
        self.assertNotIn("Step 1 of 6", cmd, "old 'of 6' numbering should be gone")
        # Step 4 still exists — it's now "workspace setup" (was Step 5 of 6).
        # What's gone is the "Setting up your private dashboard host" heading.
        self.assertNotIn("Setting up your private dashboard host", cmd,
            "the publishing-host-signup step heading should be removed")
        self.assertIn("Step 4 of 5 — Setting up your finance workspace", cmd,
            "Step 4 should now be the workspace-setup step (renumbered from 5/6)")

    def test_publish_sh_runs_email_code_flow_when_no_credentials(self):
        """Strategic #2 — the email-code signup logic has been MOVED from
        the installer to publish.sh. publish.sh detects missing credentials
        and runs the inline signup before publishing. After signup, future
        publishes are silent."""
        publish = (REPO / "skill" / "scripts" / "publish.sh").read_text(encoding="utf-8")
        # The email-code endpoints now live here
        self.assertIn("/api/auth/agent/request-code", publish,
            "publish.sh must POST to request-code on first publish")
        self.assertIn("/api/auth/agent/verify-code", publish,
            "publish.sh must POST to verify-code on first publish")
        # Detect missing credentials → trigger signup
        self.assertIn("SIGNUP_NEEDED=1", publish,
            "publish.sh must gate signup on missing/invalid credentials")
        # Manual paste fallback survives
        self.assertIn("manual_paste_fallback()", publish,
            "manual paste must remain reachable as a fallback")
        # The previous hard-fail-if-missing-creds path is gone
        self.assertNotIn('credential missing at $CRED_FILE — re-run install', publish,
            "publish.sh should NOT hard-fail on missing creds — it should run signup instead")

    def test_view_local_script_exists_and_opens_dashboard(self):
        """Strategic #2 — view-local.sh opens $WS/site/index.html in the
        user's browser via file://. This is the local-first default path
        invoked at the end of refresh.sh."""
        view_local = REPO / "skill" / "scripts" / "view-local.sh"
        self.assertTrue(view_local.exists(),
            "view-local.sh must exist at skill/scripts/view-local.sh")
        self.assertTrue(os.access(view_local, os.X_OK),
            "view-local.sh must be executable")
        body = view_local.read_text(encoding="utf-8")
        # Reads from the workspace's site/ folder
        self.assertIn("$WS/site", body,
            "view-local.sh must target the workspace's site/ folder")
        # Uses file:// (local), not http://
        self.assertIn('URL="file://', body,
            "view-local.sh must serve from file:// (local), not http://")
        # Cross-platform open
        for opener in ("open", "xdg-open", "start"):
            self.assertIn(opener, body,
                f"view-local.sh should support {opener} for cross-platform open")

    def test_refresh_sh_invokes_local_view_after_build(self):
        """Strategic #2 — refresh.sh ends with view-local.sh by default
        (opens dashboard in browser). --no-open bypasses for CI / scripted
        runs."""
        refresh = (REPO / "skill" / "scripts" / "refresh.sh").read_text(encoding="utf-8")
        self.assertIn("view-local.sh", refresh,
            "refresh.sh must invoke view-local.sh after building")
        self.assertIn("--no-open", refresh,
            "refresh.sh must support --no-open to skip auto-open in CI")

    def test_installer_uses_working_herenow_url(self):
        """B9.7 regression: here.now has no /signup path — that URL 404s.
        The signup logic moved from the installer to publish.sh in the
        local-first refactor (Strategic #2), but the same rule applies:
        link the homepage, not /signup."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        publish = (REPO / "skill" / "scripts" / "publish.sh").read_text(encoding="utf-8")
        for haystack, name in [(cmd, "install.sh"), (publish, "publish.sh")]:
            self.assertNotIn("here.now/signup", haystack,
                f"{name}: https://here.now/signup is a 404 — link the homepage instead")
            self.assertNotIn("here.now/sign-up", haystack,
                f"{name}: /sign-up also 404s")
            self.assertNotIn("here.now/login", haystack,
                f"{name}: /login also 404s")
        # The homepage IS valid (200) — and that's what the manual-paste
        # fallback in publish.sh opens. (Installer no longer opens it because
        # the signup flow moved to publish.sh.)
        self.assertIn('open "https://here.now/"', publish,
            "publish.sh manual-paste fallback should open here.now/ (working homepage)")

    def test_installer_python311_resolved_to_absolute_path(self):
        """Dry-run regression: 'Python 3.11 installed' diagnostic returned
        a false ✗ when Python was already on PATH. After the uv migration,
        PYTHON311 is set from `uv python find 3.11` which always returns
        an absolute path inside uv's managed install dir. The Step 6
        `test -x "$PYTHON311"` diagnostic stays valid as a result."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # PYTHON311 is set from uv python find, which returns an absolute path
        self.assertIn('"$UV_BIN" python find 3.11', cmd,
            "Step 2d should resolve PYTHON311 via `uv python find 3.11`")
        # And the diagnostic still uses test -x to validate it
        self.assertIn('check       "Python 3.11 installed"          test -x "$PYTHON311"', cmd,
            "Step 6 diagnostic should validate PYTHON311 with test -x")
        # PYTHON311 is validated for executable-ness right after resolution
        self.assertIn('if [ -z "$PYTHON311" ] || [ ! -x "$PYTHON311" ]; then', cmd,
            "Step 2d must validate PYTHON311 is non-empty and executable")

    def test_installer_fetches_skill_via_npx_skills_add(self):
        """B9.8 — finance-clarity-build skill is fetched via `npx skills add`
        (same pattern as the here-now skill in Step 2g) instead of `git clone`.
        Required non-interactive flags: --agent claude-code -g -y (without
        these the CLI prompts for agent picker, which would hang in a
        piped-from-curl context). The CLI installs the skill subdir contents
        directly to ~/.claude/skills/finance-clarity-build/ — so internal
        paths must NOT include the `/skill/` prefix that the old git-clone
        layout had."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The npx invocation for finance-clarity-build
        self.assertIn(
            'npx -y skills add "$SKILL_REPO_REF" --skill finance-clarity-build --agent claude-code -g -y',
            cmd,
            "Step 2h must use npx skills add with non-interactive flags")
        # SKILL_REPO_REF defaults to the canonical repo
        self.assertIn(
            'SKILL_REPO_REF="${FCB_SKILL_REPO_REF:-passporttowealth/passporttowealth}"',
            cmd,
            "SKILL_REPO_REF should default to passporttowealth/passporttowealth")
        # The here-now skill install also gets the non-interactive flags
        self.assertIn(
            "npx -y skills add heredotnow/skill --skill here-now --agent claude-code -g -y",
            cmd,
            "Step 2g should pass --agent claude-code -g -y to keep curl-piped install non-interactive")
        # The old git-clone path is gone
        self.assertNotIn("git clone", cmd,
            "install.sh should NOT use git clone — switched to npx skills add (B9.8)")
        # No more $SKILL_INSTALL_DIR/skill/ paths — npx-installed skills land
        # with SKILL.md at the top level, not nested under skill/
        self.assertNotIn("$SKILL_INSTALL_DIR/skill/", cmd,
            "All $SKILL_INSTALL_DIR refs must drop the /skill/ prefix — npx layout is flat")
        # Diagnostic checks the new flat layout
        self.assertIn('"$SKILL_INSTALL_DIR/SKILL.md"', cmd,
            "Step 6 diagnostic should check for SKILL.md at the top of the install dir")

    def test_install_sh_is_curl_pipe_friendly(self):
        """B9.9 — install.sh is designed to be piped from curl, not double-
        clicked from Finder. Two things from the legacy Welcome.command must
        be absent: the Finder-launched re-exec block (which would relaunch
        Terminal — pointless and broken inside a pipe), and the title /
        description should not say `Welcome.command`."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # No Finder re-exec — we're already in Terminal when piped from curl
        self.assertNotIn("REEXEC_TTY=1 open -a Terminal", cmd,
            "install.sh should not re-exec into Terminal — it's already there")
        # Header comment names install.sh, not Welcome.command
        self.assertIn("install.sh — Passport to Wealth", cmd[:500],
            "header should name install.sh as the canonical installer")
        # The canonical curl URL is documented in the header for posterity
        self.assertIn(
            "https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh",
            cmd,
            "header should document the canonical curl install URL")

    def test_install_shim_exists_and_execs_canonical(self):
        """B9.10 — installer/install is a tiny shim that exec-fetches the
        canonical install.sh from raw.githubusercontent.com. Mirrored into
        the here.now publish bundle so the user-facing URL can be the
        short, branded passporttowealth.app/install instead of the long
        raw GitHub URL."""
        shim = REPO / "installer" / "install"
        self.assertTrue(shim.exists(), "installer/install (the shim) must exist")
        self.assertTrue(os.access(shim, os.X_OK),
            "installer/install must be executable")
        body = shim.read_text(encoding="utf-8")
        self.assertIn("exec bash <(curl -fsSL", body,
            "shim must exec-fetch via curl + process substitution")
        self.assertIn(
            "https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh",
            body, "shim must point at the canonical install.sh on GitHub raw")

    def test_install_sh_appends_api_key_to_shell_rc(self):
        """B9.10 — with START-HERE removed, the API-key auth path stores the
        key in the user's shell rc (not the now-deleted launcher script) so
        `claude` picks it up from any new Terminal session. Idempotent —
        re-running the installer strips the previous block before adding a
        new one."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # Detects the user's shell
        self.assertIn('case "${SHELL:-}" in', cmd,
            "must detect the user's shell to pick the right rc file")
        self.assertIn('*/zsh) SHELL_RC="$HOME/.zshrc"', cmd,
            "must default to zshrc on modern macOS")
        # Idempotent block markers
        self.assertIn("# Passport to Wealth — Finance Clarity API key", cmd,
            "must use a marked block so re-runs can find/replace it")
        self.assertIn("# Passport to Wealth — end", cmd,
            "must mark the block end")
        # The actual export
        self.assertIn("export ANTHROPIC_API_KEY=", cmd,
            "must export ANTHROPIC_API_KEY into the shell rc")

    def test_refresh_sh_defaults_to_workspace_venv(self):
        """B9.10 — without START-HERE activating the venv, refresh.sh has to
        default PYTHON to the workspace venv's python so the pipeline runs
        with the right deps from any cwd."""
        refresh = (REPO / "skill" / "scripts" / "refresh.sh").read_text(encoding="utf-8")
        self.assertIn('elif [ -x "$WS/.venv/bin/python" ]; then', refresh,
            "refresh.sh must check for the workspace venv before falling back")
        self.assertIn('PY="$WS/.venv/bin/python"', refresh,
            "refresh.sh must default PY to the workspace venv's python")
        # PYTHON env var still overrides for testing
        self.assertIn('if [ -n "${PYTHON:-}" ]; then', refresh,
            "PYTHON env var should still override (for test fixtures)")

    def test_landing_page_uses_short_install_url(self):
        """B9.10 — the published landing page advertises the short branded URL
        (passporttowealth.app/install), not the long GitHub raw URL.
        Transparency is preserved by the README which shows the shim
        target."""
        html = (REPO / "installer" / "index.html").read_text(encoding="utf-8")
        # Mac command — short URL
        self.assertIn("https://passporttowealth.app/install", html,
            "Mac install command must use the short URL")
        # The long raw URL must NOT appear (transparency happens in README)
        self.assertNotIn(
            "raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.sh",
            html,
            "landing page must NOT show the long raw URL — that's the README's job")
        # Windows: short URL too
        self.assertIn("https://passporttowealth.app/install.ps1", html,
            "Windows install command must use the short URL")
        # Copy buttons + OS toggle
        self.assertIn('class="copy-btn"', html, "must have copy buttons on install commands")
        self.assertIn('id="tab-mac"', html, "must have OS toggle for Mac")
        self.assertIn('id="tab-win"', html, "must have OS toggle for Windows")
        # Old Gatekeeper instructions are gone (curl-pipe never triggers it)
        self.assertNotIn('Gatekeeper', html,
            "Gatekeeper instructions should be removed (curl-pipe bypasses it)")
        self.assertNotIn('right-click', html.lower(),
            "right-click → Open instructions should be removed")

    def test_legacy_installers_archived_with_readme(self):
        """B9.9 — Welcome.command, Welcome.bat, Welcome.ps1 moved to
        installer/legacy/ as a fallback for users who can't open Terminal.
        Not deleted. installer/legacy/README.md explains what they are."""
        legacy_dir = REPO / "installer" / "legacy"
        self.assertTrue(legacy_dir.is_dir(), "installer/legacy/ must exist")
        for fname in ("Welcome.command", "Welcome.bat", "Welcome.ps1", "README.md"):
            f = legacy_dir / fname
            self.assertTrue(f.exists(), f"installer/legacy/{fname} must exist")
        # Welcome.command/.bat/.ps1 must NOT be in installer/ root anymore
        for fname in ("Welcome.command", "Welcome.bat", "Welcome.ps1"):
            f = REPO / "installer" / fname
            self.assertFalse(f.exists(),
                f"installer/{fname} must be moved to installer/legacy/")

    def test_installer_brew_installs_node_for_npx(self):
        """B9.11 — install.sh has to brew-install Node.js because Apple
        doesn't ship it. Steps 2g/2h need `npx skills add` to fetch the
        here-now and finance-clarity-build skills; without Node, the
        install dead-ended on every fresh Mac.

        Fix: Step 2e now installs `node` alongside `jq` via Homebrew.
        Both are gated on `command -v` presence checks. The Step 5
        diagnostic verifies npx is available."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # Step 2e installs Node if missing
        self.assertIn('if command -v node >/dev/null 2>&1; then', cmd,
            "Step 2e should check for an existing node before installing")
        self.assertIn('run_quiet "Node.js installed" brew install node', cmd,
            "Step 2e should brew-install Node.js if missing")
        # The "installing Node" message tells the user what's happening
        self.assertIn("Installing Node.js", cmd,
            "should announce Node install (per pacing principle)")
        # Step 5 diagnostic checks npx is available (proves Node install worked)
        self.assertIn('check       "Node.js installed (npx)"        command -v npx', cmd,
            "Step 5 diagnostic must verify npx is on PATH")

    def test_installer_uses_uv_for_python_provisioning(self):
        """Strategic #1 — replace `brew install python@3.11 + venv + pip
        install` with uv (one binary, one toolchain). uv handles managed
        Python install, venv creation, and dep resolution. Removes the
        Homebrew dependency for Python entirely; brew is now only invoked
        if jq is missing."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # uv installer is fetched from astral.sh
        self.assertIn("https://astral.sh/uv/install.sh", cmd,
            "must install uv from astral.sh/uv/install.sh")
        # uv is used for: Python install, venv create, dep install
        self.assertIn('"$UV_BIN" python install 3.11', cmd,
            "must use uv to install Python 3.11")
        self.assertIn('"$UV_BIN" venv --python "$PYTHON311"', cmd,
            "must use `uv venv` (not python -m venv)")
        self.assertIn('"$UV_BIN" pip install', cmd,
            "must use `uv pip install` (not the venv's pip)")
        # The old brew-python paths are gone
        self.assertNotIn("brew install python@3.11", cmd,
            "should NOT install Python via Homebrew anymore")
        self.assertNotIn('"$PYTHON311" -m venv', cmd,
            "should NOT create venv via `python -m venv` anymore")
        self.assertNotIn('"$WS/.venv/bin/pip" install', cmd,
            "should NOT install deps via the venv's pip anymore")
        # Homebrew is lazy — only triggers if jq OR node is missing
        self.assertIn("NEED_BREW=0", cmd,
            "Homebrew install should be gated on whether brew tools are needed")
        self.assertIn('if ! command -v jq   >/dev/null 2>&1; then NEED_BREW=1; fi', cmd,
            "should mark brew needed when jq is missing")
        self.assertIn('if ! command -v node >/dev/null 2>&1; then NEED_BREW=1; fi', cmd,
            "should mark brew needed when node is missing")
        # Step 5 diagnostic checks uv (mandatory) instead of brew
        self.assertIn('check       "uv installed"                   test -x "$UV_BIN"', cmd,
            "Step 5 must check uv, not Homebrew")

    def test_installer_fx_prewarm_streams_progress_to_tty(self):
        """Dry-run regression: 'Pre-warming exchange-rate cache (last 24
        months)…' appeared to stall for 30-60s with no progress bar,
        because the installer redirected stderr to the install log
        (`2>&1`). The B9.5 progress() helper writes to stderr and
        TTY-guards itself, so it correctly went silent.

        Fix: stdout → install log (silent), stderr → /dev/tty so the
        progress bar reaches the user even though we're inside redirects."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # Find the FX prewarm invocation. Bound the slice tightly to the actual
        # fx_fetch invocation (not the surrounding diagnostic helpers, which
        # legitimately use 2>&1 for log-only output).
        fx_block_start = cmd.find("Pre-warming exchange-rate cache")
        self.assertGreater(fx_block_start, 0, "FX prewarm block must exist")
        # The fx_fetch invocation ends at the `|| warn ...` fallback; bound there
        fx_block_end = cmd.find('|| warn "FX pre-warm failed', fx_block_start)
        self.assertGreater(fx_block_end, fx_block_start, "FX prewarm fallback must exist")
        fx_block = cmd[fx_block_start:fx_block_end + 50]
        self.assertIn("fx_fetch.py", fx_block)
        self.assertIn("2>/dev/tty", fx_block,
            "FX prewarm must redirect stderr to /dev/tty so progress() shows")
        self.assertNotIn("2>&1", fx_block,
            "FX prewarm must NOT use 2>&1 — it would silence the progress bar")

    def test_installer_does_not_auto_open_privacy_hub(self):
        """B9.1 regression: auto-opening privacy.anthropic.com in the browser
        mid-consent-gate snaps focus away from Terminal and confuses users.
        Terminal/Windows-Terminal linkify URLs — let the user click if they
        want to read first."""
        cmd_path = REPO / "installer" / "install.sh"
        ps1_path = REPO / "installer" / "legacy" / "Welcome.ps1"
        cmd = cmd_path.read_text(encoding="utf-8")
        ps1 = ps1_path.read_text(encoding="utf-8")
        self.assertNotIn('open "https://privacy.anthropic.com', cmd,
            "install.sh must not auto-open the privacy hub (B9.1)")
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
