import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ledger  # noqa: E402

LEDGER = ROOT / "ledger.py"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(LEDGER), *args], cwd=ROOT, capture_output=True, text=True)


class LedgerTests(unittest.TestCase):
    def test_percentages_match_the_raw_count(self):
        self.assertIn("180", ledger.numbers("Grew the backlog 180% since I joined."))

    def test_mine_tags_the_gold_set(self):
        result = run("mine")
        self.assertEqual(result.returncode, 0, result.stderr)
        pending = json.loads((ROOT / "out" / "pending.json").read_text())
        tags = {row["id"]: row["tag"] for row in pending["claims"]}
        self.assertEqual(tags["C01"], "verified")
        self.assertEqual(tags["C02"], "retire")
        self.assertEqual(tags["C03"], "verified")
        self.assertEqual(tags["C04"], "estimate")
        self.assertEqual(tags["C05"], "flagged")
        self.assertEqual(tags["C06"], "verified")
        self.assertEqual(tags["C07"], "flagged")

    def test_approve_without_yes_is_not_a_write(self):
        run("mine")
        path = ROOT / "out" / "ledger.json"
        if path.exists():
            path.unlink()
        result = run("approve")
        self.assertEqual(result.returncode, 0)
        self.assertIn("human gate", result.stdout)
        self.assertFalse(path.exists())

    def test_approve_yes_writes_the_ledger(self):
        run("mine")
        result = run("approve", "--yes", "--approver", "Aria Chen")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads((ROOT / "out" / "ledger.json").read_text())
        self.assertEqual(doc["approver"], "Aria Chen")
        self.assertEqual(doc["counts"]["retire"], 1)

    def test_eval_publishes_the_single_system_miss(self):
        result = run("eval")
        self.assertEqual(result.returncode, 1)
        ev = json.loads((ROOT / "out" / "eval.json").read_text())
        self.assertEqual(ev["correct"], 6)
        self.assertEqual(ev["n"], 7)
        self.assertEqual(ev["weak_spot"]["id"], "C07")
        self.assertEqual(ev["weak_spot"]["got"], "flagged")
        self.assertEqual(ev["weak_spot"]["gold"], "verified")


if __name__ == "__main__":
    unittest.main()
