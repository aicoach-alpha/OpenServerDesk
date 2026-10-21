"""One focused Glances pilot gate. No production Docker invocation."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_store_general import _find_catalog_definition
from stage_host_socket import (
    GLANCES_ID,GLANCES_SERVICE,GLANCES_IMAGE,GLANCES_ENV,
    eligible,glances_environment,allow_glances_environment,
    socket_mount,
)
import stage_store_compiler as compiler
import stage_store_runtime as runtime
from stage_apps import AppError
from appstore_compatibility_matrix import listing as appstore_listing


class GlancesCuratedStage(unittest.TestCase):
    PROJECT="osd-compiled-112233445566"

    def test_pinned_compiler_stage_web_without_host_pid(self):
        _,doc=_find_catalog_definition(GLANCES_ID)
        self.assertTrue(eligible(GLANCES_ID,doc))
        plan=compiler.analyze(doc,resolver=lambda _: "sha256:"+"a"*64,
                              app_id=GLANCES_ID)
        self.assertEqual(plan["services"][0]["web_target"],61208)
        self.assertTrue(plan["services"][0]["host_socket_adapter"])
        with patch.object(compiler,"analyze",return_value=plan):
            manifest=compiler.compile_stage(self.PROJECT,GLANCES_ID,18725)
        cfg=manifest["services"][GLANCES_SERVICE]
        self.assertEqual(cfg["environment"],GLANCES_ENV)
        self.assertEqual(cfg["environment"]["USER"],"stageglances")
        self.assertEqual(cfg["environment"]["LOGNAME"],"stageglances")
        self.assertEqual(cfg["volumes"],[socket_mount()])
        self.assertEqual(cfg["user"],"1000:1000")
        self.assertEqual(cfg["cap_drop"],["ALL"])
        self.assertNotIn("pid",cfg)
        self.assertNotIn("network_mode",cfg)
        self.assertNotIn("privileged",cfg)
        self.assertNotIn("devices",cfg)
        self.assertEqual(manifest["networks"],{"isolated":{"internal":True}})
        self.assertEqual(cfg["ports"],["127.0.0.1:18725:61208"])
        self.assertTrue(allow_glances_environment(self.PROJECT,manifest["services"]))

    def test_glances_exact_catalog_only(self):
        _,doc=_find_catalog_definition(GLANCES_ID)
        for mutation in (
            lambda cfg:cfg.__setitem__("image",GLANCES_IMAGE.replace("full","other")),
            lambda cfg:cfg.__setitem__("pid","private"),
            lambda cfg:cfg.__setitem__("privileged",True),
            lambda cfg:cfg.__setitem__("devices",["/dev/sda"]),
            lambda cfg:cfg.__setitem__("volumes",[
                "/var/run/docker.sock:/var/run/docker.sock:rw"]),
            lambda cfg:cfg.__setitem__("environment",["GLANCES_OPT=-w","TZ=UTC",
                                                       "UNSAFE=1"]),
        ):
            modified=copy.deepcopy(doc)
            mutation(modified["services"][GLANCES_SERVICE])
            self.assertFalse(eligible(GLANCES_ID,modified))
        self.assertFalse(eligible("default:Portainer",doc))

    def test_runtime_rejects_host_pid_even_with_glances_label(self):
        _,doc=_find_catalog_definition(GLANCES_ID)
        plan=compiler.analyze(doc,resolver=lambda _: "sha256:"+"a"*64,
                              app_id=GLANCES_ID)
        with patch.object(compiler,"analyze",return_value=plan):
            manifest=compiler.compile_stage(self.PROJECT,GLANCES_ID,18725)
        owner="a"*32
        manifest["services"][GLANCES_SERVICE]["labels"][
            "osd.m1.compiled.owner"]=owner
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/self.PROJECT
            project.mkdir(mode=0o700)
            with patch.object(runtime,"_folder",return_value=project):
                runtime._validate(self.PROJECT,manifest,owner)
                manifest["services"][GLANCES_SERVICE]["pid"]="host"
                with self.assertRaises(AppError) as error:
                    runtime._validate(self.PROJECT,manifest,owner)
                self.assertEqual(error.exception.message,
                                 "unsafe_compiled_service_settings")

    def test_just_one_new_curated_catalog_plan(self):
        matrix=appstore_listing()
        selected=next(row for row in matrix["apps"]
                      if row["id"]==GLANCES_ID)
        self.assertTrue(selected["sandbox_plan_supported"])
        self.assertIn("host_pid_namespace_discarded",
                      selected["feature_gaps"])
        self.assertIn("stage_container_metrics_only",
                      selected["feature_gaps"])
        self.assertEqual(matrix["install_mode_counts"],{
            "isolated_stage_sandbox":676,
            "special_host_integration":50,
            "unsupported_compose_metadata":0,
        })

    def test_runtime_manifest_env_allowlist_is_exact(self):
        services={GLANCES_SERVICE:{
            "labels":{"osd.m1.compiled.app":GLANCES_ID},
            "environment":glances_environment()}}
        self.assertTrue(allow_glances_environment(self.PROJECT,services))
        services[GLANCES_SERVICE]["environment"]["GLANCES_OPT"]="-w -B 0.0.0.0"
        self.assertFalse(allow_glances_environment(self.PROJECT,services))


if __name__=="__main__":
    unittest.main()
