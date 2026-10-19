"""Focused PostgreSQL offline stage-only archive provenance and clean shutdown."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_postgres_integrity as pg
from stage_apps import AppError

P="osd-compiled-abcdef123456"
IMAGE="sha256:"+"a"*64
MANIFEST={"services":{
 "qui":{"labels":{"osd.m1.compiled.app":pg.APP}},
 "postgres":{"image":IMAGE,"labels":{"osd.m1.compiled.app":pg.APP}}}}
OK=("Database system identifier:           654321\n"+
    "Database cluster state:               shut down\n")

class ColdPgTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name)
  self.data=self.root/P/"postgres"/"volume-0"
  (self.data/"global").mkdir(parents=True)
  (self.data/"PG_VERSION").write_text("16\n")
  (self.data/"global"/"pg_control").write_bytes(b"x"*8192)
 def test_readonly_no_network_pg_controldata_from_immutable_image(self):
  with patch.object(pg.subprocess,"run",return_value=Mock(returncode=0,stdout=OK)) as runner:
   self.assertTrue(pg.verify(P,MANIFEST,self.data,self.root))
   args=runner.call_args.args[0]
   self.assertIn("--network",args)
   self.assertEqual(args[args.index("--network")+1],"none")
   self.assertIn("--read-only",args)
   self.assertEqual(args[args.index("--user")+1],"0:0")
   self.assertIn("--cap-drop",args)
   self.assertIn("ALL",args)
   self.assertIn("type=bind,src="+str(self.data)+",dst=/pgdata,readonly",args)
   self.assertEqual(args[-2:],(IMAGE,"/pgdata"))
 def test_refuse_live_postgres_and_foreign_stage_path(self):
  (self.data/"postmaster.pid").write_text("1")
  with patch.object(pg.subprocess,"run") as runner:
   with self.assertRaises(AppError):
    pg.verify(P,MANIFEST,self.data,self.root)
   runner.assert_not_called()
  (self.data/"postmaster.pid").unlink()
  with patch.object(pg.subprocess,"run") as runner:
   with self.assertRaises(AppError):
    pg.verify(P,MANIFEST,self.root/"outside",self.root)
   runner.assert_not_called()
 def test_reject_unclean_control_state(self):
  with patch.object(pg.subprocess,"run",return_value=Mock(
      returncode=0,stdout=OK.replace("shut down","in production"))):
   with self.assertRaises(AppError) as error:
    pg.verify(P,MANIFEST,self.data,self.root)
   self.assertEqual(error.exception.message,"stage_postgres_cold_integrity_failed")

if __name__=="__main__":unittest.main()
