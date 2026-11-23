"""CLI explicitly refuses paid/provider calls unless user flags are given."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from reelbrain.cli import run

URL='https://www.instagram.com/reel/Abc321/'
class LinkCliTests(unittest.TestCase):
 def test_process_link_requires_three_consents_before_token_lookup(self):
  with tempfile.TemporaryDirectory() as td:
   with patch.dict('os.environ',{'APIFY_API_TOKEN':'fake-not-used'}), patch('reelbrain.acquire_apify.ApifyReelClient') as actor:
    for flags in [[],['--allow-paid'],['--allow-paid','--allow-external']]:
     with self.assertRaises(PermissionError):
      run(['--db',str(Path(td)/'db.sqlite'),'process-link',URL,*flags])
    actor.assert_not_called()
 def test_media_worker_and_local_search_modes_remain(self):
  with tempfile.TemporaryDirectory() as td:
   self.assertEqual(run(['--db',str(Path(td)/'db.sqlite'),'fast-find','onyx']),0)
