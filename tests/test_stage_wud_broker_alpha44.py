"""One focused gate for curated WUD stage-only lifecycle planning."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_store_general import _find_catalog_definition
from stage_host_socket import WUD_ID,WUD_SERVICE,WUD_IMAGE,eligible,socket_mount
from stage_store_compiler import analyze,compile_stage
from appstore_compatibility_matrix import listing


class StageWud(unittest.TestCase):
    PROJECT="osd-compiled-112233445566"

    def test_wud_only_stage_compiled_web_and_socket(self):
        _,doc=_find_catalog_definition(WUD_ID)
        self.assertTrue(eligible(WUD_ID,doc))
        plan=analyze(doc,resolver=lambda _: "sha256:"+"a"*64,app_id=WUD_ID)
        self.assertTrue(plan["services"][0]["host_socket_adapter"])
        self.assertEqual(plan["services"][0]["web_target"],3000)
        with patch("stage_store_compiler.analyze",return_value=plan):
            manifest=compile_stage(self.PROJECT,WUD_ID,18725)
        cfg=manifest["services"][WUD_SERVICE]
        self.assertEqual(cfg["volumes"],[socket_mount()])
        self.assertEqual(cfg["user"],"1000:1000")
        self.assertEqual(cfg["cap_drop"],["ALL"])
        self.assertEqual(cfg["security_opt"],["no-new-privileges:true"])
        self.assertEqual(manifest["networks"],{"isolated":{"internal":True}})
        self.assertNotIn("environment",cfg)
        self.assertNotIn("pid",cfg)
        self.assertNotIn("privileged",cfg)
        self.assertEqual(cfg["ports"],["127.0.0.1:18725:3000"])
        self.assertEqual(cfg["restart"],"no")

    def test_other_privileges_and_mutated_digest_not_approved(self):
        _,doc=_find_catalog_definition(WUD_ID)
        for modifier in (
            lambda cfg:cfg.__setitem__("image",WUD_IMAGE.replace("6.6.1","latest")),
            lambda cfg:cfg.__setitem__("pid","host"),
            lambda cfg:cfg.__setitem__("privileged",True),
            lambda cfg:cfg.__setitem__("devices",["/dev/sda"]),
            lambda cfg:cfg.__setitem__("environment",{"WUD_WATCHER_LOCAL":"true"}),
            lambda cfg:cfg.__setitem__("volumes",[
                "/var/run/docker.sock:/var/run/docker.sock:rw"]),
            lambda cfg:cfg.__setitem__("ports",["9999:9999"]),
        ):
            change=copy.deepcopy(doc)
            modifier(change["services"][WUD_SERVICE])
            self.assertFalse(eligible(WUD_ID,change))

    def test_coverage_does_not_claim_full_runtime_parity(self):
        matrix=listing()
        row=next(x for x in matrix["apps"] if x["id"]==WUD_ID)
        self.assertTrue(row["sandbox_plan_supported"])
        self.assertIn("external_registry_update_checks_unavailable",
                      row["feature_gaps"])
        self.assertIn("no_production_container_inventory",
                      row["feature_gaps"])
        self.assertEqual(matrix["install_mode_counts"],{
            "isolated_stage_sandbox":676,
            "special_host_integration":50,
            "unsupported_compose_metadata":0,
        })


if __name__=="__main__":
    unittest.main()
