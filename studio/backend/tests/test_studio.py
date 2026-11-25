import tempfile, unittest, os
from pathlib import Path
import numpy as np
from studio.core import canonical_instagram, plan_queries, SearchIndex, Document, reciprocal_rank, cited_answer
from studio.research import safe_public_url, github_repo, public_research_query
from studio.db import filter_args

class FakeModels:
    name='fixture-only'
    def embed(self,texts,query=False):
        return np.array([[float('trading' in s.lower() or 'alpaca' in s.lower()),float('workflow' in s.lower() or 'automation' in s.lower()),.1] for s in texts],dtype='float32')
    def rerank(self,query,docs):return [float('alpaca' in x.lower()) for x in docs]
class Core(unittest.TestCase):
    def test_canonical_only(self):
        self.assertEqual(canonical_instagram('https://instagram.com/p/Abcd123/?igsh=secret'),'https://www.instagram.com/p/Abcd123/')
        for url in ['http://instagram.com/p/Abcd/','https://instagram.com.evil/p/Abcd/','https://u:p@instagram.com/p/Abcd/','https://instagram.com:444/p/Abcd/','https://instagram.com/p/Abcd/extra']:
            with self.assertRaises(ValueError):canonical_instagram(url)
    def test_planner_and_fusion(self):
        self.assertLessEqual(len(plan_queries('Alpaca trading workflow')),4)
        self.assertEqual(reciprocal_rank([['a','b'],['b','c']])[0],'b')
    def test_index_hybrid_filters_and_incremental_replace(self):
        with tempfile.TemporaryDirectory() as d:
            idx=SearchIndex(Path(d)/'x.sqlite',FakeModels())
            docs=[Document('a','https://www.instagram.com/reel/Abcd/','creator','2026-11-20','2026-11-22','completed','ocr','slide:10','Alpaca trading automation'),Document('b','https://www.instagram.com/p/Efgh/','other','2026-11-21','2026-11-23','completed','ocr','slide:1','workflow for images')]
            for x in docs:idx.replace_source(x.source,[x],'2026-11-23T00:00:00+00:00')
            result=idx.search('trading automation', ['Alpaca','trading automation'],{'creator':'creator'},8)
            self.assertEqual([r['source'] for r in result], [docs[0].source])
            self.assertEqual(result[0]['evidence'][0]['locator'],'slide:10')
            idx.replace_source(docs[0].source,[Document('c',docs[0].source,'creator','2026-11-20','2026-11-22','completed','ocr','slide:11','new words')],'2026-11-24T00:00:00+00:00')
            self.assertEqual(idx.get_sources([docs[0].source])[0]['evidence'][0]['text'],'new words')
    def test_grounded_output(self):
        self.assertEqual(cited_answer({'answer':'fake','citations':['S99']},{'S1'}),None)
        self.assertEqual(cited_answer({'answer':'fact [S1]','citations':['S1']},{'S1'})['citations'],['S1'])
    def test_public_research_boundaries(self):
        self.assertEqual(github_repo('https://github.com/owner/project/tree/main'),('owner','project'))
        self.assertIsNone(github_repo('https://evil.com/github.com/owner/project'))
        for u in ['https://127.0.0.1/x','https://localhost/','https://169.254.169.254/x','file:///etc/passwd','https://u:p@example.org/']:
            self.assertFalse(safe_public_url(u))
        self.assertEqual(public_research_query('Alpaca API docs'), 'Alpaca API docs')
        with self.assertRaises(ValueError):public_research_query('https://private.example/path?token=secret')
    def test_date_filter_validation(self):
        with self.assertRaises(ValueError):filter_args({'date_from':'2026-99-99'})
        self.assertEqual(filter_args({'creator':'@abc'})['creator'],'abc')
if __name__=='__main__':unittest.main()
