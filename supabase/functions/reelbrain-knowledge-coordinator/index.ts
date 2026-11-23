/** Reelbrain autonomous metadata/queue coordinator. Zero paid API calls.
 * The actual OCR/ASR/VLM media worker is separate and must be hosted with
 * authorized public-video acquisition and keys. Do not claim it is present.
 * Only the isolated Supabase project may invoke this function via one-shot
 * cryptographically random database-generated authorization. No public access.
 */
const env=(key:string)=>Deno.env.get(key)?.trim()??'';
const base=env('SUPABASE_URL').replace(/\/$/,'');
const secret=env('SUPABASE_SERVICE_ROLE_KEY');
const h=()=>({'apikey':secret,'authorization':'Bearer '+secret,'content-type':'application/json'});
const resp=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json','cache-control':'no-store'}});
const sha=async(s:string)=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))].map(x=>x.toString(16).padStart(2,'0')).join('');
async function rpc(endpoint:string,body:Record<string,unknown>,timeout=9000):Promise<any>{
 const res=await fetch(base+'/rest/v1/rpc/'+endpoint,{
   method:'POST',headers:h(),body:JSON.stringify(body),signal:AbortSignal.timeout(timeout)
 });
 if(!res.ok)throw new Error('database_rpc_'+endpoint+'_'+res.status);
 return await res.json();
}
Deno.serve(async request=>{
 if(request.method!=='POST')return resp({error:'method_not_allowed'},405);
 if(!base.includes('xlkdzrhzizuftbnitodr.supabase.co')||!secret)return resp({error:'project_isolation_or_secrets_unavailable'},503);
 const bytes=await request.text();
 if(bytes.length>512)return resp({error:'body_too_large'},413);
 let nonce:unknown;
 try{nonce=JSON.parse(bytes).nonce;}catch{return resp({error:'invalid_json'},400);}
 if(typeof nonce!=='string'||!/^[0-9a-f]{64}$/.test(nonce))return resp({error:'unauthorized'},403);
 let allowed=false;
 try{allowed=await rpc('reelbrain_claim_media_tick',{hash_arg:await sha(nonce)},5000)===true;}
 catch{return resp({error:'authorization_unavailable'},503);}
 if(!allowed)return resp({error:'unauthorized_or_expired'},403);
 try{
   const reaped=await rpc('reelbrain_reap_expired_dm_jobs',{batch_size:100});
   const state=await rpc('reelbrain_prepare_media_batch',{batch_size:50});
   // Media provider is explicitly NOT started here; queue remains available
   // to the separate actual media worker and is not silently consumed.
   const result={...state,expired_leases_reaped:reaped,full_media_worker_started:false,
      status:'awaiting_authorized_media_worker_host_and_provider',timestamp:new Date().toISOString()};
   const write=await fetch(base+'/rest/v1/reelbrain_worker_state?on_conflict=worker_name',{
     method:'POST',headers:{...h(),prefer:'resolution=merge-duplicates,return=minimal'},
     body:JSON.stringify({worker_name:'coordinator',last_tick:result.timestamp,
       last_result:result,last_error:null,full_media_host_connected:false,updated_at:result.timestamp}),
     signal:AbortSignal.timeout(6000)
   });
   if(!write.ok)return resp({error:'heartbeat_persistence_unavailable',retryable:true},503);
   return resp({accepted:true,...result});
 }catch(e){
   console.error('reelbrain_coordinator_failed',String((e as Error).message).slice(0,120));
   return resp({error:'coordinator_failed',retryable:true},503);
 }
});