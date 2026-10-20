"""Focused logs API contract: verified stage-only, bounded, no mutations."""
import http.client
import json
import socket
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_docker_api_broker as facade
from stage_apps import AppError


class SocketConnection(http.client.HTTPConnection):
    def __init__(self,path):
        super().__init__("localhost",timeout=7)
        self.sock_path=path

    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(7)
        self.sock.connect(self.sock_path)


class DockerLogsContract(unittest.TestCase):
    def test_bounded_log_query_rejects_unsafe_options(self):
        accepted=facade._log_request(
            "stdout=1&stderr=1&tail=120&timestamps=true&follow=1&since=0")
        self.assertEqual(accepted["tail"],120)
        self.assertTrue(accepted["follow"])
        self.assertEqual(facade._log_request("tail=all")["tail"],facade.MAX_LOG_TAIL)
        for query in ("tail=90000","tail=-1","tail=10&tail=50",
                      "details=true","filters=anything","since=../secret",
                      "stdout=false&stderr=false","until=notadate",
                      "follow=aggressive"):
            with self.subTest(query=query):
                with self.assertRaises(AppError):
                    facade._log_request(query)

    def test_pinned_stage_id_checked_before_docker_logs(self):
        ident="a"*64
        with (patch.object(facade,"stage_containers",return_value=[{"Id":ident}]),
              patch.object(facade,"_log_frames",return_value=b"safe") as mocked):
            self.assertEqual(
                facade._stage_logs_for_id(ident,"tail=10&follow=false"),b"safe")
            mocked.assert_called_once()
            with self.assertRaises(AppError) as e:
                facade._stage_logs_for_id("b"*64,"tail=10")
            self.assertEqual(e.exception.message,
                             "stage_log_container_not_registered")
            self.assertEqual(mocked.call_count,1)

    def test_unix_http_get_logs_and_writes_denied(self):
        ident="a"*64
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/"broker.sock")
            with facade.Server(path,facade.Handler) as server:
                worker=threading.Thread(target=server.serve_forever,daemon=True)
                worker.start()
                try:
                    raw=bytes([1,0,0,0])+struct.pack(">I",5)+b"hello"
                    with (patch.object(facade,"stage_containers",
                                       return_value=[{"Id":ident}]),
                          patch.object(facade,"_log_frames",
                                       return_value=raw)):
                        def request(method,url):
                            conn=SocketConnection(path)
                            try:
                                conn.request(method,url,headers={"Connection":"close"})
                                response=conn.getresponse()
                                return (response.status,dict(response.getheaders()),
                                        response.read())
                            finally:
                                conn.close()
                        status,headers,body=request(
                            "GET","/v1.43/containers/"+ident+
                            "/logs?stdout=1&stderr=1&tail=20&follow=0")
                        self.assertEqual(status,200)
                        self.assertEqual(body,raw)
                        self.assertEqual(headers["Content-Type"],
                                         "application/vnd.docker.raw-stream")
                        self.assertEqual(request(
                            "GET","/containers/"+"b"*64+"/logs?tail=20")[0],404)
                        self.assertEqual(request(
                            "GET","/containers/"+ident+
                            "/logs?tail=all")[0],200)
                        self.assertEqual(request(
                            "GET","/containers/"+ident+"/logs?details=1")[0],403)
                        self.assertEqual(request(
                            "DELETE","/containers/"+ident)[0],403)
                        self.assertEqual(request(
                            "POST","/containers/"+ident+"/exec")[0],403)
                        self.assertEqual(request(
                            "GET","/containers/"+ident+"/archive")[0],403)
                finally:
                    server.shutdown()
                    worker.join(timeout=3)

    def test_real_stage_log_reader_returns_only_verified_ids(self):
        rows=facade.stage_containers()
        self.assertTrue(rows)
        item=rows[0]
        raw=facade._stage_logs_for_id(item["Id"],"tail=3&follow=0")
        self.assertLessEqual(len(raw),facade.MAX_LOG_BYTES+256)
        cursor=0
        while cursor<len(raw):
            self.assertLessEqual(cursor+8,len(raw))
            stream=raw[cursor]
            self.assertIn(stream,(1,2))
            size=struct.unpack(">I",raw[cursor+4:cursor+8])[0]
            cursor+=8+size
        self.assertEqual(cursor,len(raw))
        with self.assertRaises(AppError):
            facade._stage_logs_for_id("0"*64,"tail=3")


if __name__=="__main__":
    unittest.main()
