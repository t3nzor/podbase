from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_PODBASE_PROJECT_NAME = "podbase"


def _find_project_root() -> Path | None:
    """Walk up from cwd looking for a pyproject.toml with name='podbase'."""
    current = Path.cwd()
    for candidate in [current, *current.parents]:
        pyproject = candidate / "pyproject.toml"
        if pyproject.exists():
            try:
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                if data.get("project", {}).get("name") == _PODBASE_PROJECT_NAME:
                    return candidate
            except (tomllib.TOMLDecodeError, OSError):
                continue
    return None


def _default_data_dir() -> Path:
    env = os.environ.get("PODBASE_DATA_DIR")
    if env:
        return Path(env)
    project_root = _find_project_root()
    if project_root is not None:
        return project_root / "data"
    return Path.home() / ".local" / "share" / "podbase"


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
