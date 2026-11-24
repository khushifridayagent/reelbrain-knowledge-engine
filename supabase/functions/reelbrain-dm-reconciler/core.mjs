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
