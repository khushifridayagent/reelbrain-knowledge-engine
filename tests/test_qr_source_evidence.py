"""Tests: deterministic QR source evidence, including small links in images/Reels."""
import shutil, tempfile, unittest
from pathlib import Path
import cv2
import numpy as np
from reelbrain.contracts import candidate_urls, evidence_filter


def qr_canvas(text,width=700,height=460):
    encoder=cv2.QRCodeEncoder_create()
    q=encoder.encode(text)
    q=cv2.resize(q,(260,260),interpolation=cv2.INTER_NEAREST)
    board=np.full((height,width,3),255,np.uint8)
    board[40:300,40:300]=cv2.cvtColor(q,cv2.COLOR_GRAY2BGR)
    return board


@unittest.skipUnless(hasattr(cv2,'QRCodeEncoder_create'),'OpenCV QR encoder not installed')
class QRProofTests(unittest.TestCase):
    def test_extract_undisclosed_repo_url_from_visible_qr(self):
        from reelbrain.qr_evidence import decode_qr_codes
        original='https://github.com/onyx-dot-app/onyx'
        readings=decode_qr_codes(qr_canvas(original))
        self.assertEqual(readings,[original])

    def test_qr_is_first_party_evidence_not_llm_hallucination(self):
        from reelbrain.contracts import Observation
        url='https://github.com/onyx-dot-app/onyx'
        ob=Observation(url,kind='qr',locator='slide:02/image:qr:1',confidence=1.0)
        found=evidence_filter(candidate_urls(ob.text),[ob])
        self.assertEqual(len(found.accepted),1)
        self.assertEqual(found.accepted[0].url,url)
        self.assertEqual(found.accepted[0].evidence_ids,(ob.uid,))

    def test_qr_on_image_is_retained_even_when_tesseract_reads_no_text(self):
        if not shutil.which('tesseract'):self.skipTest('tesseract unavailable')
        from reelbrain.media import recognize_image
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'slide.png'
            cv2.imwrite(str(p),qr_canvas('https://github.com/onyx-dot-app/onyx'))
            output=recognize_image(p,locator='slide:03')
            self.assertTrue(any(ev.kind=='qr' and
                ev.text=='https://github.com/onyx-dot-app/onyx' and
                'slide:03' in ev.locator for ev in output),output)

    def test_multiple_20_page_carousel_coverage_is_preserved(self):
        from reelbrain.engine import LocalPipelineEngine
        from reelbrain.store import KnowledgeStore
        from reelbrain.qr_evidence import read_qr_image
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            files=[]
            for page in range(1,21):
                p=base/f'page_{page:02}.png'
                cv2.imwrite(str(p),qr_canvas(
                    f'https://example.org/slide-{page:02}'))
                files.append(p)
            store=KnowledgeStore(base/'evidence.sqlite')
            try:
                # Tests exactly 20 pages with no generative provider calls.
                result=LocalPipelineEngine(
                    store,ocr=lambda p:read_qr_image(p,'image:qr')).ingest(
                    files,'https://www.instagram.com/p/DgGHCjZIZtW/')
                self.assertEqual(result['asset_count'],20)
                self.assertGreaterEqual(result['stage_observations'].get('ocr',0),20)
                rows=store.con.execute(
                    "SELECT locator,verbatim FROM evidence WHERE kind='qr'").fetchall()
                self.assertEqual(len(rows),20)
                self.assertTrue(any('slide:20' in row['locator'] for row in rows))
            finally:store.close()

    def test_temporal_qr_capture_from_real_decoded_frames(self):
        from reelbrain.qr_evidence import scan_video_qr
        url='https://github.com/onyx-dot-app/onyx'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'short.mp4'
            w=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*'mp4v'),8,(700,460))
            if not w.isOpened():self.skipTest('MP4 encoder unavailable')
            empty=np.full((460,700,3),255,np.uint8)
            qr=qr_canvas(url)
            for frame in range(24):
                w.write(qr if 8<=frame<=18 else empty)
            w.release()
            found,coverage=scan_video_qr(p,scan_hz=5.0,max_seconds=4)
            self.assertTrue(any(q.text==url for q in found),found)
            self.assertTrue(all(q.kind=='qr' for q in found))
            self.assertTrue(any(q.locator.startswith('00:01') for q in found))
            self.assertFalse(coverage['partial_scan'])

    def test_no_url_fabricated_from_unreadable_frames(self):
        from reelbrain.qr_evidence import decode_qr_codes
        no_qr=np.full((220,220,3),255,np.uint8)
        self.assertEqual(decode_qr_codes(no_qr),[])


if __name__=='__main__':unittest.main()
