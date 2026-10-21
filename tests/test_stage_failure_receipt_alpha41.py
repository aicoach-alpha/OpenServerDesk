"""Focused failure receipt: allowlisted cause, no raw logs or secrets."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_store_runtime as runtime
from stage_apps import AppError


class FailureReceipt(unittest.TestCase):
    PROJECT="osd-compiled-112233aabbcc"
    CID="a"*64

    def manifest(self):
        return {"name":self.PROJECT,"services":{"app":{
            "labels":{"osd.m1.compiled.app":"default:MySpeed"}}}}

    def test_classified_crash_metadata_does_not_persist_sensitive_logs(self):
        container={"Id":self.CID,
                   "Config":{"Labels":{
                       "com.docker.compose.project":self.PROJECT,
                       "com.docker.compose.service":"app"}},
                   "State":{"Status":"exited","ExitCode":1}}
        mock_process=SimpleNamespace(
            stdout="Traceback KeyError: getpwuid(): uid not found: 1000 SECRET=private_value",
            stderr="")
        with (patch.object(runtime,"_verify_partial",return_value=[self.CID]),
              patch.object(runtime,"docker",return_value=json.dumps([container])),
              patch.object(runtime.subprocess,"run",return_value=mock_process)):
            receipt=runtime._startup_failure_snapshot(
                self.PROJECT,self.manifest(),"a"*32,
                AppError("compiled_stage_application_exited_during_start",503))
        self.assertEqual(receipt["failure_code"],
                         "compiled_stage_application_exited_during_start")
        self.assertEqual(receipt["services"][0]["reason"],
                         "nonroot_uid_not_in_image_passwd")
        self.assertEqual(receipt["services"][0]["exit_code"],1)
        self.assertNotIn("private_value",json.dumps(receipt))
        self.assertNotIn("getpwuid()",json.dumps(receipt))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runtime,"_root",return_value=Path(tmp)):
                runtime._record_startup_failure(receipt,"rolled_back")
                record=runtime._last_startup_failure()
                self.assertEqual(record["cleanup_status"],"rolled_back")
                self.assertEqual(record["services"][0]["exit_code"],1)
                p=Path(tmp)/runtime.LAST_STARTUP_FAILURE.name
                self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_untrusted_container_provenance_yields_no_logs_or_ids(self):
        with (patch.object(runtime,"_verify_partial",
                           side_effect=AppError("foreign_container",403)),
              patch.object(runtime.subprocess,"run") as log):
            receipt=runtime._startup_failure_snapshot(
                self.PROJECT,self.manifest(),"a"*32,
                RuntimeError("password=secret"))
            self.assertEqual(receipt["failure_code"],
                             "unexpected_stage_runtime_error")
            self.assertEqual(receipt["services"],[])
            log.assert_not_called()

    def test_only_allowlisted_error_fingerprints(self):
        self.assertEqual(runtime._failed_stage_reason(
            "unrecognized TOKEN=xyz password"),"unclassified")
        self.assertEqual(runtime._failed_stage_reason(
            "PermissionError: Permission denied"),"stage_runtime_permission_denied")


if __name__=="__main__":
    unittest.main()
