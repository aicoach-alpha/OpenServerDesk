"""No production Docker mutation; validate untrusted multi-service schemas."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_topology import validate, _compose, AppError, MOUNT

class TopologyTests(unittest.TestCase):
    def test_valid_multi_service_dependency(self):
        structure=[
            {"name":"api","depends_on":["db"]},
            {"name":"db","depends_on":[]},
            {"name":"worker","depends_on":["db"]},
        ]
        mapping=validate(structure)
        self.assertEqual(mapping["api"],["db"])
        rendered=_compose("osd-m1-topology-"+"f"*12,"a"*32,mapping,
                          Path("/opt/openserverdesk-dev/runtime-stage/stage-app-manager/topology-projects/x/data"))
        self.assertIn('"network_mode": "none"',rendered)
        self.assertNotIn("/mnt/data",rendered)
        self.assertNotIn("ports",rendered)
        self.assertNotIn("privileged",rendered)
        self.assertIn(MOUNT,rendered)

    def test_untrusted_network_and_bind_flags_denied(self):
        for additional in ({"ports":["443:443"]},
                           {"volumes":["/mnt/data/nextcloud:/data"]},
                           {"environment":{"SECRET":"private"}},
                           {"privileged":True}):
            with self.subTest(additional=additional):
                with self.assertRaises(AppError):
                    validate([
                        {"name":"api","depends_on":[],**additional},
                        {"name":"db","depends_on":[]},
                    ])

    def test_dependency_cycle_and_missing_rejected(self):
        cases=[
            [{"name":"api","depends_on":["db"]},{"name":"db","depends_on":["api"]}],
            [{"name":"api","depends_on":["missing"]},{"name":"db","depends_on":[]}],
            [{"name":"api","depends_on":["api"]},{"name":"db","depends_on":[]}],
        ]
        for sample in cases:
            with self.subTest(sample=sample),self.assertRaises(AppError):
                validate(sample)

    def test_invalid_id_and_service_count_rejected(self):
        for sample in ([], [{"name":"a","depends_on":[]}],
                       [{"name":"../etc","depends_on":[]},{"name":"db","depends_on":[]}]):
            with self.subTest(sample=sample),self.assertRaises(AppError):
                validate(sample)

if __name__=="__main__":unittest.main()
