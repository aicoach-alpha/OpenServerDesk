import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import acceptance_m1_compose_compat as c


class ComposeCompatibilityTests(unittest.TestCase):
    def test_compose_never_traverses_untrusted_config_path(self):
        for path in (Path("/mnt/data/nextcloud/docker-compose.yml"),
                     Path("/etc/casaos/app.yml"),
                     Path("/var/lib/casaos/apps/../../nextcloud/docker-compose.yml")):
            with self.assertRaises(ValueError):
                c.safe_project_config(path)

    def test_complex_compose_needs_explicit_support(self):
        document={"services":{
            "db":{"image":"mariadb:10.11",
                  "volumes":["/mnt/data/nextcloud:/data"],
                  "ports":["3306:3306"],
                  "environment":{"MYSQL_ROOT_PASSWORD":"SECRET_VALUE_NEVER_REPORT"}},
            "web":{"image":"nextcloud:latest",
                   "depends_on":["db"],"ports":["8080:80"]}
        }}
        m=c.classify(document)
        self.assertEqual(m["services"],2)
        self.assertEqual(m["mount_declarations"],1)
        self.assertEqual(m["port_declarations"],2)
        self.assertIn("depends_on",m["currently_unsupported_service_keys"])
        self.assertFalse(m["general_import_runtime_verified"])
        self.assertNotIn("SECRET_VALUE_NEVER_REPORT",str(m))


if __name__=="__main__":
    unittest.main()
