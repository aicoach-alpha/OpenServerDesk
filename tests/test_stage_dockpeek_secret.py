"""One focused test suite for new, stage-owned Dockpeek secret lifecycle."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError
from stage_host_socket import DOCKPEEK_ID,DOCKPEEK_SERVICE
import stage_dockpeek_secret as secret
import stage_store_compiler as compiler


class DockpeekStageSecretTests(unittest.TestCase):
    def test_new_secret_is_private_and_survives_compiled_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            project="osd-compiled-0123456789ab"
            (root/project).mkdir(mode=0o700)
            with patch.object(secret,"ROOT",root):
                secret.create(project)
                path=root/project/secret.FILENAME
                self.assertEqual(path.stat().st_mode & 0o777,0o600)
                token=secret.credential(project)
                self.assertRegex(token,r"^[0-9a-f]{64}$")
                with self.assertRaises(AppError):
                    secret.create(project)
                with patch.object(compiler,"analyze",return_value={
                    "services":[{
                        "name":DOCKPEEK_SERVICE,
                        "mount_targets":[],
                        "read_only_targets":[],
                        "host_socket_adapter":True,
                        "immutable_image":"sha256:"+"f"*64,
                        "depends_on":[],
                        "dependency_conditions":{},
                        "web_target":8000,
                    }],
                    "all_images_cached":True,
                }):
                    first=compiler.compile_stage(project,DOCKPEEK_ID)
                    second=compiler.compile_stage(project,DOCKPEEK_ID)
                cfg=first["services"][DOCKPEEK_SERVICE]
                self.assertEqual(cfg["environment"],{"SECRET_KEY":token})
                self.assertEqual(
                    second["services"][DOCKPEEK_SERVICE]["environment"],
                    cfg["environment"])
                self.assertTrue(secret.allow_configuration(
                    project,first["services"]))
                altered={DOCKPEEK_SERVICE:{**cfg,
                    "environment":{"SECRET_KEY":"fake"}}}
                self.assertFalse(secret.allow_configuration(project,altered))
                self.assertNotIn("secret_key",str(cfg["labels"]))

    def test_refuses_untrusted_folder_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            project="osd-compiled-aabbccddeeff"
            folder=root/project
            folder.mkdir(mode=0o777)
            folder.chmod(0o777)
            with patch.object(secret,"ROOT",root):
                with self.assertRaises(AppError):
                    secret.create(project)
                folder.chmod(0o700)
                secret.create(project)
                path=folder/secret.FILENAME
                path.chmod(0o644)
                with self.assertRaises(AppError):
                    secret.credential(project)
                with self.assertRaises(AppError):
                    secret.allow_configuration(
                        project,{DOCKPEEK_SERVICE:{
                            "labels":{"osd.m1.compiled.app":DOCKPEEK_ID},
                            "environment":{"SECRET_KEY":"x"}}})


if __name__=="__main__":
    unittest.main()
