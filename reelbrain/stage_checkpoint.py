"""Lease-fenced observation checkpoints, keyed by exact media bytes and stage version."""
import hashlib,json
from dataclasses import asdict
from threading import RLock
from .contracts import Observation

VERSION='media-pass-v2'

class StageCheckpoint:
    def __init__(self,pg,lease,url,paths):
        self.pg,self.lease,self.url=pg,lease,url
        self._lock=RLock()
        h=hashlib.sha256()
        for p in paths:
            h.update(p.stat().st_size.to_bytes(8,'big'))
            with p.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        self.sha=h.hexdigest()
    @staticmethod
    def _version(unit):
        return VERSION if unit is None else VERSION+'-unit-'+hashlib.sha256(unit.encode()).hexdigest()
    def load(self,stage,*,unit=None):
        with self._lock,self.pg.transaction():
            with self.pg.cursor() as cur:
                cur.execute("""select observations,elapsed_ms from reelbrain_research.media_stage_checkpoints
                    where source_url=%s and media_sha256=%s and pipeline_version=%s and stage=%s""",
                    (self.url,self.sha,self._version(unit),stage))
                row=cur.fetchone()
        if row is None:return None
        events,elapsed=row
        return [Observation(**x) for x in events],elapsed
    def save(self,stage,events,elapsed,*,unit=None):
        from .durable_worker import assert_lease
        with self._lock,self.pg.transaction():
            assert_lease(self.pg,self.lease)
            with self.pg.cursor() as cur:
                cur.execute("""insert into reelbrain_research.media_stage_checkpoints
                    (source_url,media_sha256,pipeline_version,stage,observations,elapsed_ms)
                    values (%s,%s,%s,%s,%s::jsonb,%s)
                    on conflict(source_url,media_sha256,pipeline_version,stage) do nothing""",
                    (self.url,self.sha,self._version(unit),stage,json.dumps([asdict(x) for x in events],ensure_ascii=False),elapsed))
        print('STAGE_CHECKPOINT_SAVED stage='+stage+' observations='+str(len(events)),flush=True)

    @staticmethod
    def _provider_key(key):
        if key not in ('gemini_vision','groq_vision','cloudflare_vision'):
            raise ValueError('unsupported hybrid provider')
        return key

    def provider_delay(self,key):
        key=self._provider_key(key)
        with self._lock,self.pg.transaction():
            with self.pg.cursor() as cur:
                cur.execute("""select greatest(0,ceil(extract(epoch from blocked_until-now())))::int
                    from reelbrain_research.hybrid_provider_cooldowns where provider=%s""",(key,))
                row=cur.fetchone()
        return int(row[0]) if row else 0

    def defer_provider(self,key,seconds):
        from .durable_worker import assert_lease
        key=self._provider_key(key)
        seconds=max(300,min(86400,int(seconds)))
        with self._lock,self.pg.transaction():
            assert_lease(self.pg,self.lease)
            with self.pg.cursor() as cur:
                cur.execute("""insert into reelbrain_research.hybrid_provider_cooldowns
                    (provider,blocked_until,updated_at) values (%s,now()+(%s * interval '1 second'),now())
                    on conflict(provider) do update set
                    blocked_until=greatest(reelbrain_research.hybrid_provider_cooldowns.blocked_until,excluded.blocked_until),
                    updated_at=now()""",(key,seconds))
