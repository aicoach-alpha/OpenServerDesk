"""Focused one-click staging backup/restore and crash-recovery journal tests."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime
from stage_apps import AppError

PROJECT="osd-compiled-abcdef123456"
ENTRY={"owner":"a"*32,"app_id":"default:MySpeed","revision":1}
MANIFEST={"services":{"myspeed":{"volumes":[]}}}
RUNNING={"myspeed":{"name":"myspeed","running":True,"id":"a"*64}}
STOPPED={"myspeed":{"name":"myspeed","running":False,"id":"a"*64}}

class OnlineDataTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.file=Path(self.tmp.name)/"online-data-pending.json"
  self.patch=patch.object(runtime,"_online_file",return_value=self.file)
  self.patch.start();self.addCleanup(self.patch.stop)
 def context(self):
  return patch.multiple(runtime,
     _stop_for_online=lambda services:None,
     _owned=lambda *args,**kwargs:STOPPED,
     _resume_online=lambda *args,**kwargs:None,
     _summary=lambda *args,**kwargs:{"project":PROJECT})
 def test_one_click_backup_stops_then_checkpoints_and_resumes(self):
  with self.context(),patch.object(runtime,"data_checkpoint",return_value={
      "checkpoint":"data-abcdef123456","sqlite_files_verified":1}):
   result=runtime._online_data(PROJECT,MANIFEST,ENTRY,RUNNING,"backup-online",None)
  self.assertEqual(result["operation"],"backed_up_online")
  self.assertEqual(result["sqlite_files_verified"],1)
  self.assertFalse(self.file.exists())
 def test_restore_persists_undo_before_mutating_data(self):
  def mutate(*args):
   journal=json.loads(self.file.read_text())
   self.assertEqual(journal["undo"],"data-abcdef123456")
   return 1
  with self.context(),patch.object(runtime,"_data_validate"),patch.object(
      runtime,"_data_save",return_value="data-abcdef123456"),patch.object(
      runtime,"_data_apply",side_effect=mutate):
   result=runtime._online_data(PROJECT,MANIFEST,ENTRY,RUNNING,"restore-online",
                               "data-111111111111")
  self.assertEqual(result["operation"],"restored_online")
  self.assertEqual(result["undo"],"data-abcdef123456")
  self.assertFalse(self.file.exists())
 def test_restore_exception_keeps_journal_for_recovery(self):
  with self.context(),patch.object(runtime,"_data_validate"),patch.object(
      runtime,"_data_save",return_value="data-abcdef123456"),patch.object(
      runtime,"_data_apply",side_effect=RuntimeError("simulated interruption")):
   with self.assertRaises(AppError) as raised:
    runtime._online_data(PROJECT,MANIFEST,ENTRY,RUNNING,"restore-online",
                         "data-111111111111")
  self.assertEqual(raised.exception.message,"stage_online_data_requires_recovery")
  self.assertEqual(json.loads(self.file.read_text())["undo"],"data-abcdef123456")
  with self.context(),patch.object(runtime,"_data_apply",return_value=1) as applied:
   recovered=runtime._online_recover(PROJECT,MANIFEST,ENTRY)
  self.assertEqual(recovered["operation"],"recovered_online_data")
  self.assertTrue(recovered["restored_old_data"])
  applied.assert_called_once_with(PROJECT,MANIFEST,"data-abcdef123456")
  self.assertFalse(self.file.exists())

if __name__=="__main__":unittest.main()
