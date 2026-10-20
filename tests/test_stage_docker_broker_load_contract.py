"""Bounded metadata refresh, never stale-on-error and no host API writes."""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_docker_api_broker as broker
from stage_apps import AppError


class StageBrokerLoadContract(unittest.TestCase):
    def setUp(self):
        broker._CACHE_ROWS=()
        broker._CACHE_EXPIRES=0

    def tearDown(self):
        broker._CACHE_ROWS=()
        broker._CACHE_EXPIRES=0

    def test_stage_inventory_is_short_lived_and_serialized(self):
        rows=[{"Id":"a"*64,"Labels":{"osd.stage.scope":"staging-only"},
               "State":"running","Names":["/osd-stage-demo"]}]
        with patch.object(broker,"_refresh_stage_containers",return_value=rows) as load:
            first=broker.stage_containers()
            second=broker.stage_containers()
            self.assertEqual(first,second)
            self.assertEqual(load.call_count,1)
            broker.stage_containers(fresh=True)
            self.assertEqual(load.call_count,2)

    def test_expired_broker_cache_does_not_downgrade_unverified_state(self):
        rows=[{"Id":"a"*64}]
        with patch.object(broker,"_refresh_stage_containers",return_value=rows):
            broker.stage_containers()
        broker._CACHE_EXPIRES=0
        with patch.object(broker,"_refresh_stage_containers",
                          side_effect=AppError("stage_inspection_not_ready",503)):
            with self.assertRaises(AppError):
                broker.stage_containers()

    def test_stream_slots_are_bounded(self):
        acquired=[]
        try:
            for _ in range(4):
                self.assertTrue(broker._STATS_SLOTS.acquire(blocking=False))
                acquired.append(1)
            self.assertFalse(broker._STATS_SLOTS.acquire(blocking=False))
        finally:
            for _ in acquired:
                broker._STATS_SLOTS.release()
        self.assertGreaterEqual(broker.MAX_EVENT_SECONDS,60)
        self.assertLessEqual(broker.MAX_EVENT_SECONDS,900)
        self.assertGreaterEqual(broker.MAX_STATS_SECONDS,30)
        self.assertLessEqual(broker.MAX_STATS_SECONDS,300)


if __name__=="__main__":
    unittest.main()
