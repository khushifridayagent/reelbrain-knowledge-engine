"""Deterministic, offline QR evidence from ACTUAL video frames or post pages.

All payloads are untrusted text. Nothing is executed or fetched; URL candidates
are accepted only via the normal evidence-backed resource resolver.
"""
from __future__ import annotations
from pathlib import Path
import math
import cv2
import numpy as np
from .contracts import Observation


def decode_qr_codes(frame: np.ndarray, *, max_codes:int=16) -> list[str]:
    if not isinstance(frame,np.ndarray) or frame.ndim not in (2,3):
        raise ValueError('QR scan requires decoded image pixels')
    if frame.size==0 or frame.shape[0]*frame.shape[1]>20_000_000:
        raise ValueError('QR scan image exceeds bounded pixel budget')
    if not 1<=max_codes<=32:raise ValueError('QR code limit invalid')
    qr=cv2.QRCodeDetector()
    payloads=[]
    try:
        ok,data,_corners,_=qr.detectAndDecodeMulti(frame)
        if ok:payloads.extend(data)
    except (cv2.error,ValueError,TypeError):
        pass
    if not payloads:
        try:
            text,_,_=qr.detectAndDecode(frame)
            if text:payloads.append(text)
        except (cv2.error,ValueError,TypeError):
            pass
    unique=[]
    for value in payloads:
        if not isinstance(value,str) or not value.strip():continue
        value=value.strip()
        # Never preserve control bytes or oversized QR payload as a DB entry.
        if len(value.encode('utf-8'))>2048 or any(ord(ch)<32 for ch in value):
            continue
        if value not in unique:unique.append(value)
        if len(unique)>=max_codes:break
    return unique


def read_qr_image(path:Path|str,locator:str='image:1')->list[Observation]:
    from PIL import Image,ImageOps
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>60*1024*1024:
        raise ValueError('QR image must be a bounded regular file')
    with Image.open(p) as photo:
        photo=ImageOps.exif_transpose(photo).convert('RGB')
        if photo.width*photo.height>20_000_000:
            raise ValueError('QR image too large to decode safely')
        pixels=cv2.cvtColor(np.asarray(photo),cv2.COLOR_RGB2BGR)
    values=decode_qr_codes(pixels)
    return [Observation(value,kind='qr',locator=locator+'/qr:'+str(i),confidence=1.0)
            for i,value in enumerate(values,1)]


def scan_video_qr(path:Path|str, *, scan_hz:float=5.0,
                  max_seconds:float=300.0,max_frames:int=1500)->tuple[list[Observation],dict]:
    """Read visible QR at <=5Hz; preserve first actual timestamp per payload.

    The 300s / max_frames bound prevents unbounded GitHub Actions runtime.
    Full-video coverage is NOT claimed if video is longer than these limits.
    """
    if not (0<scan_hz<=10 and 1<=max_seconds<=900 and 1<=max_frames<=9000):
        raise ValueError('Invalid QR scan bounds')
    p=Path(path)
    if p.suffix.lower() not in {'.mp4','.mov','.mkv','.avi','.webm'} or not p.is_file():
        raise ValueError('QR scan video must be a local media file')
    cap=cv2.VideoCapture(str(p))
    if not cap.isOpened():
        cap.release()
        raise ValueError('Unable to decode video for QR scan')
    try:
        fps=float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total=float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration=total/fps if total and math.isfinite(fps) and fps>0 else None
    finally:cap.release()
    from .keyframes import iter_frames
    seen=set();obs=[];tested=0
    for t,frame in iter_frames(str(p),hz=scan_hz,end=max_seconds):
        if tested>=max_frames:break
        tested+=1
        for payload in decode_qr_codes(frame):
            if payload in seen:continue
            seen.add(payload)
            minute,sec=divmod(float(t),60)
            obs.append(Observation(payload,kind='qr',
                                   locator=f'{int(minute):02}:{sec:05.2f}/qr',
                                   confidence=1.0))
            if len(obs)>=200:break
        if len(obs)>=200:break
    partial=bool(duration is None or duration>max_seconds+0.0001 or
                 (tested>=max_frames and duration>tested/scan_hz+0.5) or
                 len(obs)>=200)
    return obs,{'sampled_frames':tested,'duration_seconds':duration,
                'scan_hz':scan_hz,'partial_scan':partial,'qr_codes':len(obs)}
