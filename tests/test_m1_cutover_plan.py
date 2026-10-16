"""Safety-focused acceptance tests for real CasaOS config-only release plan."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "migration"))
import m1_cutover_readiness as planner


class CutoverPlanTests(unittest.TestCase):
    def test_all_release_unsafe_conditions_remain_blocked(self):
        scope = {
            "production_modified": False,
            "running_container_count": 16,
            "compose_project_count": 10,
            "protected_bind_references_skipped": 4,
            "external_user_data_copied": False,
            "external_user_data_inspected": False,
        }
        sources = ["/etc/casaos", "/var/lib/casaos"]
        units = {
            name: {"state": "active", "files": ["/etc/systemd/system/"+name]}
            for name in planner.NAMES
        }
        with patch.object(planner, "select", return_value=(scope,sources)), \
             patch.object(planner, "check_backup", return_value={
                 "backup_id": "config-"+"a"*16, "files": 1652,
                 "sqlite_databases": 3, "ssd_distinct_fs": True,
             }), \
             patch.object(planner, "service_inventory", return_value=units):
            result, private=planner.assess()
        self.assertFalse(result["migration_allowed"])
        self.assertFalse(result["production_modified"])
        self.assertFalse(result["user_data_content_accessed"])
        self.assertFalse(result["external_hdd_backup_required"])
        self.assertEqual(result["verified_config_files"], 1652)
        self.assertEqual(len(result["pending_gates"]), 4)
        self.assertNotIn("selected_platform_config_source_paths", result)
        self.assertIn("selected_platform_config_source_paths", private)
        self.assertEqual(set(result["gates"]), set(planner.CRITERIA))
        self.assertTrue(result["gates"]["backup_on_independent_ssd"])
        self.assertFalse(result["gates"]["explicit_maintenance_authorization"])

    def test_missing_backup_stays_blocked(self):
        scope = {
            "production_modified": False,
            "running_container_count": 16,
            "compose_project_count": 10,
            "protected_bind_references_skipped": 4,
            "external_user_data_copied": False,
            "external_user_data_inspected": False,
        }
        with patch.object(planner, "select", return_value=(scope,["/etc/casaos"])), \
             patch.object(planner, "check_backup", side_effect=planner.NotReady("no backup")), \
             patch.object(planner, "service_inventory", side_effect=RuntimeError("no systemd")):
            result, _=planner.assess()
        self.assertFalse(result["gates"]["backup_on_independent_ssd"])
        self.assertFalse(result["gates"]["verified_ssd_snapshot_and_independent_restore"])
        self.assertFalse(result["gates"]["six_casaos_units_healthy"])
        self.assertFalse(result["migration_allowed"])

    def test_user_hdd_data_is_rejected_before_any_backup_access(self):
        self.assertTrue(planner.protected(Path("/mnt/data/nextcloud/files")))
        with self.assertRaises(planner.NotReady):
            planner.normalized_selected(["/etc/casaos", "/mnt/data/nextcloud/files"])


if __name__=="__main__":
    unittest.main()
