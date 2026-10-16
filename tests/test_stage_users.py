import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_users as s


class StagingUserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="osd-actor-")
        root=Path(self.tmp.name)/"users"
        root.mkdir(mode=0o700)
        self.root=root
        self.patches=[
            patch.object(s,"ROOT",root),
            patch.object(s,"DATABASE",root/"identities.json"),
            patch.object(s,"LOCK",root/".identities.lock"),
            patch.object(s,"enabled",return_value=True),
        ]
        for item in self.patches:item.start()

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()

    def test_admin_operator_reader_permissions_and_hashed_secrets(self):
        admin=s.create("administrator01","administrator")
        editor=s.create("operator01","operator")
        reader=s.create("reader01","reader")
        self.assertEqual(s.authorize("Bearer "+admin,"admin")["role"],"administrator")
        self.assertEqual(s.authorize("Bearer "+editor,"write")["role"],"operator")
        self.assertEqual(s.authorize("Bearer "+reader,"read")["role"],"reader")
        for token in (editor,reader):
            with self.assertRaises(s.IdentityError):
                s.authorize("Bearer "+token,"admin")
        with self.assertRaises(s.IdentityError):
            s.authorize("Bearer "+reader,"write")
        persisted=(self.root/"identities.json").read_text()
        self.assertNotIn(admin,persisted)
        self.assertNotIn(editor,persisted)
        self.assertNotIn(reader,persisted)
        self.assertEqual((self.root/"identities.json").stat().st_mode & 0o777,0o600)

    def test_disabling_last_admin_forbidden_and_reader_revoked(self):
        admin=s.create("admin01","administrator")
        user=s.create("reader01","reader")
        with self.assertRaises(s.IdentityError):
            s.revoke("admin01")
        s.revoke("reader01")
        with self.assertRaises(s.IdentityError) as context:
            s.authorize("Bearer "+user,"read")
        self.assertEqual(context.exception.status,401)
        self.assertEqual(s.authorize("Bearer "+admin,"write")["role"],"administrator")

    def test_no_default_credential_or_implicit_activation(self):
        with self.assertRaises(s.IdentityError):
            s.authorize("Bearer "+"0"*64,"read")
        with self.assertRaises(s.IdentityError):
            s.create("someone","reader")
        self.assertFalse((self.root/"identities.json").exists())


if __name__=="__main__":
    unittest.main()
