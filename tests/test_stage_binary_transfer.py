"""Real isolated HTTP binary upload/download tests, no NAS user-data mounts."""
from contextlib import nullcontext
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_users as user
import stage_storage as storage
import app


class StageBinaryTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="osd-binary-stage-")
        self.root=Path(self.temp.name)
        identities=self.root/"identities"
        files=self.root/"files"
        identities.mkdir(mode=0o700)
        files.mkdir(mode=0o700)
        self.patches=[
            patch.object(user,"ROOT",identities),
            patch.object(user,"DATABASE",identities/"identities.json"),
            patch.object(user,"LOCK",identities/".identities.lock"),
            patch.object(user,"enabled",return_value=True),
            patch.object(app,"users_enabled",return_value=True),
            patch.object(storage,"ROOT",files),
            patch.object(storage,"guarded",side_effect=lambda:nullcontext()),
        ]
        for p in self.patches:p.start()
        self.admin=user.create("administrator01","administrator")
        self.reader=user.create("reader01","reader")
        self.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base="http://127.0.0.1:"+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def request(self,name,token,payload=None):
        headers={"Authorization":"Bearer "+token}
        if payload is not None:
            headers["Content-Type"]="application/octet-stream"
            headers["X-OSD-Filename"]=name
            url=self.base+"/api/v1/stage/upload"
            method="POST"
        else:
            url=self.base+"/api/v1/stage/download?name="+name
            method="GET"
        req=Request(url,headers=headers,data=payload,method=method)
        try:
            with urlopen(req,timeout=5) as response:
                return response.status,response.read()
        except HTTPError as error:
            return error.code,error.read()

    def test_opaque_binary_roundtrip_no_overwrite(self):
        value=b"\x00\xff\x80\xc0\x09FILE\x00"*120
        code,result=self.request("stage-binary.bin",self.admin,value)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(result)["bytes"],len(value))
        code,data=self.request("stage-binary.bin",self.reader)
        self.assertEqual(code,200)
        self.assertEqual(data,value)
        code,result=self.request("stage-binary.bin",self.admin,value)
        self.assertEqual(code,409)
        self.assertEqual(json.loads(result)["error"],
                         "existing_stage_file_must_not_be_overwritten")
        self.assertEqual((self.root/"files/stage-binary.bin").read_bytes(),value)

    def test_reader_denied_upload_and_bad_path(self):
        status,response=self.request("stage.txt",self.reader,b"123")
        self.assertEqual(status,403)
        self.assertEqual(json.loads(response)["error"],"insufficient_permission")
        status,response=self.request("../outside",self.admin,b"123")
        self.assertEqual(status,400)
        self.assertEqual(json.loads(response)["error"],"invalid_stage_filename")
        self.assertFalse((self.root/"outside").exists())

    def test_oversized_upload_rejected(self):
        code,response=self.request("huge.bin",self.admin,b"X"*65537)
        self.assertEqual(code,413)
        self.assertFalse((self.root/"files/huge.bin").exists())


if __name__=="__main__":
    unittest.main()
