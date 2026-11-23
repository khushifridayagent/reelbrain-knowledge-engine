'use strict';
const $=(id)=>document.getElementById(id);
const token=$('token'), link=$('link'), status=$('status'), results=$('results');
const share=document.querySelector('meta[name="incoming-url"]');
if(share && share.content)link.value=share.content;
token.value=sessionStorage.getItem('reelbrain-session-token')||'';
token.addEventListener('change',()=>sessionStorage.setItem('reelbrain-session-token',token.value));
async function api(path,method='GET',body){
 const opts={method,headers:{Authorization:'Bearer '+token.value}};
 if(body){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body)}
 const r=await fetch(path,opts);const v=await r.json();
 if(!r.ok)throw Error(v.detail||'HTTP '+r.status);return v;
}
$('save').addEventListener('click',async()=>{
 status.textContent='Saving…';
 try{const v=await api('/api/intake/link','POST',{url:link.value});status.textContent='Saved: '+v.canonical_url+'\nStatus: '+v.status+' (media not yet processed).'}
 catch(e){status.textContent='Could not save: '+e.message}
});
$('search').addEventListener('click',async()=>{
 results.textContent='Searching…';
 try{const v=await api('/api/search?q='+encodeURIComponent($('query').value));results.replaceChildren();
 if(!v.hits.length)results.textContent='No match in imported historical catalog.';
 for(const x of v.hits){const article=document.createElement('article');const a=document.createElement('a');
 a.href=x.repo_url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=x.repo;
 const p=document.createElement('p');p.textContent=x.what_it_does+'\nVerification: '+x.verification_level+'\nSource: '+x.source_locator;
 article.append(a,p);results.append(article)}
 }catch(e){results.textContent='Search failed: '+e.message}
});
$('pending').addEventListener('click',async()=>{
 try{const v=await api('/api/pending');$('pending-list').textContent=v.items.length?v.items.map(x=>x.source_ref+' — '+x.status).join('\n'):'Inbox clear.'}
 catch(e){$('pending-list').textContent=e.message}
});

$('upload').addEventListener('click',async()=>{
 const output=$('upload-status'), file=$('media-file').files[0];
 if(!file){output.textContent='Choose a permitted image or video first.';return}
 output.textContent='Uploading to private inbox…';
 const form=new FormData();form.set('url',link.value);form.set('file',file);
 try{const response=await fetch('/api/intake/media',{method:'POST',headers:{Authorization:'Bearer '+token.value},body:form});
 const data=await response.json();if(!response.ok)throw Error(data.detail||'upload failed');
 output.textContent='Upload received. Task '+data.task_id+' — local processing has been requested. Check its status before assuming extraction succeeded.';
 }catch(e){output.textContent='Upload failed: '+e.message}
});

if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
