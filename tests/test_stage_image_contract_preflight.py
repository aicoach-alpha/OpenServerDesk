"""Targeted preflight only: no version mutation, no Docker container launches."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError, docker
from stage_store_versions import check_runtime_contract


class ImageContractTests(unittest.TestCase):
    A="sha256:"+"a"*64
    B="sha256:"+"b"*64

    def fake(self,*args):
        self.assertEqual(args[:3],("image","inspect","--format"))
        values={
            self.A:{"User":"node","WorkingDir":"/service","Entrypoint":["node"],
                    "Cmd":["server.js"],"Volumes":{"/data":{}},
                    "ExposedPorts":{"5216/tcp":{}}, "Env":["SECRET=ignored"]},
            self.B:{"User":"root","WorkingDir":"/service","Entrypoint":["node"],
                    "Cmd":["server.js"],"Volumes":{"/data":{}},
                    "ExposedPorts":{"5216/tcp":{}}, "Env":["SECRET=changed"]},
        }
        return json.dumps(values[args[4]])

    def test_changed_user_is_denied_before_shutdown(self):
        with self.assertRaises(AppError) as ex:
            check_runtime_contract(self.A,self.B,self.fake)
        self.assertEqual(ex.exception.message,
                         "stage_image_runtime_contract_incompatible")

    def test_identical_contract_is_allowed(self):
        def same(*args):
            return json.dumps({"User":"node","Entrypoint":["node"],
                "Cmd":["server"],"WorkingDir":"/myspeed",
                "Volumes":{"/myspeed/data":{}},"ExposedPorts":{"5216/tcp":{}}})
        self.assertTrue(check_runtime_contract(self.A,self.B,same)["compatible"])

    def test_image_metadata_never_exposed(self):
        self.assertTrue(check_runtime_contract(self.A,self.A,self.fake)["compatible"])
        with self.assertRaises(AppError):
            check_runtime_contract("../../etc/shadow",self.B,self.fake)

    def test_actual_cached_myspeed_upgrade_blocked_without_mutation(self):
        from stage_store_versions import target_image
        previous=target_image("default:MySpeed","1.0.8")
        latest=target_image("default:MySpeed","latest")
        self.assertNotEqual(previous,latest)
        with self.assertRaises(AppError) as ex:
            check_runtime_contract(previous,latest,docker)
        self.assertEqual(ex.exception.message,
                         "stage_image_runtime_contract_incompatible")


if __name__=="__main__":
    unittest.main()
