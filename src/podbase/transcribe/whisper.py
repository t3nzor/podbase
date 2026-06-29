from __future__ import annotations

from dataclasses import dataclass

from faster_whisper import WhisperModel  # type: ignore[import-untyped]


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


@dataclass
class TranscriptResult:
    language: str
    language_probability: float
    words: list[WordTiming]


class Transcriber:
    """Wraps faster-whisper for podcast transcription."""

    def __init__(
        self,
        model_name: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "int8",
    ) -> None:
        self._model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio file and return word-level timings."""
        segments_gen, info = self._model.transcribe(
            audio_path,
            word_timestamps=True,
            vad_filter=True,
        )

        words: list[WordTiming] = []
        for segment in segments_gen:
            if segment.words:
                for w in segment.words:
                    words.append(WordTiming(word=w.word, start=w.start, end=w.end))

        return TranscriptResult(
            language=info.language,
            language_probability=info.language_probability,
            words=words,
        )
