"""Targeted fault-injection proof: failed installs self-clean without host writes."""
from contextlib import nullcontext
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_apps import AppError
import stage_store_runtime as runtime


class StageInstallSelfCleanup(unittest.TestCase):
    ID="b"*64
    OWNER="a"*32

    def test_failed_install_compensates_exact_stage_container_and_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            calls=[]
            ps_queries=[0]
            def docker(*args,**kwargs):
                calls.append(args)
                if args[:2]==("ps","--all"):
                    # Namespace collision query is initially empty; after the
                    # simulated startup failure one exact ID needs cleanup.
                    ps_queries[0]+=1
                    return self.ID if ps_queries[0]>1 else ""
                return ""
            def make_manifest(project,app_id,host_port=None):
                return {"name":project,"services":{"app":{
                    "image":"sha256:"+"f"*64,"labels":{},
                    "volumes":[]}}}
            with (
                patch.object(runtime,"guarded",return_value=nullcontext()),
                patch.object(runtime,"_projects",return_value={}),
                patch.object(runtime,"_folder",
                             side_effect=lambda project:root/project),
                patch.object(runtime,"STATE",root/"registry.json"),
                patch.object(runtime,"docker",side_effect=docker),
                patch.object(runtime,"_service_budget",return_value=0),
                patch.object(runtime,"_pick_port",return_value=18720),
                patch.object(runtime,"compile_stage",side_effect=make_manifest),
                patch.object(runtime,"_prepare_volumes"),
                patch.object(runtime,"user_registry",
                             return_value={"owner":self.OWNER}),
                patch.object(runtime,"_validate"),
                patch.object(runtime,"_verify_partial",return_value=[self.ID]),
                patch.object(runtime,"_up",
                             side_effect=AppError("stage_startup_failed",503)),
            ):
                with self.assertRaises(AppError) as err:
                    runtime.operation("install",app_id="default:MySpeed")
                self.assertEqual(err.exception.message,"stage_startup_failed")
            removed=[call for call in calls if call[:2]==("rm","--force")]
            self.assertEqual(removed,[("rm","--force",self.ID)])
            folders=list(root.glob("osd-compiled-*"))
            self.assertEqual(len(folders),1)
            self.assertFalse((folders[0]/"pending.json").exists())
            self.assertEqual(json.loads((root/"registry.json").read_text()),{})

    def test_foreign_network_attachment_rejected_before_container_removal(self):
        project="osd-compiled-123456789abc"
        manifest={
            "name":project,"services":{"app":{"volumes":[]}},
            "networks":{"isolated":{"internal":True}},
        }
        info={"Name":project+"_isolated","Internal":True,
              "Labels":{"com.docker.compose.project":project,
                        "com.docker.compose.network":"isolated"},
              "Containers":{self.ID:{}, "c"*64:{}}}
        commands=[]
        def docker(*args,**kwargs):
            commands.append(args)
            if args[:2]==("network","ls"):
                return "d"*64
            if args[:2]==("network","inspect"):
                return json.dumps([info])
            raise AssertionError("No mutation allowed before network provenance")
        values={project:{"app_id":"default:MySpeed",
                         "owner":self.OWNER,"revision":1}}
        with (patch.object(runtime,"_validate"),
              patch.object(runtime,"_verify_partial",return_value=[self.ID]),
              patch.object(runtime,"docker",side_effect=docker)):
            with self.assertRaises(AppError) as error:
                runtime._recover_failed_install(project,manifest,self.OWNER,values)
        self.assertEqual(error.exception.message,
                         "compiled_stage_network_cleanup_unverified")
        self.assertFalse(any(call[0] in ("rm","stop") for call in commands))
        self.assertIn(project,values)

    def test_qui_delayed_install_keeps_recovery_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def manifest(project,app_id,host_port=None):
                return {"name":project,"services":{"app":{
                    "image":"sha256:"+"a"*64,
                    "labels":{},"volumes":[]}}}
            with (
                patch.object(runtime,"guarded",return_value=nullcontext()),
                patch.object(runtime,"_projects",return_value={}),
                patch.object(runtime,"_folder",
                             side_effect=lambda project:root/project),
                patch.object(runtime,"STATE",root/"registry.json"),
                patch.object(runtime,"docker",return_value=""),
                patch.object(runtime,"_service_budget",return_value=0),
                patch.object(runtime,"_pick_port",return_value=18720),
                patch.object(runtime,"compile_stage",side_effect=manifest),
                patch.object(runtime,"_prepare_volumes"),
                patch.object(runtime,"qui_secret_create"),
                patch.object(runtime,"user_registry",
                             return_value={"owner":self.OWNER}),
                patch.object(runtime,"_validate"),
                patch.object(runtime,"_up",
                             side_effect=AppError("readiness_pending",503)),
                patch.object(runtime,"_recover_failed_install",
                             side_effect=AssertionError("Qui must not auto-clean")),
            ):
                with self.assertRaises(AppError) as error:
                    runtime.operation("install",app_id=runtime.QUI_APP)
                self.assertEqual(error.exception.message,"readiness_pending")
            folders=list(root.glob("osd-compiled-*"))
            self.assertEqual(len(folders),1)
            self.assertTrue((folders[0]/"pending.json").exists())

    def test_foreign_or_unverifiable_container_blocks_auto_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            values={"osd-compiled-123456789abc":{
                "app_id":"default:MySpeed","owner":self.OWNER,
                "revision":1}}
            with (patch.object(runtime,"_validate"),
                  patch.object(runtime,"_verify_partial",
                               side_effect=AppError("foreign_container",403)),
                  patch.object(runtime,"docker") as docker):
                with self.assertRaises(AppError) as err:
                    runtime._recover_failed_install(
                        "osd-compiled-123456789abc",
                        {"services":{"app":{"volumes":[]}}},self.OWNER,
                        values)
                self.assertEqual(err.exception.message,"foreign_container")
                docker.assert_not_called()
                self.assertEqual(len(values),1)


if __name__=="__main__":
    unittest.main()
