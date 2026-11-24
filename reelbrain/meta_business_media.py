"""Official Meta Business Discovery fallback for OTHER public professional creators.

This is NOT an arbitrary IG URL extractor. It requires the owner's own
professional IG user ID, a correctly scoped Graph access token, App Review
where applicable, a PUBLIC professional creator handle, and media_url being
returned by Meta. Meta may intentionally OMIT media_url for copyrighted
audio, download restrictions or unavailable media; never guess those URLs.

All network calls are read-only. No password/session-cookie extraction,
no Graph publishing, no raw CDN URLs in logs, no persistent original MP4.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os,re,tempfile
from urllib.parse import urlsplit
from .public_bundle import PublicBundle,_valid_asset
from .public_media import PublicMediaError
from .sources import canonicalize_instagram


class MetaMediaUnavailable(PublicMediaError):
    pass


@dataclass(frozen=True)
class MetaSourceAsset:
    media_type:str
    media_url:str


_CREATOR_RE=re.compile(r'^[A-Za-z0-9._]{1,30}$')
_ID_RE=re.compile(r'^[0-9]{8,30}$')


def valid_meta_media_url(url:str)->bool:
    if not isinstance(url,str) or len(url)>4096:return False
    try:
        p=urlsplit(url)
        host=(p.hostname or '').lower()
        return (p.scheme=='https' and not p.username and not p.password
            and p.port in (None,443) and not p.fragment
            and (host=='fbcdn.net' or host.endswith('.fbcdn.net')
                 or host=='cdninstagram.com' or host.endswith('.cdninstagram.com')))
    except ValueError:return False


def meta_fallback_enabled()->bool:
    return (os.getenv('REELBRAIN_META_BUSINESS_DISCOVERY_ENABLED')=='1'
            and bool(os.getenv('REELBRAIN_META_GRAPH_TOKEN'))
            and bool(_ID_RE.fullmatch(os.getenv('REELBRAIN_META_IG_USER_ID',''))))


class MetaBusinessDiscovery:
    GRAPH='https://graph.facebook.com/v27.0'

    def __init__(self,token:str,own_ig_user_id:str,*,http=None):
        if not token or not _ID_RE.fullmatch(str(own_ig_user_id)):
            raise MetaMediaUnavailable('Public media unavailable: Meta Graph token or IG user ID missing')
        self.token=token
        self.own_id=own_ig_user_id
        self.http=http

    def find(self,url:str,creator_username:str)->tuple[MetaSourceAsset,...]:
        if not isinstance(creator_username,str):
            raise MetaMediaUnavailable('Public media unavailable: creator handle missing')
        creator=creator_username.lstrip('@')
        if not _CREATOR_RE.fullmatch(creator):
            raise MetaMediaUnavailable('Public media unavailable: invalid creator handle')
        canonical=canonicalize_instagram(url)
        target_code=canonical.rstrip('/').rsplit('/',1)[-1]
        fields=(
            'business_discovery.username('+creator+')'
            '{username,media.limit(50){id,permalink,media_type,media_url,'
            'children.limit(20){id,media_type,media_url}}}'
        )
        import httpx
        http=self.http or httpx
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/json'}
        def read_graph(path,parameters):
            try:
                response=http.get(self.GRAPH+path,params=parameters,
                    headers=headers,timeout=24,follow_redirects=False)
                payload=response.json()
                if not isinstance(payload,dict):
                    raise MetaMediaUnavailable('Public media unavailable: malformed Meta Graph reply')
                return payload
            except MetaMediaUnavailable:raise
            except Exception:
                # Raw URL, token and Graph error body must never enter logs.
                raise MetaMediaUnavailable('Public media unavailable: Meta Graph read failed') from None
        payload=read_graph('/'+self.own_id,{'fields':fields})
        error=payload.get('error')
        if isinstance(error,dict) and error.get('code')==100:
            # Meta App ID / Facebook Page ID are not the numeric
            # professional IG user ID. Resolve *only* a single linked IG
            # through official /me/accounts; never guess among multiple Pages.
            from .meta_graph_probe import choose_linked_professional_ig_id
            pages=read_graph('/me/accounts',{
                'fields':'id,instagram_business_account{id}','limit':25})
            selected=choose_linked_professional_ig_id(pages,self.own_id)
            if not selected:
                raise MetaMediaUnavailable(
                    'Public media unavailable: linked professional Instagram account missing or ambiguous')
            payload=read_graph('/'+selected,{'fields':fields})
        if not isinstance(payload,dict) or 'error' in payload:
            raise MetaMediaUnavailable('Public media unavailable: Meta Graph permission/response failure')
        profile=payload.get('business_discovery') or {}
        if not isinstance(profile,dict) or str(profile.get('username','')).lower()!=creator.lower():
            raise MetaMediaUnavailable('Public media unavailable: creator account not accessible')
        feed=profile.get('media') or {}
        rows=feed.get('data') if isinstance(feed,dict) else None
        if not isinstance(rows,list):
            raise MetaMediaUnavailable('Public media unavailable: professional account media list missing')
        matched=[]
        for item in rows[:50]:
            if not isinstance(item,dict) or not item.get('permalink'):continue
            try:observed=canonicalize_instagram(item['permalink'])
            except Exception:continue
            if observed.rstrip('/').rsplit('/',1)[-1]==target_code:
                matched.append(item)
        if len(matched)!=1:
            raise MetaMediaUnavailable('Public media unavailable: target Reel not in business discovery results')
        record=matched[0]
        entries=record.get('children',{}).get('data') if record.get('media_type')=='CAROUSEL_ALBUM' and isinstance(record.get('children'),dict) else [record]
        if (not isinstance(entries,list) or not 1<=len(entries)<=20):
            raise MetaMediaUnavailable('Public media unavailable: complete carousel pages not returned')
        assets=[]
        for child in entries:
            if not isinstance(child,dict):raise MetaMediaUnavailable('Public media unavailable: malformed media child')
            kind=child.get('media_type')
            media_url=child.get('media_url')
            if kind not in ('VIDEO','IMAGE') or not valid_meta_media_url(media_url):
                # Meta deliberately omits media_url on licensed-audio /
                # download-disabled Reels. Never substitute the cover frame.
                raise MetaMediaUnavailable('Public media unavailable: Meta restricted original video/photo URL')
            assets.append(MetaSourceAsset(kind,media_url))
        return tuple(assets)


def acquire_meta_bundle(
    url:str,creator_username:str,token:str,own_ig_user_id:str,
    output_directory:Path|str,*,lookup_http=None,download_http=None,
    max_total_bytes:int=300*1024*1024,
)->PublicBundle:
    """Acquire bounded, original Meta-provided source bytes, 1–20 pages."""
    from .public_bundle import PublicBundle
    root=Path(output_directory)
    if root.is_symlink() or not root.is_dir() or not 1024<=max_total_bytes<=300*1024*1024:
        raise MetaMediaUnavailable('Public media unavailable: invalid temporary target/budget')
    assets=MetaBusinessDiscovery(token,own_ig_user_id,http=lookup_http).find(url,creator_username)
    import httpx
    http=download_http or httpx.Client(follow_redirects=False,trust_env=False,timeout=55)
    paths=[];total=0
    try:
        for i,asset in enumerate(assets,1):
            path=root/f'page_{i:02}.{"mp4" if asset.media_type=="VIDEO" else "jpg"}'
            if path.exists() or path.is_symlink():
                raise MetaMediaUnavailable('Public media unavailable: destination collision')
            try:
                with http.stream('GET',asset.media_url,follow_redirects=False,timeout=55) as response:
                    if response.status_code!=200:
                        raise MetaMediaUnavailable('Public media unavailable: Meta CDN HTTP failure')
                    header_len=response.headers.get('content-length','')
                    if header_len.isdigit() and int(header_len)+total>max_total_bytes:
                        raise MetaMediaUnavailable('Public media unavailable: Meta source over size budget')
                    with path.open('xb') as out:
                        for chunk in response.iter_bytes(chunk_size=1<<20):
                            total+=len(chunk)
                            if total>max_total_bytes:
                                raise MetaMediaUnavailable('Public media unavailable: Meta source over size budget')
                            out.write(chunk)
            except MetaMediaUnavailable:
                raise
            except Exception:
                raise MetaMediaUnavailable('Public media unavailable: Meta CDN fetch failed') from None
            if not _valid_asset(path):
                raise MetaMediaUnavailable('Public media unavailable: Meta returned invalid media bytes')
            paths.append(path)
        return PublicBundle(tuple(paths),'meta-business-discovery-official')
    except BaseException:
        for p in paths:p.unlink(missing_ok=True)
        raise
    finally:
        # Only our own client should be closed; caller may share injected fake.
        if download_http is None and hasattr(http,'close'):http.close()


def acquire_with_meta_fallback(url:str,output_directory:Path|str,pg,*,cookies_file=None,
                               public_fetch=None,meta_fetch=None)->PublicBundle:
    """Attempt existing public extractor first, then approved official Graph.

    If Graph access isn't configured, it incurs ZERO extra network calls and
    yields the original sanitized downloader error for durable queue deferral.
    """
    from .public_bundle import acquire_public_bundle
    fetch=public_fetch or acquire_public_bundle
    try:
        return fetch(url,output_directory,cookies_file=cookies_file)
    except PublicMediaError:
        if not meta_fallback_enabled():
            raise
    with pg.cursor() as cur:
        cur.execute("""SELECT creator_handle
            FROM public.reelbrain_reel_knowledge WHERE source_url=%s LIMIT 1""",
            (canonicalize_instagram(url),))
        creator=cur.fetchone()
    if not creator or not creator[0]:
        raise MetaMediaUnavailable('Public media unavailable: source creator identity missing')
    acquire=meta_fetch or acquire_meta_bundle
    return acquire(url,str(creator[0]),
        os.environ['REELBRAIN_META_GRAPH_TOKEN'],
        os.environ['REELBRAIN_META_IG_USER_ID'],
        output_directory)
