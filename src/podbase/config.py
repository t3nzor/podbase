from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    env = os.environ.get("PODBASE_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data"


@dataclass
class Config:
    data_dir: Path = field(default_factory=_default_data_dir)
    db_path: Path = field(init=False)
    audio_dir: Path = field(init=False)
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "int8"
    keep_audio: bool = False

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "podbase.db"
        self.audio_dir = self.data_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
