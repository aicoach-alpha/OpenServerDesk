"""Fast boundary tests for compiled App Store runtime, with no Docker mutation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime
from stage_apps import AppError

class RuntimeTests(unittest.TestCase):
    def test_unsafe_projects_rejected(self):
        for value in ("nextcloud", "../root", "/mnt/data", "osd-compiled-nothex",
                      "osd-compiled-abcdef123456/.."):
            with self.subTest(value=value):
                with self.assertRaises(AppError):
                    runtime._folder(value)

    def test_unapproved_operations_denied(self):
        for verb in ("delete-production", "exec", "prune", "down-all"):
            with self.subTest(verb=verb):
                with self.assertRaises(AppError):
                    runtime.operation(verb,project="osd-compiled-abcdef123456")

    def test_manifest_never_grants_published_ports(self):
        project="osd-compiled-abcdef123456"
        image="sha256:"+"a"*64
        owner="f"*32
        spec={
            "name":project,
            "services":{"web":{
                "image":image,"pull_policy":"never","network_mode":"none",
                "cap_drop":["ALL"],
                "security_opt":["no-new-privileges:true"],
                "user":"1000:1000","pids_limit":64,"mem_limit":"256m",
                "restart":"no","volumes":[],
                "labels":{"osd.m1.compiled":"staging-only",
                          "osd.m1.compiled.project":project,
                          "osd.m1.compiled.service":"web",
                          "osd.m1.compiled.app":"default:MySpeed",
                          "osd.m1.compiled.owner":owner},
            }},
        }
        with patch.object(runtime,"_folder",return_value=Path("/tmp")):
            runtime._validate(project,spec,owner)
            spec["services"]["web"]["ports"]=["443:443"]
            with self.assertRaises(AppError):
                runtime._validate(project,spec,owner)

    def test_unknown_container_ids_rejected(self):
        project="osd-compiled-abcdef123456"
        manifest={"name":project,"services":{"web":{}}}
        with patch.object(runtime,"_validate"), \
             patch.object(runtime,"docker",return_value="not-a-valid-container-id"):
            with self.assertRaises(AppError):
                runtime._verify_partial(project,manifest,"a"*32)

if __name__=="__main__":
    unittest.main()
