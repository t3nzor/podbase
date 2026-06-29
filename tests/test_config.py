from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from podbase.config import _default_data_dir, _find_project_root


class TestFindProjectRoot:
    def test_finds_root_from_project_dir(self) -> None:
        """Running from the project root should find it."""
        result = _find_project_root()
        # We're running tests from the project root
        assert result is not None
        assert (result / "pyproject.toml").exists()
        assert (result / "src" / "podbase").is_dir()

    def test_finds_root_from_subdirectory(self, tmp_path: Path) -> None:
        """Running from a subdir should still find the project root."""
        # The actual project root has pyproject.toml with name=podbase
        # We can't easily fake a full project tree, so we test with a real subdir
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)

        # Create a fake pyproject.toml in tmp_path
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "podbase"\n'
        )

        with patch("podbase.config.Path") as mock_path:
            # Make Path.cwd() return our subdir
            mock_path.cwd.return_value = subdir
            # Keep real Path behavior for everything else
            mock_path.side_effect = lambda *args: Path(*args)
            result = _find_project_root()

        assert result == tmp_path

    def test_returns_none_when_no_project_found(self, tmp_path: Path) -> None:
        """Running from a dir with no podbase pyproject.toml should return None."""
        empty_dir = tmp_path / "unrelated"
        empty_dir.mkdir()

        with patch("podbase.config.Path") as mock_path:
            mock_path.cwd.return_value = empty_dir
            mock_path.side_effect = lambda *args: Path(*args)
            result = _find_project_root()

        assert result is None


class TestDefaultDataDir:
    def test_env_var_takes_priority(self, monkeypatch: object) -> None:
        """PODBASE_DATA_DIR env var should override everything."""
        monkeypatch.setenv("PODBASE_DATA_DIR", "/custom/path")
        result = _default_data_dir()
        assert result == Path("/custom/path")

    def test_project_root_data_dir(self) -> None:
        """When running from project root, data dir is <root>/data."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("PODBASE_DATA_DIR", None)
            result = _default_data_dir()
            # We run tests from project root
            assert result == Path.cwd() / "data"
            assert result.name == "data"

    def test_xdg_fallback(self, tmp_path: Path) -> None:
        """When no project root found, fall back to ~/.local/share/podbase."""
        empty_dir = tmp_path / "nowhere"
        empty_dir.mkdir()

        with (
            patch.dict("os.environ", {}, clear=False),
            patch("podbase.config.Path") as mock_path,
        ):
            import os

            os.environ.pop("PODBASE_DATA_DIR", None)
            mock_path.cwd.return_value = empty_dir
            mock_path.side_effect = lambda *args: Path(*args)
            # Mock Path.home() to return tmp_path/home
            home_dir = tmp_path / "home"
            home_dir.mkdir()
            mock_path.home.return_value = home_dir

            result = _default_data_dir()

        assert result == home_dir / ".local" / "share" / "podbase"
