import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_topology_health as h
from stage_apps import AppError

class HealthTests(unittest.TestCase):
    def test_mixed_statuses_are_visible_without_data_leak(self):
        registry={
            "osd-m1-topology-"+"a"*12:{"containers":{"one":"1"*64,"two":"2"*64}},
            "osd-m1-topology-"+"b"*12:{"containers":{"one":"3"*64}},
            "osd-m1-topology-"+"c"*12:{"containers":{"one":"4"*64}},
        }
        def fake(project,entry):
            if "bbbb" in project:
                return {"services":[{"running":False}]}
            if "cccc" in project:
                raise AppError("topology_container_provenance_violation",403)
            return {"services":[{"running":True},{"running":True}]}
        with patch.object(h,"guarded") as lock, \
             patch.object(h,"_registry",return_value=registry), \
             patch.object(h,"_verified",side_effect=fake):
            result=h.inspect()
        self.assertEqual(result["project_count"],3)
        self.assertEqual(result["healthy_projects"],1)
        self.assertEqual(result["degraded_projects"],1)
        self.assertEqual(result["unavailable_projects"],1)
        self.assertEqual(result["projects"][2]["running_services"],None)
        self.assertFalse(result["migration_allowed"])
        self.assertFalse(result["nextcloud_data_inspected"])
        self.assertNotIn("/mnt/data",str(result))
        self.assertNotIn("1"*64,str(result))

    def test_fail_closed_unknown_error_and_empty_projects(self):
        with patch.object(h,"guarded"),patch.object(h,"_registry",return_value={}):
            result=h.inspect()
        self.assertEqual(result["project_count"],0)
        self.assertEqual(result["healthy_projects"],0)
        entry={"containers":{"one":"0"*64}}
        with patch.object(h,"guarded"),patch.object(h,"_registry",return_value={
                "osd-m1-topology-"+"f"*12:entry}), \
             patch.object(h,"_verified",side_effect=AppError("SECRET_RAW_PATH",503)):
            result=h.inspect()
        self.assertEqual(result["projects"][0]["issue"],"unverified_service_identity")
        self.assertNotIn("SECRET_RAW_PATH",str(result))

if __name__=="__main__":unittest.main()
