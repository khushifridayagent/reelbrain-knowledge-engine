"""Conservative planning for multiple retrieval passes; LLM synthesis stays opt-in.

Not a claim that semantic search, model routing, live web verification or self-learning
is already active. The documented dependency graph defines how to add those passes.
"""
from dataclasses import dataclass
import re
from .answer import AnswerEngine
from .store import KnowledgeStore

SYNONYMS={
    'scrape':['scraping','crawler','web data'],
    'automation':['browser','automate','agent'],
    'rag':['retrieval','knowledge','search'],
    'रिसर्च':['research','web','sources'],
    'रील':['reel','instagram','video'],
    'गिटहब':['github','repository','repo'],
}

@dataclass(frozen=True)
class QueryPlan:
    intent:str
    passes:tuple[str,...]
    queries:tuple[str,...]
    allow_external:bool=False

def plan_query(query:str)->QueryPlan:
    q=query.lower().strip()
    if not q:raise ValueError('query required')
    if re.search(r'(?:github\.com/|https://|[\w-]+/[\w.-]+)',q):
        return QueryPlan('exact_resource',('exact_url','keyword'),(query,))
    expansions=[query]
    for term,words in SYNONYMS.items():
        if term in q:expansions.extend(words)
    return QueryPlan('resource_discovery',('keyword','related_resources'),tuple(dict.fromkeys(expansions)))

class GroundedPlanner:
    def __init__(self,store:KnowledgeStore):self.store=store
    def ask(self,query:str,tenant:str='default'):
        p=plan_query(query)
        raw=[];seen=set()
        for q in p.queries[:6]:
            for hit in self.store.search(q,tenant,12):
                key=(hit['resource_id'],hit['source_ref'],hit['locator'])
                if key not in seen:seen.add(key);raw.append(hit)
        raw.sort(key=lambda x:x['score'],reverse=True)
        result=AnswerEngine(self.store).ask(query,tenant)
        if not result['citations'] and raw:
            result['citations']=[{'resource_id':x['resource_id'],'url':x['canonical_url'],'source':x['source_ref'],'locator':x['locator'],'evidence':x['evidence'],'status':x['status']} for x in raw[:10]]
            result['answer']='\n'.join(f"{x['canonical_url']} — {x['source_ref']} {x['locator']} [{x['status']}]" for x in raw[:10])
        result['plan']={'intent':p.intent,'passes':p.passes,'queries':p.queries,'external_calls':0}
        return result
