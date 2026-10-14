import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools/upstream"))
import audit
class TestAudit(unittest.TestCase):
    def test_missing_sources_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):audit.audit(tmp)
    def test_two_required_components(self):
        self.assertEqual(len(audit.COMPONENTS),2)
