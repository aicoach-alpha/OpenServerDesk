"""Bounded startup check for real stage-owned Docker applications only."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime
from stage_apps import AppError

PROJECT="osd-compiled-abcdef123456"
OWNER="a"*32
MANIFEST={"services":{"myspeed":{"ports":["127.0.0.1:18720:5216"]}}}
LIVE={"myspeed":{"name":"myspeed","running":True,"status":"running","exit_code":None}}
DEAD={"myspeed":{"name":"myspeed","running":False,"status":"exited","exit_code":1}}

class ReadinessTests(unittest.TestCase):
    def test_stable_app_and_loopback_port_accepted_after_grace(self):
        with patch.object(runtime,"_owned",return_value=LIVE) as owned,\
             patch.object(runtime,"_published_port",return_value=18720),\
             patch.object(runtime,"_tcp_ready",return_value=True) as port,\
             patch.object(runtime.time,"monotonic",side_effect=[0,0,3,6,9,12]),\
             patch.object(runtime.time,"sleep"):
            result=runtime._confirm_ready(PROJECT,MANIFEST,OWNER,grace_seconds=11)
        self.assertTrue(result["running"])
        self.assertEqual(result["checked_services"],1)
        self.assertEqual(owned.call_count,5)
        self.assertEqual(port.call_count,5)

    def test_early_exit_blocks_false_install_success(self):
        with patch.object(runtime,"_owned",side_effect=[LIVE,LIVE,DEAD]),\
             patch.object(runtime,"_published_port",return_value=18720),\
             patch.object(runtime,"_tcp_ready",return_value=True),\
             patch.object(runtime.time,"monotonic",side_effect=[0,1,2,3]),\
             patch.object(runtime.time,"sleep"):
            with self.assertRaises(AppError) as raised:
                runtime._confirm_ready(PROJECT,MANIFEST,OWNER)
        self.assertEqual(raised.exception.message,"compiled_stage_application_exited_during_start")

    def test_web_port_must_respond_at_deadline(self):
        with patch.object(runtime,"_owned",return_value=LIVE),\
             patch.object(runtime,"_published_port",return_value=18720),\
             patch.object(runtime,"_tcp_ready",return_value=False),\
             patch.object(runtime.time,"monotonic",side_effect=[0,12]),\
             patch.object(runtime.time,"sleep"):
            with self.assertRaises(AppError) as raised:
                runtime._confirm_ready(PROJECT,MANIFEST,OWNER)
        self.assertEqual(raised.exception.message,"compiled_stage_application_failed_readiness")

if __name__=="__main__":unittest.main()
