"""One small read-only inspection gate with deliberate temp fixtures."""
import os
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack,nullcontext
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_apps import AppError
import stage_store_runtime as runtime


class EmptyPreparationInspection(unittest.TestCase):
    PROJECT="osd-compiled-aabbccddee12"

    def inspect(self,root,*,registered=None,docker=None):
        def query(*args,**kwargs):
            return "" if docker is None else docker(*args,**kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                runtime,"guarded",return_value=nullcontext()))
            stack.enter_context(patch.object(runtime,"_projects",
                return_value={} if registered is None else registered))
            stack.enter_context(patch.object(runtime,"_root",return_value=root))
            stack.enter_context(patch.object(runtime,"_folder",
                side_effect=lambda project:root/project))
            stack.enter_context(patch.object(runtime,"docker",side_effect=query))
            return runtime.inspect_empty_preparation(self.PROJECT)

    def test_verified_empty_preview_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/self.PROJECT
            folder.mkdir(mode=0o700)
            volume=folder/"app"/"volume-0"
            volume.mkdir(mode=0o700,parents=True)
            manifest=folder/"compose.json"
            manifest.write_text("{}")
            manifest.chmod(0o600)
            os.utime(folder,(time.time()-750,time.time()-750))
            result=self.inspect(root)
            self.assertTrue(result["eligible"])
            self.assertEqual(result["reason"],"verified_empty_scaffold")
            self.assertEqual(result["empty_volumes"],1)
            self.assertEqual(result["generated_files"],1)
            self.assertIs(result["production_mutation_allowed"],False)
            self.assertIs(result["user_data_deleted"],False)
            self.assertTrue(volume.is_dir())
            self.assertEqual(manifest.read_text(),"{}")

    def test_data_or_docker_resource_refuses_inspection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/self.PROJECT
            folder.mkdir(mode=0o700)
            data=folder/"app"/"volume-0"/"stored.txt"
            data.parent.mkdir(mode=0o700,parents=True)
            data.write_text("keep")
            os.utime(folder,(time.time()-750,time.time()-750))
            outcome=self.inspect(root)
            self.assertFalse(outcome["eligible"])
            self.assertEqual(outcome["reason"],"stage_prepare_volume_contains_data")
            self.assertEqual(data.read_text(),"keep")
            outcome=self.inspect(root,docker=lambda *args,**kw:
                                 "b"*64 if args[0]=="ps" else "")
            self.assertFalse(outcome["eligible"])
            self.assertEqual(outcome["reason"],"stage_prepare_docker_resource_present")
            self.assertTrue(folder.is_dir())

    def test_registered_or_recent_staging_never_eligible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/self.PROJECT
            folder.mkdir(mode=0o700)
            self.assertEqual(self.inspect(root)["reason"],
                             "stage_empty_cleanup_wait_for_idle")
            os.utime(folder,(time.time()-750,time.time()-750))
            result=self.inspect(root,registered={self.PROJECT:{
                "app_id":"default:MySpeed","owner":"a"*32,"revision":1}})
            self.assertFalse(result["eligible"])
            self.assertEqual(result["reason"],"stage_empty_cleanup_registered_project")
            self.assertTrue(folder.is_dir())


if __name__=="__main__":
    unittest.main()
