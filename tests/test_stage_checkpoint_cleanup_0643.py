"""Stage-only verified deletion without touching app data or active recovery."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_data as data
from stage_apps import AppError
PROJECT="osd-compiled-abcdef123456"
class CheckpointCleanupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.volume=self.root/PROJECT/"myspeed"/"volume-0"
  self.volume.mkdir(parents=True)
  (self.volume/"app.txt").write_text("data stays")
  self.manifest={"services":{"myspeed":{"volumes":[{"source":str(self.volume)}]}}}
  p=patch.object(data,"ROOT",self.root)
  p.start();self.addCleanup(p.stop)
 def test_specific_snapshot_removed_not_live_volume(self):
  a=data._save(PROJECT,self.manifest);b=data._save(PROJECT,self.manifest)
  response=data.delete_checkpoint(PROJECT,self.manifest,a)
  self.assertEqual(response["remaining"],1)
  self.assertEqual(data.listing(PROJECT,self.manifest),[b])
  self.assertEqual((self.volume/"app.txt").read_text(),"data stays")
 def test_active_recovery_prevents_checkpoint_deletion(self):
  a=data._save(PROJECT,self.manifest)
  (self.root/PROJECT/"online-data-pending.json").write_text("{}")
  with self.assertRaises(AppError) as e:
   data.delete_checkpoint(PROJECT,self.manifest,a)
  self.assertEqual(e.exception.message,"stage_checkpoint_in_use_by_recovery")
  self.assertIn(a,data.listing(PROJECT,self.manifest))
if __name__=="__main__":unittest.main()
