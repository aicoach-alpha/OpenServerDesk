import sys, tempfile, json, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import readiness
class ReadinessTests(unittest.TestCase):
    def test_missing_blocks(self):
        with patch.object(readiness,"Path",return_value=Path("/definitely/nonexistent/osd-preflight.json")):
            self.assertFalse(readiness.readiness()["migration_allowed"])
    def test_pass_still_blocks_activation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.json"
            p.write_text(json.dumps({"checks":{"a":True},"casaos_version":"v0.4.15"}))
            with patch.object(readiness,"Path",return_value=p):
                x=readiness.readiness()
            self.assertEqual(x["status"],"preflight_pass")
            self.assertFalse(x["migration_allowed"])
    def test_malformed_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.json";p.write_text("broken")
            with patch.object(readiness,"Path",return_value=p):
                self.assertEqual(readiness.readiness()["status"],"blocked")
