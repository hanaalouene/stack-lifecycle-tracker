import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from versionwatch import fetch, report, store  # noqa: E402


def row(product, cycle, latest, eol=None, is_eol=0, release="2025-01-01", verified=1):
    return {
        "product": product, "label": product.title(), "cycle": cycle, "release_date": release,
        "latest_version": latest, "latest_date": "2026-01-01", "is_lts": 0, "eoas_from": None,
        "eol_from": eol, "is_eol": is_eol, "is_maintained": int(not is_eol), "link": None,
        "source": "test", "verified": verified,
    }


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect(":memory:")
        self.today = dt.date(2026, 11, 1)
        run1 = store.start_run(self.conn)
        store.insert_rows(self.conn, run1, [
            row("mule", "4.10", "4.10.4", eol="2026-12-15"),
            row("mule", "4.9", "4.9.9", eol="2026-10-01", is_eol=1),
            row("java", "21", "21.0.5"),
        ])
        self.run2 = store.start_run(self.conn)
        store.insert_rows(self.conn, self.run2, [
            row("mule", "4.11", "4.11.0", eol="2027-06-30", release="2026-10-01"),
            row("mule", "4.10", "4.10.5", eol="2027-01-31"),
            row("mule", "4.9", "4.9.9", eol="2026-10-01", is_eol=1),
            row("java", "21", "21.0.5"),
        ])
        self.run1 = store.previous_run_id(self.conn, self.run2)

    def test_first_run_has_no_previous(self):
        self.assertIsNone(store.previous_run_id(self.conn, self.run1))

    def test_new_cycle_detected(self):
        got = store.new_cycles(self.conn, self.run2, self.run1)
        self.assertEqual([(r["product"], r["cycle"]) for r in got], [("mule", "4.11")])

    def test_new_latest_version_detected(self):
        got = store.new_latest_versions(self.conn, self.run2, self.run1)
        self.assertEqual([(r["cycle"], r["old_version"], r["new_version"]) for r in got], [("4.10", "4.10.4", "4.10.5")])

    def test_eol_date_change_detected(self):
        got = store.eol_date_changes(self.conn, self.run2, self.run1)
        self.assertEqual([(r["cycle"], r["old_eol"], r["new_eol"]) for r in got], [("4.10", "2026-12-15", "2027-01-31")])

    def test_upcoming_and_recent_eol(self):
        up = store.upcoming_eol(self.conn, self.run2, self.today, 120)
        self.assertEqual([r["cycle"] for r in up], ["4.10"])
        recent = store.recently_eol(self.conn, self.run2, self.today, 60)
        self.assertEqual([r["cycle"] for r in recent], ["4.9"])

    def test_report_renders_and_escapes(self):
        ctx = report.build_context(self.conn, self.run2, self.today, 180, ["x<script>"])
        md, html_body = report.to_markdown(ctx), report.to_html(ctx)
        self.assertIn("4.10.5", md)
        # The report has its own <script> (the filter), so check the injected text, not any script tag.
        self.assertNotIn("x<script>", html_body)
        self.assertIn("x&lt;script&gt;", html_body)

    def test_baseline_report(self):
        ctx = report.build_context(self.conn, self.run1, self.today, 180, [])
        self.assertTrue(ctx["baseline"])


class ManualTests(unittest.TestCase):
    def test_manual_unverified_flag(self):
        path = Path(__file__).resolve().parents[1] / "config" / "manual_releases.toml"
        rows = fetch.load_manual(path, "talend", dt.date(2026, 11, 1))
        self.assertTrue(rows)
        self.assertTrue(all(r["verified"] == 0 for r in rows))


if __name__ == "__main__":
    unittest.main()
