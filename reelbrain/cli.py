"""Local CLI. External paid Reel acquisition runs only after explicit consent flags."""
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from .sources import parse_saved_export,extract_instagram_urls
from .store import KnowledgeStore
from .pipeline import KnowledgePipeline
from .answer import AnswerEngine
from .media import analyze_video,recognize_image
from .contracts import candidate_urls
from .evaluation import evaluate

def run(argv=None):
    parser=argparse.ArgumentParser(prog='reelbrain',description='Evidence-first local knowledge ingestion')
    parser.add_argument('--db',default='data/reelbrain_local.db',help='LOCAL SQLite path; never remote project')
    parser.add_argument('--tenant',default='personal',help='isolation namespace')
    subs=parser.add_subparsers(dest='cmd',required=True)
    sp=subs.add_parser('import-report');sp.add_argument('file')
    sp=subs.add_parser('import-research-zip');sp.add_argument('file')
    sp=subs.add_parser('import-trending-zip');sp.add_argument('file')
    subs.add_parser('trending-counts')
    sp=subs.add_parser('trending-find');sp.add_argument('query');sp.add_argument('--limit',type=int,default=15)
    sp=subs.add_parser('trending-day');sp.add_argument('date')
    sp=subs.add_parser('fast-find');sp.add_argument('query');sp.add_argument('--limit',type=int,default=15)
    sp=subs.add_parser('serve');sp.add_argument('--port',type=int,default=8765)
    sp=subs.add_parser('media-worker');sp.add_argument('--limit',type=int,default=5)
    sp=subs.add_parser('trending-export-sql');sp.add_argument('destination');sp.add_argument('--batch-size',type=int,default=100)
    sp=subs.add_parser('import-saved');sp.add_argument('file')
    sp=subs.add_parser('import-reels-text');sp.add_argument('file')
    sp=subs.add_parser('add-url');sp.add_argument('url')
    sp=subs.add_parser('analyze-media');sp.add_argument('file');sp.add_argument('--source-url',default=None)
    sp=subs.add_parser('process-link');sp.add_argument('source_url');sp.add_argument('--allow-paid',action='store_true');sp.add_argument('--allow-external',action='store_true');sp.add_argument('--rights-confirmed',action='store_true');sp.add_argument('--use-groq-asr',action='store_true');sp.add_argument('--use-gemini-video',action='store_true');sp.add_argument('--use-groq-facts',action='store_true')
    sp=subs.add_parser('process-reel');sp.add_argument('source_url');sp.add_argument('media_path');sp.add_argument('--use-groq-asr',action='store_true');sp.add_argument('--use-gemini-video',action='store_true');sp.add_argument('--use-groq-facts',action='store_true');sp.add_argument('--allow-external',action='store_true')
    sp=subs.add_parser('ask');sp.add_argument('query')
    sp=subs.add_parser('reel-context');sp.add_argument('url')
    sp=subs.add_parser('list-pending');sp.add_argument('--limit',type=int,default=100)
    sp=subs.add_parser('backup');sp.add_argument('destination')
    sp=subs.add_parser('restore');sp.add_argument('source')
    sp=subs.add_parser('verify-backup');sp.add_argument('source')
    sp=subs.add_parser('counts')
    sp=subs.add_parser('eval');sp.add_argument('file')
    args=parser.parse_args(argv)
    if args.cmd=='serve':
        from .webapp import create_app
        import uvicorn
        api_token=os.getenv('REELBRAIN_API_TOKEN','')
        if len(api_token)<24:raise ValueError('Set REELBRAIN_API_TOKEN to a long random secret before running serve')
        app=create_app(db_path=args.db,token=api_token,tenant=args.tenant,
            meta_app_secret=os.getenv('META_APP_SECRET') or None,
            meta_verify_token=os.getenv('META_VERIFY_TOKEN') or None,
            meta_receiver_id=os.getenv('META_IG_RECEIVER_ID') or None,
            meta_allowed_senders={x.strip() for x in os.getenv('META_ALLOWED_SENDER_IDS','').split(',') if x.strip()} or None)
        uvicorn.run(app,host='127.0.0.1',port=args.port)
        return 0
    if args.cmd=='eval':
        payload=json.loads(Path(args.file).read_text(encoding='utf-8'))
        result=evaluate(payload.get('ground_truth',[]),payload.get('predictions',[]),payload.get('unsupported',0))
        print(json.dumps(result,indent=2));return 0 if result['gate_pass'] else 1
    if args.cmd in ('restore','verify-backup'):
        from .backup import restore_database,verify_database
        result=(restore_database(args.source,args.db) if args.cmd=='restore'
                else verify_database(args.source))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    db=KnowledgeStore(args.db);pipeline=KnowledgePipeline(db)
    try:
        if args.cmd=='import-report':
            result=pipeline.ingest_report(args.file,Path(args.file).read_text(encoding='utf-8'),args.tenant)
        elif args.cmd=='import-research-zip':
            from .archive import import_research_zip
            result=import_research_zip(args.file,pipeline,tenant=args.tenant)
        elif args.cmd=='import-trending-zip':
            from .trending_import import import_trending_zip
            result=import_trending_zip(args.file,db,tenant=args.tenant)
        elif args.cmd=='trending-counts':
            from .trending_import import trending_counts
            result=trending_counts(db,tenant=args.tenant)
        elif args.cmd=='trending-find':
            from .trending_import import search_catalog
            result=search_catalog(db,args.query,tenant=args.tenant,limit=args.limit)
        elif args.cmd=='fast-find':
            from .fastsearch import FastCatalogSearch
            result={'hits':FastCatalogSearch(db).search(args.query,args.tenant,args.limit),'external_calls':0}
        elif args.cmd=='media-worker':
            from .media_inbox import MediaInbox
            with MediaInbox(args.db,Path(args.db).parent/'reelbrain_private_media',args.tenant) as inbox:
                result={'tasks':inbox.process_queued(args.limit),'external_calls':0}
        elif args.cmd=='trending-day':
            from .trending_import import daily_lookup
            result=daily_lookup(db,args.date,tenant=args.tenant)
        elif args.cmd=='trending-export-sql':
            from .trending_import import export_supabase_sql
            paths=export_supabase_sql(db,args.destination,tenant=args.tenant,batch_size=args.batch_size)
            result={'scripts_written':len(paths),'paths':[str(p) for p in paths], 'remote_writes':0}
        elif args.cmd=='import-reels-text':
            raw=Path(args.file).read_text(encoding='utf-8')
            result=pipeline.ingest_reel_conversation(str(args.file),raw,tenant=args.tenant)
        elif args.cmd=='import-saved':
            raw=Path(args.file).read_text(encoding='utf-8')
            urls=parse_saved_export(json.loads(raw))
            results=[pipeline.ingest_url(u,args.tenant) for u in urls]
            new_jobs=0
            for url,item in zip(urls,results):
                prior=db.con.execute('SELECT id FROM jobs WHERE tenant=? AND kind=? AND idempotency_key=?',(args.tenant,'await_permitted_media',url)).fetchone()
                db.enqueue(args.tenant,'await_permitted_media',{'canonical_url':url,'source_id':item['source_id']},url)
                new_jobs += prior is None
            result={'input_urls':len(urls),'stored':len(results),'queued_jobs':new_jobs,'status':'link_only_waiting_for_authorized_media'}
        elif args.cmd=='add-url':result=pipeline.ingest_url(args.url,args.tenant)
        elif args.cmd=='analyze-media':
            p=Path(args.file)
            if p.suffix.lower() in ('.mp4','.mov','.mkv','.webm','.avi'):
                ev,metrics=analyze_video(p)
            else:
                ev=recognize_image(p);metrics={'ocr_frames':1}
            source_ref=args.source_url or str(p.resolve())
            candidates=[c for evidence in ev for c in candidate_urls(evidence.text)]
            result=pipeline.ingest_evidence(p.name,source_ref,'local_media',ev,candidates,tenant=args.tenant)
            result['media_metrics']=metrics
        elif args.cmd=='process-link':
            from .link_processor import LinkProcessingOptions,process_instagram_link
            from .acquire_apify import ApifyReelClient,SafeMediaDownloader
            if not (args.allow_paid and args.allow_external and args.rights_confirmed):
                raise PermissionError('process-link requires --allow-paid --allow-external --rights-confirmed')
            api_key=os.getenv('APIFY_API_TOKEN','')
            if not api_key:raise ValueError('APIFY_API_TOKEN is required for a paid provider run')
            stt=vlm=facts=None
            if args.use_groq_asr:
                from .providers import GroqSpeechToText,ProviderOptions
                stt=GroqSpeechToText(ProviderOptions(api_key=os.getenv('GROQ_API_KEY',''),
                    model=os.getenv('GROQ_ASR_MODEL','whisper-large-v3-turbo'),base_url='https://api.groq.com'))
            if args.use_gemini_video:
                from .providers import GeminiVideoResearcher
                vlm=GeminiVideoResearcher(api_key=os.getenv('GEMINI_API_KEY',''),model=os.getenv('GEMINI_VIDEO_MODEL',''))
            if args.use_groq_facts:
                from .fact_agents import GroqFactResearcher
                facts=GroqFactResearcher(api_key=os.getenv('GROQ_API_KEY',''),model=os.getenv('GROQ_RESEARCH_MODEL',''))
            from .engine import LocalPipelineEngine
            result=process_instagram_link(db,args.source_url,
                options=LinkProcessingOptions(True,True,True,args.tenant),
                apify_client=ApifyReelClient(api_key),downloader=SafeMediaDownloader(),
                engine_factory=lambda store:LocalPipelineEngine(store,audio_model=stt,video_model=vlm,fact_model=facts))
        elif args.cmd=='process-reel':
            from .engine import LocalPipelineEngine
            from .providers import GroqSpeechToText,ProviderOptions,GeminiVideoResearcher
            if (args.use_groq_asr or args.use_gemini_video or args.use_groq_facts) and not args.allow_external:
                raise PermissionError('--allow-external must be explicitly set before uploading audio/video')
            stt=(GroqSpeechToText(ProviderOptions(api_key=os.getenv('GROQ_API_KEY',''),model=os.getenv('GROQ_ASR_MODEL','whisper-large-v3-turbo'),base_url='https://api.groq.com')) if args.use_groq_asr else None)
            vlm=(GeminiVideoResearcher(api_key=os.getenv('GEMINI_API_KEY',''),model=os.getenv('GEMINI_VIDEO_MODEL','gemini-3.6-flash')) if args.use_gemini_video else None)
            if args.use_groq_facts:
                from .fact_agents import GroqFactResearcher
                facts=GroqFactResearcher(api_key=os.getenv('GROQ_API_KEY',''),model=os.getenv('GROQ_RESEARCH_MODEL',''))
            else:facts=None
            engine=LocalPipelineEngine(db,audio_model=stt,video_model=vlm,fact_model=facts)
            result=engine.ingest(args.media_path,args.source_url,args.tenant,allow_external=args.allow_external)
        elif args.cmd=='ask':result=AnswerEngine(db).ask(args.query,args.tenant)
        elif args.cmd=='reel-context':result={'reel_url':args.url,'user_notes':db.context_for_reel(args.url,args.tenant),'note':'user notes are not Reel evidence'}
        elif args.cmd=='list-pending':result=db.pending_reels(args.tenant,args.limit)
        elif args.cmd=='backup':
            from .backup import backup_database
            result=backup_database(db,args.destination)
        elif args.cmd=='counts':result=db.counts(args.tenant)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    finally:db.close()

if __name__=='__main__':sys.exit(run())
