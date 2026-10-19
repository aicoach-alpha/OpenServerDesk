"""Regression: source and destination have independent bounded quota."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_data as data
P="osd-compiled-abcdef123456"
class RestoreQuotaTests(unittest.TestCase):
 def test_two_six_byte_copies_fit_eight_byte_each_limit(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); stage=root/P;stage.mkdir()
   src=stage/"archived";dst=stage/"live"
   src.mkdir();dst.mkdir()
   (src/"value.txt").write_text("abcdef")
   (dst/"value.txt").write_text("xxxxxx")
   with patch.object(data,"ROOT",root),        patch.object(data,"LIMIT_BYTES",8),        patch.object(data,"_validate_snapshot",return_value=[(src,dst)]),        patch.object(data,"verify_pg_cold",return_value=False):
    checked=data._apply(P,{"services":{}}, "data-aaaaaaaaaaaa")
   self.assertEqual(checked,0)
   self.assertEqual((dst/"value.txt").read_text(),"abcdef")
if __name__=="__main__":unittest.main()
