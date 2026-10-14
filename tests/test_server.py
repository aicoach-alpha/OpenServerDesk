import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from app import Handler
class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.url="http://127.0.0.1:"+str(cls.http.server_address[1])
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close()
    def test_health(self):
        with urlopen(self.url+"/health") as r:
            self.assertEqual(r.status,200)
            self.assertIn(b'"environment": "staging"',r.read())
    def test_capability_denies_mutation(self):
        with urlopen(self.url+"/api/v1/capabilities") as r:
            self.assertIn(b'"production_changes": false',r.read())
    def test_missing_resource(self):
        with self.assertRaises(HTTPError) as e:urlopen(self.url+"/missing")
        self.assertEqual(e.exception.code,404)
    def test_post_rejected(self):
        with self.assertRaises(HTTPError) as e:urlopen(Request(self.url+"/api/v1/capabilities",data=b"{}"))
        self.assertEqual(e.exception.code,405)
