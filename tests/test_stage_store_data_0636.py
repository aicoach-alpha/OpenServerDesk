"""Stage-only volume snapshot/recovery acceptance with isolated temporary paths."""
from __future__ import annotations
import tempfile, sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_data as data
from stage_apps import AppError

class StageVolumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="osd-stagedata-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.project="osd-compiled-abcdef123456"
        self.folder=self.root/self.project
        self.volume=self.folder/"db"/"volume-0"
        self.volume.mkdir(parents=True,mode=0o700)
        self.text=self.volume/"data.txt"
        self.text.write_text("old-stage-record")
        self.manifest={"name":self.project,"services":{
            "db":{"volumes":[{"source":str(self.volume),"target":"/data"}]}}}
        self.stopped={"db":{"running":False}}
        self.running={"db":{"running":True}}
        self.patch=patch.object(data,"ROOT",self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_checkpoint_restore_undo_and_recover(self):
        cp=data.checkpoint(self.project,self.manifest,self.stopped)["checkpoint"]
        self.text.write_text("new-stage-record")
        restored=data.restore(self.project,self.manifest,self.stopped,cp)
        self.assertEqual(self.text.read_text(),"old-stage-record")
        self.assertFalse(restored["database_integrity_verified"])
        self.assertEqual(len(data.listing(self.project,self.manifest)),2)
        self.text.write_text("partial-update")
        pending=self.folder/"data-restore-pending.json"
        data._write(pending,{"version":1,"operation":"restore",
                             "undo":restored["undo"],"target":cp})
        data.recover(self.project,self.manifest,self.stopped)
        self.assertEqual(self.text.read_text(),"new-stage-record")
        self.assertFalse(pending.exists())

    def test_snapshot_refuses_live_services(self):
        with self.assertRaises(AppError):
            data.checkpoint(self.project,self.manifest,self.running)
        self.assertFalse((self.folder/"data-checkpoints").exists())

    def test_malicious_symlink_rejected_before_copy(self):
        (self.volume/"escape").symlink_to(self.root)
        with self.assertRaises(AppError):
            data.checkpoint(self.project,self.manifest,self.stopped)

    def test_generated_bind_root_is_writable_by_container_uid(self):
        import stage_store_runtime as runtime
        volume=self.folder/"db"/"volume-1"
        raw={"services":{"db":{"volumes":[{"source":str(volume),
                                            "target":"/var/lib/data"}]}}}
        with patch.object(runtime,"ROOT",self.root):
            with patch.object(runtime,"_root",return_value=self.root):
                runtime._prepare_volumes(self.project,raw)
        self.assertEqual(volume.stat().st_uid,1000)
        self.assertEqual(volume.stat().st_gid,1000)
        self.assertEqual(volume.stat().st_mode & 0o777,0o700)

    def test_only_project_stage_volume_is_accepted(self):
        self.manifest["services"]["db"]["volumes"][0]["source"]="/mnt/data"
        with self.assertRaises(AppError):
            data.checkpoint(self.project,self.manifest,self.stopped)

if __name__=="__main__":unittest.main()
