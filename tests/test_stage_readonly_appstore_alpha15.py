"""Focused target-:ro compatibility and isolated read-only mount gate."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError
from stage_store_general import _mount_targets,_read_only_targets,_find_catalog_definition
import stage_store_compiler as comp


class ReadonlyAppStoreTests(unittest.TestCase):
    def test_real_fail2ban_and_mame_plans(self):
        for app_id in (
            "github.com:com.bigbeartechworld.fail2ban",
            "github.com:com.bigbeartechworld.mame",
        ):
            with self.subTest(app=app_id):
                _,doc=_find_catalog_definition(app_id)
                plan=comp.analyze(doc,resolver=lambda _: "sha256:"+"a"*64)
                self.assertTrue(plan["all_images_cached"])
                self.assertEqual(len(plan["services"]),1)
                spec=plan["services"][0]
                self.assertTrue(spec["read_only_targets"])
                self.assertTrue(set(spec["read_only_targets"]) <=
                                set(spec["mount_targets"]))
                with patch.object(comp,"analyze",return_value=plan):
                    result=comp.compile_stage("osd-compiled-aabbccddee12",app_id)
                service=next(iter(result["services"].values()))
                self.assertTrue(any(m.get("read_only") is True
                                    for m in service["volumes"]))
                for volume in service["volumes"]:
                    self.assertTrue(volume["source"].startswith(
                        str(comp.STAGE)+"/osd-compiled-aabbccddee12/"))
                    if volume["target"] in spec["read_only_targets"]:
                        self.assertIs(volume["read_only"],True)
                    self.assertNotIn(":ro",volume["target"])

    def test_conflicting_or_dangerous_targets_rejected(self):
        for value in ("/var/run/docker.sock:ro",
                      "/etc/shadow:ro","/var/lib/docker:ro"):
            with self.subTest(value=value):
                with self.assertRaises(AppError):
                    _mount_targets({"volumes":[{
                        "type":"bind","source":"/unused","target":value}]})
        with self.assertRaises(AppError):
            _mount_targets({"volumes":[{
                "type":"bind","source":"/unused","target":"/mame:ro",
                "read_only":False}]})
        expected=_mount_targets({"volumes":[{
            "type":"bind","source":"/unused","target":"/mame:ro"}]})
        self.assertEqual(expected,["/mame"])
        self.assertEqual(_read_only_targets({"volumes":[{
            "type":"bind","source":"/unused","target":"/mame:ro"}]}),
                         {"/mame"})

if __name__=="__main__":
    unittest.main()
