"""Real metadata parsing fixtures; no Docker, production volumes, or external drives."""
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import casaos_appstore as store
import stage_store_compiler as compiler
from stage_apps import AppError

class FastIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="osd-catalog-fast-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        directory=self.root/"default"/"Demo"
        directory.mkdir(parents=True)
        self.path=directory/"docker-compose.yml"
        self.path.write_text("name: demo\\nservices:\\n  web:\\n    image: demo:1\\nx-casaos:\\n  id: demo\\n  title: Demo\\n".replace("\\n","\n"))
        self.public,self.paths=store._index(self.root,with_paths=True)

    def test_lookup_does_not_rescan_catalogue(self):
        with patch.object(store,"STORE_ROOT",self.root), \
             patch.object(store,"catalog",return_value=self.public), \
             patch.dict(store._state,{"paths":self.paths}), \
             patch.object(store,"_source_files",side_effect=AssertionError("rescan")):
            known,path=store.indexed_definition("default:demo")
            self.assertEqual(known["title"],"Demo")
            self.assertEqual(path,self.path)

    def test_modified_metadata_fails_closed(self):
        self.path.write_text(self.path.read_text()+"\n# changed\n")
        with patch.object(store,"STORE_ROOT",self.root), \
             patch.object(store,"catalog",return_value=self.public), \
             patch.dict(store._state,{"paths":self.paths}):
            with self.assertRaises(ValueError):
                store.indexed_definition("default:demo")

    def test_symlink_replacement_fails_closed(self):
        self.path.unlink()
        self.path.symlink_to(self.root/"default")
        with patch.object(store,"STORE_ROOT",self.root), \
             patch.object(store,"catalog",return_value=self.public), \
             patch.dict(store._state,{"paths":self.paths}):
            with self.assertRaises(ValueError):
                store.indexed_definition("default:demo")

    def test_private_paths_never_in_public_api(self):
        self.assertNotIn(str(self.root),str(self.public))
        self.assertNotIn("paths",self.public)

class ImagePreparationTests(unittest.TestCase):
    def test_cached_images_do_not_trigger_pull(self):
        with patch.object(compiler,"_find_catalog_definition",return_value=({},{})), \
             patch.object(compiler,"analyze",return_value={"services":[
                 {"name":"web","image":"demo:1","immutable_image":"sha256:"+"a"*64}]}), \
             patch.object(compiler.subprocess,"run",side_effect=AssertionError("docker pull")):
            result=compiler.prepare_images("default:demo")
        self.assertEqual(result["operation"],"already_cached")
        self.assertFalse(result["production_mutation_allowed"])

    def test_disk_gate_blocks_download(self):
        from collections import namedtuple
        Usage=namedtuple("Usage","total used free")
        with patch.object(compiler,"_find_catalog_definition",return_value=({},{})), \
             patch.object(compiler,"analyze",return_value={"services":[
                 {"name":"web","image":"demo:1","immutable_image":None}]}), \
             patch.object(compiler.shutil,"disk_usage",return_value=Usage(1,1,0)), \
             patch.object(compiler.subprocess,"run",side_effect=AssertionError("Docker accessed")):
            with self.assertRaises(AppError):
                compiler.prepare_images("default:demo")

if __name__=="__main__": unittest.main()
