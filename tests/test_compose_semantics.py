import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import compose_semantics as c

class ComposeSemanticsTests(unittest.TestCase):
    def test_credentials_and_mount_values_never_leak(self):
        private="VERY_PRIVATE_NEXTCLOUD_UPLOADS_PASSWORD"
        sample={"services":{"database":{
            "image":"mariadb:latest",
            "environment":{"MYSQL_ROOT_PASSWORD":private},
            "volumes":["/mnt/data/nextcloud/"+private+":/data"],
            "ports":["8080:80"],"healthcheck":{"test":["CMD",private]}},
            "frontend":{"image":"nextcloud","depends_on":{
                "database":{"condition":"service_healthy"}}}}}
        output=c.assess_config(sample)
        self.assertEqual(output["service_count"],2)
        self.assertEqual(output["service_dependencies"],1)
        self.assertIn("environment",output["sandbox_replay_restricted_field_kinds"])
        self.assertNotIn(private,str(output))
        self.assertFalse(output["runtime_parity_verified"])

    def test_missing_dependencies_rejected(self):
        with self.assertRaises(ValueError):
            c.assess_config({"services":{"x":{"depends_on":["missing"]}}})

    def test_self_dependency_rejected(self):
        with self.assertRaises(ValueError):
            c.assess_config({"services":{"x":{"depends_on":["x"]}}})

    def test_indirect_cyclic_dependency_fails_closed(self):
        doc={"services":{
            "first":{"image":"alpine","depends_on":["second"]},
            "second":{"image":"alpine","depends_on":{"third":{"condition":"service_started"}}},
            "third":{"image":"alpine","depends_on":["first"]},
        }}
        with self.assertRaisesRegex(ValueError, "cyclic"):
            c.assess_config(doc)

    def test_valid_chain_without_user_data_access(self):
        doc={"services":{
            "frontend":{"image":"nginx","depends_on":["db"]},
            "db":{"image":"mariadb"},
        }}
        result=c.assess_config(doc)
        self.assertEqual(result["service_dependencies"], 1)
        self.assertFalse(result["runtime_parity_verified"])

    def test_unknown_keys_count_only(self):
        output=c.assess_config({"services":{"x":{"image":"busybox",
                                               "unrecognized_option":"sensitive"}}})
        self.assertEqual(output["unknown_compose_field_kinds"],{"unrecognized_option":1})
        self.assertNotIn("sensitive",str(output))
        self.assertFalse(output["replacement_parity_passed"] if "replacement_parity_passed" in output else output["runtime_parity_verified"])

if __name__=="__main__":unittest.main()
