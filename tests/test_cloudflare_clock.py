"""Node-native tests for the Cloudflare cron backup scheduler."""
import shutil, subprocess, unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('node'), 'Node.js is required for Cloudflare Worker test fixture')
class ClockTests(unittest.TestCase):
    def test_scheduled_dispatch_guardrails(self):
        root=Path(__file__).resolve().parent.parent
        testfile=root/'deploy'/'reelbrain-cloudflare-clock.test.mjs'
        p=subprocess.run(['node','--test',str(testfile)],cwd=root,
                         capture_output=True,text=True,timeout=25)
        self.assertEqual(p.returncode,0,p.stdout[-5000:]+p.stderr[-2000:])

if __name__=='__main__':unittest.main()
