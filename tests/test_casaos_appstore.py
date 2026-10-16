"""Catalog compatibility tests: no user-upload file or Docker mutation."""
import json
import tempfile
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import casaos_appstore as store

class CasaOSAppStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="osd-safe-store-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.apps=self.root/"default"/"Apps"
        self.apps.mkdir(parents=True)
        src=self.apps/"SafeTest"
        src.mkdir()
        (src/"docker-compose.yml").write_text("""name: safe-test
services:
  web:
    image: example/demo:1.0
    ports:
      - 8080:8080
    volumes:
      - /mnt/data/nextcloud/uploads:/data
x-casaos:
  id: safe-demo
  title:
    en_US: Safe Demo
  tagline:
    en_US: A nice app
  category: Utilities
  version: '1.0'
""")
    def test_legacy_metadata_no_user_path_exposed(self):
        output=store.catalog(self.root)
        self.assertEqual(output["app_count"],1)
        item=output["apps"][0]
        self.assertEqual(item["title"],"Safe Demo")
        self.assertEqual(item["category"],"Utilities")
        self.assertTrue(item["compatibility"]["uses_bind_or_volume"])
        self.assertTrue(item["compatibility"]["uses_ports"])
        self.assertNotIn("/mnt/data",json.dumps(output))
        self.assertFalse(output["app_install_enabled"])
        self.assertFalse(output["migration_allowed"])
    def test_invalid_yaml_symlinks_and_hidden_extension(self):
        broken=self.apps/"Broken"
        broken.mkdir()
        (broken/"docker-compose.yml").write_text("services: [")
        linked=self.apps/"Alias"
        linked.symlink_to(self.apps/"SafeTest",target_is_directory=True)
        self.assertEqual(store.catalog(self.root)["app_count"],1)
    def test_malicious_yaml_tag_rejected(self):
        bad=self.apps/"BadTag"
        bad.mkdir()
        (bad/"docker-compose.yml").write_text(
            "services: !!python/object/apply:os.system ['touch /tmp/casaos-side-effect']\n"
        )
        self.assertEqual(store.catalog(self.root)["app_count"],1)
    def test_oversize_is_excluded(self):
        huge=self.apps/"Huge"
        huge.mkdir()
        (huge/"docker-compose.yml").write_text("x"*(store.MAX_COMPOSE_BYTES+1))
        self.assertEqual(store.catalog(self.root)["app_count"],1)
    def test_no_store_symlink_traversal(self):
        (self.root/"github.com").symlink_to("/mnt/data",target_is_directory=True)
        self.assertEqual(store.catalog(self.root)["app_count"],1)

if __name__=="__main__":unittest.main()
