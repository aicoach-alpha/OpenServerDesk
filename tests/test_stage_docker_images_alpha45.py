"""Focused test of Docker image metadata restricted to proven staging IDs."""
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
        super().__init__("localhost",timeout=8)
        self.socket_path=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(8)
        self.sock.connect(self.socket_path)


class StageDockerImages(unittest.TestCase):
    DIGEST="sha256:"+"a"*64
    OTHER="sha256:"+"b"*64

    def fixture(self):
        return [
          {"Id":c*64,"Names":["/osd-stage-test-"+c],
           "Image":self.DIGEST,"ImageID":self.DIGEST,
           "Labels":{"osd.stage.scope":"staging-only"}} for c in ("c","d")
        ]

    def test_stage_image_records_deduplicate_without_host_metadata(self):
        images=broker.stage_images(self.fixture())
        self.assertEqual(len(images),1)
        self.assertEqual(images[0]["Id"],self.DIGEST)
        self.assertEqual(images[0]["Containers"],2)
        self.assertEqual(images[0]["RepoTags"],[])
        self.assertEqual(images[0]["RepoDigests"],[])
        self.assertNotIn("Docker",str(images))
        self.assertNotIn("Nextcloud",str(images))
        self.assertNotIn("/mnt/",str(images))
        self.assertEqual(broker._resolve_stage_image("a"*64,images),images[0])
        with self.assertRaises(AppError) as unknown:
            broker._resolve_stage_image(self.OTHER,images)
        self.assertEqual(unknown.exception.status,404)

    def test_unverified_or_non_stage_image_sources_rejected(self):
        for key,value in (("ImageID",self.OTHER),
                          ("ImageID","redacted-stage-only"),
                          ("Labels",{"osd.stage.scope":"production"})):
            rows=self.fixture()
            rows[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(AppError):
                broker.stage_images(rows)
        with self.assertRaises(AppError):
            broker._resolve_stage_image("../../../var/lib/docker",[])

    def test_bounded_unix_api_and_mutations_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/"readonly.sock")
            with broker.Server(path,broker.Handler) as server:
                worker=threading.Thread(target=server.serve_forever,
                                        daemon=True)
                worker.start()
                try:
                    with patch.object(broker,"stage_containers",
                                      return_value=self.fixture()):
                        def request(method,url):
                            connection=Unix(path)
                            try:
                                connection.request(method,url,
                                                   headers={"Connection":"close"})
                                result=connection.getresponse()
                                return result.status,result.read()
                            finally:
                                connection.close()
                        status,body=request("GET","/v1.43/images/json?all=1&digests=1")
                        self.assertEqual(status,200)
                        self.assertEqual(len(json.loads(body)),1)
                        status,body=request(
                            "GET","/v1.43/images/"+self.DIGEST+"/json")
                        self.assertEqual(status,200)
                        self.assertEqual(json.loads(body)["Id"],self.DIGEST)
                        self.assertEqual(request(
                            "GET","/images/"+self.OTHER+"/json")[0],404)
                        self.assertEqual(request("GET","/images/json?filters=x")[0],403)
                        self.assertEqual(request("GET","/volumes")[0],403)
                        self.assertEqual(request("POST","/images/create")[0],403)
                        self.assertEqual(request(
                            "DELETE","/images/"+self.DIGEST)[0],403)
                finally:
                    server.shutdown()
                    worker.join(timeout=3)

    def test_registered_real_staging_image_ids_only(self):
        images=broker.stage_images()
        self.assertTrue(images)
        self.assertLessEqual(len(images),broker.MAX_CONTAINERS)
        for item in images:
            self.assertRegex(item["Id"],r"^sha256:[a-f0-9]{64}$")
            self.assertEqual(item["Labels"]["osd.stage.scope"],
                             "staging-only")
            self.assertTrue(set(item["RepoTags"]).issubset(
                broker.PINNED_CATALOG_ALIASES))
            self.assertFalse(item["RepoDigests"])


if __name__=="__main__":
    unittest.main()
