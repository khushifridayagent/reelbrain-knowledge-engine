import test from 'node:test';
import assert from 'node:assert/strict';
import {reelEventsFromGraph, inspectParticipantIds} from '../supabase/functions/reelbrain-dm-reconciler/core.mjs';
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