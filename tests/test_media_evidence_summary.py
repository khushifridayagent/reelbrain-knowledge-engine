import unittest
from reelbrain.media_evidence_summary import build_media_summary

class MediaSummaryTests(unittest.TestCase):
    def test_ocr_asr_are_source_evidence_with_locators_and_vlm_is_model_claim(self):
        events=[
            {'kind':'ocr','locator':'00:01.20','verbatim':'github.com/example/tool'},
            {'kind':'asr','locator':'0.0-4.2','verbatim':'Use the free server'},
            {'kind':'model_inference','locator':'gemini:00:04','verbatim':'Probably a demo of Google Cloud'}
        ]
        result={'media_processed':True,'stage_observations':{'ocr':1,'asr':1,'vlm':1},'unattempted_modalities':[],
                'stage_errors':{},'status':'evidence_saved','source_id':'TEST1','provider':'yt-dlp-public'}
        out=build_media_summary(events,result)
        self.assertTrue(out['video_analyzed'])
        self.assertTrue(out['audio_transcribed'])
        self.assertTrue(out['ocr_analyzed'])
        self.assertEqual(out['processing_stage'],'completed')
        self.assertEqual(len(out['content']['source_observations']),2)
        self.assertEqual(len(out['content']['model_inferences']),1)
        self.assertIn('00:01.20',[x['locator'] for x in out['content']['source_observations']])
        self.assertFalse(out['content'].get('verified_independently',False))

    def test_caption_alone_not_masquerading_as_frame_analysis(self):
        out=build_media_summary([{'kind':'caption','locator':'source:caption','verbatim':'A Reel about servers'}],
            {'media_processed':True,'stage_observations':{'ocr':0,'provided':1},'stage_errors':{'asr':'no audio'},'source_id':'X'})
        self.assertFalse(out['video_analyzed'])
        self.assertFalse(out['audio_transcribed'])
        self.assertTrue(out['ocr_analyzed'])
        self.assertEqual(out['processing_stage'],'partial_media')

    def test_without_media_receipt_never_marks_media_analyzed(self):
        out=build_media_summary([{'kind':'ocr','locator':'00:01','verbatim':'X'}],
            {'media_processed':False,'stage_observations':{'ocr':1},'source_id':'X'})
        self.assertFalse(out['video_analyzed'])
        self.assertFalse(out['ocr_analyzed'])
        self.assertEqual(out['processing_stage'],'media_pending')

    def test_malformed_or_huge_observations_are_bounded(self):
        result={'media_processed':True,'stage_observations':{'ocr':130},'source_id':'X'}
        out=build_media_summary([{'kind':'ocr','locator':'A'*500,'verbatim':'X'*9000}]*150,result)
        self.assertLessEqual(len(out['content']['source_observations']),80)
        self.assertLessEqual(len(out['content']['source_observations'][0]['text']),4000)
        self.assertLessEqual(len(out['content']['source_observations'][0]['locator']),64)

    def test_hosted_audio_with_required_visual_pass_can_complete(self):
        events=[{'kind':'ocr','locator':'00:01','verbatim':'Visible text'},
                {'kind':'model_inference','locator':'00:01','verbatim':'Visual explanation'}]
        base={'media_processed':True,'status':'evidence_saved',
              'stage_observations':{'ocr':1,'vlm':1},'stage_errors':{},
              'unattempted_modalities':['asr','structured_fact_model'],
              'audio_required':True}
        self.assertEqual(build_media_summary(events,base)['processing_stage'],'partial_media')
        good={**base,'hosted_audio_reused':'transcriptfetch'}
        self.assertEqual(build_media_summary(events,good)['processing_stage'],'completed')
        bad={**good,'stage_errors':{'vlm':'quota exceeded'}}
        self.assertEqual(build_media_summary(events,bad)['processing_stage'],'partial_media')
        bad={**good,'stage_observations':{'ocr':1,'vlm':0}}
        self.assertEqual(build_media_summary(events,bad)['processing_stage'],'partial_media')

if __name__=='__main__':unittest.main()