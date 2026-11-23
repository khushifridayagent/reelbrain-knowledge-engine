"""Proof that the new-repository export cannot silently include private history."""
import tempfile
import unittest
from pathlib import Path
from tools.prepare_private_repo import review_files, StageError

class PublishGuardTests(unittest.TestCase):
    def test_refuses_private_database(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'fixtures').mkdir()
            (root / 'fixtures' / 'research_seed.db').write_bytes(b'SQLite format 3')
            with self.assertRaises(StageError):
                review_files(root, ['fixtures/research_seed.db'])

    def test_refuses_original_conversations(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'references').mkdir()
            (root / 'references' / 'USER_PASTED_PROCEDURE_ORIGINAL.txt').write_text('private')
            with self.assertRaises(StageError):
                review_files(root, ['references/USER_PASTED_PROCEDURE_ORIGINAL.txt'])

    def test_ignores_dotenv_and_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'reelbrain').mkdir()
            (root / 'reelbrain' / 'main.py').write_text('print("ok")')
            (root / '.env').write_text('API_KEY=secret')
            with self.assertRaises(StageError):
                review_files(root, ['.env'])
            self.assertEqual(['reelbrain/main.py'], review_files(root, ['reelbrain/main.py']))

    def test_refuses_symlink_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'link.py').symlink_to('/etc/passwd')
            with self.assertRaises(StageError):
                review_files(root, ['link.py'])

    def test_rejects_embedded_secret_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'code.py').write_text('GITHUB_TOKEN = "ghp_' + 'a'*36 + '"')
            with self.assertRaises(StageError):
                review_files(root, ['code.py'])
