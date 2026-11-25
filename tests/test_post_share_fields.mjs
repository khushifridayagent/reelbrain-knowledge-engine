import test from 'node:test';
import assert from 'node:assert/strict';
import { recoverApprovedMessage } from '../supabase/functions/reelbrain-dm-reconciler/core.mjs';
const mid='test_message_123',sender='123456',professional='654321';
test('explicit documented share subfields recover a static post',async()=>{
 const graph=async(path,params)=>{
  if(path===mid) return {id:mid,from:{id:sender}, ...(params.fields.includes('shares{type,url,id}')?{shares:{data:[{type:'ig_post',url:'https://www.instagram.com/p/Example123/?igsh=tracking'}]}}:{})};
  return {};
 };
 const result=await recoverApprovedMessage(graph,'fixture',mid,sender,professional);
 assert.equal(result.status,'queued');
 assert.deepEqual(result.urls,['https://www.instagram.com/p/Example123/']);
});
test('an unavailable or wrong-sender message does not become a job',async()=>{
 const graph=async()=>({id:mid,from:{id:'999999'},shares:{data:[{url:'https://www.instagram.com/p/Example123/'}]}});
 assert.equal(await recoverApprovedMessage(graph,'fixture',mid,sender,professional),null);
});
