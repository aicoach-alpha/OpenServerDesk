import json
import tempfile
import unittest
from pathlib import Path
from volume_fixture import snapshot, validate


class VolumeFixtureTests(unittest.TestCase):
    def test_nested_volume_snapshot_and_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data, archive = root / "volume", root / "archive"
            (data / "app" / "config").mkdir(parents=True)
            (data / "app" / "config" / "settings.json").write_text('{"fixture": true}')
            snapshot(data, archive)
            (data / "app" / "config" / "settings.json").write_text("modified")
            self.assertEqual(validate(archive), 1)
            self.assertEqual((archive / "data" / "app" / "config" / "settings.json").read_text(), '{"fixture": true}')

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = root / "data"
            data.mkdir()
            (data / "escape").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                snapshot(data, root / "archive")

    def test_symlink_source_root_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            real = root / "real"
            real.mkdir()
            (real / "fixture").write_text("x")
            (root / "alias").symlink_to(real, target_is_directory=True)
            with self.assertRaises(ValueError):
                snapshot(root / "alias", root / "archive")

    def test_snapshot_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = root / "data"
            data.mkdir()
            (data / "x").write_text("ok")
            snapshot(data, root / "archive")
            (root / "archive" / "data" / "x").write_text("bad")
            with self.assertRaises(ValueError):
                validate(root / "archive")


if __name__ == "__main__":
    unittest.main()
