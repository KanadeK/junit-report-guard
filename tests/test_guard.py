from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from junit_report_guard import audit


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def xml(self, text: str, name: str = "input.xml", encoding: str = "utf-8") -> Path:
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return path

    def codes(self, result):
        return {finding["code"] for finding in result["findings"]}

    def test_realistic_nested_counts_and_outcomes(self):
        path = self.xml("""<testsuites tests="4" errors="1" failures="1" skipped="1">
          <testsuite name="outer" tests="4">
            <testcase name="pass"/>
            <testcase name="fail"><failure/><failure/></testcase>
            <testsuite name="nested" tests="2">
              <testcase name="error"><error/></testcase>
              <testcase name="skip"><skipped/></testcase>
            </testsuite>
          </testsuite></testsuites>""")
        result = audit([path])
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            result["totals"], {"tests": 4, "errors": 1, "failures": 1, "skipped": 1, "passed": 1}
        )
        self.assertIn("test-failures", self.codes(audit([path], require_success=True)))

    def test_duplicate_identity_across_shards(self):
        one = self.xml('<testsuite name="a"><testcase classname="X" name="same"/></testsuite>')
        two = self.xml(
            '<testsuite name="b"><testcase classname="X" name="same"/></testsuite>', "other.xml"
        )
        result = audit([one, two])
        finding = result["findings"][0]
        self.assertEqual(finding["code"], "duplicate-test")
        self.assertEqual(finding["first"]["file"], str(one))
        self.assertEqual(finding["file"], str(two))

    def test_distinct_classnames_are_distinct(self):
        path = self.xml(
            '<testsuite><testcase classname="A" name="x"/>'
            '<testcase classname="B" name="x"/></testsuite>'
        )
        self.assertTrue(audit([path])["ok"])

    def test_empty_missing_input_and_file_count(self):
        self.assertIn("no-input", self.codes(audit([])))
        path = self.xml('<testsuite tests="0"/>')
        self.assertIn("empty-report", self.codes(audit([path], require_files=2)))
        self.assertIn("file-count", self.codes(audit([path], require_files=2)))

    def test_stale_and_invalid_counts(self):
        path = self.xml('<testsuite tests="3" skipped="-1"><testcase name="x"/></testsuite>')
        self.assertEqual(self.codes(audit([path])), {"count-mismatch", "invalid-count"})

    def test_invalid_timings(self):
        for value in ("-1", "NaN", "Infinity", "bad", "1e99999999999999999999"):
            with self.subTest(value=value):
                path = self.xml(f'<testsuite><testcase name="x" time="{value}"/></testsuite>')
                self.assertIn("invalid-time", self.codes(audit([path])))

    def test_finite_scientific_time(self):
        path = self.xml('<testsuite time="1e-4"><testcase name="x" time="0"/></testsuite>')
        self.assertTrue(audit([path])["ok"])

    def test_missing_name_and_conflicting_outcome(self):
        path = self.xml("<testsuite><testcase><failure/><skipped/></testcase></testsuite>")
        self.assertEqual(self.codes(audit([path])), {"missing-name", "conflicting-outcomes"})

    def test_namespace_and_unicode(self):
        path = self.xml('<testsuite xmlns="urn:junit"><testcase name="中文✓"/></testsuite>')
        self.assertTrue(audit([path])["ok"])

    def test_dtd_rejected_even_utf16(self):
        text = (
            '<!DOCTYPE testsuite [<!ENTITY leak "PRIVATE_MARKER">]>'
            '<testsuite><testcase name="&leak;"/></testsuite>'
        )
        for encoding in ("utf-8", "utf-16"):
            with self.subTest(encoding=encoding):
                result = audit([self.xml(text, encoding=encoding)])
                self.assertEqual(self.codes(result), {"input-error"})
                self.assertNotIn("PRIVATE_MARKER", json.dumps(result))

    def test_malformed_missing_and_nonfile(self):
        for path in (self.xml("<testsuite>"), self.root / "missing", self.root):
            with self.subTest(path=path):
                self.assertIn("input-error", self.codes(audit([path])))

    def test_hidden_testcase_and_wrong_root(self):
        path = self.xml('<testsuite><extension><testcase name="hidden"/></extension></testsuite>')
        self.assertIn("hidden-testcase", self.codes(audit([path])))
        path = self.xml('<testcase name="x"/>')
        self.assertIn("root-element", self.codes(audit([path])))

    def test_resource_limits(self):
        path = self.xml('<testsuite><testcase name="x"/><testcase name="y"/></testsuite>')
        self.assertIn("input-error", self.codes(audit([path], max_bytes=3)))
        self.assertIn("input-error", self.codes(audit([path], max_cases=1)))
        self.assertIn("input-error", self.codes(audit([path], max_depth=1)))
        for options in ({"max_bytes": 0}, {"max_findings": -1}, {"require_files": 0}):
            with self.assertRaises(ValueError):
                audit([path], **options)

    def test_duplicate_input_and_bounded_findings(self):
        path = self.xml('<testsuite tests="99"><testcase/><testcase/></testsuite>')
        result = audit([path, path], max_findings=1)
        self.assertEqual(len(result["findings"]), 1)
        self.assertTrue(result["findings_truncated"])
        self.assertEqual(result["finding_count"], 4)

    def test_cli_privacy_exit_codes_and_no_modification(self):
        path = self.xml(
            '<testsuite><testcase name="failed"><failure message="SECRET_CELL">'
            "PRIVATE_TRACE</failure><system-out>SECRET_LOG</system-out>"
            "</testcase></testsuite>"
        )
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        result = subprocess.run(
            [sys.executable, "-m", "junit_report_guard", str(path), "--json", "--require-success"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        for secret in ("SECRET_CELL", "PRIVATE_TRACE", "SECRET_LOG"):
            self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        bad = subprocess.run(
            [sys.executable, "-m", "junit_report_guard", str(path), "--max-findings", "0"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(bad.returncode, 2)

    def test_published_examples(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        report = audit([examples / "shard-a.xml", examples / "shard-b.xml"], require_files=2)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["totals"]["tests"], 3)
        broken = audit([examples / "broken.xml"])
        self.assertEqual(self.codes(broken), {"duplicate-test", "count-mismatch"})


if __name__ == "__main__":
    unittest.main()
