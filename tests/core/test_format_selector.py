"""Property-based tests for `app.core.format_selector.FormatSelector`."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.format_selector import FormatSelectionError, FormatSelector
from app.models import DownloadOptions, DownloadType, FormatInfo, MediaType

_HEIGHT_STRATEGY = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=4320),
)
_MAX_HEIGHT_STRATEGY = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=4320),
)


@st.composite
def _video_audio_formats(draw: st.DrawFn) -> list[FormatInfo]:
    """Build a non-empty list of video formats that already embed audio.

    Every generated format has `media_type=MediaType.VIDEO_AUDIO`, so the
    "selected video lacks embedded audio" branch (merge logic, covered by
    Property 2) is never triggered here. This keeps the property focused
    purely on max-height behavior, as described by Property 1.
    """
    heights = draw(st.lists(_HEIGHT_STRATEGY, min_size=1, max_size=8))
    return [
        FormatInfo(
            format_id=f"format-{index}",
            extension="mp4",
            height=height,
            media_type=MediaType.VIDEO_AUDIO,
        )
        for index, height in enumerate(heights)
    ]


@settings(max_examples=100)
@given(formats=_video_audio_formats(), max_height=_MAX_HEIGHT_STRATEGY)
def test_select_video_respects_max_height_or_raises_consistently(
    formats: list[FormatInfo],
    max_height: int | None,
) -> None:
    # Feature: media-downloader-app, Property 1: Seleção de vídeo respeita a altura máxima ou falha de forma consistente
    """**Validates: Requirements 2.2, 2.3**"""
    selector = FormatSelector()
    options = DownloadOptions(
        url="https://example.com/watch?v=sample",
        download_type=DownloadType.VIDEO,
        max_height=max_height,
    )

    satisfying_formats = [
        format_info
        for format_info in formats
        if max_height is None
        or (format_info.height is not None and format_info.height <= max_height)
    ]

    if not satisfying_formats:
        with pytest.raises(FormatSelectionError):
            selector._select_video(formats, options)
        return

    selection = selector._select_video(formats, options)
    video_format = selection.video_format

    assert video_format is not None
    assert (
        max_height is None
        or video_format.height is None
        or video_format.height <= max_height
    )


@st.composite
def _video_only_format(draw: st.DrawFn) -> FormatInfo:
    """Build a single video format that does not embed any audio stream."""
    height = draw(_HEIGHT_STRATEGY)
    return FormatInfo(
        format_id="video-only",
        extension="mp4",
        height=height,
        media_type=MediaType.VIDEO,
    )


_AUDIO_BITRATE_STRATEGY = st.one_of(
    st.none(),
    st.floats(
        min_value=0,
        max_value=512,
        allow_nan=False,
        allow_infinity=False,
    ),
)


@st.composite
def _audio_only_formats(draw: st.DrawFn) -> list[FormatInfo]:
    """Build a (possibly empty) list of audio-only formats with varying bitrates."""
    bitrates = draw(st.lists(_AUDIO_BITRATE_STRATEGY, min_size=0, max_size=8))
    return [
        FormatInfo(
            format_id=f"audio-{index}",
            extension="m4a",
            bitrate=bitrate,
            media_type=MediaType.AUDIO,
        )
        for index, bitrate in enumerate(bitrates)
    ]


@settings(max_examples=100)
@given(video_format=_video_only_format(), audio_formats=_audio_only_formats())
def test_select_video_without_embedded_audio_selects_consistent_audio(
    video_format: FormatInfo,
    audio_formats: list[FormatInfo],
) -> None:
    # Feature: media-downloader-app, Property 2: Vídeo sem áudio embutido sempre resulta em seleção de áudio consistente
    """**Validates: Requirements 2.4, 2.5**"""
    selector = FormatSelector()
    options = DownloadOptions(
        url="https://example.com/watch?v=sample",
        download_type=DownloadType.VIDEO,
        max_height=None,
    )
    formats = [video_format, *audio_formats]

    if not audio_formats:
        with pytest.raises(FormatSelectionError):
            selector._select_video(formats, options)
        return

    selection = selector._select_video(formats, options)

    assert selection.requires_merge is True
    assert selection.video_format == video_format

    max_bitrate = max(audio_format.bitrate or 0 for audio_format in audio_formats)
    assert selection.audio_format is not None
    assert (selection.audio_format.bitrate or 0) == max_bitrate


@st.composite
def _nonempty_audio_only_formats(draw: st.DrawFn) -> list[FormatInfo]:
    """Build a non-empty list of audio-only formats with varying bitrates."""
    bitrates = draw(st.lists(_AUDIO_BITRATE_STRATEGY, min_size=1, max_size=8))
    return [
        FormatInfo(
            format_id=f"audio-{index}",
            extension="m4a",
            bitrate=bitrate,
            media_type=MediaType.AUDIO,
        )
        for index, bitrate in enumerate(bitrates)
    ]


@settings(max_examples=100)
@given(audio_formats=_nonempty_audio_only_formats())
def test_select_audio_maximizes_bitrate(
    audio_formats: list[FormatInfo],
) -> None:
    # Feature: media-downloader-app, Property 3: Seleção de áudio sempre maximiza o bitrate
    """**Validates: Requirements 3.1, 3.3**"""
    selector = FormatSelector()

    selection = selector._select_audio(audio_formats)

    assert selection.video_format is None
    assert selection.audio_format is not None

    selected_bitrate = selection.audio_format.bitrate or 0
    max_bitrate = max(audio_format.bitrate or 0 for audio_format in audio_formats)
    assert selected_bitrate == max_bitrate

    for audio_format in audio_formats:
        assert selected_bitrate >= (audio_format.bitrate or 0)


def test_select_raises_when_media_has_no_formats(
    make_media_info,
) -> None:
    """**Validates: Requirements 2.6**"""
    selector = FormatSelector()
    media = make_media_info(formats=[])
    options = DownloadOptions(
        url="https://example.com/watch?v=sample",
        download_type=DownloadType.VIDEO,
    )

    with pytest.raises(FormatSelectionError):
        selector.select(media, options)


def test_select_audio_raises_when_no_audio_only_format_available(
    make_media_info,
    make_format_info,
) -> None:
    """**Validates: Requirements 3.2**"""
    selector = FormatSelector()
    media = make_media_info(
        formats=[
            make_format_info(
                format_id="video-only",
                media_type=MediaType.VIDEO,
            ),
            make_format_info(
                format_id="video-audio",
                media_type=MediaType.VIDEO_AUDIO,
            ),
        ]
    )
    options = DownloadOptions(
        url="https://example.com/watch?v=sample",
        download_type=DownloadType.AUDIO,
    )

    with pytest.raises(FormatSelectionError):
        selector.select(media, options)
