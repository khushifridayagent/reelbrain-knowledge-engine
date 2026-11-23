"""Export isolated, unverified historical research records for remote SQL import.

No network calls and no access to any existing cloud project; only a local
private SQLite database and a newly-created output directory are used.
"""
import argparse
from hashlib import sha256
from pathlib import Path
import json
from reelbrain.store import KnowledgeStore
from reelbrain.trending_import import trending_counts

TABLES={
 'archives':('trend_archives',('archive_sha','archive_name','source_id','coverage_json','verified_manifest_count','imported_at')),
 'catalog':('trend_catalog',('archive_sha','repo','catalog_number','repo_url','what_it_does','core_features','practical_use_cases','evidence','source_verification','verification_level','source_locator')),
 'daily_leaders':('trend_leaders',('archive_sha','day','row_json')),
 'ranked_entries':('trend_ranked',('archive_sha','day','source','rank','repo','row_json')),
 'capture_provenance':('trend_captures',('archive_sha','day','source','row_json')),
}

def export(db_file:str,folder:str,tenant='personal'):
    out=Path(folder)
    if out.exists() and list(out.iterdir()):raise FileExistsError('output folder must be new or empty')
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    database=KnowledgeStore(db_file)
    try:
        counts=trending_counts(database,tenant)
        if counts['archive_count']!=1:raise ValueError('expected exactly one research archive to avoid mixing sources')
        manifest={}
        for name,(table,cols) in TABLES.items():
            path=out/f'{name}.jsonl';n=0
            with path.open('w',encoding='utf8') as f:
                for row in database.con.execute('SELECT '+','.join(cols)+f' FROM {table} WHERE tenant=? ORDER BY archive_sha',(tenant,)):
                    record=dict(zip(cols,row))
                    if name=='archives':record['coverage_json']=json.loads(record['coverage_json'])
                    if 'row_json' in record:record['row_json']=json.loads(record['row_json'])
                    f.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n');n+=1
            manifest[name]={'rows':n,'file':path.name,'size_bytes':path.stat().st_size,'sha256':sha256(path.read_bytes()).hexdigest()}
        (out/'manifest.json').write_text(json.dumps({'target_project_ref':'xlkdzrhzizuftbnitodr','tenant':tenant,'tables':manifest},indent=2),encoding='utf8')
        return manifest
    finally:database.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('database');p.add_argument('output_folder');a=p.parse_args()
    print(json.dumps(export(a.database,a.output_folder),indent=2))
