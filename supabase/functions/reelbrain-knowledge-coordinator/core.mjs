/** Pure control plane: does not download media or claim that metadata is full video analysis. */
export function canonicalQueuedReel(raw){
  if(typeof raw!=='string'||raw.length>2048)return null;
  try{
    const u=new URL(raw);
    if(u.protocol!=='https:'||!['instagram.com','www.instagram.com'].includes(u.hostname)||u.port||u.username||u.password||u.hash)return null;
    const path=u.pathname.split('/').filter(Boolean);
    if(path.length!==2||path[0]!=='reel'||!/^[A-Za-z0-9_-]{4,160}$/.test(path[1]))return null;
    return `https://www.instagram.com/reel/${path[1]}/`;
  }catch{return null;}
}
export function planPendingKnowledge(rows,existing,limit=30){
  const known=new Map((Array.isArray(existing)?existing:[]).filter(r=>typeof r?.source_url==='string').map(r=>[r.source_url,r]));
  const insert=[],update=[],seen=new Set();
  const capped=Math.min(Math.max(Number.isSafeInteger(limit)?limit:20,1),50);
  for(const row of Array.isArray(rows)?rows:[]){
    if(insert.length+update.length>=capped)break;
    if(!['queued','leased'].includes(row?.status))continue;
    const url=canonicalQueuedReel(row?.source_url);
    if(!url||seen.has(url))continue;
    seen.add(url);
    const old=known.get(url);
    if(!old){
      insert.push({source_url:url,source_provider:'meta_instagram_dm_webhook',
        processing_stage:'media_pending',video_analyzed:false,audio_transcribed:false,ocr_analyzed:false,
        verified_reel_content:{note:'Verified direct Instagram Reel link only; video frames, audio and OCR are not processed.'},
        content_evidence:[{kind:'signed_meta_webhook',source:'Instagram 1:1 Reel DM URL',level:'source_url_only'}]
      });
    }else if(old.processing_stage==='metadata_only')update.push(url);
  }
  return {insert,update};
}
export function summarizeQueue(rows){
  const r={queued:0,leased:0,dead_letter:0,terminal:0};
  for(const row of rows||[]){
    if(row?.status==='queued')r.queued++;
    else if(row?.status==='leased')r.leased++;
    else if(row?.status==='dead_letter')r.dead_letter++;
    else if(['processed','partial'].includes(row?.status))r.terminal++;
  }
  return r;
}