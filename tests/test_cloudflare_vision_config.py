"""Cloudflare Workers AI Qwen Vision is a hosted inference backend, not a GPU VM."""
import unittest
from unittest.mock import patch
from reelbrain.cloudflare_vision_config import cloudflare_qwen_config


class CloudflareQwenTests(unittest.TestCase):
    def test_strictly_disabled_by_default(self):
        with patch.dict('os.environ',{
            'REELBRAIN_CLOUDFLARE_VISION_ENABLED':'0',
            'REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED':'1',
            'CLOUDFLARE_AI_API_TOKEN':'fixture',
            'CLOUDFLARE_ACCOUNT_ID':'0123456789abcdef0123456789abcdef'
        },clear=True):
            self.assertIsNone(cloudflare_qwen_config())

    def test_requires_explicit_external_upload_approval(self):
        with patch.dict('os.environ',{
            'REELBRAIN_CLOUDFLARE_VISION_ENABLED':'1',
            'REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED':'0',
            'CLOUDFLARE_AI_API_TOKEN':'fixture',
            'CLOUDFLARE_ACCOUNT_ID':'0123456789abcdef0123456789abcdef'
        },clear=True):
            self.assertIsNone(cloudflare_qwen_config())

    def test_uses_official_openai_compatible_endpoint_and_hosted_vision_model(self):
        with patch.dict('os.environ',{
            'REELBRAIN_CLOUDFLARE_VISION_ENABLED':'1',
            'REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED':'1',
            'CLOUDFLARE_AI_API_TOKEN':'fixture',
            'CLOUDFLARE_ACCOUNT_ID':'0123456789abcdef0123456789abcdef'
        },clear=True):
            config=cloudflare_qwen_config()
            self.assertEqual(config['base_url'],
              'https://api.cloudflare.com/client/v4/accounts/0123456789abcdef0123456789abcdef/ai/v1')
            self.assertEqual(config['model'],'@cf/qwen/qwen3.8-27b')
            self.assertEqual(config['api_key'],'fixture')

    def test_rejects_malformed_account_id(self):
        with patch.dict('os.environ',{
            'REELBRAIN_CLOUDFLARE_VISION_ENABLED':'1',
            'REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED':'1',
            'CLOUDFLARE_AI_API_TOKEN':'fixture',
            'CLOUDFLARE_ACCOUNT_ID':'some/path/traversal'
        },clear=True):
            with self.assertRaises(ValueError):
                cloudflare_qwen_config()

if __name__=='__main__':unittest.main()
