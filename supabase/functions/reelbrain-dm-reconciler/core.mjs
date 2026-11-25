/** Strict Meta Graph 1:1 DM projection; retain only Reel URL, attachment kinds and ID. */
export function inspectParticipantIds(participants,sender,professional){
 const data=Array.isArray(participants?.data)?participants.data:[];
 return data.some(x=>String(x?.id)===String(sender)) && data.some(x=>String(x?.id)===String(professional));
}
const PATTERN=/https?:\/\/[^\s<>'"`]+/g;
function canonical(url){
 try{
  const u=new URL(url.trim().replace(/[.,;!\]})]+$/g,''));
  const p=u.pathname.split('/').filter(Boolean);
  if(u.protocol!=='https:'||!['instagram.com','www.instagram.com'].includes(u.hostname)||u.port||u.username||u.password||p.length!==2||!['reel','p','tv'].includes(p[0])||!/^[a-zA-Z0-9_-]{4,160}$/.test(p[1]))return null;
  return `https://www.instagram.com/${p[0]}/${p[1]}/`;
 }catch{return null;}
}
function strings(value,out,depth=0){
 if(depth>6||out.length>=100||value==null)return;
 if(typeof value==='string'){
  if(value.length<=10000 && /instagram\.com/.test(value))out.push(value);
 } else if(Array.isArray(value)){
  for(const item of value.slice(0,30))strings(item,out,depth+1);
 }else if(typeof value==='object'){
  for(const [k,v] of Object.entries(value).slice(0,50)){
   if(['data','message','text','attachments','attachment','shares','share','media','payload','url','permalink','link','reel','post'].includes(k))strings(v,out,depth+1);
  }
 }
}
export function reelEventsFromGraph(items,sender,professional){
 const output=[];
 for(const item of Array.isArray(items)?items.slice(0,100):[]){
  if(String(item?.from?.id)!==String(sender)||String(sender)===String(professional))continue;
  const id=item?.id;
  if(typeof id!=='string'||id.length<1||id.length>256)continue;
  const texts=[];
  strings(item.message,texts);
  strings(item.attachments,texts);
  strings(item.shares,texts);
  strings(item.share,texts);
  const urls=new Set();
  for(const text of texts){for(const match of text.match(PATTERN)||[]){const url=canonical(match);if(url)urls.add(url);if(urls.size>=12)break;}if(urls.size>=12)break;}
  const attachments=Array.isArray(item.attachments)?item.attachments:(Array.isArray(item.attachments?.data)?item.attachments.data:[]);
  const kinds=attachments.slice(0,20).map(x=>String(x?.type||'unknown').slice(0,50));
  const suspect=kinds.length>0||!!item.shares||!!item.share||/(?:instagram|reel|https?:\/\/|www\.)/i.test(String(item.message||''));
  output.push({sid:String(sender),mid:id,urls:[...urls],status:urls.size?'queued':suspect?'needs_review':'no_reel_link',attachment_types:kinds});
 }
 return output;
}
export function validGraphId(value){
 return typeof value==='string' && /^[A-Za-z0-9_.:-]{5,256}$/.test(value);
}
export function linkedPageId(payload,professional){
 const id=String(payload?.id||'');
 return /^[0-9]{3,32}$/.test(id) &&
        id!==String(professional) &&
        String(payload?.instagram_business_account?.id||'')===String(professional) ? id:null;
}
export function graphErrorCategory(status,payload){
 const code=payload?.error?.code, sub=payload?.error?.error_subcode;
 return 'graph_http_'+(Number.isInteger(status)?status:0)
   +(Number.isInteger(code)?'_code_'+code:'')
   +(Number.isInteger(sub)?'_sub_'+sub:'');
}

const safeGraphFailure=e=>{
 const msg=String(e?.message||'');
 return /^graph_http_\d+(?:_code_\d+)?(?:_sub_\d+)?$/.test(msg)?msg:'graph_network_unavailable';
};
const unsupportedField=e=>/^graph_http_400_code_100(?:_sub_\d+)?$/.test(safeGraphFailure(e));
/** Resolve the linked Page without ever persisting or returning tokens to callers of the Edge Function. */
export async function resolvePageSession(graph,credential,professional){
 let identity;
 try{identity=await graph('me',{fields:'id,instagram_business_account{id}'},credential);}
 catch(e){if(!unsupportedField(e))throw new Error('identity_page_'+safeGraphFailure(e));}
 const page=linkedPageId(identity,professional);
 if(page)return {id:page,token:credential,mode:'direct_page'};
 if(identity?.instagram_business_account?.id)throw new Error('meta_token_not_linked_page');
 let accounts;
 try{accounts=await graph('me/accounts',{fields:'id,instagram_business_account{id},access_token',limit:'100'},credential);}
 catch(e){throw new Error('identity_accounts_'+safeGraphFailure(e));}
 const matches=(Array.isArray(accounts?.data)?accounts.data:[]).filter(row=>linkedPageId(row,professional)&&typeof row.access_token==='string'&&row.access_token.length>0);
 if(matches.length!==1)throw new Error('meta_token_not_linked_page');
 return {id:linkedPageId(matches[0],professional),token:matches[0].access_token,mode:'derived_page'};
}
export async function listApprovedConversations(graph,session,sender){
 const path=encodeURIComponent(session.id)+'/conversations';
 let response;
 try{response=await graph(path,{platform:'instagram',user_id:sender,limit:'5'},session.token);}
 catch(e){if(!unsupportedField(e))throw new Error('conversation_list_'+safeGraphFailure(e));}
 if(Array.isArray(response?.data)&&response.data.length)return response;
 try{return await graph(path,{platform:'instagram',limit:'15'},session.token);}
 catch(e){throw new Error('conversation_list_'+safeGraphFailure(e));}
}

/** Bounded reconsideration of unresolved receipts; linked receipts are immutable dedup hits. */
export function buildReceiptRecheck(history,maxReview=2){
 const known=new Map((Array.isArray(history)?history:[]).map(row=>[String(row.message_id||''),row.status]));
 const visited=new Set();
 let reviewCount=0;
 return {
  isReview:id=>known.get(id)==='needs_review',
  take(id){
   if(visited.has(id))return false;
   visited.add(id);
   if(!known.has(id))return true;
   if(known.get(id)!=='needs_review'||reviewCount>=maxReview)return false;
   reviewCount++;
   return true;
  }
 };
}

/** Only missing or invalid credentials may use the independently tested system user.
 * A mismatched Page or permission failure is never bypassed. No credential is logged.
 */
export async function resolvePageSessionWithFallback(graph,primary,tested,professional){
 if(primary){
  try{return {...await resolvePageSession(graph,primary,professional),credential_source:'configured'};}
  catch(e){
   if(!tested || tested===primary || !/^(?:identity_page|identity_accounts)_graph_http_\d+_code_190(?:_sub_\d+)?$/.test(String(e?.message||'')))throw e;
  }
 }
 if(!tested)throw new Error('meta_token_not_configured');
 return {...await resolvePageSession(graph,tested,professional),credential_source:'tested_system_user'};
}

/** Keyset page: advance even on unavailable messages, wrap only at the end. */
export function selectReviewPage(history,cursor=0,limit=4){
 const rows=(Array.isArray(history)?history:[]).filter(x=>x?.status==='needs_review'&&Number.isSafeInteger(Number(x.id))&&Number(x.id)>0&&validGraphId(x.message_id)).sort((a,b)=>Number(a.id)-Number(b.id));
 const next=rows.filter(x=>Number(x.id)>Number(cursor)).slice(0,limit);
 const selected=next.length?next:rows.slice(0,limit);
 return {rows:selected,cursor:selected.length?Number(selected.at(-1).id):0};
}
/** Request explicit share subfields on the first read, while Meta still exposes the message. */
export async function readGraphMessage(graph,credential,mid){
 const path=encodeURIComponent(mid);
 let item;
 try{item=await graph(path,{fields:'id,from,created_time,message,attachments,shares{type,url,id}'},credential,4000);}
 catch(e){
  if(!unsupportedField(e))throw e;
  try{item=await graph(path,{fields:'id,from,created_time,message,attachments'},credential,4000);}
  catch(e2){if(!unsupportedField(e2))throw e2;item=await graph(path,{fields:'id,from,created_time,message'},credential,4000);}
 }
 return item;
}

/** Official Graph only. Native media IDs are never converted to guessed shortcodes. */
export async function recoverApprovedMessage(graph,credential,mid,sender,professional){
 if(!validGraphId(mid)||String(sender)===String(professional))return null;
 const path=encodeURIComponent(mid);
 const item=await readGraphMessage(graph,credential,mid);
 if(item?.id!==mid||String(item?.from?.id)!==String(sender))return null;
 let event=reelEventsFromGraph([item],sender,professional)[0];
 if(!event||event.urls.length)return event||null;
 if(!item.shares || (Array.isArray(item.shares.data) && !item.shares.data.length)){
  try{
   const shares=await graph(path+'/shares',{fields:'type,url,id'},credential,3000);
   event=reelEventsFromGraph([{...item,shares}],sender,professional)[0]||event;
  }catch{/* No URL is a review, not a successful recovery. */}
 }
 if(event.urls.length)return event;
 const attachments=Array.isArray(item.attachments)?item.attachments:(item.attachments?.data||[]);
 const ids=new Set();
 for(const a of attachments.slice(0,12)){
  if(!['ig_post','ig_reel'].includes(a?.type))continue;
  const id=String(a?.payload?.ig_post_media_id||a?.ig_post_media_id||'');
  if(/^[0-9]{5,32}$/.test(id))ids.add(id);
 }
 const urls=new Set();
 for(const id of [...ids].slice(0,2)){
  try{
   const media=await graph(id,{fields:'id,permalink'},credential,3000);
   const url=String(media?.id)===id&&typeof media?.permalink==='string'?canonical(media.permalink):null;
   if(url)urls.add(url);
  }catch{/* Access denied or omitted permalink stays unresolved. */}
 }
 return urls.size?{...event,urls:[...urls],status:'queued'}:event;
}
