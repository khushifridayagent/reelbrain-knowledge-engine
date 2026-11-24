"""Optional paid provider bridge: never enabled implicitly.

Strict URL identity, explicit per-call consent, no bypass of private/login-only
posts. Output media URLs are untrusted; download is separate and host-restricted.
No call to Apify was made in building this release (mock tests only).
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,os,tempfile
import httpx
from .sources import canonicalize_instagram, InvalidSource

class AcquisitionError(RuntimeError):pass

@dataclass(frozen=True)
class AcquiredPost:
    url:str
    shortcode:str
    caption:str
    media_url:str|None
    provider:str='apify/instagram-reel-scraper'
    verified_media:bool=False

class ApifyReelClient:
    ENDPOINT='https://api.apify.com/v2/acts/apify~instagram-reel-scraper/run-sync-get-dataset-items'
    def __init__(self,token:str,*,client=None,timeout_seconds:float=180):
        if not token:raise AcquisitionError('APIFY_API_TOKEN missing')
        self.token=token
        self.client=client or httpx.Client(timeout=timeout_seconds,follow_redirects=False,trust_env=False)
        self.timeout=timeout_seconds
        self.requests_made=0
    def inspect(self,url:str,*,allow_paid:bool=False)->AcquiredPost:
        if not allow_paid:raise PermissionError('External paid Apify run needs --allow-paid')
        try:canon=canonicalize_instagram(url)
        except InvalidSource as e:raise AcquisitionError(str(e)) from e
        if '/reel/' not in canon:raise AcquisitionError('actor limited to reels')
        if self.requests_made>=1:raise AcquisitionError('single-run budget exhausted')
        self.requests_made+=1
        try:
            response=self.client.post(self.ENDPOINT,
                    headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'},
                    json={'username':[canon],'resultsLimit':1,'includeTranscript':False,'includeDownloadedVideo':False},
                    timeout=self.timeout)
            response.raise_for_status()
            items=response.json()
        except (httpx.HTTPError,ValueError) as e:raise AcquisitionError('provider request failed or invalid JSON') from e
        if not isinstance(items,list) or len(items)!=1 or not isinstance(items[0],dict):
            raise AcquisitionError('provider returned no unique matching reel')
        obj=items[0]
        shortcode=canon.rstrip('/').split('/')[-1]
        if obj.get('shortCode')!=shortcode:
            raise AcquisitionError('provider shortcode does not match requested Reel')
        for field in ('inputUrl','url'):
            if obj.get(field):
                try:observed=canonicalize_instagram(str(obj[field]))
                except InvalidSource as e:raise AcquisitionError('provider identity malformed') from e
                # The official Reel actor documents that its canonical
                # output URL can be /p/<shortcode>/ even when the input is
                # /reel/<shortcode>/. Preserve the original Reel URL, and
                # verify the media's stable shortcode rather than the alias.
                observed_code=observed.rstrip('/').rsplit('/',1)[-1]
                if observed_code!=shortcode:
                    raise AcquisitionError('provider permalink shortcode mismatch')
        if obj.get('error'):
            raise AcquisitionError('provider reported inaccessible reel')
        media_url=obj.get('videoUrl') if isinstance(obj.get('videoUrl'),str) else None
        return AcquiredPost(canon,shortcode,
            (obj.get('caption') or '')[:30000] if isinstance(obj.get('caption'),str) else '',
            media_url,verified_media=False)

class SafeMediaDownloader:
    """Download only provider-returned Instagram CDN videos; no HTTP redirects or localhost.

    This is not an access-control bypass: source must be accessible and authorized.
    """
    def __init__(self,*,client=None,max_bytes:int=100*1024*1024):
        if not 0<max_bytes<=100*1024*1024:raise ValueError('invalid download size')
        self.client=client or httpx.Client(follow_redirects=False,trust_env=False,timeout=50)
        self.max_bytes=max_bytes
    @staticmethod
    def allowed(url:str)->bool:
        try:p=urlsplit(url)
        except ValueError:return False
        if p.scheme!='https' or p.username or p.password or p.fragment or p.port not in (None,443):return False
        host=(p.hostname or '').lower()
        return (host.endswith('.fbcdn.net') or host=='fbcdn.net' or
                host.endswith('.cdninstagram.com') or host=='cdninstagram.com')
    def download(self,url:str,destination:str|Path)->Path:
        if not self.allowed(url):raise AcquisitionError('media host is not approved; refusing SSRF')
        out=Path(destination)
        if out.is_symlink() or out.parent.is_symlink():raise AcquisitionError('unsafe destination')
        out.parent.mkdir(parents=True,exist_ok=True)
        tmp=None
        try:
            with self.client.stream('GET',url,follow_redirects=False,timeout=50) as resp:
                if resp.status_code!=200:raise AcquisitionError(f'media returned HTTP {resp.status_code}')
                if resp.headers.get('content-length','').isdigit() and int(resp.headers['content-length'])>self.max_bytes:
                    raise AcquisitionError('content length exceeds download budget')
                fd,name=tempfile.mkstemp(prefix='.download_',suffix='.mp4',dir=out.parent)
                tmp=Path(name)
                if os.name=='posix':os.chmod(tmp,0o600)
                total=0
                with os.fdopen(fd,'wb') as f:
                    for chunk in resp.iter_bytes(chunk_size=1<<20):
                        total+=len(chunk)
                        if total>self.max_bytes:raise AcquisitionError('download exceeded byte budget')
                        f.write(chunk)
            with tmp.open('rb') as f:header=f.read(16)
            if total<16 or header[4:8]!=b'ftyp':raise AcquisitionError('download not a valid mp4/mov container')
            if out.exists():raise AcquisitionError('refusing to overwrite existing media')
            os.replace(tmp,out);tmp=None
            return out
        finally:
            if tmp is not None:tmp.unlink(missing_ok=True)
