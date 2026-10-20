"""Focused fault injection for pre-Docker stage installation preparation.

Only tempfile directories and mocked Docker are mutated, never host containers
or existing production/staging projects.
"""
from contextlib import nullcontext
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_apps import AppError
import stage_store_runtime as runtime
import stage_store_compiler
import stage_store_general


class PrepareAutoCleanup(unittest.TestCase):
    APP="default:MySpeed"

    def fake_stage(self,root,*,app_id=None,compile_error=None,prepare=None,docker=None):
        app_id=app_id or self.APP
        manifest=lambda project,app,host_port=None:{
            "name":project,"services":{"app":{"image":"sha256:"+"a"*64,
                                             "labels":{},"volumes":[]}}}
        def fake_docker(*args,**kwargs):
            return "" if docker is None else docker(*args,**kwargs)
        return (
            patch.object(runtime,"guarded",return_value=nullcontext()),
            patch.object(runtime,"_root",return_value=root),
            patch.object(runtime,"_folder",side_effect=lambda name:root/name),
            patch.object(runtime,"STATE",root/"registry.json"),
            patch.object(runtime,"_projects",return_value={}),
            patch.object(runtime,"docker",side_effect=fake_docker),
            patch.object(runtime,"_service_budget",return_value=0),
            patch.object(runtime,"_pick_port",return_value=18720),
            patch.object(runtime,"user_registry",return_value={"owner":"a"*32}),
            patch.object(stage_store_general,"_find_catalog_definition",
                         return_value=({},{"services":{"app":{"image":"safe"}}})),
            patch.object(stage_store_compiler,"analyze",
                         return_value={"services":[{"name":"app"}]}),
            patch.object(runtime,"compile_stage",
                         side_effect=compile_error if compile_error else manifest),
            patch.object(runtime,"_prepare_volumes",side_effect=prepare),
            patch.object(runtime,"_validate"),
        )

    def perform(self,mocks,app_id=None):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for item in mocks:
                stack.enter_context(item)
            return runtime.operation("install",app_id=app_id or self.APP)

    def test_compile_failure_erases_new_empty_scaffold_and_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            calls=[]
            def docker(*args,**kw):
                calls.append(args)
                return ""
            def secret(project):
                path=root/project/"dockpeek-staging-secret.json"
                path.write_text("{}")
                path.chmod(0o600)
            mocks=self.fake_stage(root,app_id=runtime.DOCKPEEK_ID,
                compile_error=AppError("catalog_image_not_cached",409),
                docker=docker)
            with patch.object(runtime,"dockpeek_secret_create",side_effect=secret):
                with self.assertRaises(AppError) as error:
                    self.perform(mocks,runtime.DOCKPEEK_ID)
            self.assertEqual(error.exception.message,"catalog_image_not_cached")
            self.assertFalse(list(root.glob("osd-compiled-*")))
            self.assertFalse((root/"registry.json").exists())
            self.assertTrue(calls)
            self.assertTrue(all(call[0] in ("ps","network") for call in calls))

    def test_partial_empty_stage_volume_is_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def partial(project,raw):
                path=root/project/"app"/"volume-0"
                path.mkdir(mode=0o700,parents=True)
                raise AppError("stage_volume_preparation_failed",503)
            with self.assertRaises(AppError) as error:
                self.perform(self.fake_stage(root,prepare=partial))
            self.assertEqual(error.exception.message,
                             "stage_volume_preparation_failed")
            self.assertFalse(list(root.glob("osd-compiled-*")))

    def test_unknown_volume_content_is_preserved_and_cleanup_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def partial(project,raw):
                path=root/project/"app"/"volume-0"
                path.mkdir(mode=0o700,parents=True)
                (path/"user-data.txt").write_text("keep")
                raise AppError("stage_volume_preparation_failed",503)
            with self.assertRaises(AppError) as error:
                self.perform(self.fake_stage(root,prepare=partial))
            self.assertEqual(error.exception.message,
                             "compiled_stage_prepare_cleanup_required")
            folders=list(root.glob("osd-compiled-*"))
            self.assertEqual(len(folders),1)
            self.assertEqual((folders[0]/"app"/"volume-0"/"user-data.txt").read_text(),
                             "keep")

    def test_unexpected_container_namespace_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ps=[0]
            def docker(*args,**kw):
                if args[0]=="ps":
                    ps[0]+=1
                    return "c"*64 if ps[0]>1 else ""
                return ""
            with self.assertRaises(AppError) as error:
                self.perform(self.fake_stage(root,
                    compile_error=AppError("image_unavailable",409),docker=docker))
            self.assertEqual(error.exception.message,
                             "compiled_stage_prepare_cleanup_required")
            self.assertEqual(ps[0],2)
            self.assertEqual(len(list(root.glob("osd-compiled-*"))),1)


if __name__=="__main__":
    unittest.main()
