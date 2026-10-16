"""Real loopback Handler auth tests, never touching installed stage users."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import app
import stage_users as user


class StageMultiuserHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="stage-user-http-")
        root=Path(self.tmp.name)/"users"
        root.mkdir(mode=0o700)
        self.patches=[
            patch.object(user,"ROOT",root),
            patch.object(user,"DATABASE",root/"identities.json"),
            patch.object(user,"LOCK",root/".identities.lock"),
            patch.object(user,"enabled",return_value=True),
            patch.object(app,"users_enabled",return_value=True),
        ]
        for item in self.patches:item.start()
        self.admin=user.create("administrator01","administrator")
        self.reader=user.create("reader01","reader")
        self.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()

    def request(self,path,token,method="GET",data=None):
        b="http://127.0.0.1:"+str(self.server.server_port)
        h={"Authorization":"Bearer "+token}
        if data is not None:h["Content-Type"]="application/json"
        req=Request(b+path,method=method,headers=h,data=data)
        try:
            with urlopen(req,timeout=4) as response:
                return response.status,json.load(response)
        except HTTPError as error:
            return error.code,json.load(error)

    def test_reader_whoami_can_read_but_cannot_post(self):
        status,identity=self.request("/api/v1/stage/whoami",self.reader)
        self.assertEqual(status,200)
        self.assertEqual(identity["actor"],"reader01")
        self.assertEqual(identity["role"],"reader")
        self.assertNotIn("write",identity["permissions"])
        status,body=self.request("/api/v1/stage/apps",self.reader,"POST",
                                 b'{"action":"install"}')
        self.assertEqual(status,403)
        self.assertEqual(body["error"],"insufficient_permission")
        status,identity=self.request("/api/v1/stage/whoami",self.admin)
        self.assertEqual(status,200)
        self.assertEqual(identity["role"],"administrator")
        self.assertIn("write",identity["permissions"])

    def test_invalid_stage_token_denied_without_fallback(self):
        status,body=self.request("/api/v1/stage/whoami","0"*64)
        self.assertEqual(status,401)
        self.assertEqual(body["error"],"invalid_credential")


if __name__=="__main__":
    unittest.main()
