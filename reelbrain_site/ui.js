'use strict';
const $=(id)=>document.getElementById(id); $('access').value=sessionStorage.getItem('reelbrain_token')||'';
$('access').addEventListener('change',()=>sessionStorage.setItem('reelbrain_token',$('access').value.trim()));
const notice=(s)=>{$('notice').textContent=s;};
async function api(path,options={}){
  const token=$('access').value.trim();if(!token)throw Error('Enter your owner access token.');
  const res=await fetch(path,{...options,headers:{...(options.headers||{}),Authorization:'Bearer '+token},cache:'no-store'});
  let data;try{data=await res.json();}catch{throw Error('Server returned non-JSON response');}
  if(!res.ok)throw Error(data.detail||data.error||'Request failed');return data;
}
function el(tag,text,cls){const x=document.createElement(tag);x.textContent=text||'';if(cls)x.className=cls;return x;}
$('search').addEventListener('click',async()=>{const q=$('q').value.trim();if(q.length<2){notice('Type at least two characters.');return;}
  $('results').replaceChildren();notice('Searching...');
  try{const data=await api('/api/search?q='+encodeURIComponent(q));notice(`${data.results.length} evidence-indexed result(s).`);
    for(const hit of data.results){const card=el('article','','card');card.append(el('h3',hit.repo),el('p',hit.what_it_does||'Purpose not verified'),el('p','Evidence: '+hit.verification_level+' • '+hit.source_locator,'meta'));
      const link=el('a','Open source ↗');link.href=hit.repo_url;link.target='_blank';link.rel='noopener noreferrer';card.append(link);
      const btn=el('button','A bit more: capabilities & limitations','secondary');btn.style.marginLeft='1rem';const box=el('div','','');
      btn.addEventListener('click',async()=>{btn.disabled=true;box.textContent='Checking public GitHub evidence...';try{const data=await api('/api/details?url='+encodeURIComponent(hit.repo_url));box.textContent=JSON.stringify(data,null,2);}catch(e){box.textContent=e.message;}finally{btn.disabled=false;}});
      card.append(btn,box);$('results').append(card);}
  }catch(e){notice(e.message);}});
$('submit').addEventListener('click',async()=>{try{const data=await api('/api/intake',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:$('reel').value.trim()})});notice(`Queued / deduplicated: ${data.job.source_url} (${data.job.status})`);}catch(e){notice(e.message);}});
