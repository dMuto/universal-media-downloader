"""Tests for `app.core.ffmpeg_service.FFmpegService`."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.ffmpeg_service import FFmpegError, FFmpegService

_RESERVED_WINDOWS_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_filename_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        min_codepoint=48,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=12,
).filter(
    lambda name: name.strip() != "" and name.lower() not in _RESERVED_WINDOWS_NAMES
)


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    video_name=_filename_strategy,
    audio_name=_filename_strategy,
    output_name=_filename_strategy,
)
def test_merge_command_always_copies_streams_without_reencoding(
    tmp_path: Path,
    video_name: str,
    audio_name: str,
    output_name: str,
) -> None:
    # Feature: media-downloader-app, Property 8: Comando de merge sempre copia os fluxos sem recodificação
    video_path = tmp_path / "in" / f"{video_name}.mp4"
    audio_path = tmp_path / "in" / f"{audio_name}.m4a"
    output_path = tmp_path / "out" / f"{output_name}.mkv"

    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"")
    audio_path.write_bytes(b"")

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    captured_commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured_commands.append(command)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"")
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    with patch("app.core.ffmpeg_service.subprocess.run", side_effect=fake_run):
        result = service.merge(video_path, audio_path, output_path)

    assert result == output_path
    assert len(captured_commands) == 1

    command = captured_commands[0]

    assert "-c:v" in command
    assert "-c:a" in command
    assert command.count("copy") == 2
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "copy"
    assert str(video_path) in command
    assert str(audio_path) in command
    assert str(output_path) in command


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    video_name=_filename_strategy,
    audio_name=_filename_strategy,
    output_name=_filename_strategy,
    missing=st.sampled_from(["video", "audio", "both"]),
)
def test_merge_never_invokes_ffmpeg_when_input_files_are_missing(
    tmp_path: Path,
    video_name: str,
    audio_name: str,
    output_name: str,
    missing: str,
) -> None:
    # Feature: media-downloader-app, Property 9: Arquivos de entrada inexistentes nunca disparam o processo do FFmpeg
    video_path = tmp_path / "in" / f"{video_name}.mp4"
    audio_path = tmp_path / "in" / f"{audio_name}.m4a"
    output_path = tmp_path / "out" / f"{output_name}.mkv"

    video_path.parent.mkdir(parents=True, exist_ok=True)

    if missing == "video":
        audio_path.write_bytes(b"")
    elif missing == "audio":
        video_path.write_bytes(b"")
    # when missing == "both", neither file is created on disk

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    with patch("app.core.ffmpeg_service.subprocess.run") as mock_run:
        with pytest.raises(FFmpegError):
            service.merge(video_path, audio_path, output_path)

        mock_run.assert_not_called()


def test_ffmpeg_service_uses_explicit_path_when_provided(tmp_path: Path) -> None:
    # Feature: media-downloader-app, Requirement 5.1
    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    with patch("app.core.ffmpeg_service.shutil.which") as mock_which:
        service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    assert service.executable == fake_ffmpeg.resolve()
    mock_which.assert_not_called()


def test_ffmpeg_service_falls_back_to_system_path_when_no_explicit_path(
    tmp_path: Path,
) -> None:
    # Feature: media-downloader-app, Requirement 5.1
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_bytes(b"")

    with patch(
        "app.core.ffmpeg_service.shutil.which", return_value=str(fake_ffmpeg)
    ) as mock_which:
        service = FFmpegService()

    mock_which.assert_called_once_with("ffmpeg")
    assert service.executable == fake_ffmpeg.resolve()


def test_ffmpeg_service_raises_descriptive_error_when_ffmpeg_not_found() -> None:
    # Feature: media-downloader-app, Requirement 5.2
    with patch("app.core.ffmpeg_service.shutil.which", return_value=None):
        with pytest.raises(FFmpegError) as exc_info:
            FFmpegService()

    assert str(exc_info.value)


def test_merge_raises_error_with_stderr_details_when_ffmpeg_fails(
    tmp_path: Path,
) -> None:
    # Feature: media-downloader-app, Requirement 5.5
    video_path = tmp_path / "in" / "video.mp4"
    audio_path = tmp_path / "in" / "audio.m4a"
    output_path = tmp_path / "out" / "result.mkv"

    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"")
    audio_path.write_bytes(b"")

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    failure = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="codec not supported"
    )

    with patch("app.core.ffmpeg_service.subprocess.run", return_value=failure):
        with pytest.raises(FFmpegError) as exc_info:
            service.merge(video_path, audio_path, output_path)

    assert "codec not supported" in str(exc_info.value)


def test_merge_raises_error_when_output_file_missing_after_success(
    tmp_path: Path,
) -> None:
    # Feature: media-downloader-app, Requirement 5.6
    video_path = tmp_path / "in" / "video.mp4"
    audio_path = tmp_path / "in" / "audio.m4a"
    output_path = tmp_path / "out" / "result.mkv"

    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"")
    audio_path.write_bytes(b"")

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    success_but_no_output = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    with (
        patch(
            "app.core.ffmpeg_service.subprocess.run", return_value=success_but_no_output
        ),
        pytest.raises(FFmpegError) as exc_info,
    ):
        service.merge(video_path, audio_path, output_path)

    assert not output_path.exists()
    assert str(exc_info.value)


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    audio_name=_filename_strategy,
    output_name=_filename_strategy,
    bitrate=st.integers().filter(lambda value: value not in {128, 192, 256, 320}),
)
def test_convert_to_mp3_rejects_unsupported_bitrate_without_invoking_ffmpeg(
    tmp_path: Path,
    audio_name: str,
    output_name: str,
    bitrate: int,
) -> None:
    # Feature: media-downloader-app, Property 10: Conversão para MP3 valida o bitrate antes de qualquer execução
    audio_path = tmp_path / "in" / f"{audio_name}.m4a"
    output_path = tmp_path / "out" / f"{output_name}.mp3"

    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"")

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    with patch("app.core.ffmpeg_service.subprocess.run") as mock_run:
        with pytest.raises(FFmpegError):
            service.convert_to_mp3(audio_path, output_path, bitrate)

        mock_run.assert_not_called()


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    audio_name=_filename_strategy,
    output_name=_filename_strategy,
    bitrate=st.sampled_from([128, 192, 256, 320]),
)
def test_convert_to_mp3_command_contains_bitrate_and_libmp3lame_for_supported_values(
    tmp_path: Path,
    audio_name: str,
    output_name: str,
    bitrate: int,
) -> None:
    # Feature: media-downloader-app, Property 10: Conversão para MP3 valida o bitrate antes de qualquer execução
    audio_path = tmp_path / "in" / f"{audio_name}.m4a"
    output_path = tmp_path / "out" / f"{output_name}.mp3"

    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"")

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    captured_commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured_commands.append(command)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"")
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    with patch("app.core.ffmpeg_service.subprocess.run", side_effect=fake_run):
        result = service.convert_to_mp3(audio_path, output_path, bitrate)

    assert result == output_path
    assert len(captured_commands) == 1

    command = captured_commands[0]

    assert "-c:a" in command
    assert command[command.index("-c:a") + 1] == "libmp3lame"
    assert "-b:a" in command
    assert command[command.index("-b:a") + 1] == f"{bitrate}k"


def test_merge_creates_output_directory_before_writing_file(tmp_path: Path) -> None:
    # Feature: media-downloader-app, Requirement 5.7
    video_path = tmp_path / "in" / "video.mp4"
    audio_path = tmp_path / "in" / "audio.m4a"
    output_path = tmp_path / "out" / "nested" / "result.mkv"

    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"")
    audio_path.write_bytes(b"")

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    service = FFmpegService(ffmpeg_path=fake_ffmpeg)

    assert not output_path.parent.exists()

    def fake_run(command, **kwargs):
        # The output directory must already exist by the time FFmpeg would write to it.
        assert output_path.parent.is_dir()
        output_path.write_bytes(b"")
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    with patch("app.core.ffmpeg_service.subprocess.run", side_effect=fake_run):
        result = service.merge(video_path, audio_path, output_path)

    assert result == output_path
    assert output_path.parent.is_dir()
