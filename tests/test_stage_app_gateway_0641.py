import sys,unittest,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_app_gateway as gate
from stage_apps import AppError
PROJECT="osd-compiled-abcdef123456"
BASE="/stage-app/"+PROJECT+"/"
class GatewayTests(unittest.TestCase):
 def setUp(self):
  with gate._lock:gate._sessions.clear()
 def test_requires_session(self):
  with self.assertRaises(AppError) as e:gate.proxy("GET",BASE,"",{})
  self.assertEqual(e.exception.status,401)
 def test_session_scoped_and_denies_foreign_app(self):
  candidate={"project":PROJECT,"app_id":"default:MySpeed","outbound_network_pilot":True,"all_running":True,"web_url":"http://127.0.0.1:18720"}
  with patch.object(gate,"listing",return_value={"apps":[candidate]}):
   doc,cookie=gate.issue(PROJECT)
   self.assertEqual(doc["entry"],BASE)
   for item in ("HttpOnly","SameSite=Strict","Path="+BASE):self.assertIn(item,cookie)
   gate._cookie(PROJECT,cookie.split(";",1)[0])
   candidate["app_id"]="other:app"
   with self.assertRaises(AppError):gate.issue(PROJECT)
 def test_expires(self):
  with patch.object(gate,"_matching",return_value=18720):_,cookie=gate.issue(PROJECT)
  token=cookie.split("=",1)[1].split(";",1)[0]
  with gate._lock:gate._sessions[token]=(PROJECT,time.monotonic()-1)
  with self.assertRaises(AppError):gate._cookie(PROJECT,cookie.split(";",1)[0])
 def test_no_path_escape(self):
  for bad in (BASE+"../../x",BASE+"%2e%2e/foo",BASE+"%2f%2fexample.com",BASE+"hello%5cworld",BASE+"a//b","/stage-app/foreign/x",BASE+"a/./b"):
   with self.subTest(bad=bad),self.assertRaises(AppError):gate.parse_route(bad)
  self.assertEqual(gate.parse_route(BASE+"assets/my.js?abc=1"),(PROJECT,"/assets/my.js?abc=1"))
 def test_asset_and_api_rewriting(self):
  html=b'<script src="/assets/app.js"></script><a href="/api"></a>'
  data=gate.rewrite(html,"text/html; charset=utf-8",PROJECT)
  self.assertIn((BASE+"assets/app.js").encode(),data)
  self.assertIn((BASE+"api").encode(),data)
  self.assertEqual(gate.rewrite(b"binary","image/png",PROJECT),b"binary")
 def test_loopback_only(self):
  a={"project":PROJECT,"app_id":"default:MySpeed","outbound_network_pilot":True,"all_running":True,"web_url":"http://127.0.0.1:18800"}
  with patch.object(gate,"listing",return_value={"apps":[a]}):
   self.assertEqual(gate._matching(PROJECT),18800)
   a["web_url"]="http://169.254.169.254:18800"
   with self.assertRaises(AppError):gate._matching(PROJECT)
 def test_origin_protected(self):
  with patch.object(gate,"_matching",return_value=18800):_,cookie=gate.issue(PROJECT)
  with patch.object(gate,"_matching",return_value=18800):
   with self.assertRaises(AppError) as e:gate.proxy("POST",BASE+"api",cookie.split(";",1)[0],{"Origin":"https://evil.example"},b'{}')
  self.assertEqual(e.exception.status,403)
if __name__=="__main__":unittest.main()
