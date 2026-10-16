import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_general as g

SHA="sha256:"+"a"*64
class ImmutableImageTests(unittest.TestCase):
    def test_current_native_catalog_image_resolves_content(self):
        plan=g.preflight("default:MySpeed")
        self.assertTrue(plan["eligible"])
        self.assertTrue(plan["image_cached"])
        self.assertRegex(plan["image_id"],r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(plan["immutable_image_id_verified"])
    def test_latest_source_resolves_to_immutable_local_image(self):
        doc={"services":{"web":{"image":"redis:latest","ports":["9000:9000"]}}}
        with patch.object(g,"_find_catalog_definition",return_value=({"title":"Redis"},doc)),\
             patch.object(g,"_command",return_value=SHA) as docker:
            plan=g.preflight("default:Redis")
        self.assertEqual(plan["image"],"redis:latest")
        self.assertEqual(plan["image_id"],SHA)
        self.assertTrue(plan["eligible"])
        docker.assert_called_with("image","inspect","--format","{{.Id}}",
                                  "redis:latest",timeout=12)
    def test_unversioned_image_can_be_pinned_in_cache(self):
        doc={"services":{"web":{"image":"redis"}}}
        with patch.object(g,"_find_catalog_definition",return_value=({"title":"Redis"},doc)),\
             patch.object(g,"_command",return_value=SHA):
            plan=g.preflight("default:Redis")
        self.assertTrue(plan["eligible"])
        self.assertEqual(plan["image_id"],SHA)
    def test_no_image_cache_stays_blocked_from_install(self):
        doc={"services":{"web":{"image":"redis:latest"}}}
        with patch.object(g,"_find_catalog_definition",return_value=({"title":"Redis"},doc)),\
             patch.object(g,"_command",side_effect=g.AppError("not_cached",503)):
            plan=g.preflight("default:Redis")
        self.assertTrue(plan["eligible"])
        self.assertFalse(plan["image_cached"])
        self.assertIsNone(plan["image_id"])
    def test_malicious_image_not_processed(self):
        doc={"services":{"web":{"image":"redis:latest;rm -rf /"}}}
        with patch.object(g,"_find_catalog_definition",return_value=({"title":"Bad"},doc)),\
             patch.object(g,"_command",side_effect=AssertionError("should not inspect")):
            plan=g.preflight("default:Bad")
        self.assertFalse(plan["eligible"])
if __name__=="__main__":unittest.main()
