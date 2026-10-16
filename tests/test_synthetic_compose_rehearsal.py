import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import synthetic_compose_rehearsal as c

class SyntheticRehearsalTests(unittest.TestCase):
    def test_redacts_secrets_and_mounts_and_ports(self):
        marker="SPECIAL_SUPERSECRET_USER_UPLOAD_VALUE"
        source={"services":{
            "web":{"image":"nextcloud:prod","ports":["443:443"],
                   "environment":{"PASSWORD":marker},
                   "volumes":["/mnt/data/nextcloud/"+marker+":/var/www"],
                   "depends_on":["db"]},
            "db":{"image":"mariadb:prod","environment":{"PASS":marker}}}}
        parsed,m=c.synthetic(source)
        encoded=json.dumps(parsed)
        self.assertNotIn(marker,encoded)
        self.assertNotIn("/mnt/data",encoded)
        self.assertNotIn("nextcloud:prod",encoded)
        self.assertNotIn("443:443",encoded)
        self.assertEqual(parsed["services"]["web"]["depends_on"],["db"])
        self.assertEqual(m["service_count"],2)
        for service in parsed["services"].values():
            self.assertEqual(service["network_mode"],"none")
            self.assertEqual(service["image"],"busybox:latest")
            self.assertNotIn("volumes",service)
            self.assertNotIn("ports",service)

    def test_rejects_untrusted_service_key(self):
        with self.assertRaises(ValueError):
            c.synthetic({"services":{"../host":{"image":"busybox"}}})

if __name__=="__main__": unittest.main()
