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
  output.push({sid:String(sender),mid:id,urls:[...urls],status:urls.size?'queued':'needs_review',attachment_types:kinds});
 }
 return output;
}