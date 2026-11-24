"""Video text extraction must stream scene-change frames, not retain huge arrays."""
import unittest
from unittest.mock import patch
import numpy as np


class StreamingKeyframesTests(unittest.TestCase):
    def test_frame_analyse_does_not_materialize_changed_frame_list(self):
        from reelbrain import keyframes
        frame=np.zeros((12,16,3),dtype=np.uint8)
        def stream(path,hz,thresh):
            for t in (0.0,5.0,10.0):
                yield t,frame
        with patch.object(keyframes,'changed_frames',side_effect=AssertionError('must not retain all frames')):
            with patch.object(keyframes,'iter_changed_frames',side_effect=stream) as it:
                with patch.object(keyframes,'ocr',return_value=('working OCR evidence',95.0)):
                    events=keyframes.analyse('fixture.mp4')
        self.assertEqual([e.t for e in events],[0,5,10])
        self.assertEqual(len(events),3)
        it.assert_called_once()

    def test_scene_scan_can_be_stopped_without_full_video_memory(self):
        from reelbrain import keyframes
        frame=np.zeros((12,16,3),dtype=np.uint8)
        with patch.object(keyframes,'iter_frames',return_value=iter([(0.0,frame),(0.2,frame),(0.4,frame)])):
            changes=list(keyframes.iter_changed_frames('fixture.mp4',hz=10))
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0][0],0)
if __name__ == '__main__':
    unittest.main()
