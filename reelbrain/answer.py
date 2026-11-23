"""Evidence-locked retrieval: a simple deterministic baseline, not an LLM Agentic RAG claim."""
from __future__ import annotations
from .store import KnowledgeStore

class AnswerEngine:
    def __init__(self,store:KnowledgeStore):self.store=store
    def ask(self,query:str,tenant:str='default',limit:int=10)->dict:
        rows=self.store.search(query,tenant,limit)
        if not rows:return {'answer':'No supporting evidence found in this knowledge base.','citations':[],'route':'keyword','limitations':['No semantic/vector model was invoked.']}
        citations=[{'resource_id':r['resource_id'],'name':r['name'],'url':r['canonical_url'],'status':r['status'],'source':r['source_ref'],'locator':r['locator'],'evidence':r['evidence'],'kind':r['evidence_kind'],'score':r['score'],'facts':[f['field_type']+': '+f['value'] for f in r.get('facts',[])]} for r in rows]
        answer='\n'.join(f"{x['name']} — {x['url']} [observed: {x['source']} {x['locator']}; verification: {x['status']}]" for x in citations)
        return {'answer':answer,'citations':citations,'route':'keyword','limitations':['The resource appeared in source material; it has not been independently verified unless status is higher than seen.']}
