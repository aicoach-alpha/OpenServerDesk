"""Single precise gate: switch version cannot escape the catalog repository."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from stage_apps import AppError
import stage_store_versions as version


class VersionSelectionTests(unittest.TestCase):
    def test_catalog_scope(self):
        self.assertEqual(version.repository("default:MySpeed"),
                         "germannewsmaker/myspeed")
        cached=version.cached_versions("default:MySpeed",
            lambda *a,**kw:"germannewsmaker/myspeed:1.0.8\n"
                          "germannewsmaker/myspeed:latest\n"
                          "other/repo:latest\n"
                          "germannewsmaker/myspeed:<none>\n")
        self.assertEqual(cached,["1.0.8","latest"])

    def test_switch_uses_cached_immutable_digest(self):
        image="sha256:"+"f"*64
        def resolver(ref):
            self.assertEqual(ref,"germannewsmaker/myspeed:1.0.8")
            return image
        self.assertEqual(version.target_image("default:MySpeed","1.0.8",
                                              resolver),image)
        with self.assertRaises(AppError):
            version.target_image("default:MySpeed","../api",resolver)
        with self.assertRaises(AppError):
            version.target_image("default:MySpeed","other/repo:latest",resolver)
        with self.assertRaises(AppError):
            version.target_image("default:MySpeed","evil@sha256:abc",resolver)

    def test_current_tag_resolution(self):
        current="sha256:"+"b"*64
        mapping={"germannewsmaker/myspeed:1.0.8":current,
                 "germannewsmaker/myspeed:latest":"sha256:"+"c"*64}
        matches=version.current_tags("default:MySpeed",current,
                                     ["1.0.8","latest"],mapping.get)
        self.assertEqual(matches,["1.0.8"])
        self.assertEqual(version.current_tags("default:MySpeed",
            "sha256:"+"a"*64,["1.0.8","latest"],mapping.get),[])

    def test_not_cached_rejected(self):
        with self.assertRaises(AppError) as ex:
            version.target_image("default:MySpeed","future123",lambda _:None)
        self.assertEqual(ex.exception.message,"stage_image_version_not_cached")
        with self.assertRaises(AppError) as ex:
            version.target_image("default:MySpeed","latest",
                                 lambda _:"sha256:"+"z"*64)
        self.assertEqual(ex.exception.message,"stage_image_version_not_cached")

    def test_mutations_are_explicit(self):
        from stage_store_runtime import operation
        with self.assertRaises(AppError):
            operation("stop",image_tag="1.0.8")
        with self.assertRaises(AppError):
            operation("switch-version",project="not-a-project")
        # No localhost or production target is accepted.
        with self.assertRaises(AppError):
            operation("switch-version",project="../../production",
                      image_tag="latest")


if __name__=="__main__":
    unittest.main()
