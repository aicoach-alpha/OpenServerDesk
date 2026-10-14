import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import migrate_installer as m
class TestInstaller(unittest.TestCase):
    def test_missing_backup_fail_closed(self):
        with patch.object(m.preflight,"inspect",return_value={"checks":{"casaos_present":True},"casaos_version":"v0.4.15"}):
            result=m.gate(Path("/nonexistent/casaos.tar.gz"))
        self.assertIn("backup_missing",result["failures"])
        self.assertFalse(result["safe_to_activate"])
    def test_no_candidate_always_blocked(self):
        with patch.object(m.preflight,"inspect",return_value={"checks":{"casaos_present":True},"casaos_version":"v0.4.15"}):
            result=m.gate(Path("/nonexistent/casaos.tar.gz"))
        self.assertIn("signed_candidate_not_provided",result["failures"])
        self.assertFalse(result["activation_implemented"])
    def test_no_mutating_host_commands(self):
        src=Path(m.__file__).read_text()
        for forbidden in ("dpkg -i","apt install","systemctl stop","docker stop","rm -rf"):
            self.assertNotIn(forbidden,src)
if __name__=="__main__":unittest.main()
