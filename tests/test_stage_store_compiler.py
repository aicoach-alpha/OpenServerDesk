import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_store_compiler import analyze,AppError
ID="sha256:"+"a"*64
def cached(_):return ID
class CompilerTests(unittest.TestCase):
    def test_multi_service_and_cached_images(self):
        spec={"services":{
          "web":{"image":"web:latest","depends_on":["db"],
                 "ports":["80:80"],"environment":{"SECRET":"secret"},
                 "volumes":["/mnt/data/nextcloud:/app/data"]},
          "db":{"image":"db:1","volumes":["/mnt/data:/var/lib/db"]},
        }}
        out=analyze(spec,resolver=cached)
        self.assertEqual(out["startup_order"],["db","web"])
        self.assertEqual(out["volume_count"],2)
        self.assertTrue(out["all_images_cached"])
        self.assertNotIn("/mnt/data",str(out))
        self.assertNotIn("secret",str(out))
    def test_missing_cached_image_fails_ready(self):
        out=analyze({"services":{"web":{"image":"web:latest"}}},resolver=lambda _:None)
        self.assertFalse(out["all_images_cached"])
    def test_cycle_rejected(self):
        with self.assertRaises(AppError):
            analyze({"services":{
              "a":{"image":"a:1","depends_on":["b"]},
              "b":{"image":"b:2","depends_on":["a"]},
            }},resolver=cached)
    def test_protected_target_rejected(self):
        with self.assertRaises(AppError):
            analyze({"services":{"a":{"image":"a:1","volumes":["/mnt/data:/proc"]}}},
                    resolver=cached)
    def test_unknown_dependency_rejected(self):
        with self.assertRaises(AppError):
            analyze({"services":{"a":{"image":"a:1","depends_on":["ghost"]}}},
                    resolver=cached)
if __name__=="__main__":unittest.main()
