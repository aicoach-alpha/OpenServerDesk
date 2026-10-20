"""Exact Dockpeek staging-only metadata pilot, no host Docker privileges."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError
from stage_store_general import _find_catalog_definition
from stage_store_compiler import analyze,compile_stage
from stage_host_socket import (
    DOCKPEEK_ID,DOCKPEEK_IMAGE,DOCKPEEK_SERVICE,
    PILOT_ID,APPROVED_PILOTS,eligible,socket_mount,approved_app,
)


class DockpeekAdapterContract(unittest.TestCase):
    def test_fixed_catalog_image_stage_broker(self):
        _,doc=_find_catalog_definition(DOCKPEEK_ID)
        self.assertTrue(eligible(DOCKPEEK_ID,doc))
        plan=analyze(doc,resolver=lambda _:"sha256:"+"a"*64,
                     app_id=DOCKPEEK_ID)
        self.assertTrue(plan["services"][0]["host_socket_adapter"])
        self.assertEqual(plan["services"][0]["name"],DOCKPEEK_SERVICE)
        with patch("stage_store_compiler.analyze",return_value=plan):
            manifest=compile_stage("osd-compiled-123456789abc",DOCKPEEK_ID)
        cfg=manifest["services"][DOCKPEEK_SERVICE]
        self.assertEqual(cfg["volumes"],[socket_mount()])
        self.assertTrue(cfg["volumes"][0]["read_only"])
        self.assertNotEqual(cfg["volumes"][0]["source"],"/var/run/docker.sock")
        self.assertEqual(cfg["user"],"1000:1000")
        self.assertEqual(cfg["cap_drop"],["ALL"])
        self.assertEqual(manifest["networks"],{"isolated":{"internal":True}})

    def test_reject_digest_change_and_untrusted_app(self):
        _,doc=_find_catalog_definition(DOCKPEEK_ID)
        for modified in ("image","privileged","devices","network_mode","volumes"):
            variant=copy.deepcopy(doc)
            cfg=variant["services"][DOCKPEEK_SERVICE]
            if modified=="image":
                cfg["image"]=DOCKPEEK_IMAGE.replace("v1.7.2","v1.7.3")
            elif modified=="privileged":
                cfg["privileged"]=True
            elif modified=="devices":
                cfg["devices"]=["/dev/sda"]
            elif modified=="network_mode":
                cfg["network_mode"]="host"
            else:
                cfg["volumes"].append("/etc/shadow:/shadow:ro")
            with self.subTest(field=modified):
                self.assertFalse(eligible(DOCKPEEK_ID,variant))
        self.assertFalse(eligible(PILOT_ID,doc))
        self.assertFalse(approved_app("default:Portainer"))
        self.assertEqual(set(APPROVED_PILOTS),{PILOT_ID,DOCKPEEK_ID})

    def test_approved_socket_images_cannot_switch_to_unaudited_tag(self):
        from stage_store_versions import cached_versions,target_image
        for app in (PILOT_ID,DOCKPEEK_ID):
            with self.subTest(app=app):
                self.assertEqual(cached_versions(app,lambda *a,**kw:""),[])
                with self.assertRaises(AppError) as err:
                    target_image(app,"latest")
                self.assertEqual(err.exception.message,
                                 "broker_pilot_image_version_pinned")

    def test_compiled_facade_scope_rejects_wrong_app(self):
        _,doc=_find_catalog_definition(DOCKPEEK_ID)
        self.assertFalse(eligible("default:Portainer",doc))
        with self.assertRaises(AppError) as error:
            analyze(doc,resolver=lambda _:"sha256:"+"a"*64,
                    app_id="default:Portainer")
        self.assertEqual(error.exception.message,"unsafe_container_volume_target")


if __name__=="__main__":
    unittest.main()
