"""Budget-gated, public Instagram post fallback. No account cookies or raw logs.

Use only the dedicated owner-provided token, on an account whose hard monthly
limit is at most $5. Check live usage before each bounded actor run.
"""
from __future__ import annotations
import math
import os
import httpx
from .sources import canonicalize_instagram
from .public_media import PublicMediaError
from .meta_business_media import MetaSourceAsset,valid_meta_media_url,download_source_assets

KEY='REELBRAIN_POST_APIFY_API_TOKEN'
ROOT='https://api.apify.com/v2'
ACTOR=ROOT+'/acts/apify~instagram-scraper/run-sync-get-dataset-items'
MAX_CHARGE=0.02
SOFT_LIMIT=4.50

def unavailable(reason):
    return PublicMediaError('Public media unavailable: apify_post_'+reason)

def budget_available(payload):
    try:
        data=payload['data']
        used=data['current']['monthlyUsageUsd']
        active=data['current']['activeActorJobCount']
        maximum=data['limits']['maxMonthlyUsageUsd']
        if any(type(v) not in (float,int) or not math.isfinite(v) for v in (used,active,maximum)):return False
        return 0<maximum<=5 and 0<=used and active==0 and used+MAX_CHARGE<=min(SOFT_LIMIT,maximum)
    except (KeyError,TypeError,ValueError,OverflowError):return False

def parse_post_assets(url,items):
    canon=canonicalize_instagram(url)
    if '/p/' not in canon:raise unavailable('post_only')
    if not isinstance(items,list) or len(items)!=1 or not isinstance(items[0],dict):raise unavailable('no_unique_post')
    item=items[0];code=canon.rstrip('/').rsplit('/',1)[-1]
    if item.get('error') or item.get('shortCode')!=code:raise unavailable('identity_mismatch')
    for field in ('url','inputUrl'):
        if item.get(field):
            try:match=canonicalize_instagram(item[field])==canon
            except (ValueError,TypeError,AttributeError):match=False
            if not match:raise unavailable('identity_mismatch')
    if any(item.get(k) is True for k in ('isPrivate','private','ownerIsPrivate')):raise unavailable('source_not_public')
    owner=item.get('owner')
    if isinstance(owner,dict) and any(owner.get(k) is True for k in ('isPrivate','is_private','private')):raise unavailable('source_not_public')
    children=item.get('childPosts')
    if item.get('type')=='Sidecar':
        if not isinstance(children,list) or not 2<=len(children)<=20:raise unavailable('incomplete_carousel')
        for field in ('childPostsCount','childrenCount'):
            if item.get(field) is not None and (type(item[field]) is not int or item[field]!=len(children)):raise unavailable('incomplete_carousel')
        images=item.get('images')
        if images is not None and (not isinstance(images,list) or (images and len(images)!=len(children))):raise unavailable('incomplete_carousel')
        rows=children
    elif item.get('type') in ('Image','Video') and not children:
        rows=[item]
    else:raise unavailable('unknown_or_incomplete_media')
    assets=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('type') not in ('Image','Video') or row.get('error'):raise unavailable('unknown_media_type')
        kind='IMAGE' if row['type']=='Image' else 'VIDEO'
        media=row.get('displayUrl' if kind=='IMAGE' else 'videoUrl')
        if not isinstance(media,str) or not valid_meta_media_url(media) or media in seen:raise unavailable('missing_duplicate_or_untrusted_media')
        seen.add(media);assets.append(MetaSourceAsset(kind,media))
    return tuple(assets)

def acquire_apify_post(url,output_directory,token,*,http=None):
    if not token:raise unavailable('credential_missing')
    canon=canonicalize_instagram(url)
    if '/p/' not in canon:raise unavailable('post_only')
    client=http or httpx.Client(follow_redirects=False,trust_env=False,timeout=190)
    headers={'Authorization':'Bearer '+token,'Accept':'application/json'}
    try:
        try:
            limits=client.get(ROOT+'/users/me/limits',headers=headers,timeout=15,follow_redirects=False)
            if limits.status_code in (401,403):raise unavailable('credential_invalid')
            if limits.status_code!=200 or not budget_available(limits.json()):raise unavailable('credits_exhausted_or_budget_unverified')
            response=client.post(ACTOR,headers=headers,
                params={'timeout':120,'maxItems':1,'maxTotalChargeUsd':MAX_CHARGE,'restartOnError':'false'},
                json={'directUrls':[canon],'resultsType':'posts','resultsLimit':1,'addParentData':False},
                timeout=150,follow_redirects=False)
            if response.status_code in (401,403):raise unavailable('credential_invalid')
            if response.status_code==402:raise unavailable('credits_exhausted')
            if response.status_code==429:raise unavailable('rate_limited')
            if response.status_code!=200 and response.status_code!=201:raise unavailable('actor_unavailable')
            assets=parse_post_assets(canon,response.json())
        except PublicMediaError:raise
        except Exception:raise unavailable('network_or_response_failure') from None
        return download_source_assets(assets,output_directory,provider='apify-public-post')
    finally:
        if http is None:client.close()
