import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from atomic_pair_rollback import rollback, sha


class PairRollbackTests(unittest.TestCase):
    def fixture(self, root):
        bundle, live = root / "bundle", root / "live"
        bundle.mkdir()
        live.mkdir()
        (bundle / "userservice").write_bytes(b"known-good-binary")
        with sqlite3.connect(bundle / "user.db") as db:
            db.execute("CREATE TABLE users (name TEXT)")
            db.execute("INSERT INTO users VALUES ('synthetic')")
        (bundle / "manifest.json").write_text(json.dumps({
            name: sha(bundle / name) for name in ("userservice", "user.db")
        }))
        (live / "userservice").write_bytes(b"candidate-binary")
        (live / "user.db").write_bytes(b"invalid-candidate-db")
        return bundle, live

    def test_pair_restored(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            self.assertTrue(all(rollback(b, t).values()))
            with sqlite3.connect(t / "user.db") as conn:
                self.assertEqual(conn.execute("SELECT name FROM users").fetchone()[0], "synthetic")

    def test_invalid_snapshot_denied_without_change(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            (b / "userservice").write_bytes(b"tampered")
            before = [(t / name).read_bytes() for name in ("userservice", "user.db")]
            with self.assertRaises(ValueError):
                rollback(b, t)
            self.assertEqual(before, [(t / name).read_bytes() for name in ("userservice", "user.db")])

    def test_injected_failure_restores_previous_pair(self):
        with tempfile.TemporaryDirectory() as d:
            b, t = self.fixture(Path(d))
            before = [(t / name).read_bytes() for name in ("userservice", "user.db")]
            with self.assertRaises(RuntimeError):
                rollback(b, t, fail_after_first=True)
            self.assertEqual(before, [(t / name).read_bytes() for name in ("userservice", "user.db")])


if __name__ == "__main__":
    unittest.main()
