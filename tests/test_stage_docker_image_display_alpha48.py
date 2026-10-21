"""One focused proof: stage-only display tag, immutable ID and event agree."""
import http.client
import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_docker_api_broker as broker
from stage_apps import AppError


class Unix(http.client.HTTPConnection):
    def __init__(self,path):
        super().__init__("localhost",timeout=7)
        self.path=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(7)
        self.sock.connect(self.path)


class StageDisplayContract(unittest.TestCase):
    DIGEST="sha256:"+"a"*64
    TAG="germannewsmaker/myspeed:1.0.8"

    def fixture(self):
        return {"Id":"c"*64,"Names":["/stage-myspeed"],"Image":self.TAG,
                "ImageID":self.DIGEST,"State":"running",
                "Labels":{"osd.stage.scope":"staging-only",
                          "osd.stage.catalog.image_tag":self.TAG}}

    def test_display_tag_image_list_and_event_are_consistent(self):
        row=self.fixture()
        self.assertEqual(broker._stage_display_image(row),self.TAG)
        image=broker.stage_images([row])[0]
        self.assertEqual(image["RepoTags"],[self.TAG])
        self.assertEqual(image["Id"],self.DIGEST)
        event=broker._container_event(row,"start")
        self.assertEqual(event["from"],self.TAG)
        self.assertEqual(event["Actor"]["Attributes"]["image"],self.TAG)
        self.assertEqual(event["Actor"]["Attributes"]["osd.stage.immutable_image"],
                         self.DIGEST)

    def test_changed_or_unapproved_alias_is_denied(self):
        row=self.fixture()
        for change in (
            dict(row,Image="fake/repo:latest"),
            dict(row,ImageID="sha256:"+"b"*64,
                 Image="fake/repo:latest"),
            dict(row,Labels={"osd.stage.scope":"staging-only",
                             "osd.stage.catalog.image_tag":"evil/image:latest"}),
        ):
            with self.subTest(change=change),self.assertRaises(AppError):
                broker._stage_display_image(change)
        no_tag=dict(row,Image=self.DIGEST,
                    Labels={"osd.stage.scope":"staging-only"})
        self.assertEqual(broker._stage_display_image(no_tag),self.DIGEST)
        self.assertEqual(broker._container_event(no_tag,"start")["from"],
                         self.DIGEST)

    def test_unix_container_list_inspection_and_event_contract(self):
        row=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/"broker.sock")
            with broker.Server(path,broker.Handler) as server:
                worker=threading.Thread(target=server.serve_forever,daemon=True)
                worker.start()
                try:
                    with patch.object(broker,"stage_containers",
                                      return_value=[row]):
                        def req(url):
                            connection=Unix(path)
                            try:
                                connection.request("GET",url,
                                                   headers={"Connection":"close"})
                                response=connection.getresponse()
                                return response.status,response.read()
                            finally:connection.close()
                        status,body=req("/v1.43/containers/json?all=1")
                        self.assertEqual(status,200)
                        result=json.loads(body)[0]
                        self.assertEqual(result["Image"],self.TAG)
                        self.assertEqual(result["ImageID"],self.DIGEST)
                        status,body=req("/v1.43/containers/"+row["Id"][:12]+"/json")
                        self.assertEqual(status,200)
                        result=json.loads(body)
                        self.assertEqual(result["Config"]["Image"],self.TAG)
                        self.assertEqual(result["Image"],self.DIGEST)
                finally:
                    server.shutdown()
                    worker.join(timeout=3)

    def test_live_verified_stage_image_keeps_real_digest(self):
        rows=broker.stage_containers(fresh=True)
        self.assertTrue(rows)
        for row in rows:
            name=broker._stage_display_image(row)
            self.assertEqual(name,row["Image"])
            self.assertTrue(row["ImageID"].startswith("sha256:"))
            image=next(x for x in broker.stage_images(rows)
                       if x["Id"]==row["ImageID"])
            self.assertIn(name,image["RepoTags"] if name!=row["ImageID"]
                          else [row["ImageID"]])


if __name__=="__main__":
    unittest.main()
