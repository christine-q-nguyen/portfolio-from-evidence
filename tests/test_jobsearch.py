import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import jobsearch  # noqa: E402

OUT = ROOT / "out"


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / script), *args], cwd=ROOT, capture_output=True, text=True)


class JobSearchTests(unittest.TestCase):
    def setUp(self):
        run("ledger.py", "mine")
        run("ledger.py", "approve", "--yes", "--approver", "Aria Chen")
        (OUT / "seen.json").unlink(missing_ok=True)

    def tearDown(self):
        (OUT / "seen.json").unlink(missing_ok=True)

    def test_resume_uses_only_approved_claims(self):
        result = run("jobsearch.py", "resume", "--role", "adoption-pm")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (OUT / "resume-adoption-pm.md").read_text()
        self.assertIn("three months to about ten days", text)  # C01, verified
        self.assertIn("97% in our testing", text)  # C04, an estimate in its softened form
        self.assertNotIn("in production", text)
        self.assertNotIn("180%", text)  # C02, retired
        self.assertNotIn("Trained 40 people", text)  # C05, flagged
        self.assertLess(text.index("Sorted 142"), text.index("three months"))  # most relevant to this role first

    def test_resume_waits_for_the_human_gate(self):
        (OUT / "ledger.json").unlink()
        result = run("jobsearch.py", "resume")
        self.assertEqual(result.returncode, 2)
        self.assertIn("approve --yes", result.stderr)

    def test_fit_says_what_to_verify_next(self):
        result = run("jobsearch.py", "fit")
        self.assertEqual(result.returncode, 0, result.stderr)
        fit = json.loads((OUT / "fit.json").read_text())
        self.assertEqual(fit["adoption-pm"]["score"], 80)
        self.assertEqual(fit["service-design-lead"]["score"], 75)
        self.assertEqual(fit["enablement-lead"]["score"], 40)
        waiting = {c for v in fit["enablement-lead"]["verify"] for c in v["claims"]}
        self.assertEqual(waiting, {"C05", "C07"})  # the two flagged claims hold back the role Aria wanted
        self.assertEqual([g["need"] for g in fit["adoption-pm"]["gaps"]], ["Measures adoption"])

    def test_digest_ranks_by_fit_and_remembers_what_it_showed(self):
        result = run("jobsearch.py", "digest")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads((OUT / "digest.json").read_text())
        self.assertEqual(doc["ranked"][0]["id"], "P02")
        self.assertEqual({s["id"] for s in doc["below"]}, {"P04", "P08"})
        contoso = next(s for s in doc["ranked"] if s["id"] == "P01")
        self.assertEqual(contoso["verify"], ["C05", "C07"])
        again = run("jobsearch.py", "digest")
        self.assertIn("no new roles", again.stdout)

    def test_pay_ranges_parse(self):
        self.assertEqual(jobsearch.comp_top("$205,300 – $259,600"), 259600)
        self.assertEqual(jobsearch.comp_top("$146K – $185K • Offers Equity"), 185000)
        self.assertIsNone(jobsearch.comp_top(""))


if __name__ == "__main__":
    unittest.main()
