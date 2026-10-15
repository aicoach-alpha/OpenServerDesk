import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from journaled_pair import digest, recover, replace_pair


class JournalTests(unittest.TestCase):
    def fixture(self, root):
        b, t = root / "bundle", root / "live"
        b.mkdir()
        t.mkdir()
        (b / "userservice").write_bytes(b"older-valid")
        with sqlite3.connect(b / "user.db") as db:
            db.execute("CREATE TABLE u (name TEXT)")
            db.execute("INSERT INTO u VALUES ('restored')")
        (b / "manifest.json").write_text(json.dumps({n: digest(b / n) for n in ("userservice", "user.db")}))
        (t / "userservice").write_bytes(b"new-current")
        (t / "user.db").write_bytes(b"current-payload")
        return b, t

    def test_restore_after_successful_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            replace_pair(b, t)
            self.assertEqual((t / "userservice").read_bytes(), b"older-valid")
            self.assertTrue(recover(t))
            self.assertEqual((t / "userservice").read_bytes(), b"new-current")
            self.assertEqual((t / "user.db").read_bytes(), b"current-payload")

    def test_crash_after_first_file_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            code = """
import os
import journaled_pair as j
old_replace = os.replace
def kill_after_first(src, dst):
    old_replace(src, dst)
    if str(dst).endswith('/userservice'):
        os._exit(71)
os.replace = kill_after_first
j.replace_pair(__import__('sys').argv[1], __import__('sys').argv[2])
"""
            p = subprocess.run([sys.executable, "-c", code, str(b), str(t)], env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "tools" / "migration")})
            self.assertEqual(p.returncode, 71)
            self.assertTrue(recover(t))
            self.assertEqual((t / "userservice").read_bytes(), b"new-current")
            self.assertEqual((t / "user.db").read_bytes(), b"current-payload")

    def test_crash_during_journal_preparation_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            code = """
import os
import journaled_pair as j
original = j.save
def crash_after_first_copy(src, dest):
    original(src, dest)
    if str(dest).endswith('/.osd-undo-preparing/userservice'):
        os._exit(72)
j.save = crash_after_first_copy
j.replace_pair(__import__('sys').argv[1], __import__('sys').argv[2])
"""
            process = subprocess.run([sys.executable, "-c", code, str(b), str(t)],
                                     env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "tools" / "migration")})
            self.assertEqual(process.returncode, 72)
            self.assertEqual((t / "userservice").read_bytes(), b"new-current")
            self.assertEqual((t / "user.db").read_bytes(), b"current-payload")
            with self.assertRaises(RuntimeError):
                recover(t)
            with self.assertRaises(RuntimeError):
                replace_pair(b, t)

    def test_second_process_cannot_write_while_target_locked(self):
        import fcntl
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            with open(t / ".osd-rollback.lock", "a+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                code = """
import journaled_pair as j, sys
try:
    j.replace_pair(sys.argv[1], sys.argv[2])
except RuntimeError as e:
    sys.exit(0 if 'lock' in str(e) else 2)
sys.exit(3)
"""
                proc = subprocess.run([sys.executable, "-c", code, str(b), str(t)],
                    env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "tools" / "migration")})
                self.assertEqual(proc.returncode, 0)
                self.assertEqual((t / "userservice").read_bytes(), b"new-current")
                self.assertEqual((t / "user.db").read_bytes(), b"current-payload")

    def test_active_sqlite_wal_sidecar_blocks_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            (t / "user.db-wal").write_bytes(b"synthetic pending frames")
            with self.assertRaises(RuntimeError):
                replace_pair(b, t)
            self.assertEqual((t / "userservice").read_bytes(), b"new-current")
            self.assertFalse((t / ".osd-undo").exists())

    def test_corrupt_undo_denies_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            replace_pair(b, t)
            (t / ".osd-undo" / "user.db").write_bytes(b"tampered")
            with self.assertRaises(RuntimeError):
                recover(t)


if __name__ == "__main__":
    unittest.main()
