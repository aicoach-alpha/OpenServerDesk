"""One small gate: authenticated operator action deletes no retained data."""
from contextlib import ExitStack,nullcontext
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_apps import AppError
import stage_store_runtime as runtime


class OperatorEmptyScaffold(unittest.TestCase):
    PROJECT="osd-compiled-123456789abc"

    def invoke(self,root,*,registered=None,docker=None):
        active={} if registered is None else registered
        def safe_docker(*args,**kwargs):
            return "" if docker is None else docker(*args,**kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                runtime,"guarded",return_value=nullcontext()))
            stack.enter_context(patch.object(runtime,"_projects",return_value=active))
            stack.enter_context(patch.object(runtime,"_root",return_value=root))
            stack.enter_context(patch.object(runtime,"_folder",
                                            side_effect=lambda ident:root/ident))
            stack.enter_context(patch.object(runtime,"docker",side_effect=safe_docker))
            return runtime.operation("clean-preparation",project=self.PROJECT)

    def test_old_verified_empty_scaffold_removed_without_docker_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/self.PROJECT
            folder.mkdir(mode=0o700)
            service=folder/"app"
            volume=service/"volume-0"
            volume.mkdir(mode=0o700,parents=True)
            compose=folder/"compose.json"
            compose.write_text("{}")
            compose.chmod(0o600)
            os.utime(folder,(time.time()-800,time.time()-800))
            operations=[]
            def docker(*args,**kwargs):
                operations.append(args)
                return ""
            result=self.invoke(root,docker=docker)
            self.assertEqual(result["operation"],"cleaned_empty_scaffold")
            self.assertFalse(result["user_data_deleted"])
            self.assertFalse(result["production_mutation_allowed"])
            self.assertFalse(folder.exists())
            self.assertTrue(operations)
            self.assertTrue(all(op[0] in ("ps","network") for op in operations))

    def test_retained_volume_contents_are_never_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/self.PROJECT
            folder.mkdir(mode=0o700)
            volume=folder/"app"/"volume-0"
            volume.mkdir(mode=0o700,parents=True)
            file=volume/"retain.data"
            file.write_text("keep this stage data")
            os.utime(folder,(time.time()-800,time.time()-800))
            with self.assertRaises(AppError) as err:
                self.invoke(root)
            self.assertEqual(err.exception.message,
                             "stage_prepare_volume_contains_data")
            self.assertEqual(file.read_text(),"keep this stage data")

    def test_recent_or_registered_project_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/self.PROJECT
            folder.mkdir(mode=0o700)
            with self.assertRaises(AppError) as err:
                self.invoke(root)
            self.assertEqual(err.exception.message,
                             "stage_empty_cleanup_wait_for_idle")
            os.utime(folder,(time.time()-800,time.time()-800))
            with self.assertRaises(AppError) as err:
                self.invoke(root,registered={self.PROJECT:{"owner":"a"*32}})
            self.assertEqual(err.exception.message,
                             "invalid_stage_empty_cleanup_request")
            self.assertTrue(folder.exists())


if __name__=="__main__":
    unittest.main()
