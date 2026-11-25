// Explicit, one-off hosted smoke; run in the trusted Studio build environment.
// Never print secrets, raw responses, user evidence, or provider payloads.
import { authorized, sameOrigin } from '../lib/auth.mjs';
const fail = (stage) => { console.error('STUDIO_SMOKE ' + stage + ' FAIL'); process.exit(1); };
const pass = (stage) => console.log('STUDIO_SMOKE ' + stage + ' PASS');
const pwd=process.env.STUDIO_OWNER_PASSWORD;
if(!pwd || !authorized('Basic '+Buffer.from('owner:'+pwd).toString('base64'),pwd))fail('owner_auth');
if(authorized('Basic '+Buffer.from('owner:wrong').toString('base64'),pwd))fail('owner_auth');
pass('owner_auth');
const origin=process.env.STUDIO_SITE_ORIGIN;
if(origin!=='https://reelbrain-knowledge-engine.vercel.app' || !sameOrigin(origin,'reelbrain-knowledge-engine.vercel.app',origin))fail('origin');
pass('origin');
const base=process.env.STUDIO_BACKEND_URL;
const token=process.env.STUDIO_HOST_TOKEN||process.env.STUDIO_BACKEND_TOKEN;
if(base!=='https://reelbrain-studio-api.vercel.app'||!token||token.length<32)fail('backend_configuration');
async function check(stage,path,body) {
  try {
    const r=await fetch(base+path,{method:body?'POST':'GET',headers:{authorization:'Bearer '+token,...(body?{'content-type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),redirect:'error',signal:AbortSignal.timeout(100000)});
    if(!r.ok){console.error('STUDIO_SMOKE '+stage+' HTTP '+r.status);fail(stage);}
    return await r.json();
  }catch{fail(stage);}
}
const ready=await check('ready','/ready');
if(ready.status!=='ready')fail('ready');pass('ready');
const counts=await check('counts','/counts',{question:'count saved items',mode:'count'});
if(!Number.isInteger(counts.total)||counts.total<1||!Number.isInteger(counts.posts))fail('counts');
pass('counts');
const search=await check('search','/search',{question:'GitHub tools and repositories',mode:'search',limit:3});
if(!Array.isArray(search.sources)||!search.sources.length||!search.answer?.answer||!Array.isArray(search.answer.citations)||!search.answer.citations.length)fail('search');
pass('search');
if(search.answer.kind==='saved_excerpts')fail('llm_synthesis');
pass('llm_synthesis');
