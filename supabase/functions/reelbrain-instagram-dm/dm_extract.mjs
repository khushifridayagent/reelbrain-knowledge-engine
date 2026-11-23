/** Pure parser for official Instagram 1:1 business-message events.
 * Do not put API secrets here. All inputs are untrusted even after HMAC verification.
 */
const URL_PATTERN = /https?:\/\/[^\s<>"'`]+/gi;
const ID_PATTERN = /^[A-Za-z0-9_-]{4,160}$/;
const SUPPORTED_TYPES = new Set(['ig_reel','reel','ig_post','post','share','media_share','story_mention','story_reply']);

export function canonical(input){
  if(typeof input!=='string' || input.length>2048)return null;
  let url;
  try{ url=new URL(input.trim().replace(/[.,;!\]\)}]+$/g,'')); }catch{return null;}
  if(url.protocol!=='https:' || !['instagram.com','www.instagram.com'].includes(url.hostname.toLowerCase()) || url.port || url.username || url.password)return null;
  const path=url.pathname.split('/').filter(Boolean);
  if(path.length!==2 || !['reel','p','tv'].includes(path[0]) || !ID_PATTERN.test(path[1]))return null;
  return `https://www.instagram.com/${path[0]}/${path[1]}/`;
}

function gatherStrings(obj, acc, depth=0){
  if(depth>4 || acc.length>=80 || obj===null || obj===undefined)return;
  if(typeof obj==='string'){
    if(obj.length<=20000 && obj.includes('instagram.com'))acc.push(obj);
  } else if(Array.isArray(obj)){
    for(const item of obj.slice(0,30))gatherStrings(item,acc,depth+1);
  }else if(typeof obj==='object'){
    for(const [key,value] of Object.entries(obj).slice(0,40)){
      if(['url','permalink','link','text','media','share','story','reel','attachments','payload','caption'].includes(key))gatherStrings(value,acc,depth+1);
    }
  }
}
export function extractLinks(message){
  if(!message || typeof message!=='object')return [];
  const texts=[];
  gatherStrings(message.text,texts);
  gatherStrings(message.attachments,texts);
  gatherStrings(message.share,texts);
  gatherStrings(message.reel,texts);
  const urls=new Set();
  for(const value of texts){
    for(const match of value.matchAll(URL_PATTERN)){
      const link=canonical(match[0]);if(link)urls.add(link);
      if(urls.size>12)throw new Error('too_many_links');
    }
  }
  return [...urls];
}
export function collectApprovedEvents(payload,allowed,receiver){
  if(!payload || typeof payload!=='object' || payload.object!=='instagram' || !Array.isArray(payload.entry))throw new Error('invalid_instagram_envelope');
  if(payload.entry.length>100)throw new Error('too_many_events');
  const result=[];let total=0;
  for(const item of payload.entry){
    if(!item || typeof item!=='object')continue;
    if(!Array.isArray(item.messaging)){
      // If Meta changes the messaging envelope shape, never ACK and discard it.
      if(Array.isArray(item.changes) && item.changes.some(x=>x?.field==='messages'))throw new Error('unhandled_message_envelope');
      continue;
    }
    if(item.messaging.length>100)throw new Error('too_many_events');
    for(const event of item.messaging){
      if(++total>100)throw new Error('too_many_events');
      if(!event || typeof event!=='object' || event.thread || event.participants)continue;
      const sender=event.sender?.id,recipient=event.recipient?.id, msg=event.message;
      if(typeof sender!=='string' || !allowed.has(sender))continue;
      if(recipient!==receiver)throw new Error('approved_sender_unexpected_recipient');
      // Skip delivery/read metadata, not incoming messages.
      if(!msg || typeof msg!=='object')continue;
      if(msg.is_echo || msg.is_deleted)continue;
      if(typeof msg.mid!=='string' || !msg.mid || msg.mid.length>256)throw new Error('approved_message_missing_id');
      if(Array.isArray(msg.attachments) && msg.attachments.length>20)throw new Error('too_many_attachments');
      const urls=extractLinks(msg);
      const kinds=Array.isArray(msg.attachments)?msg.attachments.slice(0,20).map(a=>String(a?.type||'unknown').slice(0,50)):[];
      const suspected=kinds.length>0 || !!msg.share || !!msg.reel || (typeof msg.text==='string' && /(?:reel|instagram|http|www\.)/i.test(msg.text));
      result.push({sid:sender,mid:msg.mid,urls,status:urls.length?'queued':(suspected?'needs_review':'no_reel_link'),attachment_types:kinds});
    }
  }
  return result;
}