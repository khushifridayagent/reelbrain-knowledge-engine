import shutil,tempfile,unittest
from pathlib import Path
from reelbrain.media import recognize_image,analyze_video,MediaError
from reelbrain.contracts import candidate_urls

@unittest.skipUnless(shutil.which('tesseract') and shutil.which('ffmpeg'),'OCR/media tools required')
class MediaProofTests(unittest.TestCase):
    def test_local_ocr_on_sample_image(self):
        from PIL import Image,ImageDraw,ImageFont
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'img.png'
            im=Image.new('RGB',(1280,330),'white');draw=ImageDraw.Draw(im)
            path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
            font=ImageFont.truetype(path,45)
            draw.text((28,90),'github.com/onyx-dot-app/onyx',font=font,fill='black')
            im.save(p)
            evidence=recognize_image(p,'slide:1')
            self.assertTrue(any('github.com/onyx-dot-app/onyx' in x.text for x in evidence),evidence)
            self.assertTrue(candidate_urls(evidence[0].text))
    def test_video_timestamp_and_detection(self):
        import cv2,numpy as np
        from PIL import Image,ImageDraw,ImageFont
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'short.mp4'
            writer=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*'mp4v'),8,(1280,400))
            if not writer.isOpened():self.skipTest('codec absent')
            font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',43)
            for i in range(24):
                im=Image.new('RGB',(1280,400),'white');draw=ImageDraw.Draw(im)
                text='github.com/onyx-dot-app/onyx' if 8<=i<13 else 'Test research video'
                draw.text((32,130),text,font=font,fill='black')
                writer.write(cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2BGR))
            writer.release()
            ev,stats=analyze_video(p,frame_rate=4,max_seconds=3,max_ocr_frames=30)
            self.assertTrue(any('github.com/onyx-dot-app/onyx' in x.text for x in ev),(ev,stats))
            self.assertTrue(any(x.locator.startswith('00:01') for x in ev))
            self.assertGreater(stats['ocr_frames'],0)
if __name__=='__main__':unittest.main()
