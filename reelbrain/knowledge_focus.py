"""Knowledge-focused native screening, no QR or stored frame imagery.

Every decoded frame is screened for text-like changes; only selected original
resolution frames receive OCR. This is heuristic coverage, not perfect OCR.
"""
from __future__ import annotations
from pathlib import Path
from itertools import islice
import hashlib,json,math,os,subprocess,time
from concurrent.futures import ThreadPoolExecutor
from .contracts import Observation,candidate_urls
from .native_hybrid import Frame,NativeInspectionPending,digest,reconcile_ocr_reads
VERSION='knowledge-focus-v1'

def unique_knowledge(rows):
    """Retain distinct literal text, including uncertainty, with first locator."""
    seen=set();out=[]
    for x in rows:
        if x.kind not in ('ocr','ocr_uncertain') or not x.text.strip():continue
        key=(x.kind,' '.join(x.text.split()))
        if key not in seen:seen.add(key);out.append(x)
    return out

def focused_candidates(frames):
    """Screen every frame; short novel text is not subject to a sampling interval."""
    import cv2
    import numpy as np
    previous=None;last_selected=None;last_time=-1e9;count=0
    for f in frames:
        if f.index!=count or not math.isfinite(f.timestamp_ms):raise RuntimeError('native frame sequence incomplete')
        count+=1
        gray=cv2.cvtColor(f.pixels,cv2.COLOR_BGR2GRAY)
        # Keep original resolution for text-like stroke detection. A compact
        # maximum-pooled fingerprint preserves small local changes.
        kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(9,3))
        dark=cv2.morphologyEx(gray,cv2.MORPH_BLACKHAT,kernel)
        light=cv2.morphologyEx(gray,cv2.MORPH_TOPHAT,kernel)
        strokes=cv2.threshold(cv2.max(dark,light),24,255,cv2.THRESH_BINARY)[1]
        joined=cv2.morphologyEx(strokes,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(15,3)))
        n,labels,stats,_=cv2.connectedComponentsWithStats(joined,8)
        textmask=np.zeros_like(gray)
        for x,y,w,h,area in stats[1:]:
            if w>=16 and 3<=h<=max(20,gray.shape[0]//5) and w>=1.6*h and area>=32:
                textmask[y:y+h,x:x+w]=strokes[y:y+h,x:x+w]
        # A fixed-size fingerprint of local stroke density; no biometric data.
        thumb=cv2.resize(textmask,(96,96),interpolation=cv2.INTER_AREA)
        present=bool(np.max(thumb)>=18)
        # Detect spatially localized changes, including a single-frame overlay.
        if last_selected is None:novel=True
        else:
            delta=cv2.absdiff(thumb,last_selected)
            novel=bool(np.max(delta)>=38 and np.count_nonzero(delta>=14)>=3)
        scene=previous is None or float(np.mean(cv2.absdiff(cv2.resize(gray,(96,96)),previous)))>=24
        previous=cv2.resize(gray,(96,96))
        if f.index==0 or (present and (novel or f.timestamp_ms-last_time>=1800)) or scene:
            last_selected=thumb;last_time=f.timestamp_ms
            yield f

def focused_read(pixels):
    import cv2
    def read(image):
        ok,b=cv2.imencode('.png',image)
        if not ok:raise RuntimeError('focused frame encode failed')
        p=subprocess.run(['tesseract','stdin','stdout','-l','eng+hin','--psm','11'],
                         input=b.tobytes(),capture_output=True,timeout=30,
                         env={**os.environ,'OMP_THREAD_LIMIT':'1'})
        if p.returncode:raise RuntimeError('focused OCR failed')
        return p.stdout.decode('utf-8',errors='replace').strip()
    first=read(pixels)
    if not first:return []
    # A second enlarged pass is reserved for links, not repeated OCR on faces.
    if candidate_urls(first) or 'github' in first.lower() or 'http' in first.lower():
        h,w=pixels.shape[:2];factor=min(1.5,2400/max(h,w))
        enlarged=cv2.resize(pixels,None,fx=factor,fy=factor,interpolation=cv2.INTER_CUBIC) if factor>1 else pixels
        return reconcile_ocr_reads([first,read(enlarged)],[])
    return [Observation(first,kind='ocr')]

class FocusedOCR:
    checkpoint_version=VERSION
    def __init__(self,*,max_seconds=600,max_new_chunks=64,parallelism=2):
        self.deadline=time.monotonic()+max_seconds
        self.max_new_chunks=max_new_chunks;self.parallelism=parallelism
    def analyze(self,path,*,checkpoint=None,asset_index=0):
        import cv2
        import av
        path=Path(path);retained=[];screened=0;selected=0;new=0
        def inspect(stream,expected):
            nonlocal screened,selected,new
            def counted():
                nonlocal screened
                for f in stream:
                    screened+=1;yield f
            candidates=iter(focused_candidates(counted()))
            try:
                while True:
                    batch=list(islice(candidates,8))
                    if not batch:break
                    selected+=len(batch)
                    key=hashlib.sha256(json.dumps([(f.index,f.timestamp_ms,digest(f.pixels)) for f in batch]).encode()).hexdigest()
                    unit=f'{VERSION}:{asset_index}:{key}'
                    cached=checkpoint.load('ocr',unit=unit) if checkpoint else None
                    if cached is not None:retained.extend(cached[0]);continue
                    if new>=self.max_new_chunks or time.monotonic()>=self.deadline:
                        raise NativeInspectionPending('focused coverage pending: resume saved chunks',unique_knowledge(retained))
                    began=time.monotonic()
                    def one(f):
                        return [Observation(e.text,kind=e.kind,locator=f'frame:{f.index}@{f.timestamp_ms:.3f}ms',confidence=e.confidence) for e in focused_read(f.pixels)]
                    with ThreadPoolExecutor(max_workers=self.parallelism) as pool:
                        rows=[e for group in pool.map(one,batch) for e in group]
                    rows=unique_knowledge(rows)
                    if checkpoint:checkpoint.save('ocr',rows,int((time.monotonic()-began)*1000),unit=unit)
                    retained.extend(rows);new+=1
                if not screened or (expected is not None and screened!=expected):
                    raise RuntimeError('focused decode count incomplete')
                # Store counts only, not per-frame fingerprints or pictures.
                print(f'FOCUSED_SCREEN frames={screened} selected={selected} observations={len(unique_knowledge(retained))}',flush=True)
                return unique_knowledge(retained)
            except NativeInspectionPending:raise
            except Exception:raise NativeInspectionPending('focused OCR incomplete; resume saved chunks',unique_knowledge(retained)) from None
            finally:candidates.close()
        if path.suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
            pixels=cv2.imread(str(path))
            if pixels is None:raise NativeInspectionPending('image decode failed',[])
            return inspect([Frame(0,0.,pixels)],1)
        with av.open(str(path)) as container:
            if not container.streams.video:raise NativeInspectionPending('no video stream',[])
            video=container.streams.video[0]
            def frames():
                for i,f in enumerate(container.decode(video)):
                    if f.pts is None or f.time_base is None:raise RuntimeError('native timestamp missing')
                    yield Frame(i,float(f.pts*f.time_base)*1000.,f.to_ndarray(format='bgr24'))
            return inspect(frames(),int(video.frames or 0) or None)
