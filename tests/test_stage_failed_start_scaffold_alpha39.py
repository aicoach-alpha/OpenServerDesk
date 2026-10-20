"""Targeted fault injection: failed-stage rollback leaves only real data."""
from contextlib import ExitStack,nullcontext
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime
import stage_store_compiler
import stage_store_general
from stage_apps import AppError


class FailedStartScaffold(unittest.TestCase):
    APP="default:MySpeed"

    def attempt(self,root,*,retained=False):
        stage=[]
        def prepare(project,raw):
            directory=root/project/"app"/"volume-0"
            directory.mkdir(mode=0o700,parents=True)
            stage.append(directory)
        def fail_start(project):
            if retained:
                (stage[0]/"app-data.txt").write_text("do not delete")
            raise AppError("stage_app_startup_failed",503)
        def compile(project,app,host_port=None):
            return {"name":project,"services":{"app":{
                "image":"sha256:"+"a"*64,"volumes":[],"labels":{}}}}
        with ExitStack() as stack:
            for name,kw in (
                ("guarded",{"return_value":nullcontext()}),
                ("_projects",{"return_value":{}}),
                ("_root",{"return_value":root}),
                ("_folder",{"side_effect":lambda name:root/name}),
                ("STATE",{"new":root/"registry.json"}),
                ("docker",{"return_value":""}),
                ("_service_budget",{"return_value":0}),
                ("_pick_port",{"return_value":18720}),
                ("user_registry",{"return_value":{"owner":"a"*32}}),
                ("compile_stage",{"side_effect":compile}),
                ("_prepare_volumes",{"side_effect":prepare}),
                ("_validate",{}),
                ("_verify_partial",{"return_value":[]}),
                ("_up",{"side_effect":fail_start}),
            ):
                stack.enter_context(patch.object(runtime,name,**kw))
            stack.enter_context(patch.object(stage_store_general,
                "_find_catalog_definition",return_value=({},
                     {"services":{"app":{"image":"mock"}}})))
            stack.enter_context(patch.object(stage_store_compiler,"analyze",
                return_value={"services":[{"name":"app"}]}))
            with self.assertRaises(AppError) as error:
                runtime.operation("install",app_id=self.APP)
            self.assertEqual(error.exception.message,"stage_app_startup_failed")
        return list(root.glob("osd-compiled-*"))

    def test_empty_compensated_install_has_no_orphan_scaffold(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertEqual(self.attempt(root),[])
            self.assertTrue((root/"registry.json").exists())

    def test_app_volume_contents_survive_compensation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            projects=self.attempt(root,retained=True)
            self.assertEqual(len(projects),1)
            file=projects[0]/"app"/"volume-0"/"app-data.txt"
            self.assertEqual(file.read_text(),"do not delete")
            self.assertFalse((projects[0]/"pending.json").exists())


if __name__=="__main__":
    unittest.main()
