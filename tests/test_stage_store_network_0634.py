"""Staging-only isolated network rules; no Docker or host filesystem operations."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_compiler as compiler
import stage_store_runtime as runtime
from stage_apps import AppError

class NetworkSafety(unittest.TestCase):
    def test_loopback_port_rules(self):
        self.assertTrue(runtime.PORT.fullmatch("127.0.0.1:18720:80"))
        self.assertTrue(runtime.PORT.fullmatch("127.0.0.1:19999:65535"))
        for bad in ("0.0.0.0:18720:80","127.0.0.1:18690:80",
                    "127.0.0.1:19999:invalid","127.0.0.1:20000:80"):
            self.assertFalse(runtime.PORT.fullmatch(bad),bad)

    def test_compiler_removes_source_host_binding_and_original_secrets(self):
        project="osd-compiled-abcdef123456"
        doc={"services":{"app":{"image":"example:1",
                     "ports":["0.0.0.0:443:8080"],
                     "environment":{"PASSWORD":"NEVER_REUSE"},
                     "volumes":["/mnt/data/nextcloud:/app/data"]},
                "db":{"image":"db:1"}}}
        original=compiler.analyze
        with patch.object(compiler,"_find_catalog_definition",return_value=({},doc)), \
             patch.object(compiler,"analyze",side_effect=lambda d:original(
                 d,resolver=lambda _: "sha256:"+"a"*64)):
            plan=compiler.compile_stage(project,"test:app",host_port=18722)
        self.assertEqual(plan["services"]["app"]["ports"],["127.0.0.1:18722:8080"])
        self.assertEqual(plan["networks"],{"isolated":{"internal":True}})
        self.assertNotIn("NEVER_REUSE",str(plan))
        self.assertNotIn("/mnt/data",str(plan))

    def test_runtime_rejects_external_network_and_ports(self):
        project="osd-compiled-abcdef123456"
        owner="a"*32
        data={"name":project,"networks":{"isolated":{"internal":True}},
              "services":{"web":{"image":"sha256:"+"b"*64,"pull_policy":"never",
                  "networks":["isolated"],"cap_drop":["ALL"],"security_opt":["no-new-privileges:true"],
                  "user":"1000:1000","pids_limit":64,"mem_limit":"256m",
                  "restart":"no","volumes":[],
                  "ports":["127.0.0.1:18722:80"],
                  "labels":{"osd.m1.compiled":"staging-only","osd.m1.compiled.project":project,
                            "osd.m1.compiled.service":"web","osd.m1.compiled.app":"test:app",
                            "osd.m1.compiled.owner":owner}}}}
        with patch.object(runtime,"_folder",return_value=Path("/tmp")):
            runtime._validate(project,data,owner)
            data["services"]["web"]["ports"]=["0.0.0.0:18722:80"]
            with self.assertRaises(AppError):
                runtime._validate(project,data,owner)

if __name__=="__main__":unittest.main()
