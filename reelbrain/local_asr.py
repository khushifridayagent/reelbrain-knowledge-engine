"""Local, CPU-capable, multilingual open-source Whisper transcription.

The model runs only after actual media is available, with no remote ASR upload.
GitHub-hosted compute may have time/memory limits; never promise a latency SLA.
"""
from __future__ import annotations
from pathlib import Path
from .contracts import Observation


class FasterWhisperSpeechToText:
    def __init__(self,model_size:str='small',*,model=None):
        if model_size not in {'tiny','base','small','medium'}:
            raise ValueError('Unsupported bounded local Whisper model')
        self.model_size=model_size
        self._model=model

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError('faster-whisper is required for local ASR') from exc
            self._model=WhisperModel(self.model_size,device='cpu',
                                    compute_type='int8',cpu_threads=2)
        return self._model

    def transcribe(self,audio:Path)->list[Observation]:
        segments,_info=self._load().transcribe(
            str(audio), beam_size=3, vad_filter=True,
            condition_on_previous_text=False,
        )
        out=[]
        for segment in segments:
            text=str(segment.text or '').strip()
            if not text:continue
            start=max(0.0,float(segment.start))
            end=max(start,float(segment.end))
            out.append(Observation(text,kind='asr',locator=f'{start:.2f}-{end:.2f}'))
        return out
