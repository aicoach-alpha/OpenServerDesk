"""Integration rehearsal using only generated CasaOS-like fixtures."""
import json
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backup_restore as b


class TestSyntheticRestore(unittest.TestCase):
    def test_files_and_sqlite_are_restored_from_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="osd-m1-fixture-") as td:
            root = Path(td)
            config = root / "etc" / "casaos"
            apps = root / "var" / "lib" / "casaos" / "apps"
            db = root / "var" / "lib" / "casaos" / "db"
            config.mkdir(parents=True)
            apps.mkdir(parents=True)
            db.mkdir(parents=True)
            (config / "gateway.ini").write_text("[gateway]\nport=19001\n")
            (apps / "synthetic.compose.yml").write_text("services:\n  fixture:\n    image: busybox\n")
            database = db / "user.db"
            with sqlite3.connect(database) as conn:
                conn.execute("CREATE TABLE synthetic_user(id INTEGER PRIMARY KEY, name TEXT)")
                conn.execute("INSERT INTO synthetic_user(name) VALUES (?)", ("fixture-only",))
            with patch.object(b, "SRC", [config, apps]), patch.object(b, "DB", db), patch.object(b, "DEST", root / "backups"):
                archive = b.backup()
                self.assertTrue(archive.exists())
                (config / "gateway.ini").write_text("[gateway]\nport=99999\n")
                with sqlite3.connect(database) as conn:
                    conn.execute("DELETE FROM synthetic_user")
                result = b.rehearse(archive)
                self.assertEqual(result["sqlite_verified"], 1)
                self.assertGreaterEqual(result["files_verified"], 3)
                self.assertFalse(result["production_modified"])
                self.assertFalse(result["external_hdd_copied"])
                with tarfile.open(archive, "r:gz") as tf:
                    restored = tf.extractfile(str(config.relative_to("/")) + "/gateway.ini")
                    self.assertEqual(restored.read(), b"[gateway]\nport=19001\n")
                    db_entry = tf.extractfile(str(database.relative_to("/")))
                    snapshot = root / "snapshot.db"
                    snapshot.write_bytes(db_entry.read())
                with sqlite3.connect(snapshot) as conn:
                    self.assertEqual(conn.execute("SELECT name FROM synthetic_user").fetchone()[0], "fixture-only")
                with sqlite3.connect(database) as conn:
                    self.assertEqual(conn.execute("SELECT count(*) FROM synthetic_user").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
