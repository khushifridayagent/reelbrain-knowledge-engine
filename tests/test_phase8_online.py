import unittest
from unittest.mock import patch
from reelbrain.online_research import repository_name, summarize_repository, ResearchUnavailable

class ResearchTests(unittest.TestCase):
    def test_only_canonical_github_repository(self):
        self.assertEqual(repository_name('https://github.com/onyx-dot-app/onyx/issues/1'),'onyx-dot-app/onyx')
        for url in ('http://github.com/foo/bar','https://github.com.evil.com/foo/bar','https://github.com/foo','https://github.com/foo/bar?token=hello'):
            with self.subTest(url=url):self.assertIsNone(repository_name(url))
    def test_returns_source_based_capabilities_and_limitations(self):
        def fake_json(path):
            if path.endswith('/readme'):
                return {'content':'IyBNaW5pIENvcmUKCi0gU2VhcmNoIGluZGV4ZXMgZmlsZXMK','encoding':'base64','html_url':'https://github.com/example/mini/blob/main/README.md'}
            return {'full_name':'example/mini','html_url':'https://github.com/example/mini',
                    'description':'A search tool','archived':False,'stargazers_count':14,
                    'pushed_at':'2026-11-01T00:00:00Z','license':{'spdx_id':'MIT'},
                    'open_issues_count':4}
        with patch('reelbrain.online_research._fetch_json',side_effect=fake_json):
            result=summarize_repository('https://github.com/example/mini')
        self.assertEqual(result['status'],'repository_readme_checked')
        self.assertEqual(result['execution_status'],'not_tested')
        self.assertIn('source_url',result)
        self.assertTrue(result['limitations'])
        self.assertIn('Search indexes',result['readme_excerpts'][0])
    def test_other_sites_require_external_research_provider(self):
        with self.assertRaises(ResearchUnavailable):summarize_repository('https://example.com')
if __name__=='__main__':unittest.main()
