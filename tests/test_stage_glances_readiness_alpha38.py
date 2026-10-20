"""One bounded Glances startup-readiness contract check; no Docker."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime
from stage_apps import AppError


class GlancesReadinessBound(unittest.TestCase):
    def test_allow_30_seconds_but_reject_more_than_existing_cap(self):
        manifest={"name":"osd-compiled-123456789abc","services":{"app":{}},
                  "networks":{"isolated":{"internal":True}}}
        services={"app":{"running":True,"health":None,"status":"running"}}
        with (patch.object(runtime,"_published_port",return_value=18720),
              patch.object(runtime,"_owned",return_value=services),
              patch.object(runtime,"_completed_services",return_value=set()),
              patch.object(runtime,"_stage_service_ready",return_value=True),
              patch.object(runtime,"_dependency_map",return_value={}),
              patch.object(runtime,"_private_ready",return_value=True),
              patch.object(runtime.time,"monotonic",side_effect=[100.0,131.0])):
            result=runtime._confirm_ready("osd-compiled-123456789abc",
                                          manifest,"a"*32,grace_seconds=30)
            self.assertTrue(result["running"])
        with self.assertRaises(AppError) as error:
            runtime._confirm_ready("osd-compiled-123456789abc",
                                   manifest,"a"*32,grace_seconds=35)
        self.assertEqual(error.exception.message,"invalid_stage_startup_grace")


if __name__=="__main__":
    unittest.main()
