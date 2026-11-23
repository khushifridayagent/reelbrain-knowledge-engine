"""Optional local read-only MCP service. Not authenticated for public hosting.

Use over a trusted local/stdio connection only. Never publish a naked MCP
endpoint because tenant strings alone are not an authentication mechanism.
"""
from __future__ import annotations
from pathlib import Path
import os
from .store import KnowledgeStore

class LocalKnowledgeTools:
    def __init__(self,db_path):self.path=Path(db_path)
    def search_knowledge(self,query:str,tenant:str='personal',limit:int=10)->list[dict]:
        db=KnowledgeStore(self.path)
        try:return db.search(query,tenant,limit=min(max(limit,1),50))
        finally:db.close()
    def get_resource(self,resource_id:str,tenant:str='personal')->dict|None:
        db=KnowledgeStore(self.path)
        try:
            record=db.con.execute('SELECT * FROM resources WHERE id=? AND tenant=?',(resource_id,tenant)).fetchone()
            if record is None:return None
            data=dict(record)
            data['sources']=[dict(x) for x in db.con.execute('''SELECT s.source_ref,e.kind,e.locator,e.verbatim FROM citations c
              JOIN evidence e ON c.evidence_id=e.id AND c.source_id=e.source_id
              JOIN sources s ON e.source_id=s.id WHERE c.tenant=? AND c.resource_id=? ORDER BY s.source_ref''',(tenant,resource_id))]
            data['facts']=[dict(x) for x in db.con.execute('SELECT field_type,value,verbatim_quote,claim_status FROM facts WHERE tenant=? AND resource_id=?',(tenant,resource_id))]
            return data
        finally:db.close()
    def list_unresolved(self,tenant:str='personal',limit:int=100)->list[dict]:
        db=KnowledgeStore(self.path)
        try:return [dict(x) for x in db.con.execute('SELECT id,canonical_url,name,status FROM resources WHERE tenant=? AND status=? LIMIT ?', (tenant,'unresolved',max(1,min(limit,100))))]
        finally:db.close()


def main():
    try:from mcp.server.fastmcp import FastMCP
    except ImportError as exc:raise SystemExit('Install optional MCP package: pip install mcp') from exc
    tools=LocalKnowledgeTools(os.getenv('REELBRAIN_LOCAL_DB','data/reelbrain_local.db'))
    mcp=FastMCP('reelbrain-local')
    @mcp.tool()
    def search_knowledge(query:str,tenant:str='personal',limit:int=10)->list[dict]:
        """Return evidence-backed, not necessarily verified, resource cards."""
        return tools.search_knowledge(query,tenant,limit)
    @mcp.tool()
    def get_resource(resource_id:str,tenant:str='personal')->dict|None:
        """Return source observations and any explicitly stored claims."""
        return tools.get_resource(resource_id,tenant)
    @mcp.tool()
    def list_unresolved(tenant:str='personal')->list[dict]:
        """Return resources explicitly flagged unresolved."""
        return tools.list_unresolved(tenant)
    mcp.run(transport='stdio')

if __name__=='__main__':main()
