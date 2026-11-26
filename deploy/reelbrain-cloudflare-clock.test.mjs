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
    if(url.includes('/runs?'))return {ok:true,json:async()=>({workflow_runs:[]})};
    if(opts.method==='GET') return {ok:true,status:200,json:async()=>({state:'active'})};
    if(opts.method==='POST') return {ok:true,status:204};
    throw Error('unexpected HTTP method');
  };
  const status=await dispatchOnce({GITHUB_TOKEN:'fixture-secret'},fake);
  assert.equal(status,'dispatched');
  assert.equal(calls.length,3);
  assert.ok(calls[0].url.endsWith('/repos/khushifridayagent/reelbrain-knowledge-engine/actions/workflows/reelbrain-media-batch.yml'));
  assert.ok(calls[2].url.endsWith('/dispatches'));
  assert.deepEqual(JSON.parse(calls[2].body),{ref:'main'});
});
test('inactivity-disabled schedule is explicitly reenabled before dispatch',async()=>{
  const methods=[];
  const fake=async(url,opts)=>{
    methods.push(opts.method);
    if(url.includes('/runs?'))return {ok:true,json:async()=>({workflow_runs:[]})};
    if(opts.method==='GET')return {ok:true,status:200,json:async()=>({state:'disabled_inactivity'})};
    return {ok:true,status:204};
  };
  const status=await dispatchOnce({GITHUB_TOKEN:'fixture-secret'},fake);
  assert.equal(status,'dispatched');
  assert.deepEqual(methods,['GET','PUT','GET','POST']);
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

test('existing pending successor is not replaced by a fresh dispatch', async()=>{
  for(const state of ['queued','pending','waiting','requested']){
    const methods=[];
    const fake=async(url,opts)=>{
      methods.push(opts.method);
      if(url.includes('/runs?'))return {ok:true,json:async()=>({workflow_runs:[{status:'in_progress'},{status:state}]})};
      if(opts.method==='GET')return {ok:true,json:async()=>({state:'active'})};
      return {ok:true,status:204};
    };
    assert.equal(await dispatchOnce({GITHUB_TOKEN:'fixture'},fake),'already_queued');
    assert.deepEqual(methods,['GET','GET']);
  }
});
test('a running batch without a successor may enqueue exactly one next batch',async()=>{
  const calls=[];
  const fake=async(url,opts)=>{
    calls.push(opts.method);
    if(url.includes('/runs?'))return {ok:true,json:async()=>({workflow_runs:[{status:'in_progress'},{status:'completed'}]})};
    if(opts.method==='GET')return {ok:true,json:async()=>({state:'active'})};
    return {ok:true,status:204};
  };
  assert.equal(await dispatchOnce({GITHUB_TOKEN:'fixture'},fake),'dispatched');
  assert.deepEqual(calls,['GET','GET','POST']);
});
test('unknown or unavailable queue state fails closed',async()=>{
  for(const reply of [{ok:false,status:503},{ok:true,json:async()=>({})},{ok:true,json:async()=>({workflow_runs:[{status:'unknown'}]})}]){
    const calls=[];
    const fake=async(url,opts)=>{
      calls.push(opts.method);
      if(url.includes('/runs?'))return reply;
      if(opts.method==='GET')return {ok:true,json:async()=>({state:'active'})};
      return {ok:true,status:204};
    };
    assert.notEqual(await dispatchOnce({GITHUB_TOKEN:'fixture'},fake),'dispatched');
    assert.deepEqual(calls,['GET','GET']);
  }
});
test('explicitly disabled workflow is not reenabled by the clock',async()=>{
  const calls=[];
  const status=await dispatchOnce({GITHUB_TOKEN:'fixture'},async(url,opts)=>{
    calls.push(opts.method);
    return {ok:true,json:async()=>({state:'disabled_manually'})};
  });
  assert.equal(status,'workflow_disabled');
  assert.deepEqual(calls,['GET']);
});
