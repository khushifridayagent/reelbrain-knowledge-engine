"""Strict Cloudflare Workers AI Qwen visual inference endpoint configuration.

Only config, no network/model calls. Existing QwenVLResearcher performs
actual frame sampling when original media is available. This does not
retrieve media from Instagram or constitute audio transcription.
"""
from __future__ import annotations
import os
import re

_ACCOUNT_RE=re.compile(r'^[a-fA-F0-9]{32}$')


def cloudflare_qwen_config()->dict|None:
    if os.getenv('REELBRAIN_CLOUDFLARE_VISION_ENABLED')!='1':
        return None
    if os.getenv('REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED')!='1':
        return None
    account=os.getenv('CLOUDFLARE_ACCOUNT_ID','')
    key=os.getenv('CLOUDFLARE_AI_API_TOKEN','')
    if not account or not key:
        return None
    if not _ACCOUNT_RE.fullmatch(account):
        raise ValueError('Invalid Cloudflare account identifier')
    return {
        'base_url':'https://api.cloudflare.com/client/v4/accounts/'+account.lower()+'/ai/v1',
        'model':'@cf/qwen/qwen3.8-27b',
        'api_key':key
    }
