"""Scoped version transition and database rollback tests; no Docker invoked."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as run
import stage_store_data as data
from stage_apps import AppError

PROJECT="osd-compiled-abcdef123456"
OLD={"name":PROJECT,"services":{"app":{"image":"sha256:"+"a"*64}}}
NEW={"name":PROJECT,"services":{"app":{"image":"sha256:"+"b"*64}}}
def services():return {"app":{"id":"a"*64,"name":"app","running":True}}
def stopped():return {"app":{"id":"a"*64,"name":"app","running":False}}
class VersionDataTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.previous=self.root/"previous.json"
  self.journal=self.root/"pending.json"
  self.entry={"app_id":"example:test","owner":"a"*32,"revision":1}
  self.values={PROJECT:self.entry}
  mocks=[
    patch.object(run,"_folder",return_value=self.root),
    patch.object(run,"STATE",self.root/"registry.json"),
    patch.object(run,"_stop_for_online",return_value=None),
    patch.object(run,"_owned",return_value=stopped()),
    patch.object(run,"_resume_online",return_value=None),
    patch.object(run,"_summary",side_effect=lambda p,e:{"project":p,"revision":e["revision"]}),
    patch.object(run,"_data_save",side_effect=["data-aaaaaaaaaaaa","data-bbbbbbbbbbbb"]),
    patch.object(run,"_data_validate",return_value=[]),
    patch.object(run,"_data_apply",return_value=1),
    patch.object(run,"_up",return_value=None)
  ]
  for mocked in mocks:
   mocked.start();self.addCleanup(mocked.stop)
 def test_update_then_rollback_restores_exact_data(self):
  first=run._versioned_change(PROJECT,self.entry,self.values,OLD,services(),
                              "update",NEW,self.journal,self.previous)
  self.assertEqual(first["operation"],"update")
  self.assertEqual(first["data_checkpoint"],"data-aaaaaaaaaaaa")
  self.assertTrue(first["application_data_rollback"])
  self.assertFalse(self.journal.exists())
  self.assertEqual(json.loads((self.root/"previous-data.json").read_text()),
    {"checkpoint":"data-aaaaaaaaaaaa","manifest_sha256":run._manifest_sha(OLD)})
  second=run._versioned_change(PROJECT,self.entry,self.values,NEW,services(),
                               "rollback",OLD,self.journal,self.previous)
  self.assertEqual(second["operation"],"rollback")
  self.assertTrue(second["data_restored"])
  self.assertEqual(second["data_checkpoint"],"data-bbbbbbbbbbbb")
  self.assertEqual(json.loads((self.root/"previous-data.json").read_text())["checkpoint"],
                   "data-bbbbbbbbbbbb")
  self.assertEqual(self.entry["revision"],3)
 def test_rollback_missing_version_link_rejected_before_change(self):
  with self.assertRaises(AppError) as error:
   run._check_version_link(PROJECT,OLD,None)
  self.assertEqual(error.exception.message,"stage_previous_data_link_missing_or_mismatched")
  self.assertFalse(self.journal.exists())
 def test_update_error_recovers_prior_config_and_checkpoint(self):
  calls=[RuntimeError("new version failed"),None]
  with patch.object(run,"_up",side_effect=calls),patch.object(
    run,"_validate"),patch.object(run,"_verify_partial",return_value=[]),patch.object(
    run,"docker",return_value=""):
   with self.assertRaises(AppError) as error:
    run._versioned_change(PROJECT,self.entry,self.values,OLD,services(),
                          "update",NEW,self.journal,self.previous)
  self.assertEqual(error.exception.message,"stage_version_change_failed_original_and_data_restored")
  self.assertFalse(self.journal.exists())
  self.assertEqual(json.loads((self.root/"compose.json").read_text()),OLD)
  self.assertEqual(self.entry["revision"],1)
 def test_unsafe_recovery_retains_journal(self):
  record={"version":2,"operation":"update","old":OLD,"target":NEW,
          "revision":1,"running":["app"],"backup":"data-cccccccccccc",
          "prior":None,"prior_data":None}
  run._atomic(self.journal,record)
  with patch.object(run,"_validate"),patch.object(run,"_verify_partial",
      side_effect=AppError("foreign_compiled_recovery_container",403)):
   with self.assertRaises(AppError) as error:
    run._recover_versioned(PROJECT,self.entry,record,self.values,self.journal)
  self.assertEqual(error.exception.message,"stage_version_recovery_unverified_containers")
  self.assertTrue(self.journal.exists())

if __name__=="__main__":unittest.main()
