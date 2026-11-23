import os, sys, tempfile, shutil, unittest
sys.path.insert(0, os.path.dirname(__file__))
import make_clip
from reelbrain import keyframes


@unittest.skipUnless(shutil.which("tesseract") and shutil.which("ffmpeg"), "needs ffmpeg + tesseract")
class KeyframeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.clip = make_clip.build(os.path.join(cls.dir, "clip.mp4"))   # URL visible only 7.4-7.7 s

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_fixed_1fps_misses_the_flash(self):
        found = [c.value.lower() for e in keyframes.fixed_fps_baseline(self.clip, 1.0) for c in e.candidates]
        self.assertNotIn("onyx-dot-app/onyx", found)

    def test_pass_c_catches_the_flash_with_a_timestamp(self):
        ev = keyframes.analyse(self.clip)
        hits = [e for e in ev for c in e.candidates if c.value.lower() == "onyx-dot-app/onyx"]
        self.assertEqual(len(hits), 1)
        self.assertTrue(7.3 <= hits[0].t <= 7.8, hits[0].t)

    def test_scene_changes_found(self):
        times = [round(t) for t, _ in keyframes.changed_frames(self.clip)]
        self.assertEqual(times[0], 0)
        self.assertEqual(len(times), 5)                                  # 5 distinct visual states in the clip


if __name__ == "__main__":
    unittest.main()
