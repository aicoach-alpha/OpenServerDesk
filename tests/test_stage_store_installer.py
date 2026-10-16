"""Mocked negative security cases, plus real CasaOS store image provenance."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_installer as pilot
from stage_apps import AppError

class StageStorePilotTests(unittest.TestCase):
    def test_matches_original_casaos_store_tag(self):
        self.assertEqual(pilot._catalog_image(),pilot.IMAGE)
        self.assertEqual(pilot.APP_ID,"default:MySpeed")
        self.assertEqual(pilot.DATA_TARGET,"/myspeed/data")

    def test_store_image_tag_changed_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            metadata=root/"default"/"Apps"/"MySpeed"/"docker-compose.yml"
            metadata.parent.mkdir(parents=True)
            metadata.write_text("services:\n  myspeed:\n    image: other/untrusted:latest\n")
            with patch.object(pilot,"STORE_ROOT",root),patch.object(pilot,"CANDIDATE",metadata):
                with self.assertRaises(AppError):
                    pilot._catalog_image()

    def test_symlinked_store_definition_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            app=root/"default"/"Apps"/"MySpeed"
            app.mkdir(parents=True)
            (app/"docker-compose.yml").symlink_to("/mnt/data/secret")
            with patch.object(pilot,"STORE_ROOT",root),patch.object(pilot,"CANDIDATE",app/"docker-compose.yml"):
                with self.assertRaises(AppError):
                    pilot._catalog_image()

    def test_unknown_app_never_invokes_docker(self):
        with patch.object(pilot,"guarded"), \
             patch.object(pilot,"_registry",return_value={}), \
             patch.object(pilot,"_run",side_effect=AssertionError("docker invoked")):
            with self.assertRaises(AppError):
                pilot.action("install",app_id="default:Nextcloud")

    def test_root_policy_no_host_paths(self):
        self.assertTrue(pilot.ROOT.is_relative_to(pilot.STAGE))
        self.assertNotIn("/mnt/data",str(pilot.ROOT))
        self.assertEqual(pilot.IMAGE,"germannewsmaker/myspeed:1.0.8")

if __name__=="__main__":unittest.main()
