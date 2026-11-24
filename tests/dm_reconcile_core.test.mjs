import test from 'node:test';
import assert from 'node:assert/strict';
import {reelEventsFromGraph, inspectParticipantIds, linkedPageId, graphErrorCategory, validGraphId} from '../supabase/functions/reelbrain-dm-reconciler/core.mjs';
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
