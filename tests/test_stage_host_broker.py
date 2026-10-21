"""Host broker is authenticated by its API route and never grants host rights."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError
import stage_host_broker as broker


class HostBrokerContract(unittest.TestCase):
    def test_catalog_exactly_classified_default_denied(self):
        data=broker.contracts()
        self.assertEqual(data["count"],50)
        self.assertFalse(data["host_privileged_access"])
        self.assertFalse(data["production_mutation_allowed"])
        self.assertFalse(data["runtime_compatibility_proven"])
        self.assertEqual(len(data["contracts"]),50)
        for app in data["contracts"]:
            self.assertFalse(app["host_privileged_access"])
            self.assertFalse(app["stage_docker_socket_exposed"])
            self.assertFalse(app["production_mutation_allowed"])
            self.assertFalse(app["external_hdd_user_data_access"])
            self.assertEqual(app["granted_host_capabilities"],[])
        assert any("host_docker_or_casaos_api" in x["requested_host_capabilities"]
                   for x in data["contracts"])

    def test_readonly_stage_inventory_only_and_protected_excluded(self):
        sample={"production_mutation_allowed":False,"complete":True,
                "applications":[
                    {"source":"store_compiled","running":True,
                     "readiness":"ready","lifecycle_writable":True,
                     "secret":"must-not-leak","project":"secret-project"},
                    {"source":"store_compiled","running":True,
                     "lifecycle_writable":False,"secret":"protected"},
                ]}
        with patch.object(broker,"inventory",return_value=sample):
            value=broker.inspect("default:Portainer")
        self.assertEqual(value["stage_readonly_inventory"]["total"],1)
        self.assertEqual(value["stage_readonly_inventory"]["running"],1)
        self.assertNotIn("secret",str(value))
        self.assertNotIn("secret-project",str(value))
        self.assertNotIn("/mnt/",str(value))
        self.assertEqual(value["granted_host_capabilities"],[])

    def test_denies_unknown_and_arbitrary_host_requests(self):
        for app in ("../passwd","default:MySpeed","", "a"*117):
            with self.subTest(app=app):
                with self.assertRaises(AppError):
                    broker.inspect(app)
        with patch.object(broker,"inventory",
                          return_value={"production_mutation_allowed":True}):
            with self.assertRaises(AppError):
                broker.inspect("default:Portainer")

    def test_stage_readonly_live_inventory_no_host_side_effects(self):
        info=broker.inspect("default:Portainer")
        self.assertEqual(info["decision"],
                         "host_capabilities_denied_stage_inventory_only")
        self.assertIsInstance(info["stage_readonly_inventory"]["total"],int)
        self.assertFalse(info["external_hdd_user_data_access"])


if __name__=="__main__":
    unittest.main()
