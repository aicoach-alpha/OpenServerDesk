"""Targeted proof for Dozzle Docker events, short IDs and bounded stats."""
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
import stage_docker_api_broker as facade
import stage_docker_api_stats as stats
from stage_apps import AppError


class Unix(http.client.HTTPConnection):
    def __init__(self,path):
        super().__init__("localhost",timeout=12)
        self.path=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(12)
        self.sock.connect(self.path)


class DockerStageEventsStats(unittest.TestCase):
    A="a"*64
    B="b"*64

    def fixture(self):
        return [{"Id":self.A,"Names":["/osd-stage-app"],
                 "Labels":{"osd.stage.scope":"staging-only"},
                 "Image":"sha256:"+"a"*64,
                 "ImageID":"sha256:"+"a"*64,
                 "State":"running"}]

    def test_prefix_can_only_resolve_verified_stage_id(self):
        data=self.fixture()
        self.assertEqual(facade._resolve_stage_item("a"*12,data)["Id"],self.A)
        with self.assertRaises(AppError):
            facade._resolve_stage_item("b"*12,data)
        with self.assertRaises(AppError):
            facade._resolve_stage_item("a"*11,data)
        with self.assertRaises(AppError):
            facade._resolve_stage_item("a"*12,data+[dict(data[0],Id="a"*12+"c"*52)])

    def test_stage_lifecycle_event_image_matches_immutable_inventory(self):
        row=self.fixture()[0]
        event=facade._container_event(row,"start")
        self.assertEqual(event["Actor"]["Attributes"]["image"],row["ImageID"])
        self.assertEqual(event["from"],row["ImageID"])
        changed=dict(row,ImageID="openserverdesk/stage-only")
        with self.assertRaises(AppError):
            facade._container_event(changed,"start")

    def test_event_and_stats_options_are_readonly_bounded(self):
        self.assertEqual(facade._event_request(
            "since=0&filters=%7B%22type%22%3A%5B%22container%22%5D%7D")["since"],"0")
        self.assertFalse(facade._stats_request("stream=0&one-shot=1"))
        for param in ("filters={bad-json}","since=-1","until=../../etc/passwd",
                      "filters=%7B%22volume%22%3A%5B%22all%22%5D%7D",
                      "since=1&since=2"):
            with self.subTest(param=param), self.assertRaises(AppError):
                facade._event_request(param)
        for param in ("stream=maybe","filters=all","stream=1&stream=0"):
            with self.subTest(param=param), self.assertRaises(AppError):
                facade._stats_request(param)

    def test_socket_event_stream_stats_and_short_id(self):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/"read.sock")
            with facade.Server(path,facade.Handler) as server:
                thread=threading.Thread(target=server.serve_forever,daemon=True)
                thread.start()
                try:
                    values=self.fixture()
                    fake_stats={"id":self.A,"pids_stats":{"current":3},
                                "memory_stats":{"usage":128,"limit":268435456}}
                    with (patch.object(facade,"stage_containers",
                                       return_value=values),
                          patch.object(facade,"stage_stats_snapshot",
                                       return_value=fake_stats),
                          patch.object(facade,"MAX_EVENT_SECONDS",.12),
                          patch.object(facade,"MAX_STATS_SECONDS",.12)):
                        def req(method,uri):
                            c=Unix(path)
                            try:
                                c.request(method,uri,headers={"Connection":"close"})
                                res=c.getresponse()
                                return res.status,dict(res.getheaders()),res.read()
                            finally:c.close()
                        status,_,raw=req("GET","/v1.43/containers/"+self.A[:12]+"/json")
                        self.assertEqual(status,200)
                        self.assertEqual(json.loads(raw)["Id"],self.A)
                        status,_,raw=req("GET","/v1.43/events?since=0")
                        self.assertEqual(status,200)
                        records=[json.loads(x) for x in raw.splitlines() if x]
                        self.assertTrue(records)
                        self.assertTrue(all(row["Actor"]["ID"]==self.A for row in records))
                        self.assertTrue(all(row["Type"]=="container" for row in records))
                        status,_,raw=req(
                            "GET","/containers/"+self.A[:12]+"/stats?stream=0")
                        self.assertEqual(status,200)
                        self.assertEqual(json.loads(raw)["id"],self.A)
                        status,_,raw=req(
                            "GET","/containers/"+self.A[:12]+"/stats?stream=1")
                        self.assertEqual(status,200)
                        self.assertTrue(json.loads(raw.splitlines()[0]))
                        self.assertEqual(req("POST","/containers/"+self.A+"/start")[0],403)
                        self.assertEqual(req("GET","/networks")[0],403)
                finally:
                    server.shutdown()
                    thread.join(timeout=3)

    def test_actual_stage_stats_from_verifiable_id(self):
        rows=facade.stage_containers()
        self.assertTrue(rows)
        result=stats.snapshot(rows[0])
        self.assertEqual(result["id"],rows[0]["Id"])
        self.assertGreaterEqual(result["memory_stats"]["usage"],0)
        self.assertEqual(result["osd_source"],"staging_verified_docker_stats_cli")
        self.assertEqual(result["networks"],{})
        self.assertNotIn("/mnt/",str(result))


if __name__=="__main__":
    unittest.main()
