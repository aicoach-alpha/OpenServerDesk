import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import host_status as status


class HostStatusScopeTests(unittest.TestCase):
    def test_real_linux_readonly_report_does_not_touch_external_hdd(self):
        touched=[]
        real=status.os.statvfs
        def scoped(path):
            assert str(path) in ("/","/mnt/ssd-turbo")
            touched.append(str(path))
            return real(path)
        with patch.object(status.os,"statvfs",side_effect=scoped):
            report=status.status()
        self.assertEqual(set(touched),{"/","/mnt/ssd-turbo"})
        self.assertFalse(report["external_user_data_disks_inspected"])
        self.assertFalse(report["migration_allowed"])
        self.assertGreaterEqual(report["cpu_logical_cores"],1)
        self.assertGreater(report["memory"]["total_bytes"],0)
        self.assertEqual(report["scope"],"nas_root_and_ssd_only")

    def test_hdd_path_denied_even_if_directly_supplied(self):
        with self.assertRaises(status.HostStatusError):
            status._disk(Path("/mnt/data"))

if __name__=="__main__":
    unittest.main()
