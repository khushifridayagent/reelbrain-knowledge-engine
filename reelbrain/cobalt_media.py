"""Ephemeral, local-only open-source Cobalt public Reel acquisition.

The runner starts a pinned Cobalt image without keys or mounted credentials.
No use of third-party public instances, cookies or proxy rotation.
"""
from __future__ import annotations
import json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from .sources import canonicalize_instagram
from .public_media import PublicMediaError
from .public_bundle import PublicBundle,_valid_asset
from .meta_business_media import valid_meta_media_url

ENDPOINT='http://127.0.0.1:9000/'
IMAGE_LIMIT=100*1024*1024

def unavailable(reason):
    return PublicMediaError('Public media unavailable: cobalt_'+reason)

def cobalt_ready(url:str)->bool:
    canon=canonicalize_instagram(url)
    return os.getenv('REELBRAIN_COBALT_READY','').strip().lower() in ('1','true') and ('/reel/' in canon or '/tv/' in canon)

def validate_cobalt_response(data:dict)->str:
    if not isinstance(data,dict):
        raise unavailable('invalid_reply')
    status=data.get('status')
    if status not in ('redirect','tunnel'):
        raise unavailable('no_direct_video')
    url=data.get('url')
    if not isinstance(url,str) or len(url)>4096:
        raise unavailable('invalid_url')
    if status=='redirect':
        if valid_meta_media_url(url):return url
        raise unavailable('untrusted_cdn')
    try:
        p=urlsplit(url)
        if (p.scheme=='http' and p.hostname=='127.0.0.1' and p.port==9000
                and p.path=='/tunnel' and not p.username and not p.password and not p.fragment):
            return url
    except ValueError:pass
    raise unavailable('untrusted_tunnel')

def acquire_cobalt_reel(url,output_directory,*,http=None,runner=None)->PublicBundle:
    canon=canonicalize_instagram(url)
    if '/reel/' not in canon and '/tv/' not in canon:raise unavailable('unsupported_source')
    root=Path(output_directory)
    if root.is_symlink() or not root.is_dir():raise unavailable('invalid_target')
    path=root/'cobalt_reel.mp4'
    if path.exists() or path.is_symlink():raise unavailable('destination_collision')
    client=http or httpx.Client(timeout=45,follow_redirects=False,trust_env=False)
    created=False
    try:
        try:
            response=client.post(ENDPOINT,json={'url':canon,'downloadMode':'auto','videoQuality':'1080'},
                headers={'Accept':'application/json'},timeout=45,follow_redirects=False)
            if response.status_code==429:raise unavailable('rate_limited')
            if response.status_code!=200:raise unavailable('request_failed')
            media_url=validate_cobalt_response(response.json())
            start=time.monotonic()
            total=0
            with client.stream('GET',media_url,timeout=45,follow_redirects=False) as stream:
                if stream.status_code!=200:raise unavailable('stream_failed')
                length=stream.headers.get('content-length','')
                if length.isdigit() and int(length)>IMAGE_LIMIT:raise unavailable('size_limit')
                with path.open('xb') as f:
                    created=True
                    for chunk in stream.iter_bytes(chunk_size=1<<20):
                        total+=len(chunk)
                        if total>IMAGE_LIMIT or time.monotonic()-start>90:
                            raise unavailable('download_budget')
                        f.write(chunk)
            if not _valid_asset(path):raise unavailable('invalid_video_bytes')
            run=runner or subprocess.run
            probe=run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
                'stream=width,height:format=duration','-of','json',str(path)],
                capture_output=True,text=True,timeout=20)
            if probe.returncode:raise unavailable('not_decodable_video')
            details=json.loads(probe.stdout)
            stream_info=details.get('streams') or []
            if (not stream_info or float(details.get('format',{}).get('duration',0))<=0
                    or int(stream_info[0].get('width',0))<=0 or int(stream_info[0].get('height',0))<=0):
                raise unavailable('missing_motion_stream')
            decode=run(['ffmpeg','-v','error','-i',str(path),'-frames:v','2','-f','null','-'],
                capture_output=True,text=True,timeout=25)
            if decode.returncode:raise unavailable('decode_failed')
            return PublicBundle((path,),'cobalt-self-hosted-public')
        except PublicMediaError:raise
        except Exception:raise unavailable('network_or_decode_failure') from None
    except BaseException:
        if created:path.unlink(missing_ok=True)
        raise
    finally:
        if http is None:client.close()
