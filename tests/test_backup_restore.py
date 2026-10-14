import io, tarfile, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import backup_restore as b
class TestBackup(unittest.TestCase):
    def test_no_external_data_in_roots(self):
        self.assertTrue(all(not str(p).startswith("/mnt/data") for p in b.SRC+[b.DB]))
    def test_malicious_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t=Path(d)/"evil.tar.gz"
            with tarfile.open(t,"w:gz") as tf:
                data=b"x"
                info=tarfile.TarInfo("../evil")
                info.size=len(data)
                tf.addfile(info,io.BytesIO(data))
            with self.assertRaises(ValueError):b.rehearse(t)
    def test_empty_db_backup_rehearsal(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,"SRC",[]),patch.object(b,"DB",Path(d)),patch.object(b,"DEST",Path(d)/"dest"):
                result=b.backup()
                self.assertEqual(b.rehearse(result)["sqlite_verified"],0)
if __name__=="__main__":unittest.main()
