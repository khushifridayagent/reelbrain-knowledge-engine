"""Private local knowledge files cannot silently redirect to unrelated projects."""
import os
import stat
import tempfile
import unittest
from pathlib import Path
from reelbrain.store import KnowledgeStore

class LocalDbPrivacyTests(unittest.TestCase):
    def test_new_db_permissions_private(self):
        if os.name == 'nt':self.skipTest('POSIX-only mode bits')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'new'/'secret.sqlite'
            db=KnowledgeStore(p)
            db.close()
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(p.parent.stat().st_mode),0o700)
    def test_refuses_symlink_to_existing_database(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'unrelated.sqlite'
            target.write_bytes(b'DO NOT MODIFY THIS FILE')
            link=Path(temp)/'link.sqlite'
            link.symlink_to(target)
            with self.assertRaises(ValueError): KnowledgeStore(link)
            self.assertEqual(target.read_bytes(),b'DO NOT MODIFY THIS FILE')
if __name__=='__main__':unittest.main()
