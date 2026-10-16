"""Exact-catalogue egress pilot; all other apps remain internal-only."""
import sys,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_compiler as compiler
import stage_store_runtime as runtime
from stage_apps import AppError

PROJECT="osd-compiled-abcdef123456"
OWNER="b"*32
IMAGE="sha256:"+"a"*64

def source(image="germannewsmaker/myspeed:1.0.8",mode="bridge"):
    return {"services":{"myspeed":{"image":image,"network_mode":mode,
           "ports":[{"target":5216,"published":"5216","protocol":"tcp"}],
           "volumes":["./myspeed:/myspeed/data"]}}}

def generate(app_id="default:MySpeed",document=None):
    doc=source() if document is None else document
    real=compiler.analyze
    with patch.object(compiler,"_find_catalog_definition",return_value=({},doc)),\
         patch.object(compiler,"analyze",side_effect=lambda d:real(d,resolver=lambda _:IMAGE)):
        return compiler.compile_stage(PROJECT,app_id,host_port=18740)

class OutboundPolicy(unittest.TestCase):
    def test_only_exact_myspeed_108_may_use_outbound(self):
        plan=generate()
        self.assertEqual(plan["networks"],{"egress":{"driver":"bridge","internal":False}})
        self.assertEqual(plan["services"]["myspeed"]["networks"],["egress"])
        self.assertEqual(plan["services"]["myspeed"]["ports"],["127.0.0.1:18740:5216"])
        self.assertNotIn("./myspeed",str(plan))
        self.assertEqual(generate("default:MySpeed-new")["networks"],
                         {"isolated":{"internal":True}})
        self.assertEqual(generate(document=source("germannewsmaker/myspeed:1.0.9"))["networks"],
                         {"isolated":{"internal":True}})
        self.assertEqual(generate(document=source(mode="none"))["networks"],
                         {"isolated":{"internal":True}})

    def test_runtime_rejects_other_app_in_egress_manifest(self):
        doc=source()
        doc["services"]["myspeed"]["volumes"]=[]
        p=generate(document=doc)
        p["services"]["myspeed"]["labels"]["osd.m1.compiled.owner"]=OWNER
        with patch.object(runtime,"_folder",return_value=Path("/tmp")):
            runtime._validate(PROJECT,p,OWNER)
            p["services"]["myspeed"]["labels"]["osd.m1.compiled.app"]="foreign:app"
            with self.assertRaises(AppError):
                runtime._validate(PROJECT,p,OWNER)

    def test_exact_network_provenance_blocks_relabelled_bridge(self):
        p=generate()
        spec=p["services"]["myspeed"]
        host={"NetworkMode":PROJECT+"_egress","PortBindings":
            {"5216/tcp":[{"HostIp":"127.0.0.1","HostPort":"18740"}]}}
        info=[{"Name":PROJECT+"_egress","Internal":False,"Driver":"bridge",
               "Labels":{"com.docker.compose.project":PROJECT,
                         "com.docker.compose.network":"egress"}}]
        with patch.object(runtime,"docker",side_effect=lambda *args,**kwargs:json.dumps(info)):
            runtime._network_check(PROJECT,p,spec,host,{})
            info[0]["Internal"]=True
            with self.assertRaises(AppError):
                runtime._network_check(PROJECT,p,spec,host,{})

if __name__=="__main__":unittest.main()
