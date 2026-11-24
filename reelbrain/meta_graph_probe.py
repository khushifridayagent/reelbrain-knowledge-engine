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


def choose_linked_professional_ig_id(pages:dict, configured_id:str)->str|None:
    """Select only an unambiguous Page-linked IG professional ID.

    A Meta App ID, Facebook Page ID and Instagram Professional ID are
    DIFFERENT numeric values. Never guess among several linked accounts.
    """
    if not isinstance(pages,dict) or not isinstance(pages.get('data'),list):
        return None
    if (pages.get('paging') or {}).get('next'):
        # Pagination not exhausted: cannot safely assume only one.
        return None
    found=set()
    for page in pages['data'][:100]:
        if not isinstance(page,dict):continue
        account=page.get('instagram_business_account')
        ident=account.get('id') if isinstance(account,dict) else None
        if isinstance(ident,str) and _ID_RE.fullmatch(ident):
            found.add(ident)
    if configured_id in found:return configured_id
    if len(found)==1:return next(iter(found))
    return None


def inspect_graph_permissions(token:str,*,http=None)->dict:
    """Return only safe booleans for official Meta Business Discovery scopes.

    No raw Graph error messages, user/page IDs, or access tokens are included.
    """
    required=('instagram_basic','instagram_manage_insights',
              'pages_read_engagement','pages_show_list')
    empty={p:False for p in required}
    if not token:return {'readable':False,**empty}
    import httpx
    client=http or httpx
    try:
        r=client.get(_BASE+'/me/permissions',
          headers={'Authorization':'Bearer '+token,'Accept':'application/json'},
          timeout=10,follow_redirects=False)
        payload=r.json()
        if r.status_code>=400 or not isinstance(payload,dict) or not isinstance(payload.get('data'),list):
            return {'readable':False,**empty}
        granted={v['permission'] for v in payload['data'] if isinstance(v,dict)
                 and isinstance(v.get('permission'),str) and v.get('status')=='granted'}
        return {'readable':True,**{key:key in granted for key in required}}
    except Exception:
        return {'readable':False,**empty}


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
    resolved_from_page=False
    if error=='unsupported_graph_field_or_ig_id':
        # The user may have pasted a Page ID or App ID by mistake.
        # Recover ONLY if /me/accounts identifies exactly one linked IG.
        pages,page_error=request('/me/accounts',{
            'fields':'id,instagram_business_account{id}', 'limit':25
        })
        if page_error:
            return {'status':'linked_page_access_denied' if
                    page_error=='insufficient_graph_permissions' else page_error,
                    'token_valid':True}
        resolved=choose_linked_professional_ig_id(pages,own_ig_id)
        if not resolved:
            entries=pages.get('data',[]) if isinstance(pages,dict) else []
            linked={str(v['instagram_business_account']['id'])
                    for v in entries if isinstance(v,dict)
                    and isinstance(v.get('instagram_business_account'),dict)
                    and _ID_RE.fullmatch(str(v['instagram_business_account'].get('id','')))}
            return {'status':'linked_professional_id_ambiguous_or_missing',
                    'token_valid':True,
                    'visible_facebook_pages':len(entries),
                    'visible_professional_instagram_accounts':len(linked),
                    'page_pagination_incomplete':bool(
                        (pages.get('paging') or {}).get('next'))}
        account,error=request('/'+resolved,{'fields':'id,username'})
        if error:return {'status':error,'token_valid':True}
        own_ig_id=resolved
        resolved_from_page=True
    elif error:
        return {'status':error,'token_valid':True}
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
    if error:return {'status':error,'token_valid':True,'account_id_valid':True,
                     'resolved_from_linked_page':resolved_from_page}
    discovery=data.get('business_discovery') or {}
    if not isinstance(discovery,dict) or (
        str(discovery.get('username','')).lower()!=creator.lower()
    ):
        return {'status':'business_discovery_unavailable',
                'token_valid':True,'account_id_valid':True,
                'resolved_from_linked_page':resolved_from_page}
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
                'token_valid':True,'account_id_valid':True,
                'resolved_from_linked_page':resolved_from_page,
                'matched_media':len(matches),
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
        'resolved_from_linked_page':resolved_from_page,
        'matched_media':len(matches),'original_urls':count,'slide_count':len(children)
    }
