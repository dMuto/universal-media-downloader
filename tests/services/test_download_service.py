"""Tests for `app.services.download_service.DownloadService`.

This module targets `app/services/download_service.py` (`DownloadService`,
`DownloadHandle`), which does **not** exist yet at this stage of the TDD
plan (Fase 1 / RED). Every test in this file is expected to fail with an
`ImportError`/`ModuleNotFoundError` until task 15 (Fase 2) implements the
service.

The fakes and factories defined near the top of this module are shared
infrastructure meant to be reused by the other `DownloadService` test tasks
(5.6 - 5.10), which append more tests to this same file.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yt_dlp
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.downloader import Downloader
from app.core.ffmpeg_service import FFmpegError, FFmpegService
from app.core.format_selector import FormatSelectionError, FormatSelector
from app.models import (
    AppConfig,
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    DownloadStatus,
    DownloadType,
    FormatSelection,
    HistoryEntry,
)
from app.services.config_service import ConfigService
from app.services.download_service import DownloadHandle, DownloadService
from app.services.history_service import HistoryService

# ---------------------------------------------------------------------------
# Shared fakes/factories for `DownloadService` tests (tasks 5.5 - 5.10).
#
# `DownloadService` is designed to compose `Downloader`, `FormatSelector`
# and `FFmpegService` (plus `ConfigService`/`HistoryService`) via
# constructor injection, so every test below builds `MagicMock(spec=...)`
# fakes for those collaborators instead of touching the real Core/yt-dlp.
# ---------------------------------------------------------------------------


def make_fake_downloader() -> MagicMock:
    """Return a `MagicMock` fake honoring `Downloader`'s public surface."""
    return MagicMock(spec=Downloader)


def make_fake_format_selector() -> MagicMock:
    """Return a `MagicMock` fake honoring `FormatSelector`'s public surface."""
    return MagicMock(spec=FormatSelector)


def make_fake_ffmpeg_service() -> MagicMock:
    """Return a `MagicMock` fake honoring `FFmpegService`'s public surface."""
    return MagicMock(spec=FFmpegService)


def wait_for_completion(
    event: threading.Event,
    timeout: float = 5.0,
) -> bool:
    """Block the calling (test) thread until `event` is set or times out.

    `DownloadService` runs operations on a background worker thread and
    reports completion via the `on_complete` callback, so tests use this
    helper (backed by a `threading.Event` set from within `on_complete`)
    to wait deterministically instead of polling or sleeping.
    """
    return event.wait(timeout=timeout)


def make_download_options(
    destination: Path,
    *,
    download_type: DownloadType = DownloadType.VIDEO,
) -> DownloadOptions:
    """Build a minimal, valid `DownloadOptions` for use across tests."""
    return DownloadOptions(
        url="https://example.com/watch?v=sample",
        download_type=download_type,
        destination=destination,
    )


# ---------------------------------------------------------------------------
# Property test (task 5.5): internal failures occurring anywhere within an
# operation orchestrated by `DownloadService` (format selection, download,
# FFmpeg merge/conversion, or any other unexpected exception inside the
# worker) must never escape as unhandled exceptions. `DownloadService` is
# the final error-handling boundary before the GUI (Requirements 9.4, 10.4):
# any such failure SHALL surface as a `DownloadResult(success=False,
# error_message=<non-empty str>)` delivered through `on_complete`, never as
# a propagated exception out of `start_download`/`cancel` themselves.
# ---------------------------------------------------------------------------

_EXCEPTION_FACTORIES: dict[str, Callable[[str], Exception]] = {
    "yt_dlp_download_error": lambda message: yt_dlp.utils.DownloadError(message),
    "ffmpeg_error": lambda message: FFmpegError(message),
    "format_selection_error": lambda message: FormatSelectionError(message),
    "os_error": lambda message: OSError(message),
    "generic_exception": lambda message: RuntimeError(message),
}

_RAISE_POINTS = ("format_selector", "downloader")

_error_message_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        min_codepoint=48,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=40,
)


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    raise_point=st.sampled_from(_RAISE_POINTS),
    exception_name=st.sampled_from(sorted(_EXCEPTION_FACTORIES)),
    error_message=_error_message_strategy,
)
def test_start_download_internal_failures_never_escape_unhandled(
    tmp_path: Path,
    make_media_info,
    raise_point: str,
    exception_name: str,
    error_message: str,
) -> None:
    # Feature: media-downloader-app, Property 11: Falhas internas nunca escapam como exceções não tratadas
    """**Validates: Requirements 9.4, 10.4**"""
    media = make_media_info()
    options = make_download_options(tmp_path)

    exception_factory = _EXCEPTION_FACTORIES[exception_name]
    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    if raise_point == "format_selector":
        fake_format_selector.select.side_effect = exception_factory(error_message)
    else:
        fake_format_selector.select.return_value = FormatSelection(
            video_format=media.formats[0],
        )
        fake_downloader.download.side_effect = exception_factory(error_message)

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    try:
        handle = service.start_download(media, options, on_complete=on_complete)
    except Exception as exc:  # pragma: no cover - this is the failure we assert against
        raise AssertionError(
            f"[{raise_point}/{exception_name}] start_download() propagated "
            f"an exception instead of handling it internally: {exc!r}"
        ) from exc

    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        f"[{raise_point}/{exception_name}] on_complete was not invoked "
        f"within the timeout after an internal failure."
    )

    assert len(received_results) == 1
    result = received_results[0]

    assert isinstance(result, DownloadResult)
    assert result.success is False, (
        f"[{raise_point}/{exception_name}] Esperava DownloadResult(success=False) "
        f"após uma falha interna, mas obteve success={result.success!r}."
    )
    assert result.error_message, (
        f"[{raise_point}/{exception_name}] Esperava uma `error_message` textual "
        f"não vazia descrevendo a falha interna, mas obteve "
        f"{result.error_message!r}."
    )

    progress = service.get_progress(handle.operation_id)
    if progress is not None:
        assert progress.status == DownloadStatus.FAILED, (
            f"[{raise_point}/{exception_name}] Esperava status FAILED no "
            f"progresso final, mas obteve {progress.status!r}."
        )

    try:
        service.cancel(handle.operation_id)
    except Exception as exc:  # pragma: no cover - this is the failure we assert against
        raise AssertionError(
            f"[{raise_point}/{exception_name}] cancel() on an already-terminal "
            f"operation propagated an exception instead of being a no-op: {exc!r}"
        ) from exc


# ---------------------------------------------------------------------------
# Property test (task 5.6): the raw yt-dlp progress dict delivered to the
# `progress_hook` that `DownloadService` passes down to `Downloader.download`
# may have an arbitrary subset of its optional fields (`downloaded_bytes`,
# `total_bytes`, `speed`, `eta`, `filename`) missing or explicitly `None`.
# Whatever `DownloadProgress` ends up being emitted towards `on_progress`
# SHALL contain `None` for each field absent from the source dict (never a
# presumed/default value) and SHALL contain the exact value for each field
# present in the source dict (Requirements 7.2, 7.5).
# ---------------------------------------------------------------------------

_OPTIONAL_PROGRESS_FIELDS: dict[str, st.SearchStrategy] = {
    "downloaded_bytes": st.integers(min_value=0, max_value=10**10),
    "total_bytes": st.integers(min_value=0, max_value=10**10),
    "speed": st.floats(
        min_value=0,
        max_value=10**8,
        allow_nan=False,
        allow_infinity=False,
    ),
    "eta": st.integers(min_value=0, max_value=100_000),
    "filename": st.text(min_size=1, max_size=50),
}


@st.composite
def _raw_progress_dicts(draw: st.DrawFn) -> dict:
    """Build a raw yt-dlp progress dict with an arbitrary subset of the
    optional fields missing, explicitly `None`, or populated with a
    realistic value, mirroring `_raw_format_dicts` in
    `tests/core/test_downloader.py`.
    """
    data: dict = {"status": "downloading"}

    for field, strategy in _OPTIONAL_PROGRESS_FIELDS.items():
        presence = draw(st.sampled_from(["missing", "none", "value"]))

        if presence == "missing":
            continue

        if presence == "none":
            data[field] = None
            continue

        data[field] = draw(strategy)

    return data


def _progress_matches_raw_dict(progress: DownloadProgress, raw: dict) -> bool:
    """Return whether `progress`'s optional fields reflect exactly what was
    present (or absent) in the raw yt-dlp-style `raw` progress dict:
    missing/`None` source fields SHALL map to `None`, present fields SHALL
    map to the exact same value.
    """
    for field in _OPTIONAL_PROGRESS_FIELDS:
        if getattr(progress, field) != raw.get(field):
            return False

    return True


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(raw_progress_dicts=st.lists(_raw_progress_dicts(), min_size=1, max_size=5))
def test_emitted_progress_reflects_only_available_fields(
    tmp_path: Path,
    make_media_info,
    raw_progress_dicts: list[dict],
) -> None:
    # Feature: media-downloader-app, Property 12: Progresso emitido reflete apenas os campos disponíveis
    """**Validates: Requirements 7.2, 7.5**"""
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    def fake_download(*args, **kwargs):
        progress_hook = kwargs.get("progress_hook")

        if progress_hook is None:
            for arg in args:
                if callable(arg):
                    progress_hook = arg
                    break

        if progress_hook is not None:
            for raw_progress in raw_progress_dicts:
                progress_hook(raw_progress)

        output_path = tmp_path / "output.mp4"
        return DownloadResult(
            success=True,
            file_path=output_path,
            file_size=123,
        )

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_progress: list[DownloadProgress] = []
    received_results: list[DownloadResult] = []

    def on_progress(progress: DownloadProgress) -> None:
        received_progress.append(progress)

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(
        media,
        options,
        on_progress=on_progress,
        on_complete=on_complete,
    )

    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout while verifying "
        "emitted progress."
    )

    assert len(received_results) == 1
    assert received_results[0].success is True

    for raw_progress in raw_progress_dicts:
        assert any(
            _progress_matches_raw_dict(progress, raw_progress)
            for progress in received_progress
        ), (
            f"Nenhum DownloadProgress emitido corresponde exatamente ao "
            f"dict de progresso bruto {raw_progress!r} (campos ausentes "
            f"deveriam mapear para None, campos presentes deveriam manter "
            f"o valor exato)."
        )


# ---------------------------------------------------------------------------
# Property test (task 5.7): for any operation orchestrated by
# `DownloadService` (analysis, download, merge or conversion), the sequence
# of `DownloadStatus` values emitted via `on_progress` SHALL be
# non-decreasing with respect to the phase ordering (`PENDING ->
# ANALYZING/DOWNLOADING -> PROCESSING -> terminal state`) and SHALL contain
# exactly one terminal state (`COMPLETED`, `FAILED` or `CANCELLED`) as its
# last element: `COMPLETED` iff the operation succeeds, `FAILED` iff an
# error occurs, `CANCELLED` iff a cancellation is confirmed (Requirements
# 7.3, 7.4, 8.3).
# ---------------------------------------------------------------------------

_STATUS_PHASE_RANK: dict[DownloadStatus, int] = {
    DownloadStatus.PENDING: 0,
    DownloadStatus.ANALYZING: 1,
    DownloadStatus.DOWNLOADING: 1,
    DownloadStatus.PROCESSING: 2,
    DownloadStatus.COMPLETED: 3,
    DownloadStatus.FAILED: 3,
    DownloadStatus.CANCELLED: 3,
}

_TERMINAL_STATUSES = frozenset(
    {DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED}
)

_OUTCOME_TERMINAL_STATUS: dict[str, DownloadStatus] = {
    "success": DownloadStatus.COMPLETED,
    "failure": DownloadStatus.FAILED,
    "cancelled": DownloadStatus.CANCELLED,
}


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(outcome=st.sampled_from(sorted(_OUTCOME_TERMINAL_STATUS)))
def test_progress_status_machine_has_exactly_one_coherent_terminal_state(
    tmp_path: Path,
    make_media_info,
    outcome: str,
) -> None:
    # Feature: media-downloader-app, Property 13: Máquina de estados de progresso tem exatamente um estado terminal coerente
    """**Validates: Requirements 7.3, 7.4, 8.3**"""
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    # `handle` is only known after `start_download()` returns, but the
    # "cancelled" scenario needs to call `service.cancel(handle.operation_id)`
    # from *inside* the fake downloader (i.e. from the worker that is
    # executing the download), simulating a cooperative cancellation point
    # confirmed mid-flight. A small handshake via `handle_ready`/
    # `handle_holder` lets the fake wait for the handle to become available
    # regardless of whether `start_download()` runs the worker synchronously
    # or on a background thread.
    handle_ready = threading.Event()
    handle_holder: dict[str, DownloadHandle] = {}

    def fake_download(*args, **kwargs):
        progress_hook = kwargs.get("progress_hook")
        if progress_hook is None:
            for arg in args:
                if callable(arg):
                    progress_hook = arg
                    break

        if progress_hook is not None:
            progress_hook(
                {"status": "downloading", "downloaded_bytes": 100, "total_bytes": 1000}
            )
            progress_hook(
                {"status": "downloading", "downloaded_bytes": 500, "total_bytes": 1000}
            )

        if outcome == "success":
            return DownloadResult(
                success=True,
                file_path=tmp_path / "output.mp4",
                file_size=123,
            )

        if outcome == "failure":
            return DownloadResult(success=False, error_message="boom")

        # outcome == "cancelled": confirm the cancellation from within the
        # download worker itself, before the worker returns its
        # (necessarily unsuccessful) result.
        handle_ready.wait(timeout=5.0)
        handle = handle_holder.get("handle")
        if handle is not None:
            service.cancel(handle.operation_id)
        return DownloadResult(success=False, error_message="Operação cancelada")

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_statuses: list[DownloadStatus] = []
    received_results: list[DownloadResult] = []

    def on_progress(progress: DownloadProgress) -> None:
        received_statuses.append(progress.status)

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(
        media,
        options,
        on_progress=on_progress,
        on_complete=on_complete,
    )
    handle_holder["handle"] = handle
    handle_ready.set()

    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        f"[{outcome}] on_complete was not invoked within the timeout while "
        f"verifying the progress status machine."
    )

    assert received_statuses, (
        f"[{outcome}] Esperava ao menos um DownloadStatus emitido via "
        f"on_progress, mas nenhum foi recebido."
    )

    ranks = [_STATUS_PHASE_RANK[status] for status in received_statuses]
    assert ranks == sorted(ranks), (
        f"[{outcome}] A sequência de estados {received_statuses!r} não é "
        f"não-decrescente em relação à ordem de fases "
        f"(PENDING -> ANALYZING/DOWNLOADING -> PROCESSING -> terminal); "
        f"ranks observados: {ranks!r}."
    )

    terminal_statuses = [
        status for status in received_statuses if status in _TERMINAL_STATUSES
    ]
    assert len(terminal_statuses) == 1, (
        f"[{outcome}] Esperava exatamente um estado terminal na sequência "
        f"{received_statuses!r}, mas encontrou {terminal_statuses!r}."
    )
    assert received_statuses[-1] in _TERMINAL_STATUSES, (
        f"[{outcome}] Esperava que o estado terminal fosse o último "
        f"elemento da sequência, mas obteve {received_statuses!r}."
    )

    expected_terminal = _OUTCOME_TERMINAL_STATUS[outcome]
    assert received_statuses[-1] == expected_terminal, (
        f"[{outcome}] Esperava o estado terminal {expected_terminal!r}, "
        f"mas obteve {received_statuses[-1]!r}."
    )


# ---------------------------------------------------------------------------
# Property test (task 5.8): for any download/merge operation cancelled at an
# arbitrary point relative to how many temporary artifacts it has already
# created, once the cancellation is confirmed: (a) no final file in the
# destination directory SHALL be replaced by partial data, and (b) no
# temporary file created by that operation SHALL remain on the filesystem
# (Requirements 8.2, 8.4).
#
# `DownloadService` creates a `threading.Event` (`cancel_event`) per
# operation and passes it down into `Downloader.download(...,
# cancel_event=...)`; `DownloadService.cancel(operation_id)` simply calls
# `cancel_event.set()`. The fake `Downloader.download` below plays the role
# of a cooperative worker: it writes an arbitrary number of partial/temp
# files under a clearly-temporary subdirectory of the destination (never
# directly into the destination itself), waits for `cancel_event` to be set
# by `service.cancel(...)`, and only then performs the cleanup that the
# real `Downloader`/`DownloadService` is expected to implement.
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(num_temp_files_before_cancel=st.integers(min_value=0, max_value=3))
def test_cancellation_does_not_corrupt_destination_and_removes_temp_files(
    tmp_path: Path,
    make_media_info,
    num_temp_files_before_cancel: int,
) -> None:
    # Feature: media-downloader-app, Property 14: Cancelamento não corrompe o destino e remove temporários
    """**Validates: Requirements 8.2, 8.4**"""
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    def fake_download(*args, **kwargs):
        cancel_event = kwargs.get("cancel_event")
        if cancel_event is None:
            for arg in args:
                if isinstance(arg, threading.Event):
                    cancel_event = arg
                    break

        assert cancel_event is not None, (
            "DownloadService deveria passar um `cancel_event` (threading.Event) "
            "para Downloader.download(), mas nenhum foi recebido."
        )

        # Simulate partial download artifacts created *before* cancellation
        # is confirmed, always inside a clearly-temporary subdirectory of
        # the destination, never directly as a final file in `tmp_path`.
        temp_dir = tmp_path / "umd_tmp_cancel_op"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_files = []
        for i in range(num_temp_files_before_cancel):
            temp_file = temp_dir / f"part_{i}.tmp"
            temp_file.write_bytes(b"partial-data")
            temp_files.append(temp_file)

        # Wait (without a real test-driven sleep) until `service.cancel(...)`
        # sets the event, then perform the cooperative cleanup that
        # `Downloader`/`DownloadService` is expected to implement.
        confirmed = cancel_event.wait(timeout=5.0)
        assert confirmed, (
            "cancel_event nunca foi sinalizado por service.cancel() dentro do timeout."
        )

        for temp_file in temp_files:
            temp_file.unlink(missing_ok=True)
        if temp_dir.exists():
            temp_dir.rmdir()

        return DownloadResult(success=False, error_message="Operação cancelada")

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    service.cancel(handle.operation_id)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        f"[num_temp_files_before_cancel={num_temp_files_before_cancel}] "
        f"on_complete was not invoked within the timeout after cancellation."
    )

    assert len(received_results) == 1
    result = received_results[0]
    assert isinstance(result, DownloadResult)
    assert result.success is False, (
        f"[num_temp_files_before_cancel={num_temp_files_before_cancel}] "
        f"Esperava DownloadResult(success=False) após o cancelamento, mas "
        f"obteve success={result.success!r}."
    )

    remaining_entries = list(tmp_path.iterdir())
    assert remaining_entries == [], (
        f"[num_temp_files_before_cancel={num_temp_files_before_cancel}] "
        f"Esperava o diretório de destino {tmp_path} livre de arquivos "
        f"finais corrompidos e de temporários após o cancelamento, mas "
        f"encontrou: {remaining_entries!r}."
    )


# ---------------------------------------------------------------------------
# Property test (task 5.9): for any operation (completed successfully,
# failed or cancelled) processed by `DownloadService`, there SHALL exist
# exactly one `HistoryEntry` added to the injected `HistoryService` whose
# `url`, `download_type` and `status` fields correspond exactly to the
# operation's, with `file_path` populated if and only if
# `status == DownloadStatus.COMPLETED` (Requirements 14.1).
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    outcome=st.sampled_from(sorted(_OUTCOME_TERMINAL_STATUS)),
    download_type=st.sampled_from(list(DownloadType)),
)
def test_every_finished_operation_generates_exactly_one_consistent_history_entry(
    tmp_path: Path,
    make_media_info,
    outcome: str,
    download_type: DownloadType,
) -> None:
    # Feature: media-downloader-app, Property 16: Toda operação finalizada gera exatamente uma entrada de histórico consistente
    """**Validates: Requirements 14.1**"""
    media = make_media_info()
    options = make_download_options(tmp_path, download_type=download_type)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()
    fake_history_service = MagicMock(spec=HistoryService)

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    # Same handshake pattern as task 5.7's test: the "cancelled" scenario
    # needs to call `service.cancel(handle.operation_id)` from *inside* the
    # fake downloader, so it must wait until the handle (only known after
    # `start_download()` returns) is published by the test thread.
    handle_ready = threading.Event()
    handle_holder: dict[str, DownloadHandle] = {}

    expected_file_path: Path | None = None

    def fake_download(*args, **kwargs):
        nonlocal expected_file_path

        if outcome == "success":
            expected_file_path = tmp_path / "output.mp4"
            return DownloadResult(
                success=True,
                file_path=expected_file_path,
                file_size=1234,
            )

        if outcome == "failure":
            return DownloadResult(success=False, error_message="boom")

        # outcome == "cancelled": confirm the cancellation from within the
        # download worker itself, before the worker returns its
        # (necessarily unsuccessful) result.
        handle_ready.wait(timeout=5.0)
        handle = handle_holder.get("handle")
        if handle is not None:
            service.cancel(handle.operation_id)
        return DownloadResult(success=False, error_message="Operação cancelada")

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
        history_service=fake_history_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    handle_holder["handle"] = handle
    handle_ready.set()

    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        f"[{outcome}/{download_type!r}] on_complete was not invoked within "
        f"the timeout while verifying history entry generation."
    )

    assert len(received_results) == 1

    assert fake_history_service.add_entry.call_count == 1, (
        f"[{outcome}/{download_type!r}] Esperava que "
        f"HistoryService.add_entry fosse chamado exatamente uma vez, mas "
        f"foi chamado {fake_history_service.add_entry.call_count} vez(es)."
    )

    call_args = fake_history_service.add_entry.call_args
    entry = call_args.args[0] if call_args.args else call_args.kwargs.get("entry")
    assert isinstance(entry, HistoryEntry), (
        f"[{outcome}/{download_type!r}] Esperava que add_entry fosse "
        f"chamado com uma `HistoryEntry`, mas obteve {entry!r}."
    )

    assert entry.url == options.url, (
        f"[{outcome}/{download_type!r}] Esperava HistoryEntry.url == "
        f"{options.url!r}, mas obteve {entry.url!r}."
    )
    assert entry.download_type == download_type, (
        f"[{outcome}/{download_type!r}] Esperava HistoryEntry.download_type "
        f"== {download_type!r}, mas obteve {entry.download_type!r}."
    )

    expected_status = _OUTCOME_TERMINAL_STATUS[outcome]
    assert entry.status == expected_status, (
        f"[{outcome}/{download_type!r}] Esperava HistoryEntry.status == "
        f"{expected_status!r}, mas obteve {entry.status!r}."
    )

    if expected_status == DownloadStatus.COMPLETED:
        assert entry.file_path == expected_file_path, (
            f"[{outcome}/{download_type!r}] Esperava HistoryEntry.file_path "
            f"== {expected_file_path!r} para uma operação concluída, mas "
            f"obteve {entry.file_path!r}."
        )
    else:
        assert entry.file_path is None, (
            f"[{outcome}/{download_type!r}] Esperava HistoryEntry.file_path "
            f"== None para uma operação não concluída (status="
            f"{expected_status!r}), mas obteve {entry.file_path!r}."
        )


# ---------------------------------------------------------------------------
# Unit tests de exemplo (task 5.10) para `DownloadService`.
#
# Diferente dos testes de propriedade acima (tasks 5.5 - 5.9), estes testes
# cobrem cenários de exemplo específicos: estado inicial emitido ao iniciar
# uma operação (7.1); `cancel()` aceito durante uma operação em curso (8.1);
# `cancel()` em operação já terminal como no-op sem erro (8.5); `analyze`/
# `start_download` executando fora da thread chamadora (9.1); conclusão
# consultável pela thread principal via `get_progress` (9.3); tradução de
# erro interno em mensagem amigável sem vazar a exceção bruta (10.4); e
# aplicação do bitrate de áudio padrão da `ConfigService` quando
# `audio_bitrate` não é informado (6.6).
# ---------------------------------------------------------------------------


def test_initial_progress_emitted_when_starting_download_is_non_terminal(
    tmp_path: Path,
    make_media_info,
) -> None:
    """Estado inicial emitido ao iniciar uma operação de download.

    O primeiro `DownloadProgress` entregue via `on_progress` deve refletir
    que a operação começou (um status não terminal, como `PENDING`,
    `ANALYZING` ou `DOWNLOADING`), nunca pulando direto para um estado
    terminal sem nenhuma emissão intermediária.

    **Validates: Requirements 7.1**
    """
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    start_delay = threading.Event()

    def fake_download(*args, **kwargs):
        # Dá à thread de teste uma janela breve para observar progresso
        # emitido antes da operação atingir um estado terminal.
        start_delay.wait(timeout=0.1)
        return DownloadResult(
            success=True,
            file_path=tmp_path / "output.mp4",
            file_size=123,
        )

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_progress: list[DownloadProgress] = []
    received_results: list[DownloadResult] = []

    def on_progress(progress: DownloadProgress) -> None:
        received_progress.append(progress)

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(
        media,
        options,
        on_progress=on_progress,
        on_complete=on_complete,
    )

    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout while verifying "
        "the initial progress emission."
    )

    assert len(received_results) == 1

    non_terminal_statuses = {
        DownloadStatus.PENDING,
        DownloadStatus.ANALYZING,
        DownloadStatus.DOWNLOADING,
    }

    assert received_progress, (
        "Esperava ao menos um DownloadProgress emitido via on_progress ao "
        "iniciar a operação, mas nenhum foi recebido."
    )
    assert received_progress[0].status in non_terminal_statuses, (
        f"Esperava que o primeiro DownloadProgress emitido refletisse um "
        f"estado não terminal ({non_terminal_statuses!r}) indicando que a "
        f"operação começou, mas obteve {received_progress[0].status!r}."
    )


def test_cancel_accepted_during_in_flight_operation(
    tmp_path: Path,
    make_media_info,
) -> None:
    """`cancel()` aceito durante uma operação em curso.

    **Validates: Requirements 8.1**
    """
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    def fake_download(*args, **kwargs):
        cancel_event = kwargs.get("cancel_event")
        if cancel_event is None:
            for arg in args:
                if isinstance(arg, threading.Event):
                    cancel_event = arg
                    break

        if cancel_event is not None:
            cancel_event.wait(timeout=5.0)

        return DownloadResult(success=False, error_message="Operação cancelada")

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    try:
        service.cancel(handle.operation_id)
    except Exception as exc:  # pragma: no cover - this is the failure we assert against
        raise AssertionError(
            f"cancel() em uma operação em curso propagou uma exceção em "
            f"vez de ser aceito: {exc!r}"
        ) from exc

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout after cancel() "
        "was called on an in-flight operation."
    )

    assert len(received_results) == 1
    assert received_results[0].success is False, (
        f"Esperava DownloadResult(success=False) após o cancelamento de "
        f"uma operação em curso, mas obteve "
        f"success={received_results[0].success!r}."
    )


def test_cancel_on_already_terminal_operation_is_noop(
    tmp_path: Path,
    make_media_info,
) -> None:
    """`cancel()` em uma operação já terminal é um no-op sem erro.

    **Validates: Requirements 8.5**
    """
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    fake_downloader.download.return_value = DownloadResult(
        success=True,
        file_path=tmp_path / "output.mp4",
        file_size=123,
    )

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout before testing "
        "cancel() on an already-terminal operation."
    )
    assert len(received_results) == 1

    try:
        service.cancel(handle.operation_id)
    except Exception as exc:  # pragma: no cover - this is the failure we assert against
        raise AssertionError(
            f"cancel() em uma operação já terminal propagou uma exceção "
            f"em vez de ser um no-op silencioso: {exc!r}"
        ) from exc


def test_start_download_executes_outside_calling_thread(
    tmp_path: Path,
    make_media_info,
) -> None:
    """`start_download` executa `Downloader.download` fora da thread chamadora.

    **Validates: Requirements 9.1**
    """
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    download_threads: list[threading.Thread] = []

    def fake_download(*args, **kwargs):
        download_threads.append(threading.current_thread())
        return DownloadResult(
            success=True,
            file_path=tmp_path / "output.mp4",
            file_size=123,
        )

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    calling_thread = threading.current_thread()
    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout while verifying "
        "that start_download executes outside the calling thread."
    )

    assert len(received_results) == 1
    assert len(download_threads) == 1
    assert download_threads[0] is not calling_thread, (
        f"Esperava que Downloader.download fosse executado em uma thread "
        f"diferente da chamadora {calling_thread!r}, mas foi executado na "
        f"mesma thread {download_threads[0]!r}."
    )


def test_analyze_executes_outside_calling_thread(
    make_media_info,
) -> None:
    """`analyze` executa `Downloader.analyze` fora da thread chamadora.

    **Validates: Requirements 9.1**
    """
    media = make_media_info()

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    analyze_threads: list[threading.Thread] = []

    def fake_analyze(*args, **kwargs):
        analyze_threads.append(threading.current_thread())
        return media

    fake_downloader.analyze.side_effect = fake_analyze

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received: list[tuple] = []

    def on_complete(result_media, error_message) -> None:
        received.append((result_media, error_message))
        completion_event.set()

    calling_thread = threading.current_thread()
    handle = service.analyze(
        "https://example.com/watch?v=sample",
        on_complete=on_complete,
    )
    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout while verifying "
        "that analyze executes outside the calling thread."
    )

    assert len(analyze_threads) == 1
    assert analyze_threads[0] is not calling_thread, (
        f"Esperava que Downloader.analyze fosse executado em uma thread "
        f"diferente da chamadora {calling_thread!r}, mas foi executado na "
        f"mesma thread {analyze_threads[0]!r}."
    )


def test_completed_operation_progress_is_queryable_from_calling_thread(
    tmp_path: Path,
    make_media_info,
) -> None:
    """Conclusão consultável pela thread principal via `get_progress`.

    Além de notificar via `on_complete`, o resultado final de uma operação
    deve ficar disponível para consulta pela thread chamadora através de
    `DownloadService.get_progress(operation_id)`, sem depender do callback.

    **Validates: Requirements 9.3**
    """
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    fake_downloader.download.return_value = DownloadResult(
        success=True,
        file_path=tmp_path / "output.mp4",
        file_size=123,
    )

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout while verifying "
        "get_progress querying from the calling thread."
    )
    assert len(received_results) == 1

    progress = service.get_progress(handle.operation_id)
    assert progress is not None, (
        "Esperava que get_progress() retornasse um DownloadProgress "
        "consultável pela thread principal após a conclusão, mas obteve "
        "None."
    )
    assert isinstance(progress, DownloadProgress)
    assert progress.status == DownloadStatus.COMPLETED, (
        f"Esperava DownloadProgress.status == DownloadStatus.COMPLETED, "
        f"mas obteve {progress.status!r}."
    )


def test_internal_exception_is_translated_without_leaking_raw_exception(
    tmp_path: Path,
    make_media_info,
) -> None:
    """Tradução de erro interno em mensagem amigável sem vazar a exceção.

    **Validates: Requirements 10.4**
    """
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    fake_downloader.download.side_effect = RuntimeError(
        "some internal technical detail"
    )

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout while verifying "
        "error message translation."
    )

    assert len(received_results) == 1
    result = received_results[0]

    assert result.success is False, (
        f"Esperava DownloadResult(success=False) após uma falha interna "
        f"não tratada, mas obteve success={result.success!r}."
    )
    assert isinstance(result.error_message, str) and result.error_message, (
        f"Esperava uma `error_message` textual não vazia descrevendo a "
        f"falha de forma amigável, mas obteve {result.error_message!r}."
    )
    assert "RuntimeError" not in result.error_message, (
        f"A mensagem de erro não deveria vazar o nome da exceção Python "
        f"bruta, mas obteve {result.error_message!r}."
    )
    assert "Traceback" not in result.error_message, (
        f"A mensagem de erro não deveria conter um traceback, mas obteve "
        f"{result.error_message!r}."
    )


def test_default_audio_bitrate_applied_when_not_informed(
    tmp_path: Path,
    make_media_info,
) -> None:
    """Bitrate de áudio padrão da `ConfigService` aplicado quando ausente.

    Quando `DownloadOptions.audio_bitrate` não é informado para um download
    de áudio, `DownloadService` deve preencher o valor com
    `ConfigService.load().default_audio_bitrate` antes de chamar
    `Downloader.download`.

    **Validates: Requirements 6.6**
    """
    media = make_media_info()
    options = make_download_options(tmp_path, download_type=DownloadType.AUDIO)
    assert options.audio_bitrate is None

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()
    fake_config_service = MagicMock(spec=ConfigService)
    fake_config_service.load.return_value = AppConfig(default_audio_bitrate=256)

    fake_format_selector.select.return_value = FormatSelection(
        audio_format=media.formats[0],
    )

    captured_options: list[DownloadOptions] = []

    def fake_download(*args, **kwargs):
        called_options = kwargs.get("options")
        if called_options is None:
            for arg in args:
                if isinstance(arg, DownloadOptions):
                    called_options = arg
                    break
        captured_options.append(called_options)
        return DownloadResult(
            success=True,
            file_path=tmp_path / "output.mp3",
            file_size=123,
        )

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
        config_service=fake_config_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    completed_in_time = wait_for_completion(completion_event)
    assert completed_in_time, (
        "on_complete was not invoked within the timeout while verifying "
        "the default audio bitrate application."
    )

    assert len(received_results) == 1
    assert len(captured_options) == 1
    called_options = captured_options[0]
    assert called_options is not None, (
        "Esperava capturar as DownloadOptions efetivamente passadas para "
        "Downloader.download(), mas nenhuma foi recebida."
    )
    assert called_options.audio_bitrate == 256, (
        f"Esperava que DownloadService preenchesse audio_bitrate com o "
        f"valor padrão 256 vindo de ConfigService.load(), mas obteve "
        f"{called_options.audio_bitrate!r}."
    )


def test_shutdown_rejects_new_submissions_and_waits_for_in_flight_operation(
    tmp_path: Path,
    make_media_info,
) -> None:
    """`DownloadService.shutdown()` encerra o `ThreadPoolExecutor` interno.

    Após `shutdown(wait=True)`: (a) a chamada só retorna depois que a
    operação já submetida antes dela termina (comprovado aqui pelo
    `on_complete` já ter sido entregue no momento em que `shutdown()`
    retorna); e (b) novas submissões (`analyze`/`start_download`, que
    delegam a `self._executor.submit`) deixam de ser aceitas, levantando
    `RuntimeError`, conforme o comportamento padrão de
    `concurrent.futures.ThreadPoolExecutor` após `shutdown()`.
    """
    media = make_media_info()
    options = make_download_options(tmp_path)

    fake_format_selector = make_fake_format_selector()
    fake_downloader = make_fake_downloader()
    fake_ffmpeg_service = make_fake_ffmpeg_service()

    fake_format_selector.select.return_value = FormatSelection(
        video_format=media.formats[0],
    )

    # A operação em curso só termina depois que `release_download` é
    # sinalizado, permitindo observar que `shutdown(wait=True)` de fato
    # aguarda sua conclusão antes de retornar.
    release_download = threading.Event()

    def fake_download(*args, **kwargs):
        release_download.wait(timeout=5.0)
        return DownloadResult(
            success=True,
            file_path=tmp_path / "output.mp4",
            file_size=123,
        )

    fake_downloader.download.side_effect = fake_download

    service = DownloadService(
        downloader=fake_downloader,
        format_selector=fake_format_selector,
        ffmpeg_service=fake_ffmpeg_service,
    )

    completion_event = threading.Event()
    received_results: list[DownloadResult] = []

    def on_complete(result: DownloadResult) -> None:
        received_results.append(result)
        completion_event.set()

    handle = service.start_download(media, options, on_complete=on_complete)
    assert isinstance(handle, DownloadHandle)

    # Garante que a operação ainda está em curso (não terminou) antes de
    # chamar shutdown(), para que o teste de fato comprove que
    # shutdown(wait=True) espera por ela.
    assert not completion_event.is_set()

    shutdown_thread = threading.Thread(target=service.shutdown)
    shutdown_thread.start()

    # Dá um pequeno intervalo para `shutdown()` começar a bloquear antes
    # de liberar a operação em curso, sem depender de um timing exato.
    shutdown_thread.join(timeout=0.2)
    assert shutdown_thread.is_alive(), (
        "Esperava que shutdown(wait=True) estivesse bloqueado aguardando "
        "a operação em curso, mas retornou antes dela terminar."
    )

    release_download.set()
    shutdown_thread.join(timeout=5.0)
    assert not shutdown_thread.is_alive(), (
        "shutdown(wait=True) não retornou dentro do timeout após a "
        "operação em curso ser liberada."
    )

    assert completion_event.is_set(), (
        "Esperava que a operação em curso tivesse sido concluída (e "
        "on_complete entregue) antes de shutdown(wait=True) retornar."
    )
    assert len(received_results) == 1
    assert received_results[0].success is True

    # Após o encerramento, novas submissões não são aceitas: tanto
    # `analyze` quanto `start_download` delegam a `self._executor.submit`,
    # que levanta `RuntimeError` em um executor já encerrado.
    with pytest.raises(RuntimeError):
        service.analyze("https://example.com/watch?v=sample")

    with pytest.raises(RuntimeError):
        service.start_download(media, options)
