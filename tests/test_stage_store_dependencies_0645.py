"""Focused dependency ordering and health readiness (no Docker mutation)."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_compiler as compiler
import stage_store_runtime as runtime
from stage_apps import AppError
P="osd-compiled-abcdef123456"
OWNER="a"*32

class DependencyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.plan={"name":P,"services":{
            "web":{"depends_on":["db"]},
            "cache":{"depends_on":["db"]},
            "db":{}}}
    def test_reverse_stop_start_and_resume_order(self):
        self.assertEqual(runtime._startup_order(self.plan),["db","cache","web"])
        s={k:{"id":k,"running":True,"depends_on":list(v.get("depends_on",[]))}
           for k,v in self.plan["services"].items()}
        calls=[]
        with patch.object(runtime,"docker",side_effect=lambda *args,**kwargs:calls.append(args)):
            runtime._stop_for_online(s)
        self.assertEqual([args[-1] for args in calls],["web","cache","db"])
        state={k:{**value,"running":False} for k,value in s.items()}
        calls.clear()
        def fake_docker(*args,**kwargs):
            calls.append(args)
            if args[0]=="start":state[args[1]]["running"]=True
        with patch.object(runtime,"_owned",side_effect=lambda *args,**kwargs:state),             patch.object(runtime,"_confirm_ready",return_value={"running":True}),             patch.object(runtime,"docker",side_effect=fake_docker):
            runtime._resume_online(P,self.plan,OWNER,set(state))
        self.assertEqual([args[-1] for args in calls],["db","cache","web"])

    def test_dict_service_healthy_condition_is_retained(self):
        doc={"services":{
            "db":{"image":"local:db"},
            "web":{"image":"local:web","depends_on":{"db":{"condition":"service_healthy"}}}}}
        raw=compiler.analyze(doc,resolver=lambda _: "sha256:"+"a"*64)
        self.assertEqual(raw["startup_order"],["db","web"])
        with patch.object(compiler,"_find_catalog_definition",return_value=({},doc)),             patch.object(compiler,"analyze",return_value=raw):
            config=compiler.compile_stage(P,"local:sample")
        self.assertEqual(config["services"]["web"]["depends_on"],
                         {"db":{"condition":"service_healthy"}})
        self.assertEqual(runtime._startup_order(config),["db","web"])

    def test_missing_healthcheck_fails_closed_and_cycles_rejected(self):
        self.plan["services"]["web"]["depends_on"]={"db":{"condition":"service_healthy"}}
        state={"db":{"running":True,"health":None},"web":{"running":False,"health":None},
               "cache":{"running":False,"health":None}}
        with patch.object(runtime,"_owned",return_value=state):
            with self.assertRaises(AppError) as err:
                runtime._wait_for_dependency(P,self.plan,OWNER,"web")
        self.assertEqual(err.exception.message,"compiled_dependency_healthcheck_missing")
        self.plan["services"]["db"]["depends_on"]=["web"]
        with self.assertRaises(AppError):
            runtime._startup_order(self.plan)

    def test_unhealthy_service_rejected_from_deployment_readiness(self):
        manifest={"name":P,"services":{"db":{},"web":{"depends_on":["db"]}}}
        state={"db":{"running":True,"health":"unhealthy","status":"running"},
               "web":{"running":True,"health":None,"status":"running"}}
        with patch.object(runtime,"_owned",return_value=state),             patch.object(runtime,"_published_port",return_value=None),             patch.object(runtime.time,"monotonic",side_effect=[0,12]):
            with self.assertRaises(AppError) as err:
                runtime._confirm_ready(P,manifest,OWNER)
        self.assertEqual(err.exception.message,"compiled_stage_application_failed_readiness")

if __name__=="__main__":unittest.main()
