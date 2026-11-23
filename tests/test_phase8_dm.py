import unittest
from reelbrain.instagram_dm import links_from_event, collect_dm_shares, instagram_url

class MetaDMIntakeTests(unittest.TestCase):
    def test_canonicalization_strips_tracking_and_refuses_lookalike(self):
        self.assertEqual(instagram_url('https://www.instagram.com/reel/ABCDE12/?utm_source=dm'),
                         'https://www.instagram.com/reel/ABCDE12/')
        self.assertIsNone(instagram_url('https://instagram.com.evil.com/reel/ABCDE12/'))
        self.assertIsNone(instagram_url('http://instagram.com/reel/ABCDE12/'))
    def test_new_2026_ig_reel_post_webhook_and_text(self):
        e={'sender':{'id':'111'},'recipient':{'id':'999'},'message':{'mid':'MID-1','attachments':[
          {'type':'ig_reel','payload':{'url':'https://www.instagram.com/reel/Aa11bb/?igsh=hi'}},
          {'type':'ig_post','payload':{'url':'https://www.instagram.com/p/Bb22cc/'}}],
          'text':'https://instagram.com/reel/Cc33dd/'}}
        self.assertEqual(set(links_from_event(e)),{
           'https://www.instagram.com/reel/Aa11bb/',
           'https://www.instagram.com/p/Bb22cc/',
           'https://www.instagram.com/reel/Cc33dd/'})
    def test_echo_deleted_group_and_unauthorized_senders_ignored(self):
        good={'sender':{'id':'111'},'recipient':{'id':'999'},'message':{'mid':'a','text':'https://instagram.com/reel/X12345/'}}
        bad={'sender':{'id':'222'},'recipient':{'id':'999'},'message':{'mid':'b','text':'https://instagram.com/reel/X12345/'}}
        self.assertEqual(len(collect_dm_shares({'object':'instagram','entry':[{'messaging':[good,bad]}]},'999',{'111'})),1)
        self.assertFalse(collect_dm_shares({'object':'instagram','entry':[{'messaging':[{**good,'message':{**good['message'],'is_echo':True}}]}]},'999',{'111'}))
        self.assertFalse(collect_dm_shares({'object':'instagram','entry':[{'messaging':[{**good,'thread':{'participants':3}}]}]},'999',{'111'}))
    def test_same_reel_shared_many_times_uses_durable_url_key(self):
        e={'sender':{'id':'111'},'recipient':{'id':'999'},'message':{'mid':'a','text':'https://instagram.com/reel/X12345/'}}
        duplicate={'sender':{'id':'111'},'recipient':{'id':'999'},'message':{'mid':'b','text':'https://instagram.com/reel/X12345/?igsh=foo'}}
        rows=collect_dm_shares({'object':'instagram','entry':[{'messaging':[e,duplicate]}]},'999',{'111'})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].source_url,'https://www.instagram.com/reel/X12345/')
        self.assertEqual(len(rows[0].sender_digest),64)
        self.assertNotIn('111',str(rows[0]))
if __name__=='__main__': unittest.main()
