import tempfile,unittest
from pathlib import Path
from reelbrain.store import KnowledgeStore
from reelbrain.pipeline import KnowledgePipeline
class McpHelpersTests(unittest.TestCase):
    def test_tools_enforce_explicit_tenant(self):
        from reelbrain.mcp_server import LocalKnowledgeTools
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mcp.db';db=KnowledgeStore(p)
            try:
                KnowledgePipeline(db).ingest_report('a.md','See https://github.com/acme/alpha',tenant='alice')
                KnowledgePipeline(db).ingest_report('b.md','See https://github.com/different/bravo',tenant='bob')
            finally:db.close()
            tools=LocalKnowledgeTools(p)
            self.assertEqual(len(tools.search_knowledge('alpha',tenant='alice')),1)
            self.assertEqual(tools.search_knowledge('alpha',tenant='bob'),[])
            self.assertEqual(tools.list_unresolved(tenant='alice'),[])
            ids=tools.search_knowledge('alpha',tenant='alice')
            self.assertIsNotNone(tools.get_resource(ids[0]['resource_id'],tenant='alice'))
            self.assertIsNone(tools.get_resource(ids[0]['resource_id'],tenant='bob'))
