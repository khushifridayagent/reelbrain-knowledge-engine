/** Reelbrain v0.9 – Meta 1:1 DM signed receiver, durable per-message receipts.
 * Scope: Only approved sender Instagram-scoped IDs; never group chats.
 * 200 is emitted only after Postgres atomically saves every accepted message receipt.
 * No media download, no chat replies, no secrets/PII in logs.
 */
import { collectApprovedEvents } from './dm_extract.mjs';
const env=(name:string)=>Deno.env.get(name)?.trim()||'';
const E=new TextEncoder();
const json=(obj:unknown,status=200)=>new Response(JSON.stringify(obj), {status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store'}});
const URL_BASE=()=>env('SUPABASE_URL').replace(/\/$/,'');
const key=()=>env('SUPABASE_SERVICE_ROLE_KEY');
const headers=()=>({'apikey':key(),'authorization':'Bearer '+key(),'content-type':'application/json'});
const MAX_BYTES=256_000;
function equal(a:string,b:string):boolean {
  const aa=E.encode(a),bb=E.encode(b);
  let delta=aa.length^bb.length;
  for(let i=0;i<Math.max(aa.length,bb.length);i++)delta|=(aa[i]||0)^(bb[i]||0);
  return delta===0;
}
async function validSignature(body:Uint8Array,signature:string,appSecret:string):Promise<boolean>{
  if(!/^sha256=[0-9a-f]{64}$/i.test(signature))return false;
  const hkey=await crypto.subtle.importKey('raw',E.encode(appSecret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const actual=[...new Uint8Array(await crypto.subtle.sign('HMAC',hkey,body))].map(x=>x.toString(16).padStart(2,'0')).join('');
  return equal('sha256='+actual,signature.toLowerCase());
}
function configured():boolean {
  return ['META_APP_SECRET','META_VERIFY_TOKEN','META_IG_PROFESSIONAL_ID','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY'].every(n=>!!env(n));
}
Deno.serve(async (request:Request)=>{
  const url=new URL(request.url);
  if(request.method==='GET'){
    const expected=env('META_VERIFY_TOKEN');
    if(!expected)return json({error:'verification_not_configured'},503);
    if(url.searchParams.get('hub.mode')!=='subscribe'|| !equal(url.searchParams.get('hub.verify_token')||'',expected))return json({error:'forbidden'},403);
    const challenge=url.searchParams.get('hub.challenge')||'';
    if(!/^\d{1,100}$/.test(challenge))return json({error:'invalid_challenge'},400);
    return new Response(challenge,{headers:{'content-type':'text/plain','cache-control':'no-store'}});
  }
  if(request.method!=='POST')return json({error:'method_not_allowed'},405);
  if(!configured())return json({error:'meta_credentials_incomplete',retryable:true},503);
  if(Number(request.headers.get('content-length')||0)>MAX_BYTES)return json({error:'payload_too_large',retryable:true},503);
  let raw:Uint8Array;
  try{raw=new Uint8Array(await request.arrayBuffer());}catch{return json({error:'body_read_failed',retryable:true},503);}
  if(raw.length>MAX_BYTES)return json({error:'payload_too_large',retryable:true},503);
  if(!await validSignature(raw,request.headers.get('x-hub-signature-256')||'',env('META_APP_SECRET')))return json({error:'invalid_signature'},403);
  let parsed:any;
  try{parsed=JSON.parse(new TextDecoder().decode(raw));}catch{return json({error:'invalid_json'},400);}
  if(parsed?.object!=='instagram')return json({accepted:true,applicable:false});

  // A signed event is NOT automatically an authorized user message.
  // The private allowlist is loaded AFTER signature verification, on each request.
  const allowRes=await fetch(URL_BASE()+'/rest/v1/reelbrain_sender_candidates?select=sender_id&approved=eq.true&limit=20',{
    headers:headers(),signal:AbortSignal.timeout(6000)
  }).catch(()=>null);
  if(!allowRes?.ok){console.error('reelbrain_allowlist_unavailable');return json({error:'allowlist_unavailable',retryable:true},503);}
  const rows=await allowRes.json().catch(()=>null);
  if(!Array.isArray(rows))return json({error:'malformed_allowlist',retryable:true},503);
  const allowed=new Set<string>(rows.filter(x=>typeof x?.sender_id==='string'&&/^[0-9]{3,32}$/.test(x.sender_id)).map(x=>x.sender_id));
  if(!allowed.size)return json({error:'empty_allowlist',retryable:true},503);

  let messages;
  try{messages=collectApprovedEvents(parsed,allowed,env('META_IG_PROFESSIONAL_ID'));}
  catch(e){console.error('reelbrain_unrecognized_or_oversized_signed_DM_payload',String((e as Error).message).slice(0,60));return json({error:'unparsed_signed_message',retryable:true},503);}
  if(!messages.length)return json({accepted:true,authorized_messages:0,ignored:true});
  // Atomic and idempotent write: every message gets a private receipt even if no URL.
  // Source URLs, with a separate per-message association, are deduplicated in the queue.
  const res=await fetch(URL_BASE()+'/rest/v1/rpc/reelbrain_accept_dm_batch',{
    method:'POST',headers:headers(),body:JSON.stringify({_events:messages}),signal:AbortSignal.timeout(8000)
  }).catch(()=>null);
  if(!res?.ok){console.error('reelbrain_signed_message_persist_failed',res?.status||'network');return json({error:'receipt_persistence_failed',retryable:true},503);}
  const result=await res.json().catch(()=>null);
  if(!result || result.received_messages!==messages.length){console.error('reelbrain_receipt_count_mismatch');return json({error:'receipt_ack_mismatch',retryable:true},503);}
  console.log('reelbrain_signed_dm_saved',JSON.stringify({messages:messages.length,newReceipts:result.new_receipts,unresolved:result.new_unresolved_receipts}));
  return json({accepted:true,authorized_messages:messages.length,receipts_saved_or_deduplicated:result.received_messages,
    new_receipts:result.new_receipts,unresolved:result.new_unresolved_receipts,
    reel_links_seen:result.reel_links_seen,media_processed:false});
});