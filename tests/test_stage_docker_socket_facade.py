"""One targeted safety gate for the read-only synthetic Docker socket."""
import http.client
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError
from stage_store_general import _find_catalog_definition
from stage_store_compiler import analyze,compile_stage
import stage_docker_api_broker as facade
from stage_host_socket import (
    PILOT_ID,PILOT_IMAGE,eligible,is_facade_mount,socket_mount,
)


class UnixClient(http.client.HTTPConnection):
    def __init__(self,path):
        super().__init__("localhost",timeout=4)
        self.sockpath=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(4)
        self.sock.connect(self.sockpath)


class FacadeContractTests(unittest.TestCase):
    def test_exact_curated_catalog_compiler(self):
        _,doc=_find_catalog_definition(PILOT_ID)
        self.assertTrue(eligible(PILOT_ID,doc))
        plan=analyze(doc,resolver=lambda _: "sha256:"+"a"*64,
                     app_id=PILOT_ID)
        self.assertTrue(plan["services"][0]["host_socket_adapter"])
        with patch("stage_store_compiler.analyze",return_value=plan):
            manifest=compile_stage("osd-compiled-123456789abc",PILOT_ID)
        cfg=manifest["services"]["app"]
        self.assertEqual(cfg["volumes"],[socket_mount()])
        self.assertTrue(is_facade_mount(cfg["volumes"][0]))
        self.assertEqual(cfg["user"],"1000:1000")
        self.assertEqual(cfg["cap_drop"],["ALL"])
        self.assertEqual(manifest["networks"],{"isolated":{"internal":True}})
        self.assertNotEqual(cfg["volumes"][0]["source"],"/var/run/docker.sock")
        with self.assertRaises(AppError):
            analyze(doc,resolver=lambda _:None)

    def test_prepare_and_install_preflight_retain_pilot_identity(self):
        from contextlib import nullcontext
        import stage_store_compiler as compiler
        import stage_store_runtime as runtime
        with patch.object(compiler,"analyze",return_value={
            "services":[{"image":PILOT_IMAGE,
                         "immutable_image":"sha256:"+"a"*64}]
        }) as analyze:
            outcome=compiler.prepare_images(PILOT_ID)
        self.assertEqual(outcome["operation"],"already_cached")
        self.assertEqual(analyze.call_args.kwargs["app_id"],PILOT_ID)
        with (patch.object(runtime,"guarded",return_value=nullcontext()),
              patch.object(runtime,"_projects",return_value={}),
              patch.object(compiler,"analyze",return_value={
                  "services":[{"name":"app"}]}) as preflight,
              patch.object(runtime,"_service_budget",
                           side_effect=AppError("preflight_boundary_reached"))):
            with self.assertRaises(AppError) as error:
                runtime.operation("install",app_id=PILOT_ID)
            self.assertEqual(error.exception.message,
                             "preflight_boundary_reached")
            self.assertEqual(preflight.call_args.kwargs["app_id"],PILOT_ID)

    def test_no_other_catalog_or_digest_can_use_socket(self):
        _,doc=_find_catalog_definition(PILOT_ID)
        changed=json.loads(json.dumps(doc))
        changed["services"]["app"]["image"]=PILOT_IMAGE.replace("v11.1.1","v11.1.2")
        self.assertFalse(eligible(PILOT_ID,changed))
        self.assertFalse(eligible("default:Portainer",doc))
        with self.assertRaises(AppError):
            analyze(changed,resolver=lambda _:None,app_id=PILOT_ID)

    def test_readonly_unix_socket_http_and_writes_denied(self):
        with tempfile.TemporaryDirectory() as root:
            path=str(Path(root)/"test.sock")
            server=facade.Server(path,facade.Handler)
            server.timeout=0.4
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                with patch.object(facade,"stage_containers",return_value=[
                    {"Id":"a"*64,"Names":["/osd-stage-test"],
                     "Image":"openserverdesk/stage-only",
                     "Labels":{"osd.stage.scope":"staging-only"}}
                ]):
                    def request(method,url):
                        conn=UnixClient(path)
                        try:
                            conn.request(method,url,headers={"Connection":"close"})
                            res=conn.getresponse()
                            return res.status,res.read()
                        finally:
                            conn.close()
                    self.assertEqual(request("GET","/v1.43/_ping"),(200,b"OK"))
                    code,payload=request("GET","/v1.43/containers/json?all=1")
                    self.assertEqual(code,200)
                    self.assertEqual(len(json.loads(payload)),1)
                    self.assertEqual(request("DELETE","/containers/"+"a"*64)[0],403)
                    self.assertEqual(request("POST","/containers/create")[0],403)
                    self.assertEqual(request("GET","/containers/"+"b"*64+"/json")[0],404)
                    self.assertEqual(request("GET","/containers/"+"a"*64+"/logs")[0],403)
                    self.assertEqual(request("GET","/volumes")[0],403)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_real_stage_metadata_has_no_host_or_user_data(self):
        records=facade.stage_containers()
        self.assertLessEqual(len(records),facade.MAX_CONTAINERS)
        for row in records:
            self.assertEqual(row["Labels"]["osd.stage.scope"],"staging-only")
            self.assertFalse(row["Mounts"])
            self.assertFalse(row["Ports"])
            self.assertNotIn("Nextcloud",str(row))
            self.assertNotIn("/mnt/",str(row))
            self.assertNotIn("casaos",str(row).lower())


if __name__=="__main__":
    unittest.main()
