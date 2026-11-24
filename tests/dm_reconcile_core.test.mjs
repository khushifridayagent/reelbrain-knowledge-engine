import test from 'node:test';
import assert from 'node:assert/strict';
import {reelEventsFromGraph, inspectParticipantIds, linkedPageId, graphErrorCategory, validGraphId, resolvePageSession, listApprovedConversations, buildReceiptRecheck} from '../supabase/functions/reelbrain-dm-reconciler/core.mjs';
const sender='12345001',business='12345002';
test('Graph Reel attachment becomes a safe canonical receipt',()=>{
 const input=[{id:'mid.REEL1',from:{id:sender},created_time:'2026-11-23T21:23:00+0000',message:'',attachments:{data:[{type:'ig_reel',payload:{url:'https://www.instagram.com/reel/DaQLc80PIBU/?igsh=abc'}}]}}];
 const v=reelEventsFromGraph(input,sender,business);
 assert.equal(v.length,1);
 assert.equal(v[0].status,'queued');
 assert.deepEqual(v[0].urls,['https://www.instagram.com/reel/DaQLc80PIBU/']);
 assert.equal(JSON.stringify(v).includes('igsh='),false);
});
test('Unknown Reel presentation is queued for review without fake URL',()=>{
 const rows=[{id:'mid.REEL2',from:{id:sender},message:'A Reel!',attachments:{data:[{type:'ig_reel',payload:{}}]}}];
 const v=reelEventsFromGraph(rows,sender,business);
 assert.equal(v.length,1);
 assert.equal(v[0].status,'needs_review');
 assert.equal(v[0].urls.length,0);
});
test('Foreign sender and personal replies are rejected',()=>{
 const rows=[{id:'mid.INTRUDER',from:{id:'8888'},message:'https://www.instagram.com/reel/DaQLc80PIBU/'},
 {id:'mid.BIZ',from:{id:business},message:'https://www.instagram.com/reel/DaQLc80PIBU/'}];
 assert.deepEqual(reelEventsFromGraph(rows,sender,business),[]);
});
test('Conversation participants must include both IDs',()=>{
 assert.ok(inspectParticipantIds({data:[{id:sender},{id:business}]},sender,business));
 assert.equal(inspectParticipantIds({data:[{id:sender},{id:'88888'}]},sender,business),false);
});
test('only the linked Facebook Page may be used for conversations',()=>{
 assert.equal(linkedPageId({id:'12345003',instagram_business_account:{id:business}},business),'12345003');
 assert.equal(linkedPageId({id:'12345003',instagram_business_account:{id:'999999'}},business),null);
 assert.equal(linkedPageId({id:business},business),null);
});
test('Meta message IDs may contain dots and safe errors include numeric code only',()=>{
 assert.equal(validGraphId('mid.REEL1'),true);
 assert.equal(validGraphId('abc/def'),false);
 assert.equal(graphErrorCategory(400,{error:{code:190,error_subcode:463,message:'private'}}),'graph_http_400_code_190_sub_463');
});

test('user token resolves only exact linked Page and keeps token out of errors',async()=>{
 const calls=[];
 const graph=async(path,params,credential)=>{
  calls.push(path);
  if(path==='me')throw new Error('graph_http_400_code_100');
  return {data:[{id:'12345003',instagram_business_account:{id:business},access_token:'fixture-page-secret'},{id:'12345004',instagram_business_account:{id:'12345005'},access_token:'wrong'}]};
 };
 const session=await resolvePageSession(graph,'fixture-user-secret',business);
 assert.equal(session.id,'12345003');
 assert.equal(session.token,'fixture-page-secret');
 assert.equal(session.mode,'derived_page');
 assert.deepEqual(calls,['me','me/accounts']);
});
test('direct linked page requires no account enumeration',async()=>{
 const session=await resolvePageSession(async(path)=>{assert.equal(path,'me');return {id:'12345003',instagram_business_account:{id:business}}},'fixture-page-secret',business);
 assert.equal(session.mode,'direct_page');
});
test('expired token never falls back to enumerating accounts',async()=>{
 let n=0;
 await assert.rejects(resolvePageSession(async()=>{n++;throw new Error('graph_http_400_code_190_sub_463')},'fixture',business),/identity_page_graph_http_400_code_190_sub_463/);
 assert.equal(n,1);
});
test('unsupported filtered query falls back to same Page with no alternate account',async()=>{
 let n=0;
 const session={id:'12345003',token:'fixture'};
 const result=await listApprovedConversations(async(path,params,credential)=>{
  assert.equal(path,'12345003/conversations');assert.equal(credential,'fixture');
  n++;if(n===1)throw new Error('graph_http_400_code_100');
  assert.equal(params.user_id,undefined);return {data:[{id:'t_example'}]};
 },session,sender);
 assert.equal(n,2);assert.equal(result.data[0].id,'t_example');
});

test('previous unresolved messages are eligible for bounded rechecks but linked messages stay deduped',()=>{
 const state=buildReceiptRecheck([{message_id:'mid.linked',status:'queued'},{message_id:'mid.plain',status:'no_reel_link'},{message_id:'mid.review1',status:'needs_review'},{message_id:'mid.review2',status:'needs_review'},{message_id:'mid.review3',status:'needs_review'}],2);
 assert.equal(state.take('mid.linked'),false);
 assert.equal(state.take('mid.plain'),false);
 assert.equal(state.take('mid.new'),true);
 assert.equal(state.take('mid.new'),false);
 assert.equal(state.take('mid.review1'),true);
 assert.equal(state.take('mid.review2'),true);
 assert.equal(state.take('mid.review3'),false);
});
test('plain text is not a missing Reel receipt',()=>{
 const v=reelEventsFromGraph([{id:'mid.plain',from:{id:sender},message:'Hello'}],sender,business);
 assert.equal(v[0].status,'no_reel_link');
});
