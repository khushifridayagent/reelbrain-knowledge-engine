import os,unittest
from unittest.mock import patch
from reelbrain.durable_worker import checked_config
class WorkerTests(unittest.TestCase):
    def test_rejects_missing_budget_permission_before_any_claim(self):
        with patch.dict(os.environ,{'REELBRAIN_DB_URL':'','APIFY_API_TOKEN':'',
        'REELBRAIN_PAID_PROVIDER_APPROVED':'','REELBRAIN_SOURCE_RIGHTS_CONFIRMED':''}):
            with self.assertRaises(RuntimeError):checked_config()
    def test_consent_flags_and_connection_are_required(self):
        with patch.dict(os.environ,{'REELBRAIN_DB_URL':'postgresql://example:pass@localhost/db',
        'APIFY_API_TOKEN':'fake','REELBRAIN_PAID_PROVIDER_APPROVED':'true','REELBRAIN_SOURCE_RIGHTS_CONFIRMED':'true'}):
            self.assertIn('db_url',checked_config())
if __name__=='__main__':unittest.main()
