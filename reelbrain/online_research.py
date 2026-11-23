"""On-demand, non-persistent, read-only feature/limitations research.

Only publicly documented GitHub repositories are supported with this adapter.
Never installs, executes, stores in the Reelbrain core database or claims tests ran.
"""
from __future__ import annotations
import base64,json,re
from urllib.parse import urlsplit,quote
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError

class ResearchUnavailable(RuntimeError):pass
_PART=re.compile(r'^[A-Za-z0-9_.-]{1,100}$')
class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):return None

def repository_name(url:str)->str|None:
    if not isinstance(url,str) or len(url)>2048:return None
    try:parts=urlsplit(url)
    except ValueError:return None
    if parts.scheme!='https' or parts.hostname not in ('github.com','www.github.com') or parts.username or parts.password or parts.port or parts.query or parts.fragment:
        return None
    seg=parts.path.strip('/').split('/')
    if len(seg)<2 or not _PART.fullmatch(seg[0]) or not _PART.fullmatch(seg[1]) or seg[1].endswith('.git'):
        return None
    return f'{seg[0]}/{seg[1]}'

def _fetch_json(path:str)->dict:
    if not re.fullmatch(r'/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/readme)?',path):raise ResearchUnavailable('non-allowlisted API path')
    url='https://api.github.com'+path
    req=Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'Reelbrain-Research-ReadOnly/0.8'})
    try:
        with build_opener(_NoRedirect()).open(req,timeout=5) as res:
            if res.status!=200:raise ResearchUnavailable(f'GitHub HTTP {res.status}')
            content=res.read(180_000)
            if len(content)>=180_000:raise ResearchUnavailable('GitHub response exceeded byte limit')
            obj=json.loads(content)
            if not isinstance(obj,dict):raise ResearchUnavailable('bad GitHub response')
            return obj
    except (URLError,HTTPError,TimeoutError,ValueError) as e:
        raise ResearchUnavailable(f'GitHub API unavailable: {type(e).__name__}') from e

def summarize_repository(url:str)->dict:
    repo=repository_name(url)
    if not repo:raise ResearchUnavailable('Only GitHub public repository inspection is implemented; others need a separately approved research adapter')
    data=_fetch_json('/repos/'+repo)
    if data.get('private') or data.get('full_name','').lower()!=repo.lower():raise ResearchUnavailable('GitHub did not confirm same public repo identity')
    claims=[];readme_link=None
    try:
        doc=_fetch_json('/repos/'+repo+'/readme')
        if doc.get('encoding')=='base64':
            raw=base64.b64decode(str(doc.get('content','')),validate=False)
            text=raw[:30_000].decode('utf-8','replace')
            for line in text.splitlines():
                stripped=line.strip()
                # Excerpts are creator/README claims, not independent proof.
                if (stripped.startswith(('- ','* ','## ','### ')) and
                    12<=len(stripped)<=350 and not stripped.startswith(('- [', '* ['))):
                    claims.append(stripped.lstrip('-*# ').strip())
                if len(claims)>=12:break
            readme_link=doc.get('html_url')
    except ResearchUnavailable:pass
    lic=data.get('license') or {}
    return {'repository':data.get('full_name'),'source_url':data.get('html_url'),
            'readme_source_url':readme_link,'status':'repository_readme_checked' if readme_link else 'github_metadata_only',
            'execution_status':'not_tested',
            'description':data.get('description') or 'Not declared',
            'licence_spdx':lic.get('spdx_id') if isinstance(lic,dict) else None,
            'archived':bool(data.get('archived')),'stars_observed':data.get('stargazers_count'),
            'last_push':data.get('pushed_at'),'open_issues_observed':data.get('open_issues_count'),
            'readme_excerpts':claims,
            'limitations':['README feature descriptions are publisher claims, not proof of performance.',
                           'No installation, sandbox test, load benchmark, security audit, or legal review performed.',
                           'Project-specific compatibility, quota, cost and maintenance require verification.'],
            'source_type':'live_github_metadata_and_optional_readme', 'persisted':False}
