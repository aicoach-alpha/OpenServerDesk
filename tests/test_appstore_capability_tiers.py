"""Focused coverage and host capability tiers for all CasaOS definitions."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from appstore_compatibility_matrix import listing


class RemediationTests(unittest.TestCase):
    def test_every_catalog_entry_has_precise_safe_status(self):
        data=listing()
        self.assertEqual(data["app_count"],726)
        self.assertEqual(data["sandbox_plan_supported"],675)
        self.assertEqual(data["install_mode_counts"],{
            "isolated_stage_sandbox":675,
            "special_host_integration":51,
            "unsupported_compose_metadata":0,
        })
        self.assertFalse(data["production_mutation_allowed"])
        self.assertFalse(data["nextcloud_user_data_inspected"])
        items={row["id"]:row for row in data["apps"]}
        for name in ("github.com:com.bigbeartechworld.fail2ban",
                     "github.com:com.bigbeartechworld.mame"):
            item=items[name]
            self.assertEqual(item["install_mode"],
                             "isolated_stage_sandbox")
            self.assertTrue(item["sandbox_plan_supported"])
            self.assertIn("readonly_source_content_not_imported",
                          item["feature_gaps"])
        vpn=items["casaos.app:org.icewhale.v2raya"]
        self.assertEqual(vpn["remediation_code"],
                         "requires_host_dns_and_network_capabilities")
        self.assertEqual(vpn["install_mode"],"special_host_integration")
        self.assertFalse(vpn["sandbox_plan_supported"])


if __name__=="__main__":
    unittest.main()
