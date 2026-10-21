"""One scoped lifecycle gate: uninstall precedes optional empty cleanup."""
import sys
import tempfile
import unittest
from contextlib import ExitStack,nullcontext
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime


class StagePostUninstall(unittest.TestCase):
    PROJECT="osd-compiled-123456789abc"
    OWNER="a"*32

    def perform(self,root,app_id="default:MySpeed",retained=False,foreign=False):
        folder=root/self.PROJECT
        folder.mkdir(mode=0o700)
        config=folder/"compose.json"
        config.write_text("{}")
        config.chmod(0o600)
        volume=folder/"app"/"volume-0"
        volume.mkdir(mode=0o700,parents=True)
        if retained:
            (volume/"database.txt").write_text("preserve stage data")
        manifest={"name":self.PROJECT,"services":{"app":{"labels":{},
                          "volumes":[]}}}
        registry={self.PROJECT:{"owner":self.OWNER,"app_id":app_id,"revision":1}}
        events=[]
        def read_docker(*args,**kw):
            events.append(args)
            if foreign and args[0]=="ps":
                return "b"*64
            return ""
        with ExitStack() as stack:
            patches=[
                patch.object(runtime,"guarded",return_value=nullcontext()),
                patch.object(runtime,"_projects",return_value=registry),
                patch.object(runtime,"_root",return_value=root),
                patch.object(runtime,"_folder",
                             side_effect=lambda name:root/name),
                patch.object(runtime,"STATE",root/"registry.json"),
                patch.object(runtime,"_current",
                             return_value=(manifest,{"app":{"running":True}})),
                patch.object(runtime,"_down_owned",
                             side_effect=lambda *args:events.append(("down",))),
                patch.object(runtime,"docker",side_effect=read_docker),
            ]
            for item in patches:
                stack.enter_context(item)
            result=runtime.operation("uninstall",project=self.PROJECT)
        self.assertFalse(registry)
        self.assertFalse((folder/"pending.json").exists())
        return result,folder,events

    def test_uninstall_reclaims_only_generated_empty_scaffold(self):
        with tempfile.TemporaryDirectory() as temp:
            result,folder,events=self.perform(Path(temp))
            self.assertEqual(result["operation"],"uninstalled")
            self.assertTrue(result["empty_scaffold_reclaimed"])
            self.assertTrue(result["stage_data_retained"])
            self.assertFalse(folder.exists())
            self.assertIn(("down",),events)

    def test_uninstall_retains_nonempty_data_with_success(self):
        with tempfile.TemporaryDirectory() as temp:
            result,folder,_=self.perform(Path(temp),retained=True)
            self.assertFalse(result["empty_scaffold_reclaimed"])
            self.assertEqual((folder/"app"/"volume-0"/"database.txt").read_text(),
                             "preserve stage data")

    def test_uninstall_does_not_remove_unknown_docker_or_qui(self):
        with tempfile.TemporaryDirectory() as temp:
            result,folder,_=self.perform(Path(temp),foreign=True)
            self.assertFalse(result["empty_scaffold_reclaimed"])
            self.assertTrue(folder.is_dir())
        with tempfile.TemporaryDirectory() as temp:
            result,folder,_=self.perform(Path(temp),app_id=runtime.QUI_APP)
            self.assertFalse(result["empty_scaffold_reclaimed"])
            self.assertTrue(folder.is_dir())


if __name__=="__main__":
    unittest.main()
