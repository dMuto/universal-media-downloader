"""Example-based tests for the `DownloadPanel` / `ProgressWidget` GUI components.

RED phase (TDD): `app/gui/download_panel.py` and `app/gui/progress_widget.py`
do not exist yet. These tests are expected to fail with an `ImportError`
(`ModuleNotFoundError`) until task 17 implements the GUI layer. They are
written now so they become meaningful (and are expected to pass, possibly
after minor adjustment) once `DownloadPanel`/`ProgressWidget` exist.

Design contract assumed from `.kiro/specs/media-downloader-app/design.md`
(section "`app/gui` (novo)"), since the real implementation does not exist:

- `DownloadPanel(master, download_service)`:
    - exposes `url_var`, `download_type_var`, `max_height_var`,
      `audio_bitrate_var`, `destination_var` (Tkinter-style variables bound
      to the corresponding input widgets).
    - `on_analyze()` reads `url_var` and calls `download_service.analyze(
      url, on_complete=...)`.
    - `on_download()` builds a `DownloadOptions` from the current selection
      and calls `download_service.start_download(media, options,
      on_progress=..., on_complete=...)`.
    - `on_cancel()` calls `download_service.cancel(operation_id)` for the
      currently tracked operation.
    - exposes `title_text`, `uploader_text`, `thumbnail_text` (or
      equivalent getters) reflecting the analyzed `MediaInfo`.
    - exposes `error_text` reflecting the last `error_message` received
      from the service (never a raw exception/traceback).
    - exposes a `progress_widget` attribute (a `ProgressWidget` instance)
      that is updated whenever the service reports progress.
- `ProgressWidget(master)`:
    - `update_progress(progress: DownloadProgress)` updates the displayed
      percentage and status.
    - exposes `percentage_text`/`status_text` (or equivalent getters)
      reflecting the last `DownloadProgress` applied.

Only `app.services`/`app.models` concepts are used by the fakes below, per
the requirement that the GUI never imports `Downloader`, `FormatSelector`
or `FFmpegService` directly.

**Validates: Requirements 12.3, 12.4, 12.5, 12.6, 12.7**
"""

from dataclasses import dataclass, field
from typing import Callable, Optional
from uuid import UUID, uuid4

import pytest

from app.models import (
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    DownloadStatus,
    DownloadType,
    MediaInfo,
)

# These imports are the actual target of this RED-phase test: neither
# module exists yet, so collecting this file MUST fail with an
# ImportError (ModuleNotFoundError) until task 17 is implemented.
from app.gui.download_panel import DownloadPanel
from app.gui.progress_widget import ProgressWidget


@dataclass(frozen=True)
class FakeDownloadHandle:
    """Minimal stand-in for `DownloadService`'s `DownloadHandle`."""

    operation_id: UUID


class FakeDownloadService:
    """Fake/stub `DownloadService` recording calls made by the GUI.

    Mirrors the public API described in design.md for `DownloadService`
    (`analyze`, `start_download`, `cancel`, `get_progress`) without
    touching any real Core/Services code, so GUI tests never open a
    real network connection, spawn real threads, or run FFmpeg/yt-dlp.
    """

    def __init__(self) -> None:
        self.analyze_calls: list[str] = []
        self.start_download_calls: list[tuple[MediaInfo, DownloadOptions]] = []
        self.cancel_calls: list[UUID] = []

        self._operation_id = uuid4()
        self._analyze_on_complete: Optional[
            Callable[[Optional[MediaInfo], Optional[str]], None]
        ] = None
        self._download_on_progress: Optional[Callable[[DownloadProgress], None]] = None
        self._download_on_complete: Optional[Callable[[DownloadResult], None]] = None

    def analyze(self, url, on_complete=None) -> FakeDownloadHandle:
        self.analyze_calls.append(url)
        self._analyze_on_complete = on_complete
        return FakeDownloadHandle(operation_id=self._operation_id)

    def start_download(self, media, options, on_progress=None, on_complete=None):
        self.start_download_calls.append((media, options))
        self._download_on_progress = on_progress
        self._download_on_complete = on_complete
        return FakeDownloadHandle(operation_id=self._operation_id)

    def cancel(self, operation_id) -> None:
        self.cancel_calls.append(operation_id)

    def get_progress(self, operation_id):
        return None

    # --- test helpers used to simulate asynchronous notifications ---

    def simulate_analyze_complete(self, media=None, error=None) -> None:
        assert self._analyze_on_complete is not None, "analyze() was not called"
        self._analyze_on_complete(media, error)

    def simulate_progress(self, progress: DownloadProgress) -> None:
        assert self._download_on_progress is not None, "start_download() was not called"
        self._download_on_progress(progress)

    def simulate_download_complete(self, result: DownloadResult) -> None:
        assert self._download_on_complete is not None, "start_download() was not called"
        self._download_on_complete(result)

    @property
    def current_operation_id(self) -> UUID:
        return self._operation_id


@pytest.fixture
def tk_root():
    """Provide a CustomTkinter root window, skipping if no display exists.

    Headless CI environments (and the current RED phase, where
    `customtkinter` is not even a declared dependency yet) should not fail
    this fixture with a hard error; they should skip tests that need a
    real window instead.
    """

    customtkinter = pytest.importorskip("customtkinter")

    try:
        root = customtkinter.CTk()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"No display available for CustomTkinter: {exc}")
        return

    yield root
    root.destroy()


@pytest.fixture
def fake_download_service() -> FakeDownloadService:
    return FakeDownloadService()


@pytest.fixture
def download_panel(tk_root, fake_download_service):
    return DownloadPanel(tk_root, fake_download_service)


def test_analyze_displays_metadata_on_success(download_panel, fake_download_service, make_media_info):
    """12.3: after a successful analysis, title/uploader/thumbnail are shown."""

    media = make_media_info(
        title="My Video",
        uploader="Some Channel",
        thumbnail="https://example.com/thumb.jpg",
    )

    download_panel.url_var.set(media.original_url)
    download_panel.on_analyze()

    assert fake_download_service.analyze_calls == [media.original_url]

    fake_download_service.simulate_analyze_complete(media=media, error=None)

    assert media.title in download_panel.title_text
    assert media.uploader in download_panel.uploader_text
    assert media.thumbnail in download_panel.thumbnail_text


def test_analyze_displays_error_message_on_failure(download_panel, fake_download_service):
    """12.7: an analysis failure surfaces only the error message, no traceback."""

    download_panel.url_var.set("https://example.com/broken")
    download_panel.on_analyze()

    fake_download_service.simulate_analyze_complete(media=None, error="Falha ao analisar a URL")

    assert download_panel.error_text == "Falha ao analisar a URL"
    assert "Traceback" not in download_panel.error_text


def test_download_options_reflect_video_selection(download_panel, fake_download_service, make_media_info, downloads_dir):
    """12.4: selected download type/max height/destination reach `DownloadOptions`."""

    media = make_media_info()
    download_panel.url_var.set(media.original_url)
    download_panel.on_analyze()
    fake_download_service.simulate_analyze_complete(media=media, error=None)

    download_panel.download_type_var.set(DownloadType.VIDEO.value)
    download_panel.max_height_var.set(720)
    download_panel.destination_var.set(str(downloads_dir))

    download_panel.on_download()

    assert len(fake_download_service.start_download_calls) == 1
    sent_media, sent_options = fake_download_service.start_download_calls[0]

    assert sent_media == media
    assert sent_options.download_type == DownloadType.VIDEO
    assert sent_options.max_height == 720
    assert str(sent_options.destination) == str(downloads_dir)


def test_download_options_reflect_audio_selection(download_panel, fake_download_service, make_media_info, downloads_dir):
    """12.4: selected audio bitrate reaches `DownloadOptions` when type is audio."""

    media = make_media_info()
    download_panel.url_var.set(media.original_url)
    download_panel.on_analyze()
    fake_download_service.simulate_analyze_complete(media=media, error=None)

    download_panel.download_type_var.set(DownloadType.AUDIO.value)
    download_panel.audio_bitrate_var.set(320)
    download_panel.destination_var.set(str(downloads_dir))

    download_panel.on_download()

    assert len(fake_download_service.start_download_calls) == 1
    _, sent_options = fake_download_service.start_download_calls[0]

    assert sent_options.download_type == DownloadType.AUDIO
    assert sent_options.audio_bitrate == 320
    assert str(sent_options.destination) == str(downloads_dir)


def test_progress_widget_updates_from_synthetic_progress(tk_root):
    """12.5: `ProgressWidget` reflects percentage and status from `DownloadProgress`."""

    progress_widget = ProgressWidget(tk_root)

    progress = DownloadProgress(status=DownloadStatus.DOWNLOADING, percentage=42.5)
    progress_widget.update_progress(progress)

    assert "42" in progress_widget.percentage_text
    assert DownloadStatus.DOWNLOADING.value in progress_widget.status_text.lower()


def test_download_panel_forwards_service_progress_to_widget(download_panel, fake_download_service, make_media_info, downloads_dir):
    """12.5: progress reported by the service updates the panel's `ProgressWidget`."""

    media = make_media_info()
    download_panel.url_var.set(media.original_url)
    download_panel.on_analyze()
    fake_download_service.simulate_analyze_complete(media=media, error=None)

    download_panel.download_type_var.set(DownloadType.VIDEO.value)
    download_panel.max_height_var.set(720)
    download_panel.destination_var.set(str(downloads_dir))
    download_panel.on_download()

    fake_download_service.simulate_progress(
        DownloadProgress(status=DownloadStatus.DOWNLOADING, percentage=55.0)
    )

    assert "55" in download_panel.progress_widget.percentage_text


def test_cancel_button_calls_service_cancel(download_panel, fake_download_service, make_media_info, downloads_dir):
    """12.6: triggering cancel invokes `DownloadService.cancel` for the active operation."""

    media = make_media_info()
    download_panel.url_var.set(media.original_url)
    download_panel.on_analyze()
    fake_download_service.simulate_analyze_complete(media=media, error=None)

    download_panel.download_type_var.set(DownloadType.VIDEO.value)
    download_panel.max_height_var.set(720)
    download_panel.destination_var.set(str(downloads_dir))
    download_panel.on_download()

    download_panel.on_cancel()

    assert fake_download_service.cancel_calls == [fake_download_service.current_operation_id]


def test_download_panel_displays_error_message_on_download_failure(download_panel, fake_download_service, make_media_info, downloads_dir):
    """12.7: a failed `DownloadResult` surfaces only `error_message`, no traceback."""

    media = make_media_info()
    download_panel.url_var.set(media.original_url)
    download_panel.on_analyze()
    fake_download_service.simulate_analyze_complete(media=media, error=None)

    download_panel.download_type_var.set(DownloadType.VIDEO.value)
    download_panel.max_height_var.set(720)
    download_panel.destination_var.set(str(downloads_dir))
    download_panel.on_download()

    fake_download_service.simulate_download_complete(
        DownloadResult(success=False, error_message="Falha ao baixar o vídeo")
    )

    assert download_panel.error_text == "Falha ao baixar o vídeo"
    assert "Traceback" not in download_panel.error_text
