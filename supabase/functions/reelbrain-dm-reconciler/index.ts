/** Reelbrain official Instagram Graph 1:1 DM reconciliation.
 * Best-effort recovery for missed webhook deliveries. Reads ONLY approved
 * sender conversations; persists no raw private message texts or access tokens.
 * Can still report needs_review if Graph omits Reel attachments.
 */
import { inspectParticipantIds, reelEventsFromGraph, graphErrorCategory, validGraphId, resolvePageSessionWithFallback, listApprovedConversations, buildReceiptRecheck, selectReviewPage, recoverApprovedMessage } from './core.mjs';
const env=(k:string)=>Deno.env.get(k)?.trim()||'';
const base=env('SUPABASE_URL').replace(/\/$/,'');
const role=env('SUPABASE_SERVICE_ROLE_KEY');
const token=env('META_INSTAGRAM_ACCESS_TOKEN');
const testedToken=env('REELBRAIN_META_SYSTEM_USER_TEST_TOKEN');
const professional=env('META_IG_PROFESSIONAL_ID');
const json=(d:unknown,s=200)=>new Response(JSON.stringify(d),{status:s,headers:{'content-type':'application/json','cache-control':'no-store'}});
const headers=()=>({'apikey':role,'authorization':'Bearer '+role,'content-type':'application/json'});
const digest=async(text:string)=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))].map(x=>x.toString(16).padStart(2,'0')).join('');
const ident=validGraphId;
async function db(path:string,options:RequestInit={}){
 const r=await fetch(base+'/rest/v1/'+path,{...options,headers:{...headers(),...(options.headers as Record<string,string>||{})},signal:AbortSignal.timeout(7000)});
 if(!r.ok)throw new Error('db_http_'+r.status);
 return await r.json().catch(()=>null);
}
async function graph(path:string,params:Record<string,string>={},credential=token,ms=7000):Promise<any>{
 const url=new URL('https://graph.facebook.com/v26.0/'+path);
 for(const [k,v] of Object.entries(params))url.searchParams.set(k,v);
 const r=await fetch(url,{headers:{Authorization:'Bearer '+credential},redirect:'error',signal:AbortSignal.timeout(ms)});
 const result=await r.json().catch(()=>null);
 if(!r.ok || !result || typeof result!=='object' || result.error)throw new Error(graphErrorCategory(r.status,result));
 return result;
}
function datesAreRecent(value:unknown):boolean{
 if(typeof value!=='string')return true;
 const when=Date.parse(value);
 return Number.isFinite(when) && when<=Date.now()+60000 && when>=Date.now()-72*3600*1000;
}
Deno.serve(async req=>{
 if(req.method!=='POST')return json({error:'method_not_allowed'},405);
 if(!base.includes('xlkdzrhzizuftbnitodr.supabase.co')||!role)return json({error:'isolated_database_not_configured'},503);
 const body=await req.text();if(body.length>512)return json({error:'invalid_request'},413);
 let nonce:unknown, selectedName:unknown;try{const parsed=JSON.parse(body);nonce=parsed.nonce;selectedName=parsed.sender_username;}catch{return json({error:'invalid_request'},400)}
 if(typeof nonce!=='string'||!/^[a-f0-9]{64}$/.test(nonce))return json({error:'unauthorized'},403);
 let authorized=false;
 try{authorized=await db('rpc/reelbrain_claim_media_tick',{method:'POST',body:JSON.stringify({hash_arg:await digest(nonce)})})===true;}
 catch{return json({error:'authorization_failed'},503)}
 if(!authorized)return json({error:'unauthorized_or_expired'},403);
 if((!token&&!testedToken) || !/^[0-9]{3,32}$/.test(professional))return json({error:'meta_connection_not_configured'},503);
 let examined=0,recorded=0,newReceipts=0,linkedReels=0,errors=0;
 let senders:any[];
 try{senders=await db('reelbrain_sender_candidates?select=sender_id,username&approved=eq.true&limit=10');}
 catch{return json({error:'allowlist_unavailable'},503)}
 if(!Array.isArray(senders))return json({error:'invalid_allowlist'},503);
 const filtered=senders.filter(x=>typeof selectedName==='string' && typeof x?.username==='string' && x.username===selectedName);
 if(filtered.length!==1)return json({error:'one_sender_target_required'},400);
 for(const user of filtered){
   const sender=String(user.sender_id||'');if(!/^[0-9]{3,32}$/.test(sender)||sender===professional)continue;
   let checked=0,newSaved=0,unavailable=false,reason:string|null=null;
   let reviewCursor:number|undefined;
   try{
     const history=await db('reelbrain_dm_receipts?select=message_id,status&sender_igsid=eq.'+sender+'&order=first_received_at.desc&limit=500');
     const recheck=buildReceiptRecheck(history,0);
     const session=await resolvePageSessionWithFallback(graph,token,testedToken,professional);
     const conv=await listApprovedConversations(graph,session,sender);
     const threads=Array.isArray(conv.data)?conv.data.slice(0,15):[];
     console.info('reelbrain_dm_auth_mode',session.mode,session.credential_source);
     const events:any[]=[];
     // Direct recheck of known unresolved receipts is independent of the latest 20-message window.
     // The durable cursor ensures every receipt eventually receives its turn.
     const state=await db('reelbrain_dm_reconciliation_state?select=review_cursor&sender_igsid=eq.'+sender+'&limit=1');
     const cursor=Number(state?.[0]?.review_cursor||0);
     const reviewBase='reelbrain_dm_receipts?select=id,message_id,status&sender_igsid=eq.'+sender+'&status=eq.needs_review&order=id.asc&limit=4';
     let rows=await db(reviewBase+'&id=gt.'+cursor);
     if(!rows?.length)rows=await db(reviewBase);
     const review=selectReviewPage(rows,cursor,4);
     // Bound the time spent on old receipts so new message intake is not starved.
     const reviewStarted=Date.now();
     for(const row of review.rows){
       if(Date.now()-reviewStarted>24000)break;
       try{
         const recovered=await recoverApprovedMessage(graph,session.token,row.message_id,sender,professional);
         if(recovered?.status==='queued')events.push(recovered);
         checked++;
         reviewCursor=Number(row.id);
       }catch{unavailable=true;reason='graph_review_message_unavailable';reviewCursor=Number(row.id);}
     }
     for(const thread of threads){
       if(!ident(String(thread.id||'')) || events.length>=8)continue;
       const tid=encodeURIComponent(thread.id);
       const details=await graph(tid,{fields:'participants,updated_time'},session.token).catch(()=>null);
       if(!details){unavailable=true;reason='graph_conversation_detail_unavailable';continue;}
       if(!Array.isArray(details.participants?.data) || details.participants.data.length!==2 ||
           !inspectParticipantIds(details.participants,sender,professional))continue;
       if(!datesAreRecent(details.updated_time))continue;
       const listing=await graph(tid+'/messages',{limit:'20'},session.token).catch(()=>null);
       if(!listing){unavailable=true;reason='graph_message_listing_unavailable';continue;}
       const items=Array.isArray(listing?.data)?listing.data:[];
       for(const item of items){
         if(events.length>=8)break;
         const mid=String(item?.id||'');if(!ident(mid)||!datesAreRecent(item?.created_time)||!recheck.take(mid))continue;
         let detail=await graph(encodeURIComponent(mid),{fields:'id,from,created_time,message,attachments,shares'},session.token).catch(()=>null);
         if(!detail){detail=await graph(encodeURIComponent(mid),{fields:'id,from,created_time,message,attachments'},session.token).catch(()=>null);}
         if(!detail){detail=await graph(encodeURIComponent(mid),{fields:'id,from,created_time,message'},session.token).catch(()=>null);}
         if(!detail) {unavailable=true;reason='graph_message_detail_unavailable';continue;}
         if(!datesAreRecent(detail.created_time)||String(detail.from?.id)!==sender)continue;
         // No private message string persists; only canonical URL, attachment type, Meta mid.
         const extracted=reelEventsFromGraph([detail],sender,professional);
         events.push(...(recheck.isReview(mid)?extracted.filter((e:any)=>e.status==='queued'):extracted));
         checked++;
       }
     }
     if(events.length){
       const result=await db('rpc/reelbrain_accept_dm_batch',{method:'POST',body:JSON.stringify({_events:events})});
       recorded+=result?.received_messages||0;
       newReceipts+=result?.new_receipts||0;
       linkedReels+=result?.reel_links_seen||0;
       newSaved=result?.new_receipts||0;
     }
   }catch(e){unavailable=true;const msg=String((e as Error).message);reason=/^((?:(?:identity_page|identity_accounts|conversation_list)_)?graph_http_\d+(?:_code_\d+)?(?:_sub_\d+)?|(?:identity_page|identity_accounts|conversation_list)_graph_network_unavailable|meta_token_not_linked_page|db_http_\d+)$/.test(msg)?msg:'graph_or_network_unavailable';console.error('reelbrain_reconcile_sender_failed',reason);}
   if(unavailable)errors++;
   examined+=checked;
   try{
    await db('reelbrain_dm_reconciliation_state?on_conflict=sender_igsid',{
     method:'POST',headers:{prefer:'resolution=merge-duplicates,return=minimal'},
     body:JSON.stringify({sender_igsid:sender,last_checked_at:new Date().toISOString(),last_new_receipts:newSaved,
       last_error:unavailable?(reason||'partial_graph_history_unavailable'):null,
       ...(reviewCursor===undefined?{}:{review_cursor:reviewCursor})})
    });
   }catch{errors++;}
 }
 return json({accepted:true,approved_accounts_checked:filtered.length,inspected_new_messages:examined,
   receipts_seen:recorded,new_receipts:newReceipts,reel_links_seen:linkedReels,partial_failures:errors,
   note:'Official Graph history may omit native Reel attachment URLs; webhook remains primary intake.'},errors?207:200);
});