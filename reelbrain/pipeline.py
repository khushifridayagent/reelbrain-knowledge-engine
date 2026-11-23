"""Separate ingestion from external verification and model-generated suggestions."""
from __future__ import annotations
from .sources import canonicalize_instagram,parse_text,extract_instagram_mentions
from .contracts import Observation,ResourceCandidate,candidate_urls,evidence_filter
from .store import KnowledgeStore
from collections import OrderedDict

class KnowledgePipeline:
    def __init__(self,store:KnowledgeStore):self.store=store
    def ingest_report(self,filename:str,text:str,tenant:str='default')->dict:
        observations=parse_text(text,filename)
        candidates=[]
        for ev in observations:candidates.extend(candidate_urls(ev.text))
        return self.ingest_evidence(filename,filename,'research_report',observations,candidates,tenant=tenant,original=text)
    def ingest_reel_conversation(self, filename:str, text:str, tenant:str='personal', *,
                                  max_text_bytes:int=30*1024*1024)->dict:
        """Archive the user's raw chat and link *all* Reel references to notes.

        This intentionally does not transform user notes into claimed video content
        or process any media. A Reel becomes observed only after lawful acquisition.
        """
        if not isinstance(text,str):
            raise TypeError('text must be a unicode string')
        if len(text.encode('utf-8'))>max_text_bytes:
            raise ValueError('conversation exceeds configured local size budget')
        mentions=extract_instagram_mentions(text)
        notes=[Observation(m.context,kind='user_note',locator=f'{filename}:L{m.line}') for m in mentions]
        archive_id=self.store.store(tenant,filename,'conversation_archive',text,notes,[],status='notes_saved')
        self.store.archive_source_text(archive_id,tenant,text)
        urls=OrderedDict()
        for mention in mentions:
            if mention.canonical_url not in urls:
                urls[mention.canonical_url]=self.ingest_url(mention.canonical_url,tenant)['source_id']
            self.store.record_reel_mention(tenant,archive_id,urls[mention.canonical_url],
                                           f'{filename}:L{mention.line}',mention.char_offset,mention.context)
        new_jobs=0
        for url,sid in urls.items():
            previous=self.store.con.execute('SELECT id FROM jobs WHERE tenant=? AND kind=? AND idempotency_key=?',
                                             (tenant,'await_permitted_media',url)).fetchone()
            self.store.enqueue(tenant,'await_permitted_media',{'canonical_url':url,'source_id':sid},url)
            if previous is None:
                new_jobs+=1
        return {'archive_source_id':archive_id,'archive_name':filename,
                'mentions':len(mentions),'unique_urls':len(urls),'queued_jobs':new_jobs,
                'already_queued':len(urls)-new_jobs,
                'status':'user_notes_archived_reels_await_authorized_media',
                'evidence_type':'user_provided_note_not_reel_evidence'}

    def add_claims(self,source_id:str,observations:list[Observation],claims:list,tenant:str='default')->dict:
        from .profiles import validate_claims
        urls={row['canonical_url'] for row in self.store.con.execute('SELECT r.canonical_url FROM resources r JOIN citations c ON r.id=c.resource_id WHERE c.source_id=? AND c.tenant=?',(source_id,tenant)).fetchall()}
        accepted,rejected=validate_claims(claims,observations,urls)
        count=self.store.store_facts(source_id,tenant,accepted)
        return {'accepted':count,'rejected':rejected}
    def ingest_url(self,url:str,tenant:str='default')->dict:
        link=canonicalize_instagram(url)
        source_id=self.store.store(tenant,link,'reel' if '/reel/' in link else 'carousel',link,[],[],status='awaiting_authorized_media')
        return {'source_id':source_id,'status':'awaiting_authorized_media','evidence_count':0,'resource_count':0}
    def ingest_evidence(self,filename:str,source_ref:str,kind:str,observations:list[Observation],candidates:list[ResourceCandidate],tenant:str='default',original:str|None=None)->dict:
        verdict=evidence_filter(candidates,observations)
        source_id=self.store.store(tenant,source_ref,kind,original if original is not None else '\n'.join(x.text for x in observations),observations,verdict.accepted,status='evidence_saved')
        return {'source_id':source_id,'status':'evidence_saved','evidence_count':len(observations),'resource_count':len(verdict.accepted),'rejected':[{'url':x.url,'reason':x.reason} for x in verdict.rejected]}
