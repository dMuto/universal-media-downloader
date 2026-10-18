"""Example (pytest) tests for `AppConfig`.

These tests target `app/models/config.py`, which does not exist yet at this
stage of the TDD plan (Phase 1 / RED). They are expected to fail with an
`ImportError` until task 11.1 (Phase 2) creates the module.
"""

import dataclasses
from pathlib import Path

import pytest

from app.models.config import AppConfig
from app.models.download import DownloadType


def test_app_config_default_values() -> None:
    """A freshly constructed `AppConfig` SHALL expose the documented defaults.

    Validates: Requirements 13.1, 13.2
    """

    config = AppConfig()

    assert config.default_destination == Path.home() / "Downloads"
    assert config.default_download_type == DownloadType.VIDEO
    assert config.preferred_resolution == 1080
    assert config.default_audio_bitrate == 192
    assert config.ffmpeg_path is None
    assert config.theme == "system"


def test_app_config_is_immutable() -> None:
    """`AppConfig` SHALL be a frozen dataclass; mutating it SHALL raise.

    Validates: Requirements 13.1, 13.2
    """

    config = AppConfig()

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.theme = "dark"  # type: ignore[misc]
