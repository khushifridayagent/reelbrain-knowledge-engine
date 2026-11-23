/** Meta Instagram Professional 1:1 DM -> isolated durable queue.
 * Requires: META_APP_SECRET, META_VERIFY_TOKEN, META_IG_PROFESSIONAL_ID,
 * META_ALLOWED_SENDERS, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
 * Unconfigured deployments return 503, never accept arbitrary messages.
 * No media is fetched. No automatic DM reply. No group-chat support.
 */
type Json = Record<string, unknown>;
const env = (k: string) => Deno.env.get(k)?.trim() || "";
const respond = (value: Json, status=200) => new Response(JSON.stringify(value),
  {status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}});
const E = new TextEncoder();
const MAX_BYTES=256_000;
const URL_PATTERN=/https?:\/\/[^\s<>"']+/g;
function canonical(input: unknown): string | null {
  if(typeof input!=="string" || input.length>2048)return null;
  try {
    const u=new URL(input.replace(/[.,;!\]\)}]+$/, ""));
    if(u.protocol!=="https:" || !["instagram.com","www.instagram.com"].includes(u.hostname) || u.username || u.password || u.port)return null;
    const pieces=u.pathname.split("/").filter(Boolean);
    if(pieces.length<2 || !["reel","p","tv"].includes(pieces[0]) || !/^[a-zA-Z0-9_-]{4,160}$/.test(pieces[1]))return null;
    return `https://www.instagram.com/${pieces[0]}/${pieces[1]}/`;
  }catch {return null;}
}
function findUrls(message: Json): string[] {
  const texts: string[]=[];
  if(typeof message.text==="string")texts.push(message.text.slice(0,10_000));
  if(Array.isArray(message.attachments)) {
    for(const a of message.attachments.slice(0,20)) {
      if(!a || typeof a!=="object" || !["ig_reel","reel","ig_post","post","share"].includes(a.type))continue;
      if(a.payload && typeof a.payload==="object")for(const name of ["url","permalink"])
        if(typeof a.payload[name]==="string")texts.push(a.payload[name]);
    }
  }
  const found=new Set<string>();
  for(const text of texts)for(const matched of text.match(URL_PATTERN)||[]){const url=canonical(matched);if(url)found.add(url);}
  return [...found].slice(0,12);
}
function equal(a: string,b: string): boolean {
  const x=E.encode(a);const y=E.encode(b);let diff=x.length^y.length;
  for(let i=0;i<Math.max(x.length,y.length);i++)diff|=(x[i]||0)^(y[i]||0);
  return diff===0;
}
async function sha256hex(text:string):Promise<string>{return [...new Uint8Array(await crypto.subtle.digest("SHA-256",E.encode(text)))].map(n=>n.toString(16).padStart(2,"0")).join("");}
async function verifiedHmac(raw:Uint8Array,signature:string,secret:string):Promise<boolean>{
  if(!/^sha256=[0-9a-f]{64}$/i.test(signature))return false;
  const k=await crypto.subtle.importKey("raw",E.encode(secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]);
  const v=[...new Uint8Array(await crypto.subtle.sign("HMAC",k,raw))].map(n=>n.toString(16).padStart(2,"0")).join("");
  return equal("sha256="+v,signature.toLowerCase());
}
function configured():boolean{return ["META_APP_SECRET","META_VERIFY_TOKEN","META_IG_PROFESSIONAL_ID","SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY"].every(k=>!!env(k));}
Deno.serve(async(req:Request)=>{
  // Meta GET verification needs its verify token, not media-processing or POST credentials.
  const target=new URL(req.url);
  if(req.method==="GET"){
    const verifyToken=env("META_VERIFY_TOKEN");
    if(!verifyToken)return respond({error:"META_VERIFY_TOKEN not configured"},503);
    if(target.searchParams.get("hub.mode")!=="subscribe" || !equal(target.searchParams.get("hub.verify_token")||"",verifyToken))return respond({error:"Forbidden"},403);
    const challenge=target.searchParams.get("hub.challenge")||"";
    if(!/^\d{1,100}$/.test(challenge))return respond({error:"Invalid challenge"},400);
    return new Response(challenge,{headers:{"content-type":"text/plain","cache-control":"no-store"}});
  }
  if(req.method!=="POST")return respond({error:"Method not allowed"},405);
  // Real POST delivery must still provide all credentials and HMAC validation.
  if(!configured())return respond({error:"Webhook credentials not configured"},503);
  const len=Number(req.headers.get("content-length")||"0");
  if(len>MAX_BYTES)return respond({error:"Payload too large"},413);
  const raw=new Uint8Array(await req.arrayBuffer());
  if(raw.length>MAX_BYTES)return respond({error:"Payload too large"},413);
  if(!await verifiedHmac(raw,req.headers.get("x-hub-signature-256")||"",env("META_APP_SECRET")))return respond({error:"Invalid signature"},403);
  let event:Json;
  try{event=JSON.parse(new TextDecoder().decode(raw));}catch{return respond({error:"Invalid JSON"},400);}
  if(event.object!=="instagram" || !Array.isArray(event.entry))return respond({accepted:true,queued:0,ignored:true});
  // Verify signed event BEFORE accessing private allowlist. No arbitrary sender can enroll itself.
  const allowedResponse=await fetch(env("SUPABASE_URL").replace(/\/$/,"")+"/rest/v1/reelbrain_sender_candidates?select=sender_id,approved&approved=eq.true&limit=20", {
    headers:{"apikey":env("SUPABASE_SERVICE_ROLE_KEY"),"authorization":"Bearer "+env("SUPABASE_SERVICE_ROLE_KEY")},
    signal:AbortSignal.timeout(5000)
  }).catch(()=>null);
  if(!allowedResponse || !allowedResponse.ok)return respond({error:"Private sender allowlist unavailable",retryable:true},503);
  const approvedRows=await allowedResponse.json().catch(()=>null);
  if(!Array.isArray(approvedRows))return respond({error:"Invalid allowlist response",retryable:true},503);
  const allowed=new Set<string>(approvedRows.filter((x:any)=>x?.approved===true && typeof x?.sender_id==="string" && /^[0-9]{3,32}$/.test(x.sender_id)).map((x:any)=>x.sender_id));
  const jobs=new Map<string,{source_url:string,inbound_event_id:string,sender_digest:string}>();
  for(const entry of event.entry.slice(0,40)){
    if(!entry || !Array.isArray(entry.messaging))continue;
    for(const item of entry.messaging.slice(0,100)){
      if(!item || typeof item!=="object" || item.thread || item.participants)continue;
      const sender=item.sender?.id; const recipient=item.recipient?.id;const msg=item.message;
      if(typeof sender!=="string" || !allowed.has(sender) || recipient!==env("META_IG_PROFESSIONAL_ID") || !msg || typeof msg!=="object")continue;
      if(typeof msg.mid!=="string" || msg.mid.length<1 || msg.mid.length>256 || msg.is_echo || msg.is_deleted)continue;
      const hashedSender=await sha256hex(sender);const hashedMessage=await sha256hex(msg.mid);
      for(const source_url of findUrls(msg))if(!jobs.has(source_url))jobs.set(source_url,{source_url,inbound_event_id:hashedMessage,sender_digest:hashedSender});
    }
  }
  if(!jobs.size)return respond({accepted:true,queued:0});
  const api=env("SUPABASE_URL").replace(/\/$/,"")+"/rest/v1/reelbrain_dm_jobs?on_conflict=source_url";
  const res=await fetch(api,{method:"POST",headers:{"apikey":env("SUPABASE_SERVICE_ROLE_KEY"),"authorization":"Bearer "+env("SUPABASE_SERVICE_ROLE_KEY"),"content-type":"application/json","prefer":"resolution=ignore-duplicates,return=minimal"},body:JSON.stringify([...jobs.values()]),signal:AbortSignal.timeout(6000)}).catch(()=>null);
  if(!res || !res.ok)return respond({error:"Queue persistence temporarily unavailable",retryable:true},503);
  return respond({accepted:true,queued_or_deduplicated:jobs.size,media_processed:false});
});
