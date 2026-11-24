"""Lease-fenced observation checkpoints, keyed by exact media bytes and stage version."""
import hashlib,json
from dataclasses import asdict
from .contracts import Observation

VERSION='media-pass-v1'

class StageCheckpoint:
    def __init__(self,pg,lease,url,paths):
        self.pg,self.lease,self.url=pg,lease,url
        h=hashlib.sha256()
        for p in paths:
            h.update(p.stat().st_size.to_bytes(8,'big'))
            with p.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        self.sha=h.hexdigest()
    def load(self,stage):
        with self.pg.transaction():
            with self.pg.cursor() as cur:
                cur.execute("""select observations,elapsed_ms from reelbrain_research.media_stage_checkpoints
                    where source_url=%s and media_sha256=%s and pipeline_version=%s and stage=%s""",
                    (self.url,self.sha,VERSION,stage))
                row=cur.fetchone()
        if row is None:return None
        events,elapsed=row
        return [Observation(**x) for x in events],elapsed
    def save(self,stage,events,elapsed):
        from .durable_worker import assert_lease
        with self.pg.transaction():
            assert_lease(self.pg,self.lease)
            with self.pg.cursor() as cur:
                cur.execute("""insert into reelbrain_research.media_stage_checkpoints
                    (source_url,media_sha256,pipeline_version,stage,observations,elapsed_ms)
                    values (%s,%s,%s,%s,%s::jsonb,%s)
                    on conflict(source_url,media_sha256,pipeline_version,stage) do nothing""",
                    (self.url,self.sha,VERSION,stage,json.dumps([asdict(x) for x in events],ensure_ascii=False),elapsed))
        print('STAGE_CHECKPOINT_SAVED stage='+stage+' observations='+str(len(events)),flush=True)
