"""Optional public GitHub metadata checks. Never installs/runs repository code."""
import datetime
import re
from urllib.parse import urlsplit
from .contracts import canonical_resource

class VerificationError(RuntimeError):pass

def check_github_repo(repo_url:str,token:str|None=None,timeout=12)->dict:
    import httpx
    canon=canonical_resource(repo_url)
    pieces=urlsplit(canon).path.strip('/').split('/')
    if urlsplit(canon).hostname!='github.com' or len(pieces)!=2:
        raise VerificationError('only exact GitHub owner/repo supported')
    owner,repo=pieces
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+',repo):raise VerificationError('invalid repository identity')
    headers={'Accept':'application/vnd.github+json','User-Agent':'reelbrain-read-only-check/0.2'}
    if token:headers['Authorization']='Bearer '+token
    resp=httpx.get(f'https://api.github.com/repos/{owner}/{repo}',headers=headers,timeout=timeout,follow_redirects=False)
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if resp.status_code==200:
        data=resp.json()
        return {'provider':'github-api','checked_at':stamp,'http_status':200,'canonical':data.get('html_url'),'exists':True,'archived':data.get('archived'),'license':(data.get('license') or {}).get('spdx_id'),'pushed_at':data.get('pushed_at'),'stars':data.get('stargazers_count')}
    if resp.status_code in (404,410):return {'provider':'github-api','checked_at':stamp,'http_status':resp.status_code,'exists':False}
    raise VerificationError(f'GitHub API error {resp.status_code}; do not auto retry')
