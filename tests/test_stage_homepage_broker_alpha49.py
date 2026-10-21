"""Focused Homepage adapter: one fresh config volume and fake Docker API."""
import copy
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_apps import AppError
from stage_store_general import _find_catalog_definition
from stage_host_socket import (
    HOMEPAGE_ID,HOMEPAGE_SERVICE,HOMEPAGE_IMAGE,HOMEPAGE_ENV,
    HOMEPAGE_CONFIG_SOURCE,eligible,socket_mount,allow_homepage_environment,
)
import stage_store_compiler as compiler
import stage_store_runtime as runtime
from stage_app_gateway import rewrite,parse_route
from appstore_compatibility_matrix import listing


class CuratedHomepage(unittest.TestCase):
    PROJECT="osd-compiled-112233445566"

    def plan(self):
        _,doc=_find_catalog_definition(HOMEPAGE_ID)
        plan=compiler.analyze(doc,resolver=lambda _: "sha256:"+"a"*64,
                              app_id=HOMEPAGE_ID)
        with patch.object(compiler,"analyze",return_value=plan):
            manifest=compiler.compile_stage(self.PROJECT,HOMEPAGE_ID,18726)
        return doc,plan,manifest

    def test_new_config_volume_is_owned_by_stage_not_casaos(self):
        source,plan,manifest=self.plan()
        self.assertTrue(eligible(HOMEPAGE_ID,source))
        self.assertEqual(plan["services"][0]["mount_targets"],["/app/config"])
        self.assertTrue(plan["services"][0]["host_socket_adapter"])
        self.assertEqual(plan["services"][0]["web_target"],3000)
        cfg=manifest["services"][HOMEPAGE_SERVICE]
        self.assertEqual(cfg["environment"],HOMEPAGE_ENV)
        self.assertEqual(cfg["user"],"1000:1000")
        self.assertEqual(cfg["cap_drop"],["ALL"])
        self.assertEqual(cfg["security_opt"],["no-new-privileges:true"])
        self.assertEqual(cfg["restart"],"no")
        self.assertEqual(cfg["ports"],["127.0.0.1:18726:3000"])
        self.assertEqual(manifest["networks"],{"isolated":{"internal":True}})
        self.assertEqual(len(cfg["volumes"]),2)
        config,socket=cfg["volumes"]
        self.assertEqual(config["target"],"/app/config")
        self.assertEqual(config["type"],"bind")
        self.assertEqual(config["bind"],{"create_host_path":False})
        self.assertIn("/"+self.PROJECT+"/app/volume-0",config["source"])
        self.assertNotIn("/DATA/",config["source"])
        self.assertEqual(socket,socket_mount())
        self.assertNotIn("privileged",cfg)
        self.assertNotIn("network_mode",cfg)
        self.assertTrue(allow_homepage_environment(self.PROJECT,manifest["services"]))

    def test_changed_catalog_or_extra_mount_denied(self):
        doc,_,_=self.plan()
        for mutation in (
            lambda s:s.__setitem__("image",HOMEPAGE_IMAGE.replace("v2.4.0","latest")),
            lambda s:s.__setitem__("environment",{"PASSWORD":"test"}),
            lambda s:s.__setitem__("ports",["9000:9000"]),
            lambda s:s.__setitem__("pid","host"),
            lambda s:s.__setitem__("privileged",True),
            lambda s:s.__setitem__("devices",["/dev/sda"]),
            lambda s:s.__setitem__("volumes",[
                HOMEPAGE_CONFIG_SOURCE,"/var/run/docker.sock:/var/run/docker.sock:rw"]),
            lambda s:s.__setitem__("volumes",[
                HOMEPAGE_CONFIG_SOURCE,"/var/run/docker.sock:/var/run/docker.sock",
                "/mnt:/host"]),
        ):
            change=copy.deepcopy(doc)
            mutation(change["services"][HOMEPAGE_SERVICE])
            with self.subTest(modifier=mutation):
                self.assertFalse(eligible(HOMEPAGE_ID,change))

    def test_runtime_rejects_wildcard_and_extra_environment(self):
        _,_,manifest=self.plan()
        owner="a"*32
        cfg=manifest["services"][HOMEPAGE_SERVICE]
        cfg["labels"]["osd.m1.compiled.owner"]=owner
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/self.PROJECT
            folder.mkdir(mode=0o700)
            volume=folder/"app"/"volume-0"
            volume.mkdir(mode=0o700,parents=True)
            cfg["volumes"][0]["source"]=str(volume)
            with patch.object(runtime,"_folder",return_value=folder):
                runtime._validate(self.PROJECT,manifest,owner)
                cfg["environment"]={"HOMEPAGE_ALLOWED_HOSTS":"*"}
                with self.assertRaises(AppError):
                    runtime._validate(self.PROJECT,manifest,owner)

    def test_gateway_nextjs_assets_scoped_to_authenticated_stage_project(self):
        payload=(b'<link href="/_next/static/css/app.css">'
                 b'<script src="/_next/static/chunks/app.js"></script>'
                 b'<script>fetch("/api/services")</script>')
        rewritten=rewrite(payload,"text/html",self.PROJECT).decode()
        for part in ("_next/static/css/app.css",
                     "_next/static/chunks/app.js","api/services"):
            exact="/stage-app/"+self.PROJECT+"/"+part
            self.assertIn(exact,rewritten)
            self.assertEqual(parse_route(exact),(self.PROJECT,"/"+part))
        self.assertEqual(rewrite(b'{"url":"/_next/test"}',
                                 "application/json",self.PROJECT),
                         b'{"url":"/_next/test"}')
        css=rewrite(b"url(/_next/static/media/font.woff2)",
                    "text/css",self.PROJECT)
        self.assertIn(b"/stage-app/"+self.PROJECT.encode()+
                      b"/_next/static/media/font.woff2",css)

    def test_matrix_declares_only_stage_pilot_not_functional_parity(self):
        values=listing()
        row=next(item for item in values["apps"] if item["id"]==HOMEPAGE_ID)
        self.assertTrue(row["sandbox_plan_supported"])
        for gap in ("original_dashboard_config_not_imported",
                    "original_host_docker_inventory_unavailable",
                    "empty_stage_owned_config_only"):
            self.assertIn(gap,row["feature_gaps"])
        self.assertFalse(values["runtime_compatibility_proven"])
        self.assertEqual(values["install_mode_counts"],{
            "isolated_stage_sandbox":677,
            "special_host_integration":49,
            "unsupported_compose_metadata":0,
        })


if __name__=="__main__":
    unittest.main()
