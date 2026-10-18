"""Shared pytest fixtures for the test suite.

This module centralizes generic, reusable fixtures (factories for the
project's core dataclasses) so individual test files can stay focused on
the behavior they exercise instead of repeating construction boilerplate.
"""

from pathlib import Path
from typing import Callable, Optional

import pytest

from app.models import FormatInfo, MediaInfo, MediaType


@pytest.fixture
def make_format_info() -> Callable[..., FormatInfo]:
    """Return a factory for building `FormatInfo` instances with sensible defaults.

    Any `FormatInfo` field can be overridden via keyword arguments, e.g.:
        make_format_info(height=1080, media_type=MediaType.VIDEO)
    """

    def _factory(
        *,
        format_id: str = "format-1",
        extension: Optional[str] = "mp4",
        width: Optional[int] = 1280,
        height: Optional[int] = 720,
        fps: Optional[float] = 30.0,
        video_codec: Optional[str] = "avc1",
        audio_codec: Optional[str] = "aac",
        bitrate: Optional[float] = 128.0,
        size: Optional[int] = 1_000_000,
        media_type: MediaType = MediaType.VIDEO_AUDIO,
    ) -> FormatInfo:
        return FormatInfo(
            format_id=format_id,
            extension=extension,
            width=width,
            height=height,
            fps=fps,
            video_codec=video_codec,
            audio_codec=audio_codec,
            bitrate=bitrate,
            size=size,
            media_type=media_type,
        )

    return _factory


@pytest.fixture
def make_media_info(
    make_format_info: Callable[..., FormatInfo],
) -> Callable[..., MediaInfo]:
    """Return a factory for building `MediaInfo` instances with sensible defaults.

    Any `MediaInfo` field can be overridden via keyword arguments. When
    `formats` is not provided, a single default format is generated via
    `make_format_info`.
    """

    def _factory(
        *,
        title: str = "Sample Media",
        duration: Optional[float] = 120.0,
        uploader: Optional[str] = "Sample Uploader",
        thumbnail: Optional[str] = "https://example.com/thumb.jpg",
        original_url: str = "https://example.com/watch?v=sample",
        formats: Optional[list[FormatInfo]] = None,
    ) -> MediaInfo:
        return MediaInfo(
            title=title,
            duration=duration,
            uploader=uploader,
            thumbnail=thumbnail,
            original_url=original_url,
            formats=formats if formats is not None else [make_format_info()],
        )

    return _factory


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    """Return a temporary directory to be used as a download destination."""

    directory = tmp_path / "downloads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory
