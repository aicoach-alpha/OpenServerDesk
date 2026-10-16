"""SQLite-only cold-snapshot recovery acceptance, fixture is staging-owned temp root."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_data as store
from stage_apps import AppError

PROJECT="osd-compiled-abcdef123456"
class SQLiteRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.volume=self.root/PROJECT/"db"/"volume-0"
        self.volume.mkdir(parents=True)
        self.db=self.volume/"app.sqlite"
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
            con.execute("INSERT INTO items (name) VALUES (?)",("initial",))
        self.manifest={"services":{"db":{"volumes":[{"source":str(self.volume)}]}}}
        self.patch=patch.object(store,"ROOT",self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def records(self):
        with sqlite3.connect(self.db) as con:
            return [r[0] for r in con.execute("SELECT name FROM items ORDER BY id")]

    def test_sqlite_checkpoint_and_restore_preserves_rows(self):
        cp=store.checkpoint(PROJECT,self.manifest,{})
        self.assertEqual(cp["operation"],"checkpoint")
        self.assertEqual(cp["sqlite_files_verified"],1)
        self.assertTrue(cp["sqlite_quick_check_passed"])
        self.assertFalse(cp["database_integrity_verified"])
        meta=self.root/PROJECT/"data-checkpoints"/cp["checkpoint"]/"manifest.json"
        import json
        data=json.loads(meta.read_text())
        self.assertEqual(data["sqlite_files_verified"],1)
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO items (name) VALUES (?)",("new",))
        self.assertEqual(self.records(),["initial","new"])
        result=store.restore(PROJECT,self.manifest,{},cp["checkpoint"])
        self.assertEqual(result["operation"],"restored")
        self.assertEqual(result["sqlite_files_verified"],1)
        self.assertEqual(self.records(),["initial"])
        self.assertFalse((self.root/PROJECT/"data-restore-pending.json").exists())

    def test_corrupted_database_rejects_checkpoint(self):
        self.db.write_bytes(b"non-sqlite-data")
        with self.assertRaises(AppError) as error:
            store.checkpoint(PROJECT,self.manifest,{})
        self.assertEqual(error.exception.message,"stage_sqlite_invalid_header")

    def test_pending_wal_must_be_checkpointed(self):
        (self.volume/"app.sqlite-wal").write_bytes(b"uncheckpointed")
        with self.assertRaises(AppError) as error:
            store.checkpoint(PROJECT,self.manifest,{})
        self.assertEqual(error.exception.message,"stage_sqlite_uncheckpointed_journal")

    def test_crash_journal_recover_restores_previous_rows(self):
        cp=store.checkpoint(PROJECT,self.manifest,{})
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO items (name) VALUES (?)",("uncommitted-to-restore",))
        with patch.object(store,"_apply",side_effect=RuntimeError("crash")):
            with self.assertRaises(AppError) as error:
                store.restore(PROJECT,self.manifest,{},cp["checkpoint"])
        self.assertEqual(error.exception.message,"stage_data_restore_requires_recovery")
        self.assertTrue((self.root/PROJECT/"data-restore-pending.json").exists())
        result=store.recover(PROJECT,self.manifest,{})
        self.assertEqual(result["operation"],"recovered_pre_restore_data")
        self.assertEqual(self.records(),["initial","uncommitted-to-restore"])
        self.assertFalse((self.root/PROJECT/"data-restore-pending.json").exists())

if __name__=="__main__":
    unittest.main()
