import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalQueuedReel, planPendingKnowledge, summarizeQueue } from '../supabase/functions/reelbrain-knowledge-coordinator/core.mjs';
const url='https://www.instagram.com/reel/DaQLc80PIBU/';

test('queued Instagram Reel without knowledge gets safe pending placeholder',()=>{
  const p=planPendingKnowledge([{id:5,status:'queued',source_url:url}],[],10);
  assert.equal(p.insert.length,1);
  assert.equal(p.insert[0].processing_stage,'media_pending');
  assert.equal(p.insert[0].video_analyzed,false);
  assert.equal(p.insert[0].audio_transcribed,false);
  assert.equal(p.insert[0].source_provider,'meta_instagram_dm_webhook');
  assert.deepEqual(p.update,[]);
});
test('existing metadata is never overwritten; stage upgrade is separate',()=>{
  const p=planPendingKnowledge([{id:5,status:'queued',source_url:url}], [{source_url:url,processing_stage:'metadata_only'}],10);
  assert.equal(p.insert.length,0);
  assert.deepEqual(p.update,[url]);
});
test('already processed or partial media is never downgraded',()=>{
  for(const status of ['completed','partial_media','blocked']){
    const p=planPendingKnowledge([{id:5,status:'queued',source_url:url}],[{source_url:url,processing_stage:status}],10);
    assert.deepEqual(p.update,[]);
    assert.deepEqual(p.insert,[]);
  }
});
test('ignore malicious URLs, leaked creds, other domains and done jobs',()=>{
  assert.equal(canonicalQueuedReel('https://www.instagram.com/reel/X1234/'), 'https://www.instagram.com/reel/X1234/');
  assert.equal(canonicalQueuedReel('https://instagram.com@evil.com/reel/X1234/'),null);
  assert.equal(canonicalQueuedReel('http://www.instagram.com/reel/X1234/'),null);
  const p=planPendingKnowledge([{id:1,status:'processed',source_url:url},{id:2,status:'queued',source_url:'https://attacker.example/reel/X1234/'}],[],10);
  assert.deepEqual(p.insert,[]);
});
test('bounded work batch and honest count summary',()=>{
  const r=summarizeQueue([{status:'queued'},{status:'queued'},{status:'dead_letter'},{status:'leased'}]);
  assert.deepEqual(r,{queued:2,leased:1,dead_letter:1,terminal:0});
  const p=planPendingKnowledge(Array.from({length:30},(_,i)=>({id:i,status:'queued',source_url:`https://www.instagram.com/reel/Test${i+1000}/`})),[],3);
  assert.equal(p.insert.length,3);
});