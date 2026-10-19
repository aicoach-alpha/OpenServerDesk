"""Owner-aware stage-only PostgreSQL cold file inspector tests."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_postgres_integrity as pg
from stage_apps import AppError
P="osd-compiled-abcdef123456"
M={"services":{"qui":{"labels":{"osd.m1.compiled.app":pg.APP}},
               "postgres":{"image":"sha256:"+"a"*64,
                           "labels":{"osd.m1.compiled.app":pg.APP}}}}
OK="Database system identifier: 12345\nDatabase cluster state: shut down\n"
class OwnerTests(unittest.TestCase):
 def test_root_snapshot_and_uid1000_restored_volume_use_matching_reader(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);pgdata=root/P/"postgres"/"volume-0"
   (pgdata/"global").mkdir(parents=True)
   version=pgdata/"PG_VERSION";version.write_text("16\n")
   control=pgdata/"global"/"pg_control";control.write_bytes(b"x"*8192)
   with patch.object(pg.subprocess,"run",return_value=Mock(returncode=0,stdout=OK)) as runner:
    self.assertTrue(pg.verify(P,M,pgdata,root))
    self.assertEqual(runner.call_args.args[0][runner.call_args.args[0].index("--user")+1],"0:0")
    os.chown(version,1000,1000);os.chown(control,1000,1000)
    self.assertTrue(pg.verify(P,M,pgdata,root))
    args=runner.call_args.args[0]
    self.assertEqual(args[args.index("--user")+1],"1000:1000")
 def test_foreign_owner_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);pgdata=root/P/"postgres"/"volume-0"
   (pgdata/"global").mkdir(parents=True)
   version=pgdata/"PG_VERSION";version.write_text("16\n")
   control=pgdata/"global"/"pg_control";control.write_bytes(b"x"*8192)
   os.chown(version,2000,2000);os.chown(control,2000,2000)
   with patch.object(pg.subprocess,"run") as process:
    with self.assertRaises(AppError) as error:
     pg.verify(P,M,pgdata,root)
    self.assertEqual(error.exception.message,"stage_postgres_cold_owner_invalid")
    process.assert_not_called()
if __name__=="__main__":unittest.main()
