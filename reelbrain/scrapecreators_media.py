"""Optional public-media API, separate from the working spoken transcript provider.

Only user-approved, publicly available sources. No account cookies, paid top-ups,
permanent vendor media storage, or raw URLs/credentials in error logs.
"""
from __future__ import annotations

import os
import httpx
from .sources import canonicalize_instagram
from .public_media import PublicMediaError
from .meta_business_media import (
    MetaSourceAsset, valid_meta_media_url, download_source_assets,
)

API='https://api.scrapecreators.com/v1/instagram/post'
KEY='REELBRAIN_MEDIA_SCRAPECREATORS_API_KEY'
ENABLE='REELBRAIN_MEDIA_SCRAPECREATORS_ENABLED'

def unavailable(reason:str)->PublicMediaError:
    return PublicMediaError('Public media unavailable: scrapecreators_'+reason)

def media_provider_enabled()->bool:
    return os.getenv(ENABLE)=='1' and bool(os.getenv(KEY,''))

def parse_public_assets(url:str,payload:dict)->tuple[MetaSourceAsset,...]:
    canon=canonicalize_instagram(url)
    code=canon.rstrip('/').rsplit('/',1)[-1]
    data=payload.get('data') if isinstance(payload,dict) and payload.get('success') is True else None
    node=data.get('xdt_shortcode_media') if isinstance(data,dict) else None
    if not isinstance(node,dict) or node.get('shortcode')!=code:
        raise unavailable('source_identity_mismatch')
    owner=node.get('owner')
    if node.get('is_private') is True or (isinstance(owner,dict) and owner.get('is_private') is True):
        raise unavailable('source_not_public')
    side=node.get('edge_sidecar_to_children')
    if isinstance(side,dict) or node.get('__typename') in ('XDTGraphSidecar','GraphSidecar'):
        if not isinstance(side,dict) or not isinstance(side.get('edges'),list):
            raise unavailable('incomplete_carousel')
        edges=side['edges']
        count=side.get('count')
        if not 1<=len(edges)<=20 or (count is not None and count!=len(edges)) or (side.get('page_info') or {}).get('has_next_page'):
            raise unavailable('incomplete_carousel')
        rows=[edge.get('node') if isinstance(edge,dict) else None for edge in edges]
    else:
        rows=[node]
    if ('/reel/' in canon or '/tv/' in canon) and (len(rows)!=1 or rows[0] is None or rows[0].get('is_video') is not True):
        raise unavailable('reel_original_video_missing')
    assets=[]
    for row in rows:
        if not isinstance(row,dict) or type(row.get('is_video')) is not bool:
            raise unavailable('unknown_media_type')
        kind='VIDEO' if row['is_video'] else 'IMAGE'
        media_url=row.get('video_url' if row['is_video'] else 'display_url')
        if not valid_meta_media_url(media_url):
            raise unavailable('missing_or_untrusted_media_url')
        assets.append(MetaSourceAsset(kind,media_url))
    return tuple(assets)

def acquire_scrapecreators_bundle(url,output_directory,api_key,*,http=None):
    if not api_key:
        raise unavailable('credential_missing')
    canonical=canonicalize_instagram(url)
    client=http or httpx.Client(timeout=35,follow_redirects=False,trust_env=False)
    try:
        try:
            response=client.get(API,params={'url':canonical,'download_media':'false'},
                                headers={'x-api-key':api_key,'Accept':'application/json'},
                                timeout=35,follow_redirects=False)
            code=response.status_code
            if code==402:raise unavailable('credits_exhausted')
            if code==429:raise unavailable('rate_limited')
            if code==401:raise unavailable('credential_invalid')
            if code==403:raise unavailable('http_forbidden')
            if code==404:raise unavailable('source_unavailable')
            if code!=200:raise unavailable('provider_failure')
            payload=response.json()
        except PublicMediaError:raise
        except Exception:
            raise unavailable('provider_network_or_json_failure') from None
        assets=parse_public_assets(canonical,payload)
        return download_source_assets(assets,output_directory,provider='scrapecreators-public-media')
    finally:
        if http is None:client.close()

def acquire_with_public_provider(url,output_directory,pg,*,cookies_file=None):
    """Existing path stays primary; optional fallback costs at most one post call."""
    from .meta_business_media import acquire_with_meta_fallback
    try:
        return acquire_with_meta_fallback(url,output_directory,pg,cookies_file=cookies_file)
    except PublicMediaError:
        if not media_provider_enabled():
            raise
    return acquire_scrapecreators_bundle(url,output_directory,os.environ[KEY])
