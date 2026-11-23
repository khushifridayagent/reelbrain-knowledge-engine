"""Authorized local media extraction. Does not download Instagram or upload video anywhere.

Dependencies: cv2 + system tesseract optional. Scene-aware sampling, not every frame.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,subprocess,shutil
from .contracts import Observation,candidate_urls

class MediaError(RuntimeError):pass

def _require(binary:str):
    if not shutil.which(binary):raise MediaError(f'{binary} is not installed')

def recognize_image(path:str|Path, locator:str='image:1')->list[Observation]:
    """Dense image/post OCR, respecting orientation and small on-screen text."""
    _require('tesseract')
    p=Path(path)
    if not p.is_file() or p.stat().st_size>60*1024*1024:
        raise MediaError('missing/oversized image')
    from PIL import Image,ImageOps
    import tempfile
    # Normalize EXIF orientation and upscale small text before Tesseract.
    # Keep original bytes unmodified; this transient image is never persisted.
    try:
        with tempfile.TemporaryDirectory(prefix='rb_img_ocr_') as td:
            with Image.open(p) as img:
                img=ImageOps.exif_transpose(img).convert('RGB')
                if img.width*img.height>18_000_000:
                    raise MediaError('image resolution exceeds OCR memory budget')
                scale=min(2.5,2400/max(img.width,img.height))
                if scale>1.1:
                    img=img.resize((int(img.width*scale),int(img.height*scale)),
                                   Image.Resampling.LANCZOS)
                image_input=Path(td)/'ocr.png'
                img.save(image_input)
            output=[]
            for psm in (3,6):
                try:
                    result=subprocess.run(
                        ['tesseract',str(image_input),'stdout','--psm',str(psm),'-l','eng+hin'],
                        text=True,capture_output=True,timeout=25,check=True)
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                    raise MediaError('OCR image pass failed') from exc
                output.append(result.stdout.strip())
            # Preserve the reading with best URL recall, then richer text.
            text=max(output,key=lambda raw:(len(candidate_urls(raw)),len(raw)))
    except (OSError,ValueError) as exc:
        raise MediaError('Unreadable image or failed OCR normalization') from exc
    return [Observation(text,kind='ocr',locator=locator)] if text else []

def analyze_video(path:str|Path,frame_rate:float=4.,max_seconds:float=180.,max_ocr_frames:int=120, scene_threshold:float=8.)->tuple[list[Observation],dict]:
    """Decode at <=4fps; OCR time anchors at 1fps and frames with large visual changes.

    Coverage is *not* guaranteed: fast text can be missed. Return metrics, never report a perfect scan.
    """
    try:import cv2
    except ImportError as exc:raise MediaError('pip install opencv-python-headless') from exc
    p=Path(path)
    if not p.is_file() or p.suffix.lower() not in {'.mp4','.mov','.mkv','.webm','.avi'}:raise MediaError('unsupported local media file')
    if not (0<frame_rate<=8 and 0<max_seconds<=3600 and 0<max_ocr_frames<=2000):raise ValueError('out-of-range resource budget')
    cap=cv2.VideoCapture(str(p))
    if not cap.isOpened():raise MediaError('could not decode media')
    fps=cap.get(cv2.CAP_PROP_FPS) or 25
    frame_count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration=(frame_count/fps) if frame_count>0 else None
    obs=[];previous=None;next_anchor=0.; sampled=0;decoded=0;recent_hashes=set()
    # Decoding every frame is expensive; seek to time samples, retaining 4Hz as upper bound.
    t=0.; step=1/frame_rate
    import tempfile
    try:
        with tempfile.TemporaryDirectory(prefix='reelbrain_ocr_') as temp:
            while t<max_seconds and sampled<max_ocr_frames:
                cap.set(cv2.CAP_PROP_POS_MSEC,t*1000)
                ok,frame=cap.read()
                if not ok:break
                decoded+=1
                gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
                thumb=cv2.resize(gray,(96,54))
                changed=previous is None or float(cv2.absdiff(thumb,previous).mean())>=scene_threshold
                previous=thumb
                anchor=(t+0.00001)>=next_anchor
                if anchor:next_anchor=float(int(t)+1)
                if changed or anchor:
                    # Caching near-identical images reduces repeated OCR.
                    thumbnail_hash=hashlib.blake2b(thumb.tobytes(),digest_size=8).hexdigest()
                    if thumbnail_hash not in recent_hashes:
                        recent_hashes.add(thumbnail_hash)
                        if len(recent_hashes)>50:recent_hashes.clear()
                        frame_path=Path(temp)/f'frame_{sampled:05}.png'
                        cv2.imwrite(str(frame_path),frame)
                        obs.extend(recognize_image(frame_path,locator=f'{int(t)//60:02}:{t%60:05.2f}'))
                        sampled+=1
                t+=step
    finally:cap.release()
    return obs,{'duration_seconds':duration,'sampled_time_steps':decoded,'ocr_frames':sampled,'partial_scan':bool(duration and duration>max_seconds),'max_seconds':max_seconds,'frame_rate':frame_rate}

def extract_audio(video_path:str|Path,output_path:str|Path)->Path:
    """Offline convert to 16k mono WAV for optional authorized ASR, no network."""
    _require('ffmpeg');p=Path(video_path);out=Path(output_path)
    if not p.is_file():raise MediaError('missing video')
    try:subprocess.run(['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y','-i',str(p),'-vn','-ac','1','-ar','16000',str(out)],check=True,timeout=120,capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:raise MediaError('failed to extract audio') from exc
    return out
