"""Pass C: deterministic, LLM-free frame pipeline.
1. hash every ~10th-of-a-second frame (dHash) and keep only frames whose content changed,
2. OCR the kept frames with Tesseract (local, free),
3. when a frame looks URL-ish, re-sample a +/- window densely and keep the best OCR reading.
A fixed 1 FPS sampler misses text shown for under a second; this does not."""
from __future__ import annotations
import csv, io, os, subprocess, tempfile
from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import numpy as np

from .links import extract_candidates, looks_url_ish


@dataclass
class FrameEvent:
    t: float                 # seconds
    text: str
    conf: float              # mean tesseract word confidence 0-100
    candidates: list         # links.Candidate found in text
    refined: bool = False    # True if it came from a dense re-sample


def dhash(img_bgr: np.ndarray, size: int = 16) -> np.ndarray:
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size + 1, size), interpolation=cv2.INTER_AREA)
    return (g[:, 1:] > g[:, :-1]).flatten()


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def ocr(img_bgr: np.ndarray, psm: int = 6, lang: str = "eng+hin") -> "tuple[str, float]":
    """Tesseract on an upscaled grayscale frame. Returns (text, mean word confidence)."""
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    if g.shape[1] < 1600:
        g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.png")
        cv2.imwrite(p, g)
        res = subprocess.run(["tesseract", p, "stdout", "--psm", str(psm), "-l", lang, "tsv"],
                             capture_output=True, text=True, timeout=60)
    words, confs = [], []
    for row in csv.DictReader(io.StringIO(res.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        t = (row.get("text") or "").strip()
        try:
            c = float(row.get("conf", "-1"))
        except ValueError:
            c = -1
        if t and c >= 0:
            words.append((int(row["block_num"]), int(row["par_num"]), int(row["line_num"]), t))
            confs.append(c)
    lines: dict = {}
    for b, p_, l, t in words:
        lines.setdefault((b, p_, l), []).append(t)
    return "\n".join(" ".join(v) for v in lines.values()), (sum(confs) / len(confs) if confs else 0.0)


def iter_frames(path: str, hz: float, start: float = 0.0, end: Optional[float] = None) -> Iterator["tuple[float, np.ndarray]"]:
    if hz <= 0 or hz > 60 or start < 0 or (end is not None and end < start):
        raise ValueError('Invalid video sampling bounds')
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise ValueError('Original video could not be decoded')
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps / hz))
        if start:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
        i = int(start * fps)
        while True:
            ok = cap.grab()
            if not ok:
                break
            t = i / fps
            if end is not None and t > end:
                break
            if (i - int(start * fps)) % step == 0:
                ok, frame = cap.retrieve()
                if ok:
                    yield t, frame
            i += 1
    finally:
        cap.release()


def iter_changed_frames(path: str, hz: float = 10.0, thresh: int = 12) -> Iterator["tuple[float, np.ndarray]"]:
    """Yield scene-change frames incrementally without buffering entire videos."""
    last = None
    for t, frame in iter_frames(path, hz):
        current = dhash(frame)
        if last is None or hamming(current, last) >= thresh:
            yield t, frame
            last = current


def changed_frames(path: str, hz: float = 10.0, thresh: int = 12) -> list:
    """Legacy list-returning API used by fixture tests only."""
    return list(iter_changed_frames(path, hz, thresh))


def refine(path: str, t: float, pad: float = 1.5, hz: float = 8.0) -> Optional[FrameEvent]:
    """Dense re-sample around t; return the OCR reading with the most link candidates, then highest confidence."""
    best, best_key, last = None, (-1, -1.0), None
    for tt, f in iter_frames(path, hz, max(0.0, t - pad), t + pad):
        h = dhash(f)
        if last is not None and hamming(h, last) < 4:
            continue
        last = h
        text, conf = ocr(f)
        cands = extract_candidates(text)
        key = (len(cands), conf)
        if key > best_key:
            best, best_key = FrameEvent(tt, text, conf, cands, refined=True), key
    return best


def analyse(path: str, hz: float = 10.0, thresh: int = 12, dense_pad: float = 1.5) -> list:
    """Full Pass C. Returns FrameEvents in time order; refined events replace their coarse originals."""
    events = []
    for t, f in iter_changed_frames(path, hz, thresh):
        text, conf = ocr(f)
        if looks_url_ish(text):
            r = refine(path, t, dense_pad)
            if r:
                events.append(r)
                continue
        events.append(FrameEvent(t, text, conf, extract_candidates(text)))
    return events


def fixed_fps_baseline(path: str, fps: float = 1.0) -> list:
    """What a naive 1 FPS sampler would read. Used only to prove the point in tests/benchmarks."""
    out = []
    for t, f in iter_frames(path, fps):
        text, conf = ocr(f)
        out.append(FrameEvent(t, text, conf, extract_candidates(text)))
    return out
