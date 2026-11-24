"""Real Apify actor can return /p/ permalink for an input /reel/ URL."""
import unittest
from reelbrain.acquire_apify import ApifyReelClient,AcquisitionError


class FakeResponse:
    def __init__(self,items):self.items=items
    def raise_for_status(self):pass
    def json(self):return self.items
class FakeHTTPClient:
    def __init__(self,items):self.items=items;self.calls=[]
    def post(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        return FakeResponse(self.items)

class ApifyIdentityTests(unittest.TestCase):
    def test_permalink_alias_same_shortcode_is_accepted(self):
        http=FakeHTTPClient([{
            'inputUrl':'https://www.instagram.com/reel/DgGHCjZIZtW/',
            'url':'https://www.instagram.com/p/DgGHCjZIZtW/',
            'shortCode':'DgGHCjZIZtW',
            'caption':'A project described in the video',
            'videoUrl':'https://scontent.example.fbcdn.net/v/file.mp4',
        }])
        client=ApifyReelClient('testtoken',client=http)
        result=client.inspect('https://www.instagram.com/reel/DgGHCjZIZtW/',allow_paid=True)
        self.assertEqual(result.shortcode,'DgGHCjZIZtW')
        self.assertEqual(result.url,'https://www.instagram.com/reel/DgGHCjZIZtW/')
        self.assertEqual(result.caption,'A project described in the video')
        args,kw=http.calls[0]
        self.assertEqual(kw['json']['username'],
                         ['https://www.instagram.com/reel/DgGHCjZIZtW/'])
        self.assertFalse(kw['json']['includeTranscript'])
        self.assertFalse(kw['json']['includeDownloadedVideo'])

    def test_provider_wrong_reel_is_rejected(self):
        http=FakeHTTPClient([{
            'shortCode':'WRONG123',
            'url':'https://www.instagram.com/p/WRONG123/'
        }])
        with self.assertRaises(AcquisitionError):
            ApifyReelClient('testtoken',client=http).inspect(
                'https://www.instagram.com/reel/DgGHCjZIZtW/',allow_paid=True)

    def test_no_paid_calls_without_explicit_gate(self):
        http=FakeHTTPClient([])
        with self.assertRaises(PermissionError):
            ApifyReelClient('testtoken',client=http).inspect(
                'https://www.instagram.com/reel/DgGHCjZIZtW/',allow_paid=False)
        self.assertEqual(len(http.calls),0)

if __name__=='__main__':unittest.main()
