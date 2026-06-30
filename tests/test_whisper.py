from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

from podbase.transcribe.whisper import Transcriber


class TestTranscriberFallback:
    def test_cpu_fallback_on_cuda_failure(self) -> None:
        """When CUDA init fails, Transcriber falls back to CPU with a warning."""
        mock_cpu_model = MagicMock()
        mock_gpu_model_cls = MagicMock(
            side_effect=RuntimeError("Library libcublas.so.12 is not found")
        )
        mock_cpu_model_cls = MagicMock(return_value=mock_cpu_model)

        def whisper_model_factory(
            model_name: str,
            device: str = "cuda",
            compute_type: str = "int8",
        ) -> MagicMock:
            if device == "cuda":
                return mock_gpu_model_cls(model_name, device=device, compute_type=compute_type)
            return mock_cpu_model_cls(model_name, device=device, compute_type=compute_type)

        with (
            patch(
                "podbase.transcribe.whisper.WhisperModel",
                side_effect=whisper_model_factory,
            ),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            t = Transcriber(model_name="tiny", device="cuda", compute_type="int8")

        assert t._model is mock_cpu_model
        assert len(caught) == 1
        assert "CUDA init failed" in str(caught[0].message)
        assert "uv sync --extra gpu" in str(caught[0].message)

    def test_no_fallback_when_cpu_device(self) -> None:
        """When device='cpu', failure raises immediately (no fallback loop)."""
        with patch(
            "podbase.transcribe.whisper.WhisperModel",
            side_effect=RuntimeError("some error"),
        ):
            try:
                Transcriber(model_name="tiny", device="cpu")
                assert False, "Should have raised"
            except RuntimeError as exc:
                assert "some error" in str(exc)

    def test_cuda_success_no_warning(self) -> None:
        """When CUDA works, no warning is emitted."""
        mock_model = MagicMock()
        with (
            patch(
                "podbase.transcribe.whisper.WhisperModel",
                return_value=mock_model,
            ),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            t = Transcriber(model_name="tiny", device="cuda", compute_type="int8")

        assert t._model is mock_model
        assert len(caught) == 0
