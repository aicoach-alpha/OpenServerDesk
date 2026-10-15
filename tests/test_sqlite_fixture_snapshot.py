import sqlite3
import tempfile
import unittest
from pathlib import Path
from sqlite_fixture_snapshot import snapshot


class SQLiteSnapshotTests(unittest.TestCase):
    def test_wal_transaction_included_in_consistent_backup(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/"fixture.db", Path(d)/"snapshot.db"
            with sqlite3.connect(src) as writer:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("CREATE TABLE items(v TEXT)")
                writer.execute("INSERT INTO items VALUES ('visible')")
                writer.commit()
                writer.execute("PRAGMA wal_checkpoint(PASSIVE)")
                snapshot(src, dst)
                with sqlite3.connect(dst) as check:
                    self.assertEqual(check.execute("SELECT v FROM items").fetchone()[0], "visible")

    def test_reject_same_source_and_destination(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d)/"fixture.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE x(n INT)")
            with self.assertRaises(ValueError):
                snapshot(db, db)


if __name__ == "__main__":
    unittest.main()
