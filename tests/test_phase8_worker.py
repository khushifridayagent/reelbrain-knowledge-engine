import os,unittest
from unittest.mock import patch
from reelbrain.durable_worker import checked_config
class WorkerTests(unittest.TestCase):
    def test_rejects_missing_budget_permission_before_any_claim(self):
        with patch.dict(os.environ,{'REELBRAIN_DB_URL':'','APIFY_API_TOKEN':'',
        'REELBRAIN_PAID_PROVIDER_APPROVED':'','REELBRAIN_SOURCE_RIGHTS_CONFIRMED':''}):
            with self.assertRaises(RuntimeError):checked_config()
    def test_consent_flags_and_connection_are_required(self):
        with patch.dict(os.environ,{'REELBRAIN_DB_URL':'postgresql://postgres.xlkdzrhzizuftbnitodr:placeholder@aws-0-ap-south-1.pooler.supabase.com:5432/postgres',
        'APIFY_API_TOKEN':'fake','REELBRAIN_PAID_PROVIDER_APPROVED':'true','REELBRAIN_SOURCE_RIGHTS_CONFIRMED':'true','REELBRAIN_MEDIA_ACQUISITION':'apify'}):
            self.assertIn('db_url',checked_config())

    def test_public_personal_knowledge_access_works_without_false_copyright_ownership_claim(self):
        # Owner authorizes only personal analysis of accessible public Reels.
        # This is NOT a claim that third-party copyright has been transferred.
        with patch.dict(os.environ,{
                'REELBRAIN_DB_URL':'postgresql://postgres.xlkdzrhzizuftbnitodr:placeholder@aws-0-ap-south-1.pooler.supabase.com:5432/postgres',
                'REELBRAIN_MEDIA_ACQUISITION':'yt_dlp_public',
                'REELBRAIN_PERSONAL_KNOWLEDGE_USE_APPROVED':'1',
                'REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD':'1',
                'REELBRAIN_SOURCE_RIGHTS_CONFIRMED':'',
                'APIFY_API_TOKEN':'',
                'REELBRAIN_PAID_PROVIDER_APPROVED':''},clear=True):
            cfg=checked_config()
            self.assertEqual(cfg['acquisition'],'yt_dlp_public')
            self.assertFalse(cfg['apify_token'])

    def test_personal_public_knowledge_approval_does_not_unlock_paid_apify_or_private_media(self):
        with patch.dict(os.environ,{
                'REELBRAIN_DB_URL':'postgresql://postgres.xlkdzrhzizuftbnitodr:placeholder@aws-0-ap-south-1.pooler.supabase.com:5432/postgres',
                'REELBRAIN_MEDIA_ACQUISITION':'apify',
                'REELBRAIN_PERSONAL_KNOWLEDGE_USE_APPROVED':'1',
                'REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD':'1',
                'REELBRAIN_PAID_PROVIDER_APPROVED':'1',
                'APIFY_API_TOKEN':'synthetic-apify',
                'REELBRAIN_SOURCE_RIGHTS_CONFIRMED':''},clear=True):
            with self.assertRaises(RuntimeError):
                checked_config()

    def test_public_mode_rejects_missing_explicit_personal_analysis_consent(self):
        with patch.dict(os.environ,{
                'REELBRAIN_DB_URL':'postgresql://postgres.xlkdzrhzizuftbnitodr:placeholder@aws-0-ap-south-1.pooler.supabase.com:5432/postgres',
                'REELBRAIN_MEDIA_ACQUISITION':'yt_dlp_public',
                'REELBRAIN_PERSONAL_KNOWLEDGE_USE_APPROVED':'',
                'REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD':'1',
                'REELBRAIN_SOURCE_RIGHTS_CONFIRMED':''},clear=True):
            with self.assertRaises(RuntimeError):
                checked_config()


    def test_rejects_database_url_to_a_different_project_before_any_job_claim(self):
        with patch.dict(os.environ,{
                'REELBRAIN_DB_URL':'postgresql://postgres.anotherproject:example@aws-0-ap-south-1.pooler.supabase.com:5432/postgres',
                'REELBRAIN_MEDIA_ACQUISITION':'yt_dlp_public',
                'REELBRAIN_PERSONAL_KNOWLEDGE_USE_APPROVED':'1',
                'REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD':'1'},clear=True):
            with self.assertRaises(RuntimeError):
                checked_config()

if __name__=='__main__':unittest.main()
