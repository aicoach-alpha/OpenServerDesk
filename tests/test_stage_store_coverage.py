"""Focused classification tests, no Docker or user files touched."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_store_coverage import evaluate

class CoverageTests(unittest.TestCase):
    def test_single_image_is_only_statically_eligible(self):
        self.assertEqual(evaluate({"services":{"app":{"image":"vendor/app:1.2"}}}),
                         "eligible_for_isolated_staging")
    def test_multi_service_requires_engine(self):
        self.assertEqual(evaluate({"services":{"db":{"image":"db:1"},"web":{"image":"web:2"}}}),
                         "requires_multiservice_engine")
    def test_dangerous_options_flagged(self):
        self.assertEqual(evaluate({"services":{"web":{"image":"web:2","build":"."}}}),
                         "advanced_runtime_options")
    def test_unpinned_image_flagged(self):
        self.assertEqual(evaluate({"services":{"web":{"image":"example:latest"}}}),
                         "image_tag_not_pinned")
    def test_user_data_mount_does_not_leak_to_report(self):
        self.assertEqual(evaluate({"services":{"web":{"image":"example:1","volumes":["/mnt/data:/proc"]}}}),
                         "unsupported_volume_mapping")

if __name__=="__main__":unittest.main()
