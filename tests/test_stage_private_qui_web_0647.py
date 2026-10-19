"""Internal Docker bridge frontend and late-ready install regression."""
import sys,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as run
import stage_app_gateway as gateway
from stage_apps import AppError
P="osd-compiled-abcdef123456"
OWNER="a"*32
M={"name":P,"networks":{"isolated":{"internal":True}},
   "services":{"postgres":{"ports":[]},
               "qui":{"ports":["127.0.0.1:19095:7476"]}}}
ITEMS={"qui":{"id":"a"*64,"running":True,"health":"healthy","status":"running"},
       "postgres":{"id":"b"*64,"running":True,"health":"healthy","status":"running"}}
class InternalWebTests(unittest.TestCase):
 def test_exact_verified_bridge_endpoint_only(self):
  obj={"NetworkSettings":{"Networks":{P+"_isolated":{"IPAddress":"172.30.0.4"}}}}
  with patch.object(run,"docker",side_effect=lambda *args,**kwargs:json.dumps([obj])):
   self.assertEqual(run._stage_private_endpoint(P,M,OWNER,ITEMS),("172.30.0.4",7476))
   obj["NetworkSettings"]["Networks"]={"other":{"IPAddress":"172.30.0.4"}}
   with self.assertRaises(AppError):
    run._stage_private_endpoint(P,M,OWNER,ITEMS)
 def test_internal_web_readiness_without_published_host_socket(self):
  with patch.object(run,"_owned",return_value=ITEMS),patch.object(
       run,"_private_ready",return_value=True),patch.object(
       run,"_tcp_ready",side_effect=AssertionError("should not use published host port")),patch.object(
       run.time,"monotonic",side_effect=[0,2]),patch.object(
       run,"_published_port",return_value=19095):
   result=run._confirm_ready(P,M,OWNER,grace_seconds=1)
  self.assertTrue(result["web_reachable"])
 def test_qui_gateway_targets_private_bridge(self):
  a={"project":P,"app_id":"casaos.app:org.icewhale.qui","all_running":True,
     "outbound_network_pilot":False}
  with patch.object(gateway,"listing",return_value={"apps":[a]}),patch.object(
      gateway,"_projects",return_value={P:{"app_id":a["app_id"],"owner":OWNER}}),patch.object(
      gateway,"_current",return_value=(M,ITEMS)),patch.object(
      gateway,"_stage_private_endpoint",return_value=("172.30.0.4",7476)):
   target=gateway._matching(P)
   self.assertEqual(target,("172.30.0.4",7476))
   info,_=gateway.issue(P)
   self.assertEqual(info["scope"],"authenticated_qui_stage_only")
if __name__=="__main__":unittest.main()
