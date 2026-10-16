import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import docker_metrics as m


class DockerMetricsTests(unittest.TestCase):
    def setUp(self):
        self.a="a"*12
        self.inventory={
            "container_count":1,
            "containers":[{"id":self.a,"name":"not_public","state":"running"}],
        }
        self.good=json.dumps({
            "ID":self.a,"CPUPerc":"13.01%","MemUsage":"25.5MiB / 5GiB",
            "MemPerc":"0.50%","PIDs":"3","Name":"SECRETNAME",
            "BlockIO":"1234B / 3456B",
            "NetIO":"0B / 0B",
        })
    def test_clean_counters_only(self):
        with patch.object(m,"inventory",return_value=self.inventory), \
             patch.object(m,"_run",return_value=self.good):
            result=m.metrics()
        self.assertEqual(result["container_count"],1)
        self.assertEqual(result["containers"][0]["memory_used_bytes"],26738688)
        self.assertEqual(result["containers"][0]["cpu_percent"],13.01)
        self.assertEqual(set(result["containers"][0]),m.PUBLIC_FIELDS)
        self.assertNotIn("SECRETNAME",str(result))
        self.assertFalse(result["external_user_data_inspected"])

    def test_unknown_container_denied(self):
        line=self.good.replace(self.a,"b"*12)
        with patch.object(m,"inventory",return_value=self.inventory), \
             patch.object(m,"_run",return_value=line):
            with self.assertRaises(m.MetricsUnavailable):
                m.metrics()

    def test_extra_rows_denied(self):
        with patch.object(m,"inventory",return_value=self.inventory), \
             patch.object(m,"_run",return_value=self.good+"\n"+self.good):
            with self.assertRaises(m.MetricsUnavailable):
                m.metrics()

    def test_no_logs_or_read_file_commands(self):
        self.assertEqual(m.STATS_COMMAND,
            ("docker","stats","--all","--no-stream","--format","{{json .}}"))

    def test_weird_values_fail_closed(self):
        for bad in ("nan%","Infinity%","-2%","1000000%","abc","--"):
            with self.subTest(bad=bad):
                with self.assertRaises(m.MetricsUnavailable):
                    m._percentage(bad)
        for bad in ("/mnt/data","-1GiB","nanMiB"):
            with self.subTest(bad=bad):
                with self.assertRaises(m.MetricsUnavailable):
                    m._size(bad)

if __name__=="__main__":
    unittest.main()
