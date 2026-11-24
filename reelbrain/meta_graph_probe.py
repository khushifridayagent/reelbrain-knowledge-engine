"""Safe, read-only real Meta Graph token and Business Discovery diagnostics.

Live integration runner prints ONLY bounded categories: never API tokens,
Graph error messages, Instagram account IDs, usernames, or signed CDN URLs.
One burst of at most three API calls, no retries on rate limiting.
"""
from __future__ import annotations
import re
from .meta_business_media import valid_meta_media_url

_ID_RE=re.compile(r'^[0-9]{8,30}$')
_NAME_RE=re.compile(r'^[A-Za-z0-9._]{1,30}$')
_SHORTCODE_RE=re.compile(r'^[A-Za-z0-9_-]{6,30}$')
_BASE='https://graph.facebook.com/v27.0'


def classify_graph_failure(payload:dict)->str:
    error=(payload.get('error') if isinstance(payload,dict) else None) or {}
    if not isinstance(error,dict):return 'unrecognized_meta_error'
    code=error.get('code')
    sub=error.get('error_subcode')
    if code==190:return 'token_expired_or_invalid'
    if code in (4,17,32,613):return 'app_rate_limited'
    if code in (10,200):return 'insufficient_graph_permissions'
    if code==100:return 'unsupported_graph_field_or_ig_id'
    if code in (400,368):return 'meta_account_or_app_blocked'
    return 'meta_graph_error'


def check_meta_business_access(
    token:str,own_ig_id:str,enabled:str,*,creator:str='aimortal.ig',
    shortcode:str='DgGHCjZIZtW',http=None
)->dict:
    if enabled!='1':return {'status':'disabled'}
    if not token:return {'status':'missing_token'}
    if not _ID_RE.fullmatch(own_ig_id or ''):
        return {'status':'invalid_ig_user_id'}
    if not _NAME_RE.fullmatch(creator or '') or not _SHORTCODE_RE.fullmatch(shortcode or ''):
        return {'status':'invalid_source_identity'}
    import httpx
    client=http or httpx
    headers={'Authorization':'Bearer '+token,'Accept':'application/json'}
    def request(path,params):
        try:
            r=client.get(_BASE+path,headers=headers,params=params,timeout=13,
                         follow_redirects=False)
            payload=r.json()
            if not isinstance(payload,dict):return None,'invalid_graph_response'
            if r.status_code>=400 or 'error' in payload:
                return None,classify_graph_failure(payload)
            return payload,None
        except Exception:
            return None,'graph_network_unavailable'
    # Step 1: proof token still works. Persisting an expired token as a
    # GitHub Secret does NOT keep it authenticated for subsequent months.
    me,error=request('/me',{'fields':'id'})
    if error:return {'status':error}
    if not me.get('id'):return {'status':'invalid_graph_response'}
    # Step 2: caller's own (not the App ID or Page ID) professional IG node.
    account,error=request('/'+own_ig_id,{'fields':'id,username'})
    if error:return {'status':error,'token_valid':True}
    if str(account.get('id',''))!=own_ig_id:
        return {'status':'incorrect_professional_ig_id','token_valid':True}
    # Step 3: one public-professional creator and one of the original six
    # Reel shortcodes. Read-only, no downloads at this stage.
    fields=(
        'business_discovery.username('+creator+')'
        '{username,media.limit(50){permalink,media_type,media_url,'
        'children.limit(20){media_type,media_url}}}'
    )
    data,error=request('/'+own_ig_id,{'fields':fields})
    if error:return {'status':error,'token_valid':True,'account_id_valid':True}
    discovery=data.get('business_discovery') or {}
    if not isinstance(discovery,dict) or (
        str(discovery.get('username','')).lower()!=creator.lower()
    ):
        return {'status':'business_discovery_unavailable',
                'token_valid':True,'account_id_valid':True}
    entries=(discovery.get('media') or {}).get('data') or []
    if not isinstance(entries,list):entries=[]
    matches=[]
    for entry in entries:
        if not isinstance(entry,dict):continue
        u=entry.get('permalink')
        if not isinstance(u,str):continue
        try:
            from .sources import canonicalize_instagram
            observed=canonicalize_instagram(u)
        except (TypeError,ValueError):
            continue
        if observed.rstrip('/').rsplit('/',1)[-1]==shortcode:
            matches.append(entry)
    if len(matches)!=1:
        return {'status':'source_not_in_business_discovery',
                'token_valid':True,'account_id_valid':True,'matched_media':len(matches),
                'returned_media':len(entries)}
    record=matches[0]
    children=(record.get('children') or {}).get('data') if record.get('media_type')=='CAROUSEL_ALBUM' else [record]
    if not isinstance(children,list):children=[]
    count=sum(1 for child in children if isinstance(child,dict) and
              valid_meta_media_url(child.get('media_url')))
    return {
        'status':'original_media_url_available' if children and count==len(children)
                    else 'media_found_without_original_url',
        'token_valid':True,'account_id_valid':True,
        'matched_media':len(matches),'original_urls':count,'slide_count':len(children)
    }
