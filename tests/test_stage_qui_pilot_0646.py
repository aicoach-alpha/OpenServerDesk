"""Only exact Qui/Postgres CasaOS source gets private staging credentials."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_qui_pilot as qui
import stage_store_compiler as compiler
import stage_store_runtime as runtime
from stage_store_general import _find_catalog_definition
from stage_apps import AppError
P="osd-compiled-abcdef123456"
OWNER="a"*32
class QuiPilotTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name)
  self.folder=self.root/P;self.folder.mkdir()
  for m in (patch.object(qui,"ROOT",self.root),
            patch.object(compiler,"STAGE",str(self.root)),
            patch.object(runtime,"ROOT",self.root)):
   m.start();self.addCleanup(m.stop)
 def make(self):
  qui.create(P)
  self.assertRegex(qui.credential(P),r"^[0-9a-f]{48}$")
  raw=compiler.compile_stage(P,qui.APP,host_port=18740)
  runtime._prepare_volumes(P,raw)
  manifest=runtime._manifest(P,qui.APP,OWNER,raw)
  runtime._validate(P,manifest,OWNER)
  return manifest
 def test_exact_stage_only_credentials_compose_network_and_health(self):
  manifest=self.make()
  self.assertEqual(set(manifest["services"]),{"qui","postgres"})
  self.assertTrue(manifest["networks"]["isolated"]["internal"])
  self.assertEqual(manifest["services"]["qui"]["ports"],["127.0.0.1:18740:7476"])
  self.assertEqual(manifest["services"]["qui"]["depends_on"],
                   {"postgres":{"condition":"service_healthy"}})
  env=manifest["services"]["postgres"]["environment"]
  self.assertEqual(env["POSTGRES_PASSWORD"],qui.credential(P))
  self.assertNotIn(env["POSTGRES_PASSWORD"],str(manifest["services"]["qui"]["labels"]))
  self.assertEqual(manifest["services"]["qui"]["environment"]["QUI__DATABASE_ENGINE"],"postgres")
  self.assertEqual(qui.HEALTH,manifest["services"]["postgres"]["healthcheck"])
 def test_credential_file_root_only_and_catalog_drifts_rejected(self):
  self.make()
  self.assertEqual((self.folder/"qui-staging-secret.json").stat().st_mode&0o077,0)
  with self.assertRaises(AppError):qui.create(P)
  _,source=_find_catalog_definition(qui.APP)
  drift=json.loads(json.dumps(source))
  drift["services"]["qui"]["image"]="changed:image"
  self.assertFalse(qui.supported(qui.APP,drift))
 def test_arbitrary_env_or_missing_health_rejected(self):
  manifest=self.make()
  manifest["services"]["postgres"]["environment"]["POSTGRES_USER"]="root"
  with self.assertRaises(AppError):runtime._validate(P,manifest,OWNER)
  manifest=self.make_previous()
  manifest["services"]["postgres"].pop("healthcheck")
  with self.assertRaises(AppError):runtime._validate(P,manifest,OWNER)
 def make_previous(self):
  raw=compiler.compile_stage(P,qui.APP,host_port=18740)
  return runtime._manifest(P,qui.APP,OWNER,raw)
if __name__=="__main__":unittest.main()
