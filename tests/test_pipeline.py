#!/usr/bin/env python3
"""Regression tests for the Finance Clarity pipeline + install + publish surfaces.

**Prototype-phase scope (B9.19).** Trimmed from 69 → ~40 tests on 2026-05-03
to optimize for fast iteration during the 2-week tester pilot. A test earns
its place if its failure tells us a real tester is about to have a bad
experience: install will break, the dashboard or landing page will look
wrong, the pipeline will produce wrong numbers, a privacy claim will drift
from reality, or telemetry/consent gates will leak. Tests that pin specific
copy phrasing, CSS class names, default page sizes, file modes, or
once-fixed legacy bug patterns were dropped — they paid maintenance cost
without defending tester-impacting behavior.

The full Tier 1/2/3 testing roadmap (CI shellcheck, Worker dry-run deploy,
HTML lint + dead-link check, branch protection, container smoke-test of
install.sh, etc.) is in `dev/backlog.md` B9.19 for review at the end of
the prototype phase (late May 2026).

Run:
    python3 tests/test_pipeline.py

Exit 0 on success, non-zero on any failure. CI (`.github/workflows/ci.yml`)
runs this on every PR. The publish step (which makes real network calls) is
NOT exercised here — that's a separate manual step via
`installer/publish-landing.sh` and `skill/scripts/publish.sh`.
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
        # Inbox is emptied after classify (files moved, not copied).
        leftovers = [p for p in (ws / "inbox").iterdir() if p.is_file() and not p.name.startswith(".")]
        self.assertEqual(leftovers, [], "inbox should be empty after classify")

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

    def test_privacy_footer_is_honest_about_what_publishes(self):
        """The dashboard's footer claims about privacy must match reality.

        Reality: publish.sh uploads the entire site/ directory, which includes
        site/downloads/transactions_tagged.csv (every row) and the embedded
        dashboard-data JSON (which also contains the per-transaction list).

        The previous copy ('the host never received your transactions, only
        the rendered numbers') was misleading — flagged by a user. Source
        files (bank PDFs, paystubs) DO stay local; categorized transactions
        and CSV exports DO get uploaded. The footer must be specific about
        the split, not over-promise."""
        html = (self.workspace / "site" / "index.html").read_text()
        # Old misleading copy must not creep back in.
        self.assertNotIn("host never received your transactions", html,
            "dashboard footer must not claim transactions don't reach the host — "
            "downloads/transactions_tagged.csv and embedded JSON both ship them")
        self.assertNotIn("only the rendered numbers", html,
            "dashboard footer must not claim 'only the rendered numbers' — "
            "the embedded dashboard-data JSON includes per-transaction rows")
        # New honest copy must be present.
        self.assertIn("Hosted privately, behind a passcode you set", html,
            "footer must keep the passcode-gated framing")
        self.assertIn("source files", html.lower(),
            "footer must call out that source files (PDFs/statements) stay local")
        self.assertIn("categorized transactions", html,
            "footer must disclose that categorized transactions ARE uploaded")

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


class TestNetCategoryAggregation(unittest.TestCase):
    """A positive-amount row in a non-Income category must REDUCE that
    category's total, not inflate it. Regression guard for the abs() bug
    in build_site.aggregate(): a refund / benefit payout / chargeback /
    rental-deposit return that shares a merchant rule with prior debits
    used to be added to the category instead of netted out, lying about
    spend. Touches the Spend-by-category and Monthly-spend charts."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="fcb-net-cat-"))
        self.workspace = self.tmpdir / "workspace"
        self.workspace.mkdir()
        out = self.workspace / "pipeline" / "output"
        out.mkdir(parents=True)
        # Insurance: $50 paid in Jan, $300 refund in Jan, $50 paid in Feb
        # → expected net = -$200 (refund exceeds spend)
        # Restaurants: one $10 debit → expected $10
        with (out / "transactions_tagged.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "description", "amount", "currency", "account",
                        "source_file", "source_row", "category", "subcategory"])
            w.writerow(["2026-01-15", "Insurance contribution", "-50.00", "USD",
                        "Checking", "test.csv", "1", "Insurance", ""])
            w.writerow(["2026-01-22", "Insurance refund / benefit",  "300.00", "USD",
                        "Checking", "test.csv", "2", "Insurance", ""])
            w.writerow(["2026-02-15", "Insurance contribution", "-50.00", "USD",
                        "Checking", "test.csv", "3", "Insurance", ""])
            w.writerow(["2026-02-20", "Coffee shop", "-10.00", "USD",
                        "Checking", "test.csv", "4", "Restaurants", ""])
        (out / "monthly_actuals.csv").write_text("month\n2026-01\n2026-02\n")
        sanity = {
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_violations": [],
        }
        (out / "sanity_confirmed.json").write_text(json.dumps(sanity))
        self.env = {"FCB_WORKSPACE": str(self.workspace)}

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_refund_in_non_income_category_nets_against_spend(self):
        run_script("build_site.py", env_extra=self.env)
        html = (self.workspace / "site" / "index.html").read_text()
        m = re.search(r'<script id="dashboard-data"[^>]*>(.+?)</script>', html, re.DOTALL)
        self.assertIsNotNone(m, "dashboard-data <script> block missing")
        d = json.loads(m.group(1))
        cat_totals = dict(d["category_totals"])
        # If abs() bug regressed: Insurance = 50+300+50 = 400.
        # Correct net: -50+300-50 inverted to spend convention = -200.
        self.assertAlmostEqual(
            cat_totals.get("Insurance", 0), -200.00, places=2,
            msg=(f"Insurance net should be -$200 (refunds exceed spend), "
                 f"got {cat_totals.get('Insurance')}. abs() bug regression?"))
        self.assertAlmostEqual(
            cat_totals.get("Restaurants", 0), 10.00, places=2,
            msg="Restaurants should be $10 net (single debit row)")


class TestPipelineHealth(unittest.TestCase):
    """Smoke-level sanity that the pipeline scripts themselves are importable
    and the shared lib doesn't have basic syntax errors."""


    def test_installer_curl_pipe_safe(self):
        """B9.10 + B9.12 — install.sh must rebind stdin to /dev/tty early
        AND capture the result into an INTERACTIVE flag (instead of
        re-testing `-t 0` later). Bash 3.2 (Apple's default) sometimes
        returns the pre-redirect tty state from `[ -t 0 ]` even after a
        successful redirect, which previously caused pause_for_user to
        silently skip every pause + the consent gate to auto-cancel."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The TTY rebind must happen before any read prompt
        self.assertIn("exec </dev/tty", cmd,
            "must rebind stdin to /dev/tty for curl-pipe-bash to work")
        # Headless fallback: if no /dev/tty, force AUTO_MODE
        self.assertIn("AUTO_MODE_FORCED=1", cmd,
            "must fall back to AUTO_MODE when no controlling tty")
        # The rebind must come BEFORE the consent gate's read
        rebind_idx = cmd.find("exec </dev/tty")
        consent_idx = cmd.find('Type "I accept" to continue')
        self.assertLess(rebind_idx, consent_idx,
            "stdin rebind must happen before the consent prompt")
        # B9.12: INTERACTIVE flag captured ONCE — not re-tested via [ -t 0 ]
        self.assertIn("INTERACTIVE=1", cmd,
            "INTERACTIVE flag must be set after the rebind attempt")
        self.assertIn('INTERACTIVE_DIAG="rebind_ok"', cmd,
            "rebind success must record diagnostic state")
        self.assertIn('INTERACTIVE_DIAG="rebind_failed"', cmd,
            "rebind failure must record diagnostic state")
        self.assertIn('INTERACTIVE_DIAG="already_tty"', cmd,
            "pre-existing TTY must record diagnostic state")
        # pause_for_user uses the captured flag, NOT a fresh -t 0 test
        self.assertIn('if [ "$AUTO_MODE" = "1" ] || [ "$INTERACTIVE" = "0" ]; then', cmd,
            "pause_for_user must gate on $INTERACTIVE, not [ -t 0 ]")
        # Diagnostic gets logged so post-mortem support can see what happened
        self.assertIn('log "tty_state: ${INTERACTIVE_DIAG}', cmd,
            "tty diagnostic must be written to install log")
        # Designed for curl-pipe-bash, not Finder double-click — must not
        # re-exec into Terminal (we're already in one when piped from curl).
        self.assertNotIn("REEXEC_TTY=1 open -a Terminal", cmd,
            "install.sh should not re-exec into Terminal — it's already there")

    def test_installer_consent_gate_does_not_silently_cancel_on_empty(self):
        """B9.12 — empty input at the consent gate previously matched the
        cancel branch ("no"|"cancel"|"quit"|"stop"|""), causing the install
        to exit silently saying "install cancelled" if the TTY rebind
        failed. Now empty input falls through to a re-prompt with a clear
        "I didn't catch that" message; only explicit cancel words exit.
        After 5 consecutive empties we bail with a clear support pointer
        (catches the case where the rebind is genuinely broken so we
        don't loop forever)."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The cancel case no longer includes empty
        self.assertIn('"no"|"cancel"|"quit"|"stop")', cmd,
            "explicit cancel branch should not include empty input")
        self.assertNotIn('"no"|"cancel"|"quit"|"stop"|"")', cmd,
            "empty input must NOT be in the cancel branch")
        # There's an explicit empty-input branch with a clear message
        self.assertIn('"")', cmd,
            "must have a dedicated empty-input branch")
        self.assertIn("I didn't catch any input", cmd,
            "empty-input branch should explain what to type")
        # Bail-out after N empties prevents infinite loop on broken TTY
        self.assertIn("EMPTY_COUNT", cmd,
            "must track empty-input count")
        self.assertIn('if [ "$EMPTY_COUNT" -ge 5 ]', cmd,
            "must bail after 5 empties to avoid infinite loop")


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

    def test_install_sh_start_now_only_execs_when_real_tty(self):
        """Bug found 2026-05-07 in tester dry-run: the end-of-install
        'Want to start now? [Y/n]' prompt was unconditionally `exec`-ing
        into claude. That works when the user ran the script directly
        from a real terminal, but fails under curl-pipe-bash: bash isn't
        the terminal's foreground process group, so the exec'd claude
        inherits stdin pointing at /dev/tty but can't take foreground.
        Result: keystrokes don't reach claude, terminal looks frozen.

        Fix: only exec when `INTERACTIVE_DIAG="already_tty"`. In the
        rebind_ok (curl-pipe-bash) case, print instructions and let the
        user type `claude` themselves — that gives the new process
        proper foreground role."""
        cmd = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # The exec is gated on the TTY diagnostic
        self.assertIn('if [ "${INTERACTIVE_DIAG:-}" = "already_tty" ]; then', cmd,
            "exec claude must be gated on INTERACTIVE_DIAG=already_tty (real terminal)")
        # The exec lives inside that gate, not before it
        gate_idx = cmd.find('if [ "${INTERACTIVE_DIAG:-}" = "already_tty" ]; then')
        exec_idx = cmd.find('exec claude --add-dir "$WS"')
        self.assertGreater(exec_idx, gate_idx,
            "exec claude must come AFTER the already_tty gate")
        # And the curl-pipe-bash fallback gives the user the one word to type
        self.assertIn("Type one word in this same terminal to start", cmd,
            "curl-pipe-bash fallback must tell the user to type 'claude'")

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

    def test_installer_posts_anonymous_install_started_ping(self):
        """Layer 2 telemetry — install.sh and install.ps1 POST an anonymous
        install_started event to the passport-feedback Cloudflare Worker
        so we can count daily installs by platform. Guards:

        - Honors FCB_NO_ANALYTICS=1 opt-out
        - POSTs in background (non-blocking)
        - Disclosed in the Anthropic-terms consent gate
        - Sends only platform + build_stamp + advisor_id (no IP, no name,
          no machine ID)
        """
        sh = (REPO / "installer" / "install.sh").read_text(encoding="utf-8")
        # Mac side
        self.assertIn('FCB_NO_ANALYTICS:-0', sh,
            "install.sh must check FCB_NO_ANALYTICS env var for opt-out")
        self.assertIn('"event":"install_started"', sh,
            "install.sh must POST install_started event")
        self.assertIn('"platform":"mac"', sh,
            "install.sh must report platform=mac")
        self.assertIn("https://passport-feedback.rafaeldf2.workers.dev/install", sh,
            "install.sh must POST to /install on the Worker")
        # Background so install isn't blocked on telemetry network — the curl
        # POST to passport-feedback must end in a lone backgrounding `&`
        # (after the redirect, followed by space/comment/newline — not `&&`).
        self.assertRegex(sh, r"(?m)2>&1\s+&(?:\s|#|$)",
            "telemetry POST must be backgrounded with `&` after the log redirect")
        # Disclosed in consent
        self.assertIn("anonymous", sh.lower(),
            "consent gate must use the word 'anonymous'")
        self.assertIn("FCB_NO_ANALYTICS", sh,
            "consent gate must mention the opt-out env var")

        # Windows side
        ps1 = (REPO / "installer" / "install.ps1").read_text(encoding="utf-8")
        self.assertIn('$env:FCB_NO_ANALYTICS', ps1,
            "install.ps1 must check FCB_NO_ANALYTICS for opt-out")
        self.assertIn('event = "install_started"', ps1,
            "install.ps1 must POST install_started")
        self.assertIn('platform = "win"', ps1,
            "install.ps1 must report platform=win")
        self.assertIn("https://passport-feedback.rafaeldf2.workers.dev/install", ps1,
            "install.ps1 must POST to /install")
        self.assertIn("Start-Job", ps1,
            "telemetry POST must run as a background job in PowerShell")

    def test_worker_install_endpoint_validates_schema(self):
        """The Worker /install handler must validate the schema and reject:
        - non-POST methods
        - wrong/missing bearer token
        - schemas missing v=1 or event!='install_started'
        - advisor_id mismatch

        Plus it must store counts in KV and never log IP/UA. This test
        reads the Worker source for those guards."""
        worker = (REPO / "cloudflare-worker" / "src" / "index.js").read_text(encoding="utf-8")

        # /install routes go to the right handler
        self.assertIn('if (path === "/install")', worker,
            "Worker must route /install distinct from feedback")
        self.assertIn("handleInstallEvent", worker,
            "Worker must define handleInstallEvent function")
        self.assertIn("handleInstallStats", worker,
            "Worker must define handleInstallStats function for /install/stats GET")

        # Schema validation
        self.assertIn('body.v !== 1', worker,
            "must reject events with wrong schema version")
        self.assertIn('body.event !== "install_started"', worker,
            "must reject events that aren't install_started")

        # Platform sanitization — mac/win only, anything else becomes "unknown"
        self.assertIn('"mac" || body.platform === "win"', worker,
            "platform must be sanitized to a fixed allowlist")

        # KV storage with TTL (90-day retention)
        self.assertIn("FCB_METRICS.put", worker, "must write to KV")
        self.assertIn("expirationTtl", worker, "must set TTL on KV writes")
        self.assertIn("INSTALL_COUNTER_TTL_SECONDS", worker,
            "must use the named TTL constant for retention")

        # Privacy: explicitly does NOT use cf-connecting-ip or user-agent for these events
        # (We assert by absence — those headers are never read in the install path)
        install_handler_start = worker.find("async function handleInstallEvent")
        install_handler_end = worker.find("async function handleInstallStats", install_handler_start)
        self.assertGreater(install_handler_start, 0)
        self.assertGreater(install_handler_end, install_handler_start)
        install_handler = worker[install_handler_start:install_handler_end]
        self.assertNotIn("cf-connecting-ip", install_handler.lower(),
            "install event handler must NOT log client IP")
        self.assertNotIn("user-agent", install_handler.lower(),
            "install event handler must NOT log user-agent")

        # Stats endpoint is admin-gated by GITHUB_TOKEN (more restrictive than
        # the install endpoint's anti-abuse bearer)
        stats_handler_start = worker.find("async function handleInstallStats")
        stats_handler = worker[stats_handler_start:stats_handler_start + 2000]
        self.assertIn("env.GITHUB_TOKEN", stats_handler,
            "/install/stats must require GITHUB_TOKEN as bearer (admin gate)")

    def test_landing_page_assets_resolve_in_publish_bundle(self):
        """Every asset path referenced in installer/index.html must resolve
        to a regular file inside installer/ — NOT a symlink, NOT missing.

        Reason: here-now's publish.sh walks files with `find -type f`, which
        silently skips symlinks. We previously had `installer/assets/brand`
        as a symlink to `assets/brand/`, and the live landing page 404'd on
        the logo + favicon because the PNGs never made it into the publish
        bundle. This test catches that class of failure pre-publish."""
        import re as _re
        installer_dir = REPO / "installer"
        html = (installer_dir / "index.html").read_text(encoding="utf-8")

        # Pull every relative href / src that points inside the bundle. We
        # ignore absolute URLs (http/https/mailto/data:) and in-page anchors.
        candidates = set()
        for m in _re.finditer(r'(?:href|src)="([^"#?][^"#?]*)"', html):
            ref = m.group(1)
            if ref.startswith(("http://", "https://", "mailto:", "data:", "//", "#", "/")):
                continue
            # Strip query strings / fragments just in case.
            ref = ref.split("?", 1)[0].split("#", 1)[0]
            if ref:
                candidates.add(ref)

        # Sanity — we should have caught at least the brand logo + favicon
        # (otherwise the regex broke and the test is useless).
        self.assertTrue(any("brand" in c for c in candidates),
            "regex failed to find any brand assets — test is broken, not the bundle")

        for ref in sorted(candidates):
            target = installer_dir / ref
            self.assertTrue(target.exists(),
                f"installer/index.html references '{ref}' but installer/{ref} does not exist")
            # The here-now publish script uses `find -type f` which does NOT
            # follow symlinks. Reject symlinks anywhere in the resolved path
            # under installer/ so the bundle ships real files.
            cur = target
            while cur != installer_dir and cur.parent != cur:
                self.assertFalse(cur.is_symlink(),
                    f"installer/{ref} resolves through a symlink at {cur} — "
                    f"here-now publish.sh skips symlinks and the live site will 404. "
                    f"Replace with a real file/directory copy.")
                cur = cur.parent

    def test_dashboard_demo_bundle_complete(self):
        """The /dashboard-demo subdirectory of the landing-page bundle is a
        live demo dashboard built by the real skill pipeline against the
        demo-kit fixture. Guard the bundle:

        - index.html exists, fully populated (no `{{ … }}` placeholders left)
        - the dashboard's assets (brand/, fonts/, js/) all exist as real
          files (no symlinks — same regression class as the brand-logo 404)
        - the demo banner is in place so visitors know the data is synthetic
        """
        demo = REPO / "installer" / "dashboard-demo"
        self.assertTrue(demo.is_dir(), "installer/dashboard-demo must exist")
        idx = demo / "index.html"
        self.assertTrue(idx.is_file(), "installer/dashboard-demo/index.html must exist")
        body = idx.read_text(encoding="utf-8")

        # Pipeline must have populated every {{ TOKEN }}. A leftover would mean
        # build_site.py didn't see the workspace data.
        self.assertNotIn("{{", body,
            "dashboard-demo/index.html still has unfilled template placeholders")

        # Demo banner must be present so public visitors know the data is
        # synthetic (real per-client dashboards don't have this).
        self.assertIn("Demo dashboard", body,
            "demo banner must say 'Demo dashboard' so visitors aren't confused")
        self.assertIn("synthetic", body,
            "demo banner must call the data 'synthetic'")

        # Footer footnote must NOT claim this is a passcode-gated private host
        # (the template default copy applies to per-client dashboards, not this
        # public mirror — gets rewritten when copying the build output here).
        self.assertNotIn("only after the passcode is verified", body,
            "demo footer must not claim passcode-gated hosting (it's public)")
        self.assertIn("public demo dashboard", body,
            "demo footer must declare itself as a public demo dashboard")

        # Dashboard's own assets must be real files (no symlinks anywhere).
        for sub in ("assets/brand", "assets/fonts", "assets/js"):
            d = demo / sub
            self.assertTrue(d.is_dir(), f"dashboard-demo/{sub} must exist")
            self.assertFalse(d.is_symlink(),
                f"dashboard-demo/{sub} must be a real directory, not a symlink "
                f"(here-now publish.sh skips symlinks).")
            for f in d.iterdir():
                if f.is_file():
                    self.assertFalse(f.is_symlink(),
                        f"dashboard-demo/{sub}/{f.name} must be a real file, not a symlink")

    def test_install_ps1_exists_with_winget_provisioning(self):
        """B9.16 — first version of the Windows installer. Same UX patterns
        as install.sh (Anthropic terms gate, paced sections, visible
        Read-VisiblePrompt instead of Read-Host -Prompt, Ctrl+C trap
        equivalent, install log to %LOCALAPPDATA%). All system tools come
        through winget. Skills via npx (same as Mac)."""
        ps1 = REPO / "installer" / "install.ps1"
        self.assertTrue(ps1.exists(), "installer/install.ps1 must exist")
        body = ps1.read_text(encoding="utf-8")

        # Header documents the canonical install URL
        self.assertIn(
            "irm https://raw.githubusercontent.com/passporttowealth/passporttowealth/main/installer/install.ps1",
            body, "header must document the canonical irm install URL")

        # winget for tool installs
        for pkg in ("OpenJS.NodeJS.LTS", "astral-sh.uv", "jqlang.jq"):
            self.assertIn(pkg, body, f"winget must install {pkg}")
        self.assertIn("Get-Command winget", body,
            "must check winget is available before using it")

        # Same UX patterns as install.sh
        self.assertIn("Anthropic", body, "Anthropic data-terms gate must be present")
        self.assertIn("I accept", body, "consent gate must accept 'I accept'")
        self.assertIn("Pause-ForUser", body, "paced sections via Pause-ForUser")
        self.assertIn("Read-VisiblePrompt", body,
            "must use Read-VisiblePrompt (not Read-Host -Prompt) for visibility")
        self.assertIn("Test-Diagnostic", body,
            "must run Step 5 diagnostics")

        # Empty input doesn't silently cancel (same B9.12 fix as install.sh)
        # PowerShell switch case "" is the empty-input branch
        self.assertIn('"no","cancel","quit","stop"', body,
            "explicit cancel words only, no empty match")
        self.assertNotIn('"no","cancel","quit","stop","")', body,
            "empty input must NOT be in the cancel branch")
        self.assertIn("emptyCount", body, "must track empty-input count")

        # Workspace at %USERPROFILE%\Documents\my-finances
        self.assertIn('Documents\\my-finances', body,
            "workspace path must mirror Mac convention")

        # Diagnostic checks
        for label in ("Node.js installed (npx)", "uv installed", "jq installed",
                       "Claude Code installed", "Workspace folder", "Workspace venv",
                       "Finance Clarity skill"):
            self.assertIn(label, body, f"diagnostic must check: {label}")

        # End-of-install message tells user how to re-enter (no Desktop shortcut)
        self.assertIn("Open PowerShell", body,
            "end-of-install message should tell user to open PowerShell")
        self.assertIn("type:  claude", body.lower(),
            "should mention typing 'claude'")

        # Log to %LOCALAPPDATA%\PassportToWealth\Logs\
        self.assertIn("LOCALAPPDATA", body)
        self.assertIn("PassportToWealth\\Logs", body)

        # Doesn't fall back to legacy patterns
        self.assertNotIn("[STUB]", body, "no stub markers in install.ps1")


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
        # PYTHON311 must resolve to an absolute path (via `uv python find`),
        # not a bare `python3.11` that PATH lookups could miss. Was a recurring
        # dry-run false-positive before the uv migration.
        self.assertIn('"$UV_BIN" python find 3.11', cmd,
            "PYTHON311 must be resolved via `uv python find 3.11` (absolute path)")
        self.assertIn('if [ -z "$PYTHON311" ] || [ ! -x "$PYTHON311" ]; then', cmd,
            "PYTHON311 must be validated as non-empty + executable after resolution")


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
