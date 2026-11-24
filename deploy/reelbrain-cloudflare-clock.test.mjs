import test from 'node:test';
import assert from 'node:assert/strict';
import { dispatchOnce } from './reelbrain-cloudflare-clock.mjs';

test('missing GitHub token cannot dispatch or leak credentials', async () => {
  let called=0;
  const result=await dispatchOnce({}, async()=>{called++;throw Error('network should not run');});
  assert.equal(result,'disabled_missing_token');
  assert.equal(called,0);
});
test('active workflow dispatches exactly once with non-expiring queue compatibility', async()=>{
  const calls=[];
  const fake=async (url,opts)=>{
    calls.push({url,method:opts?.method,body:opts?.body});
    if(opts.method==='GET') return {ok:true,status:200,json:async()=>({state:'active'})};
    if(opts.method==='POST') return {ok:true,status:204};
    throw Error('unexpected HTTP method');
  };
  const status=await dispatchOnce({GITHUB_TOKEN:'fixture-secret'},fake);
  assert.equal(status,'dispatched');
  assert.equal(calls.length,2);
  assert.ok(calls[0].url.endsWith('/repos/khushifridayagent/reelbrain-knowledge-engine/actions/workflows/reelbrain-media-batch.yml'));
  assert.ok(calls[1].url.endsWith('/dispatches'));
  assert.deepEqual(JSON.parse(calls[1].body),{ref:'main'});
});
test('inactivity-disabled schedule is explicitly reenabled before dispatch',async()=>{
  const methods=[];
  const fake=async(url,opts)=>{
    methods.push(opts.method);
    if(opts.method==='GET')return {ok:true,status:200,json:async()=>({state:'disabled_inactivity'})};
    return {ok:true,status:204};
  };
  const status=await dispatchOnce({GITHUB_TOKEN:'fixture-secret'},fake);
  assert.equal(status,'dispatched');
  assert.deepEqual(methods,['GET','PUT','POST']);
});
test('403 API errors are reported as fixed categories without secrets',async()=>{
  const secret='DO_NOT_PRINT_THIS';
  const status=await dispatchOnce({GITHUB_TOKEN:secret},async()=>({ok:false,status:403}));
  assert.equal(status,'github_access_denied');
  assert.ok(!status.includes(secret));
});
test('external fetch surface does not expose any dispatch endpoint',async()=>{
  const module=(await import('./reelbrain-cloudflare-clock.mjs')).default;
  const response=await module.fetch(new Request('https://internal-clock.example/trigger'),{GITHUB_TOKEN:'fixture'});
  assert.equal(response.status,404);
});
