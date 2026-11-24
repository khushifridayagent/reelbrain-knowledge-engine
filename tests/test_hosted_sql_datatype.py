"""Regression: live hosted Reel transcript must persist without PostgreSQL $2 type ambiguity."""
import unittest
from contextlib import nullcontext
from reelbrain.hosted_transcript_job import _finalize

class Cursor:
    def __init__(self):self.calls=[];self.index=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,args=None):
        self.calls.append((sql,args))
        if "jsonb_build_object(" in sql:
            if "'provider',%s::text" not in sql or "'source_url',%s::text" not in sql:
                raise RuntimeError("PostgreSQL 42P18 could not infer jsonb_build_object parameter")
    def fetchone(self):return ('https://www.instagram.com/reel/DgGHCjZIZtW/',)

class DB:
    def __init__(self):self.cur=Cursor()
    def transaction(self):return nullcontext()
    def cursor(self):return self.cur

class HostedSQLRegression(unittest.TestCase):
    def test_real_provider_transcript_saves_with_explicit_pg_parameter_types(self):
        db=DB()
        src='https://www.instagram.com/reel/DgGHCjZIZtW/'
        transcript={'provider':'transcriptfetch','text':'A factual spoken tutorial',
                    'segments':[{'start':0,'end':3,'text':'A factual spoken tutorial'}]}
        self.assertTrue(_finalize(db,src,transcript))
        self.assertEqual(len(db.cur.calls),2)
        sql,params=db.cur.calls[0]
        self.assertEqual(params[1],'transcriptfetch')
        self.assertEqual(params[2],src)
        self.assertIn("provider_audio_transcript",sql)

if __name__=='__main__':unittest.main()
