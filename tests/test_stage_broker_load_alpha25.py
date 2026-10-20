"""Focused gate: cache does not bypass staging provenance or Docker reader bounds."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_docker_api_broker as facade
import stage_docker_api_stats as metrics
from stage_apps import AppError


class BrokerLoadTests(unittest.TestCase):
    def setUp(self):
        metrics._STATS_CACHE.clear()
        facade._CACHE_ROWS=()
        facade._CACHE_EXPIRES=0.0

    def test_same_stage_id_deduplicates_stats_read(self):
        row={"Id":"a"*64,"Labels":{"osd.stage.scope":"staging-only"},
             "Names":["/stage-a"],"State":"running"}
        with patch.object(metrics,"snapshot",return_value={"usage":1}) as reader:
            first=metrics.cached_snapshot(row)
            second=metrics.cached_snapshot(row)
            self.assertEqual(first,second)
            self.assertEqual(reader.call_count,1)
            self.assertIn(row["Id"],metrics._STATS_CACHE)

    def test_cache_rejects_untrusted_container_identity(self):
        row={"Id":"a"*64,"Labels":{"osd.stage.scope":"staging-only"},
             "Names":["/stage-a"],"State":"running"}
        with patch.object(metrics,"snapshot",return_value={"usage":1}):
            metrics.cached_snapshot(row)
        row["Labels"]["osd.stage.scope"]="production"
        with self.assertRaises(AppError):
            metrics.cached_snapshot(row)

    def test_provenance_refresh_is_bounded_and_deduplicated(self):
        fixture=[{"Id":"b"*64,"State":"running"}]
        with patch.object(facade,"_refresh_stage_containers",return_value=fixture) as source:
            self.assertEqual(facade.stage_containers(),fixture)
            self.assertEqual(facade.stage_containers(),fixture)
            self.assertEqual(source.call_count,1)
            self.assertEqual(facade.stage_containers(fresh=True),fixture)
            self.assertEqual(source.call_count,2)

    def test_heartbeat_stream_and_slots_remain_bounded(self):
        self.assertGreaterEqual(facade.MAX_EVENT_SECONDS,300)
        self.assertLessEqual(facade.EVENT_HEARTBEAT_SECONDS,15)
        self.assertGreaterEqual(facade.MAX_STATS_SECONDS,120)
        self.assertLessEqual(metrics.STATS_TTL_SECONDS,10)
        self.assertLessEqual(metrics.MAX_STATS_CACHE_ITEMS,16)
        self.assertLessEqual(facade.MAX_LOG_BYTES,65536)


if __name__=="__main__":
    unittest.main()
