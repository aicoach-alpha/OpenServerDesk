"""One narrow receipt-reader test; fake output uses local Python, not Docker."""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime


class BoundedReceipt(unittest.TestCase):
    CID="a"*64

    def test_huge_untrusted_log_never_exceeds_8192_bytes(self):
        original_spawn=subprocess.Popen
        original_read=os.read
        counters={"bytes":0,"peak":0}
        def disposable_spawn(args,**options):
            self.assertEqual(args,["docker","logs","--tail","24",self.CID])
            return original_spawn([sys.executable,"-c",
                  "import sys;sys.stdout.write("
                  "'KeyError: getpwuid(): uid not found: 1000\\n' "
                  "+'X'*700000);sys.stdout.flush()"],
                  **options)
        def bounded_read(fd,size):
            # subprocess.Popen itself reads its private exec-error pipe
            # before the bounded Docker log reader starts.
            if size>1024:
                return original_read(fd,size)
            chunk=original_read(fd,size)
            counters["bytes"]+=len(chunk)
            counters["peak"]=max(counters["peak"],size)
            self.assertLessEqual(counters["bytes"],8192)
            return chunk
        with (patch.object(runtime.subprocess,"Popen",
                           side_effect=disposable_spawn),
              patch.object(runtime.os,"read",side_effect=bounded_read)):
            reason=runtime._bounded_stage_log_reason(self.CID)
        self.assertEqual(reason,"nonroot_uid_not_in_image_passwd")
        self.assertGreater(counters["bytes"],100)
        self.assertLessEqual(counters["bytes"],8192)

    def test_invalid_stage_id_never_starts_reader(self):
        with patch.object(runtime.subprocess,"Popen") as spawn:
            self.assertEqual(runtime._bounded_stage_log_reason(
                "../../host"),"unclassified")
            spawn.assert_not_called()


if __name__=="__main__":
    unittest.main()
