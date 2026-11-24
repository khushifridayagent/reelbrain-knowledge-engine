"""Closing a streaming video iterator must release its OpenCV decoder."""
import unittest
from unittest.mock import patch
import numpy as np

from reelbrain import keyframes


class FakeCapture:
    released=False
    def isOpened(self):return True
    def get(self,property_id):return 25.0
    def grab(self):return True
    def retrieve(self):return True,np.zeros((8,8,3),dtype=np.uint8)
    def set(self,*args):return True
    def release(self):self.released=True


class VideoDecoderLifecycleTests(unittest.TestCase):
    def test_close_releases_opencv_decoder(self):
        cap=FakeCapture()
        with patch.object(keyframes.cv2,'VideoCapture',return_value=cap):
            stream=keyframes.iter_frames('dummy.mp4',hz=5)
            next(stream)
            stream.close()
        self.assertTrue(cap.released)

    def test_invalid_sampling_hz_fails_cleanly(self):
        with self.assertRaises(ValueError):
            list(keyframes.iter_frames('dummy.mp4',hz=0))


if __name__=='__main__':
    unittest.main()
