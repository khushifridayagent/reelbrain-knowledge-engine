import test from 'node:test';
import assert from 'node:assert/strict';
import { canonical, extractLinks, collectApprovedEvents } from '../supabase/functions/reelbrain-instagram-dm/dm_extract.mjs';
const approved = new Set(['12345','67890','44444']);
const receiver = '99999';
const envelope = (...events) => ({object:'instagram',entry:[{id:receiver,messaging:events}]});
function event(sid,mid,msg){return {sender:{id:sid},recipient:{id:receiver},message:{mid,...msg}};}
test('canonical Instagram Reel/post URL rejects lookalike and tracking while preserving identity',()=>{
 assert.equal(canonical('https://instagram.com/reel/A1234/?igsh=x'), 'https://www.instagram.com/reel/A1234/');
 assert.equal(canonical('https://www.instagram.com/p/B2345/'),'https://www.instagram.com/p/B2345/');
 for(const x of ['http://instagram.com/reel/A1234/','https://instagram.com.evil.org/reel/A1234/','https://instagram.com/reel/%2f..','https://instagram.com/reel/a/'])assert.equal(canonical(x),null,x);
});
test('every approved message has receipt, even if no usable URL',()=>{
 const body=envelope(event('12345','A',{text:'Hello'}),event('67890','B',{attachments:[{type:'unknown_new_reel',payload:{id:'123'}}]}));
 const out=collectApprovedEvents(body,approved,receiver);
 assert.equal(out.length,2);assert.equal(out[0].status,'no_reel_link');assert.deepEqual(out[0].urls,[]);
 assert.equal(out[1].status,'needs_review');assert.deepEqual(out[1].urls,[]);
});
test('duplicate Reel sent by two accounts gives two distinct receipts, same queue link',()=>{
 const body=envelope(event('12345','A',{text:'https://instagram.com/reel/A1234/?a=1'}),event('67890','B',{text:'https://www.instagram.com/reel/A1234/'}));
 const out=collectApprovedEvents(body,approved,receiver);
 assert.equal(out.length,2);assert.deepEqual(out[0].urls,out[1].urls);
});
test('reject outsider, wrong receiver, group metadata and echo',()=>{
 const a=event('12345','A',{text:'https://instagram.com/reel/A1234/'});
 const b=event('intruder','B',{text:'https://instagram.com/reel/B1234/'});
 const c={...event('67890','C',{text:'https://instagram.com/reel/C1234/'}),thread:{participants:4}};
 const d={...event('44444','D',{text:'hello',is_echo:true})};
 const e={...event('12345','E',{text:'https://instagram.com/reel/E1234/'}),recipient:{id:'other'}};
 assert.deepEqual(collectApprovedEvents(envelope(a,b,c,d,e),approved,receiver).map(x=>x.mid),['A']);
});
test('parses url from Reel attachment, share attachment and nested payloads',()=>{
 const body=envelope(event('12345','F',{attachments:[
  {type:'ig_reel',payload:{url:'https://instagram.com/reel/X0123/?igsh=1'}},
  {type:'ig_post',payload:{permalink:'https://www.instagram.com/p/Y0123/'}},
  {type:'share',payload:{media:{permalink:'https://instagram.com/reel/Z0123/'}}}
 ]}));
 const out=collectApprovedEvents(body,approved,receiver);
 assert.equal(out.length,1);assert.deepEqual(out[0].urls, ['https://www.instagram.com/reel/X0123/','https://www.instagram.com/p/Y0123/','https://www.instagram.com/reel/Z0123/']);
});
test('detects excessive event lists instead of silently discarding tail',()=>{
 const array=Array.from({length:101},(_,i)=>event('12345',String(i),{text:'a'}));
 assert.throws(()=>collectApprovedEvents(envelope(...array),approved,receiver),/too_many_events/);
});