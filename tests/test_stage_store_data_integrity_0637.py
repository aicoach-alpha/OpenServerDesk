"""Content validation is mandatory for new staging-only volume checkpoints."""
import sys, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_data as data
from stage_apps import AppError

class DigestTests(unittest.TestCase):
    def test_digest_detects_content_changes_even_same_length(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"db.sqlite").write_bytes(b"abcdefgh")
            with patch.object(data,"ROOT",root):
                before=data._digest_tree(root)
                (root/"db.sqlite").write_bytes(b"abcdEfgh")
                after=data._digest_tree(root)
                self.assertNotEqual(before,after)
    def test_snapshot_manifest_detects_tampered_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            project="osd-compiled-abcdef123456"
            vol=root/project/"db"/"volume-0"
            vol.mkdir(parents=True)
            (vol/"rows").write_text("original")
            manifest={"services":{"db":{"volumes":[{"source":str(vol)}]}}}
            with patch.object(data,"ROOT",root):
                cp=data._save(project,manifest)
                self.assertEqual((root/project/"data-checkpoints"/cp/"manifest.json").is_file(),True)
                archive=root/project/"data-checkpoints"/cp/"volumes"/"db"/"volume-0"/"rows"
                archive.write_text("tampered")
                with self.assertRaises(AppError) as raised:
                    data._validate_snapshot(project,manifest,cp)
                self.assertEqual(raised.exception.message,"stage_checkpoint_integrity_mismatch")
if __name__=="__main__":unittest.main()
