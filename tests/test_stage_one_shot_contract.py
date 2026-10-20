"""Focused source-level gate for stage-only completed init-service lifecycle."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError
from stage_store_compiler import analyze
from stage_store_general import _find_catalog_definition
from stage_multiservice_health import assess
from stage_store_runtime import (
    _completed_services, _dependency_map, _stage_service_ready,
    _wait_for_dependency,
)


class OneShotContract(unittest.TestCase):
    def test_real_casaos_one_shot_catalogs(self):
        ids=(
            "github.com:com.bigbeartechworld.buzz",
            "github.com:com.bigbeartechworld.ente",
            "casaos.app:org.icewhale.openclaw",
        )
        for app_id in ids:
            with self.subTest(app=app_id):
                _,doc=_find_catalog_definition(app_id)
                plan=analyze(doc,resolver=lambda _:None)
                manifest={"services":{}}
                for spec in plan["services"]:
                    deps=spec["dependency_conditions"]
                    manifest["services"][spec["name"]]={
                        "depends_on":({name:{"condition":condition}
                                       for name,condition in deps.items()} if deps else [])
                    }
                completed=_completed_services(manifest)
                self.assertTrue(completed)
                self.assertTrue(all(x in manifest["services"] for x in completed))
                self.assertTrue(any(
                    "service_completed_successfully" in spec["dependency_conditions"].values()
                    for spec in plan["services"]))
                self.assertIsInstance(_dependency_map(manifest),dict)

    def test_expected_exit_zero_is_healthy_lifecycle(self):
        completed={"init"}
        good={"name":"init","running":False,"status":"exited",
              "exit_code":0,"health":None}
        running={"name":"api","running":True,"status":"running",
                 "exit_code":None,"health":None}
        self.assertTrue(_stage_service_ready("init",good,completed))
        r=assess([good,running],completed_names=completed)
        self.assertEqual(r["lifecycle"],"running")
        self.assertFalse(r["partial_failure"])
        self.assertEqual(r["counts"]["completed_init"],1)
        self.assertEqual(r["counts"]["running"],1)
        self.assertEqual(r["services"][0]["readiness"],"init_completed")
        failed=dict(good,exit_code=2)
        self.assertFalse(_stage_service_ready("init",failed,completed))
        r=assess([failed,running],completed_names=completed)
        self.assertNotEqual(r["lifecycle"],"running")
        self.assertTrue(r["partial_failure"])

    def test_dependency_requires_exit_zero_not_merely_stopped(self):
        manifest={"services":{
            "init":{"depends_on":[]},
            "api":{"depends_on":{"init":{"condition":"service_completed_successfully"}}}
        }}
        good={"running":False,"status":"exited","exit_code":0,"health":None}
        with patch("stage_store_runtime._owned",return_value={"init":good}):
            self.assertIsNone(_wait_for_dependency("test",manifest,"owner","api",1))
        failed=dict(good,exit_code=1)
        with patch("stage_store_runtime._owned",return_value={"init":failed}):
            with self.assertRaises(AppError) as ctx:
                _wait_for_dependency("test",manifest,"owner","api",1)
            self.assertEqual(ctx.exception.message,"compiled_one_shot_dependency_failed")

    def test_mixed_running_and_completed_reference_rejected(self):
        source={"services":{
            "init":{"image":"example/init:1"},
            "api":{"image":"example/api:1",
                   "depends_on":{"init":{"condition":"service_completed_successfully"}}},
            "worker":{"image":"example/worker:1","depends_on":["init"]},
        }}
        with self.assertRaises(AppError) as ctx:
            analyze(source,resolver=lambda _:None)
        self.assertEqual(ctx.exception.message,"conflicting_catalog_one_shot_dependency")


if __name__=="__main__":
    unittest.main(verbosity=2)
