from __future__ import annotations

import ctypes
import warnings
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel  # type: ignore[import-untyped]


def _preload_cuda_libs() -> None:
    """Preload CUDA 12 libraries by absolute path so dlopen finds them.

    Uses ctypes.CDLL with RTLD_GLOBAL to load each .so directly into the
    process address space. When ctranslate2 later calls dlopen("libcublas.so.12"),
    the linker finds it already loaded (matched by soname) and returns the
    existing handle. Silent no-op if the libraries aren't installed.
    """
    import sysconfig

    site_lib = Path(sysconfig.get_paths()["purelib"])
    lib_dirs: list[Path] = [
        site_lib / "nvidia" / "cuda_runtime" / "lib",
        site_lib / "nvidia" / "cublas" / "lib",
        Path("/opt/cuda/lib64"),
        Path("/usr/local/lib/ollama/cuda_v12"),
    ]

    # Load in dependency order: runtime → cublas → cublasLt
    libs_in_order = ["libcudart.so.12", "libcublas.so.12", "libcublasLt.so.12"]
    for libname in libs_in_order:
        for d in lib_dirs:
            path = d / libname
            if path.exists():
                ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
                break


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
        if device == "cuda":
            _preload_cuda_libs()

        try:
            self._model = WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as exc:
            if device != "cpu":
                warnings.warn(
                    f"CUDA init failed ({exc}), falling back to CPU. "
                    f"Install the GPU dependencies for faster transcription: "
                    f"uv sync --extra gpu",
                    stacklevel=2,
                )
                self._model = WhisperModel(model_name, device="cpu", compute_type="int8")
            else:
                raise

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
