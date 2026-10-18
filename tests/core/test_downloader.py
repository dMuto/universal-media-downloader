"""Tests for `app.core.downloader.Downloader`."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.downloader import Downloader, MediaAnalysisError
from app.core.ffmpeg_service import FFmpegError, FFmpegService
from app.models import (
    DownloadOptions,
    DownloadResult,
    DownloadType,
    FormatInfo,
    FormatSelection,
    MediaInfo,
    MediaType,
)

# Strategies for the optional fields of a raw yt-dlp *format* dict. Each
# field is exercised as either missing, explicitly `None`, or a realistic
# value, so the mapping logic is proven tolerant to any subset of absent
# metadata.
_OPTIONAL_FORMAT_FIELDS: dict[str, st.SearchStrategy] = {
    "ext": st.sampled_from(["mp4", "webm", "m4a", "mkv", "3gp"]),
    "width": st.integers(min_value=0, max_value=7680),
    "height": st.integers(min_value=0, max_value=4320),
    "fps": st.floats(
        min_value=0,
        max_value=240,
        allow_nan=False,
        allow_infinity=False,
    ),
    "vcodec": st.sampled_from(["avc1", "vp9", "av01", "h264"]),
    "acodec": st.sampled_from(["aac", "opus", "mp3", "mp4a.40.2"]),
    "tbr": st.floats(
        min_value=0,
        max_value=20_000,
        allow_nan=False,
        allow_infinity=False,
    ),
    "abr": st.floats(
        min_value=0,
        max_value=512,
        allow_nan=False,
        allow_infinity=False,
    ),
    "filesize": st.integers(min_value=0, max_value=10**10),
    "filesize_approx": st.integers(min_value=0, max_value=10**10),
}


@st.composite
def _raw_format_dicts(draw: st.DrawFn) -> dict:
    """Build a raw yt-dlp format dict with an arbitrary subset of optional
    fields missing or `None`.

    `format_id` is the only field `_build_format_info` treats as required
    (it is always present here), while every other field may be absent,
    explicitly `None`, or populated with a realistic value.
    """
    data: dict = {
        "format_id": draw(
            st.one_of(
                st.text(min_size=1, max_size=20),
                st.integers(min_value=0, max_value=10_000),
            )
        ),
    }

    for field, strategy in _OPTIONAL_FORMAT_FIELDS.items():
        presence = draw(st.sampled_from(["missing", "none", "value"]))

        if presence == "missing":
            continue

        if presence == "none":
            data[field] = None
            continue

        data[field] = draw(strategy)

    return data


# Strategies for the optional fields of a raw yt-dlp *media/info* dict.
_OPTIONAL_MEDIA_FIELDS: dict[str, st.SearchStrategy] = {
    "title": st.text(min_size=0, max_size=50),
    "duration": st.floats(
        min_value=0,
        max_value=86_400,
        allow_nan=False,
        allow_infinity=False,
    ),
    "uploader": st.text(min_size=0, max_size=50),
    "channel": st.text(min_size=0, max_size=50),
    "thumbnail": st.text(min_size=0, max_size=100),
    "webpage_url": st.text(min_size=0, max_size=100),
    "original_url": st.text(min_size=0, max_size=100),
}


@st.composite
def _raw_media_dicts(draw: st.DrawFn) -> dict:
    """Build a raw yt-dlp info dict with an arbitrary subset of optional
    fields missing or `None`, including an optional `formats` list whose
    entries may themselves have missing optional fields.
    """
    data: dict = {}

    for field, strategy in _OPTIONAL_MEDIA_FIELDS.items():
        presence = draw(st.sampled_from(["missing", "none", "value"]))

        if presence == "missing":
            continue

        if presence == "none":
            data[field] = None
            continue

        data[field] = draw(strategy)

    if draw(st.booleans()):
        data["formats"] = draw(st.lists(_raw_format_dicts(), max_size=3))

    return data


@settings(max_examples=100)
@given(format_data=_raw_format_dicts())
def test_build_format_info_tolerates_missing_optional_fields(
    format_data: dict,
) -> None:
    # Feature: media-downloader-app, Property 4: Mapeamento de metadados tolera campos ausentes
    """**Validates: Requirements 1.2, 1.6**"""
    format_info = Downloader._build_format_info(format_data)

    assert isinstance(format_info, FormatInfo)
    assert format_info.format_id == str(format_data.get("format_id", ""))
    assert format_info.extension == format_data.get("ext")
    assert format_info.width == format_data.get("width")
    assert format_info.height == format_data.get("height")
    assert format_info.fps == format_data.get("fps")

    expected_video_codec = Downloader._normalize_codec(format_data.get("vcodec"))
    expected_audio_codec = Downloader._normalize_codec(format_data.get("acodec"))
    assert format_info.video_codec == expected_video_codec
    assert format_info.audio_codec == expected_audio_codec

    expected_bitrate = format_data.get("tbr") or format_data.get("abr")
    assert format_info.bitrate == expected_bitrate

    expected_size = format_data.get("filesize") or format_data.get("filesize_approx")
    assert format_info.size == expected_size


@settings(max_examples=100)
@given(info=_raw_media_dicts())
def test_build_media_info_tolerates_missing_optional_fields(
    info: dict,
) -> None:
    # Feature: media-downloader-app, Property 4: Mapeamento de metadados tolera campos ausentes
    """**Validates: Requirements 1.2, 1.6**"""
    media_info = Downloader._build_media_info(info)

    assert isinstance(media_info, MediaInfo)

    expected_title = info.get("title") or "Sem título"
    assert media_info.title == expected_title

    assert media_info.duration == info.get("duration")

    expected_uploader = info.get("uploader") or info.get("channel")
    assert media_info.uploader == expected_uploader

    assert media_info.thumbnail == info.get("thumbnail")

    expected_url = info.get("webpage_url") or info.get("original_url") or ""
    assert media_info.original_url == expected_url

    assert isinstance(media_info.formats, list)


@settings(max_examples=100)
@given(url=st.text(alphabet=" \t\n", min_size=0, max_size=20))
def test_analyze_blank_url_never_invokes_yt_dlp(url: str) -> None:
    # Feature: media-downloader-app, Property 5: URL vazia nunca invoca o yt-dlp
    """**Validates: Requirements 1.3**"""
    downloader = Downloader()

    with patch("app.core.downloader.yt_dlp.YoutubeDL") as mock_youtube_dl:
        with pytest.raises(MediaAnalysisError):
            downloader.analyze(url)

        mock_youtube_dl.assert_not_called()


@settings(max_examples=100)
@given(
    video_extension=st.one_of(
        st.none(),
        st.text(),
        st.sampled_from(["mp4", "MP4", "Mp4", "webm", "mkv"]),
    ),
    audio_codec=st.one_of(
        st.none(),
        st.text(),
        st.sampled_from(
            [
                "mp4a",
                "MP4A",
                "mp4a.40.2",
                "MP4A.40.2",
                "opus",
                "aac",
            ]
        ),
    ),
)
def test_get_merge_extension_is_deterministic(
    video_extension: str | None,
    audio_codec: str | None,
) -> None:
    # Feature: media-downloader-app, Property 7: Seleção do contêiner de merge é determinística
    """**Validates: Requirements 4.4**"""
    first_result = Downloader._get_merge_extension(
        audio_codec=audio_codec,
        video_extension=video_extension,
    )
    second_result = Downloader._get_merge_extension(
        audio_codec=audio_codec,
        video_extension=video_extension,
    )

    # (a) determinism: calling twice with the same inputs gives the same result.
    assert first_result == second_result

    expects_mp4 = (
        video_extension is not None
        and video_extension.lower() == "mp4"
        and audio_codec is not None
        and audio_codec.lower().startswith("mp4a")
    )

    if expects_mp4:
        # (b) result is ".mp4" iff video_extension is "mp4" and audio_codec
        # starts with "mp4a" (case-insensitive).
        assert first_result == ".mp4"
    else:
        # (c) otherwise ".mkv".
        assert first_result == ".mkv"


# ---------------------------------------------------------------------------
# Example tests (task 2.12): `Downloader.analyze` and `Downloader.download`.
#
# These exercise already-implemented, stable behavior with `yt_dlp.YoutubeDL`
# and `FFmpegService` mocked/faked out; no real network or FFmpeg process is
# ever invoked.
# ---------------------------------------------------------------------------


class _FakeYoutubeDL:
    """Minimal stand-in for `yt_dlp.YoutubeDL` used as a context manager.

    `Downloader` always uses `yt_dlp.YoutubeDL(options)` as a context
    manager and calls `extract_info`/`prepare_filename` on the resulting
    object. This fake replicates just that surface so tests can control
    `extract_info`'s behavior without touching the network.
    """

    def __init__(self, options: dict, extract_info_fn) -> None:
        self.options = options
        self._extract_info_fn = extract_info_fn

    def __enter__(self) -> _FakeYoutubeDL:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def extract_info(self, url: str, download: bool) -> Any:
        return self._extract_info_fn(self.options, url, download)

    def prepare_filename(self, info: dict) -> str | None:
        return None


def _make_fake_youtube_dl(extract_info_fn):
    """Return a `side_effect` factory producing `_FakeYoutubeDL` instances."""

    def _factory(options: dict) -> _FakeYoutubeDL:
        return _FakeYoutubeDL(options, extract_info_fn)

    return _factory


def test_analyze_returns_full_media_info_on_success() -> None:
    """**Validates: Requirements 1.1**"""
    downloader = Downloader()

    raw_info = {
        "title": "Sample Title",
        "duration": 245.0,
        "uploader": "Sample Channel",
        "thumbnail": "https://example.com/thumb.jpg",
        "webpage_url": "https://example.com/watch?v=abc123",
        "formats": [
            {
                "format_id": "18",
                "ext": "mp4",
                "width": 640,
                "height": 360,
                "fps": 30.0,
                "vcodec": "avc1.42001E",
                "acodec": "mp4a.40.2",
                "tbr": 500.0,
                "filesize": 12_345_678,
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 128.0,
                "filesize": 3_456_789,
            },
        ],
    }

    def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
        assert download is False
        assert url == "https://example.com/watch?v=abc123"
        return raw_info

    with patch(
        "app.core.downloader.yt_dlp.YoutubeDL",
        side_effect=_make_fake_youtube_dl(extract_info_fn),
    ):
        media_info = downloader.analyze("https://example.com/watch?v=abc123")

    assert isinstance(media_info, MediaInfo)
    assert media_info.title == "Sample Title"
    assert media_info.duration == 245.0
    assert media_info.uploader == "Sample Channel"
    assert media_info.thumbnail == "https://example.com/thumb.jpg"
    assert media_info.original_url == "https://example.com/watch?v=abc123"
    assert len(media_info.formats) == 2
    assert {format_info.format_id for format_info in media_info.formats} == {
        "18",
        "140",
    }


def test_analyze_raises_descriptive_error_when_yt_dlp_fails() -> None:
    """**Validates: Requirements 1.4**"""
    downloader = Downloader()

    def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
        raise yt_dlp.utils.DownloadError("unsupported url")

    with (
        patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ),
        pytest.raises(MediaAnalysisError) as exc_info,
    ):
        downloader.analyze("https://example.com/unsupported")

    assert "unsupported url" in str(exc_info.value)


def test_analyze_raises_descriptive_error_when_yt_dlp_returns_no_info() -> None:
    """**Validates: Requirements 1.5**

    Note on actual vs. literal behavior: the only guard in `analyze` that
    rejects a media with "no recognizable format" is `if not info: raise
    MediaAnalysisError(...)`, which only triggers when `extract_info`
    returns a falsy value (e.g. `None`). A truthy info dict whose `formats`
    list is empty or contains no recognizable entries is *not* separately
    rejected by `analyze`; it simply yields a `MediaInfo` with an empty
    `formats` list (see `_build_media_info`/`_is_media_format`). This test
    targets the verified, actual behavior: a falsy `extract_info` result.
    """
    downloader = Downloader()

    def extract_info_fn(ydl_options: dict, url: str, download: bool) -> None:
        return None

    with (
        patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ),
        pytest.raises(MediaAnalysisError) as exc_info,
    ):
        downloader.analyze("https://example.com/empty")

    assert str(exc_info.value)


def test_download_single_format_creates_success_result_with_path_and_size(
    downloads_dir: Path,
) -> None:
    """**Validates: Requirements 4.1, 4.8**"""
    downloader = Downloader()

    video_format = FormatInfo(format_id="22", extension="mp4")
    selection = FormatSelection(video_format=video_format)
    options = DownloadOptions(
        url="https://example.com/video",
        download_type=DownloadType.VIDEO,
        destination=downloads_dir,
    )

    downloaded_file = downloads_dir / "Video Title.mp4"
    content = b"fake-video-bytes"

    def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
        assert download is True
        downloaded_file.write_bytes(content)
        return {"requested_downloads": [{"filepath": str(downloaded_file)}]}

    with patch(
        "app.core.downloader.yt_dlp.YoutubeDL",
        side_effect=_make_fake_youtube_dl(extract_info_fn),
    ):
        result = downloader.download(options, selection)

    assert result.success is True
    assert result.error_message is None
    assert result.file_path == downloaded_file
    assert result.file_path.is_file()
    assert result.file_size == len(content)
    assert result.file_size == downloaded_file.stat().st_size


def test_download_and_merge_succeeds_and_removes_temporary_files(
    downloads_dir: Path,
) -> None:
    """**Validates: Requirements 4.2, 4.3**"""
    video_format = FormatInfo(
        format_id="video-1",
        extension="mp4",
        video_codec="avc1",
        audio_codec=None,
        media_type=MediaType.VIDEO,
    )
    audio_format = FormatInfo(
        format_id="audio-1",
        extension="m4a",
        video_codec=None,
        audio_codec="mp4a.40.2",
        media_type=MediaType.AUDIO,
    )
    selection = FormatSelection(video_format=video_format, audio_format=audio_format)
    options = DownloadOptions(
        url="https://example.com/video",
        download_type=DownloadType.VIDEO,
        destination=downloads_dir,
    )

    captured_temp_dirs: list[Path] = []

    def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
        assert download is True

        outtmpl = Path(ydl_options["outtmpl"])
        directory = outtmpl.parent
        captured_temp_dirs.append(directory)

        if outtmpl.name.startswith("video_"):
            file_path = directory / "video_Title.mp4"
        else:
            file_path = directory / "audio_Title.m4a"

        file_path.write_bytes(b"stream-data")
        return {"requested_downloads": [{"filepath": str(file_path)}]}

    def fake_merge(video_path: Path, audio_path: Path, output_path: Path) -> Path:
        assert video_path.is_file()
        assert audio_path.is_file()
        output_path.write_bytes(b"merged-output-data")
        return output_path

    fake_ffmpeg_service = MagicMock(spec=FFmpegService)
    fake_ffmpeg_service.merge.side_effect = fake_merge

    downloader = Downloader(ffmpeg_service=fake_ffmpeg_service)

    with patch(
        "app.core.downloader.yt_dlp.YoutubeDL",
        side_effect=_make_fake_youtube_dl(extract_info_fn),
    ):
        result = downloader.download(options, selection)

    assert result.success is True
    assert result.error_message is None
    assert result.file_path is not None
    assert result.file_path.is_file()
    assert result.file_path.parent == downloads_dir
    assert result.file_size == result.file_path.stat().st_size
    fake_ffmpeg_service.merge.assert_called_once()

    # Req 4.3: the temporary directory used for the separate video/audio
    # downloads must no longer exist once the merge has completed (cleaned
    # up by the `TemporaryDirectory` context manager).
    assert captured_temp_dirs
    for temp_dir in captured_temp_dirs:
        assert not temp_dir.exists()


def test_download_returns_failure_result_when_destination_cannot_be_created(
    tmp_path: Path,
) -> None:
    """**Validates: Requirements 4.5**"""
    downloader = Downloader()

    video_format = FormatInfo(format_id="22")
    selection = FormatSelection(video_format=video_format)
    destination = tmp_path / "unwritable_destination"
    options = DownloadOptions(
        url="https://example.com/video",
        download_type=DownloadType.VIDEO,
        destination=destination,
    )

    with (
        patch(
            "app.core.downloader.Path.mkdir",
            side_effect=OSError("disk full"),
        ),
        patch("app.core.downloader.yt_dlp.YoutubeDL") as mock_youtube_dl,
    ):
        result = downloader.download(options, selection)

        mock_youtube_dl.assert_not_called()

    assert result.success is False
    assert result.file_path is None
    assert result.error_message is not None
    assert "pasta de destino" in result.error_message


# ---------------------------------------------------------------------------
# Property test (task 3.2): internal failures of `Downloader.download` must
# never escape as unhandled exceptions, regardless of where they originate.
#
# Requirement 4.7 (already implemented today): `yt_dlp.utils.DownloadError`,
# `FFmpegError` and `OSError` raised anywhere inside `download()` (single
# format path, merge path) are expected to already be translated into a
# `DownloadResult(success=False, error_message=<non-empty str>)`.
#
# Requirement 6.5 (NOT implemented yet, Fase 2 / task 9.4): when
# `download_type == AUDIO` and `audio_bitrate` is set, `download()` is
# expected to invoke `FFmpegService.convert_to_mp3` on the downloaded audio
# and translate any `FFmpegError` raised by it into the same kind of failure
# result. As of this phase, `Downloader.download` never calls
# `convert_to_mp3` at all, so the scenario below documents (and is expected
# to FAIL on) that missing integration.
# ---------------------------------------------------------------------------

_FAILURE_SCENARIOS = (
    # Requirement 4.7 - already handled today by `Downloader.download`.
    "req_4_7__yt_dlp_download_error__single_format",
    "req_4_7__yt_dlp_download_error__merge_video_stream",
    "req_4_7__yt_dlp_download_error__merge_audio_stream",
    "req_4_7__ffmpeg_error__merge",
    "req_4_7__oserror__single_format_file_not_found",
    "req_4_7__generic_exception__single_format",
    # Requirement 6.5 - MP3 conversion integration does not exist yet.
    "req_6_5__ffmpeg_error__mp3_conversion",
)


def _build_merge_extract_info_fn(
    error_scenario: str,
    error_message: str,
):
    """Build an `extract_info_fn` for the merge (video + audio) path.

    Mirrors the layout used by
    `test_download_and_merge_succeeds_and_removes_temporary_files`, but can
    be told to raise `yt_dlp.utils.DownloadError` while downloading either
    the video or the audio stream.
    """

    def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
        outtmpl = Path(ydl_options["outtmpl"])
        is_video_stream = outtmpl.name.startswith("video_")

        if (
            error_scenario == "req_4_7__yt_dlp_download_error__merge_video_stream"
            and is_video_stream
        ):
            raise yt_dlp.utils.DownloadError(error_message)

        if (
            error_scenario == "req_4_7__yt_dlp_download_error__merge_audio_stream"
            and not is_video_stream
        ):
            raise yt_dlp.utils.DownloadError(error_message)

        directory = outtmpl.parent

        if is_video_stream:
            file_path = directory / "video_Title.mp4"
        else:
            file_path = directory / "audio_Title.m4a"

        file_path.write_bytes(b"stream-data")
        return {"requested_downloads": [{"filepath": str(file_path)}]}

    return extract_info_fn


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    scenario=st.sampled_from(_FAILURE_SCENARIOS),
    error_message=st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            min_codepoint=48,
            max_codepoint=122,
        ),
        min_size=1,
        max_size=40,
    ),
)
def test_download_never_propagates_internal_failures(
    downloads_dir: Path,
    scenario: str,
    error_message: str,
) -> None:
    # Feature: media-downloader-app, Property 11: Falhas internas nunca escapam como exceções não tratadas
    """**Validates: Requirements 4.7, 6.5**"""

    if scenario == "req_4_7__yt_dlp_download_error__single_format":
        video_format = FormatInfo(format_id="22", extension="mp4")
        selection = FormatSelection(video_format=video_format)
        options = DownloadOptions(
            url="https://example.com/video",
            download_type=DownloadType.VIDEO,
            destination=downloads_dir,
        )

        def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
            raise yt_dlp.utils.DownloadError(error_message)

        downloader = Downloader()

        with patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ):
            result = downloader.download(options, selection)

    elif scenario in (
        "req_4_7__yt_dlp_download_error__merge_video_stream",
        "req_4_7__yt_dlp_download_error__merge_audio_stream",
    ):
        video_format = FormatInfo(
            format_id="video-1",
            extension="mp4",
            video_codec="avc1",
            audio_codec=None,
            media_type=MediaType.VIDEO,
        )
        audio_format = FormatInfo(
            format_id="audio-1",
            extension="m4a",
            video_codec=None,
            audio_codec="mp4a.40.2",
            media_type=MediaType.AUDIO,
        )
        selection = FormatSelection(
            video_format=video_format,
            audio_format=audio_format,
        )
        options = DownloadOptions(
            url="https://example.com/video",
            download_type=DownloadType.VIDEO,
            destination=downloads_dir,
        )

        downloader = Downloader()
        extract_info_fn = _build_merge_extract_info_fn(scenario, error_message)

        with patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ):
            result = downloader.download(options, selection)

    elif scenario == "req_4_7__ffmpeg_error__merge":
        video_format = FormatInfo(
            format_id="video-1",
            extension="mp4",
            video_codec="avc1",
            audio_codec=None,
            media_type=MediaType.VIDEO,
        )
        audio_format = FormatInfo(
            format_id="audio-1",
            extension="m4a",
            video_codec=None,
            audio_codec="mp4a.40.2",
            media_type=MediaType.AUDIO,
        )
        selection = FormatSelection(
            video_format=video_format,
            audio_format=audio_format,
        )
        options = DownloadOptions(
            url="https://example.com/video",
            download_type=DownloadType.VIDEO,
            destination=downloads_dir,
        )

        extract_info_fn = _build_merge_extract_info_fn(scenario, error_message)

        fake_ffmpeg_service = MagicMock(spec=FFmpegService)
        fake_ffmpeg_service.merge.side_effect = FFmpegError(error_message)

        downloader = Downloader(ffmpeg_service=fake_ffmpeg_service)

        with patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ):
            result = downloader.download(options, selection)

    elif scenario == "req_4_7__oserror__single_format_file_not_found":
        video_format = FormatInfo(format_id="22", extension="mp4")
        selection = FormatSelection(video_format=video_format)
        options = DownloadOptions(
            url="https://example.com/video",
            download_type=DownloadType.VIDEO,
            destination=downloads_dir,
        )

        def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
            # No `requested_downloads` and `prepare_filename` (faked to
            # return `None`) means `_get_downloaded_file_path` cannot
            # resolve a path, which makes `_download_single_format` raise
            # `OSError` internally.
            return {}

        downloader = Downloader()

        with patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ):
            result = downloader.download(options, selection)

    elif scenario == "req_4_7__generic_exception__single_format":
        video_format = FormatInfo(format_id="22", extension="mp4")
        selection = FormatSelection(video_format=video_format)
        options = DownloadOptions(
            url="https://example.com/video",
            download_type=DownloadType.VIDEO,
            destination=downloads_dir,
        )

        def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
            raise RuntimeError(error_message)

        downloader = Downloader()

        with patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ):
            result = downloader.download(options, selection)

    elif scenario == "req_6_5__ffmpeg_error__mp3_conversion":
        audio_format = FormatInfo(
            format_id="audio-1",
            extension="m4a",
            video_codec=None,
            audio_codec="mp4a.40.2",
            media_type=MediaType.AUDIO,
        )
        selection = FormatSelection(audio_format=audio_format)
        options = DownloadOptions(
            url="https://example.com/audio",
            download_type=DownloadType.AUDIO,
            audio_bitrate=192,
            destination=downloads_dir,
        )

        downloaded_file = downloads_dir / "Audio Title.m4a"

        def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
            downloaded_file.write_bytes(b"fake-audio-bytes")
            return {"requested_downloads": [{"filepath": str(downloaded_file)}]}

        fake_ffmpeg_service = MagicMock(spec=FFmpegService)
        fake_ffmpeg_service.convert_to_mp3.side_effect = FFmpegError(error_message)

        downloader = Downloader(ffmpeg_service=fake_ffmpeg_service)

        with patch(
            "app.core.downloader.yt_dlp.YoutubeDL",
            side_effect=_make_fake_youtube_dl(extract_info_fn),
        ):
            result = downloader.download(options, selection)

        # This is the Requirement 6.5 assertion: when `download_type ==
        # AUDIO` and `audio_bitrate` is set, `Downloader.download` is
        # expected to call `FFmpegService.convert_to_mp3` on the
        # downloaded audio. It does not do so yet (Fase 2 / task 9.4), so
        # this assertion is expected to FAIL in this phase.
        fake_ffmpeg_service.convert_to_mp3.assert_called_once()

    else:  # pragma: no cover - guards against an unhandled scenario label
        raise AssertionError(f"Cenário de teste desconhecido: {scenario}")

    assert isinstance(result, DownloadResult)
    assert result.success is False, (
        f"[{scenario}] Esperava DownloadResult(success=False) após uma falha "
        f"interna, mas obteve success={result.success!r}."
    )
    assert result.error_message, (
        f"[{scenario}] Esperava uma `error_message` textual não vazia "
        f"descrevendo a falha interna, mas obteve "
        f"{result.error_message!r}."
    )


# ---------------------------------------------------------------------------
# Example test (task 3.3): successful MP3 conversion must remove the
# intermediate (unconverted) audio file.
#
# Requirement 6.4 (NOT implemented yet, Fase 2 / task 9.4): `Downloader.download`
# is expected to invoke `FFmpegService.convert_to_mp3` on the downloaded
# audio when `download_type == AUDIO` and `audio_bitrate` is set, returning a
# `DownloadResult(success=True)` that references the final MP3 file and
# removing the intermediate, unconverted audio file. As of this phase,
# `Downloader.download` never calls `convert_to_mp3` at all, so this test is
# expected to FAIL on the missing integration.
# ---------------------------------------------------------------------------


def test_download_audio_with_successful_mp3_conversion_removes_intermediate_file(
    downloads_dir: Path,
) -> None:
    """**Validates: Requirements 6.4**"""
    audio_format = FormatInfo(
        format_id="audio-1",
        extension="m4a",
        video_codec=None,
        audio_codec="mp4a.40.2",
        media_type=MediaType.AUDIO,
    )
    selection = FormatSelection(audio_format=audio_format)
    options = DownloadOptions(
        url="https://example.com/audio",
        download_type=DownloadType.AUDIO,
        audio_bitrate=192,
        destination=downloads_dir,
    )

    intermediate_file = downloads_dir / "Audio Title.m4a"
    final_mp3_file = downloads_dir / "Audio Title.mp3"

    def extract_info_fn(ydl_options: dict, url: str, download: bool) -> dict:
        assert download is True
        intermediate_file.write_bytes(b"fake-intermediate-audio-bytes")
        return {"requested_downloads": [{"filepath": str(intermediate_file)}]}

    def fake_convert_to_mp3(
        audio_path: Path,
        output_path: Path,
        bitrate: int,
    ) -> Path:
        assert audio_path == intermediate_file
        output_path.write_bytes(b"fake-mp3-bytes")
        return output_path

    fake_ffmpeg_service = MagicMock(spec=FFmpegService)
    fake_ffmpeg_service.convert_to_mp3.side_effect = fake_convert_to_mp3

    downloader = Downloader(ffmpeg_service=fake_ffmpeg_service)

    with patch(
        "app.core.downloader.yt_dlp.YoutubeDL",
        side_effect=_make_fake_youtube_dl(extract_info_fn),
    ):
        result = downloader.download(options, selection)

    # Req 6.4: `convert_to_mp3` must be invoked once with the intermediate
    # audio path and the requested bitrate.
    fake_ffmpeg_service.convert_to_mp3.assert_called_once()
    call_args = fake_ffmpeg_service.convert_to_mp3.call_args
    assert call_args.kwargs.get(
        "audio_path", call_args.args[0] if call_args.args else None
    ) == (intermediate_file)
    bitrate_used = call_args.kwargs.get(
        "bitrate", call_args.args[2] if len(call_args.args) > 2 else None
    )
    assert bitrate_used == 192

    assert result.success is True
    assert result.error_message is None
    assert result.file_path == final_mp3_file
    assert result.file_path.is_file()

    # Req 6.4: the intermediate, unconverted audio file must no longer exist
    # once the MP3 conversion has completed.
    assert not intermediate_file.exists()


def test_download_returns_failure_result_when_no_format_is_selected(
    downloads_dir: Path,
) -> None:
    """**Validates: Requirements 4.6**"""
    downloader = Downloader()

    selection = FormatSelection(video_format=None, audio_format=None)
    options = DownloadOptions(
        url="https://example.com/video",
        download_type=DownloadType.VIDEO,
        destination=downloads_dir,
    )

    with patch("app.core.downloader.yt_dlp.YoutubeDL") as mock_youtube_dl:
        result = downloader.download(options, selection)

        mock_youtube_dl.assert_not_called()

    assert result.success is False
    assert result.file_path is None
    assert result.error_message == "Nenhum formato foi selecionado."
