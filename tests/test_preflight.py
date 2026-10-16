import unittest
from unittest.mock import patch
import migration_preflight as m

class MigrationContractTest(unittest.TestCase):
    def test_user_hdd_excluded_from_platform_migration(self):
        self.assertNotIn("/mnt/data",m.PATHS)
    def test_casaos_services_inventory(self):
        self.assertEqual(len(m.SERVICES),6)
    def test_no_mutating_subprocess_invocations(self):
        import inspect
        src=inspect.getsource(m)
        for forbidden in ('systemctl restart','docker compose up','docker rm','apt-get upgrade','rsync --delete'):
            self.assertNotIn(forbidden,src)
    def test_fail_closed_when_no_casaos(self):
        with patch.object(m, 'run', return_value=(1,'')):
            result=m.inspect()
        self.assertFalse(result['eligible_for_migration_planning'])
        self.assertFalse(result['migration_allowed_now'])
if __name__=="__main__":unittest.main()
