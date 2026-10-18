"""Tests for `MainWindow`'s thread-safe polling mechanism.

`MainWindow` drains progress/result updates reported by worker threads
(via `DownloadService.analyze`/`start_download` callbacks) exclusively
from `_poll_operations`, which must only ever run on the main thread
(through Tkinter's `.after` scheduling). These tests verify that:

- callbacks returned by `register_operation` are safe to call from a
  background thread (they only enqueue data);
- `_poll_operations` drains the queue and invokes the registered
  `on_progress`/`on_complete` handlers;
- `unregister_operation` stops further handler invocations.

A real `customtkinter.CTk` window is required to instantiate `MainWindow`
(it subclasses `CTk`), so these tests use the same
`pytest.importorskip("customtkinter")` / headless-skip pattern already
used in `tests/gui/test_download_panel.py`.

**Validates: Requirements 9.2, 9.3**
"""

import threading

import pytest

from app.gui.main_window import MainWindow
from app.services.config_service import ConfigService
from app.services.history_service import HistoryService


class _FakeDownloadService:
    """Minimal stand-in: `MainWindow` only needs to store this, it never
    calls any of its methods directly in this subtask."""


@pytest.fixture
def main_window(tmp_path):
    customtkinter = pytest.importorskip("customtkinter")

    try:
        window = MainWindow(
            download_service=_FakeDownloadService(),
            config_service=ConfigService(config_path=tmp_path / "config.json"),
            history_service=HistoryService(history_path=tmp_path / "history.json"),
            auto_poll=False,
        )
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"No display available for CustomTkinter: {exc}")
        return

    yield window
    window.destroy()


def test_register_operation_returns_thread_safe_callbacks(main_window):
    """Callbacks from `register_operation` can be invoked from a background
    thread without touching any Tkinter widget directly."""

    operation_id = __import__("uuid").uuid4()
    on_progress_callback, on_complete_callback = main_window.register_operation(
        operation_id
    )

    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            on_progress_callback({"percentage": 10.0})
            on_progress_callback({"percentage": 50.0})
            on_complete_callback({"success": True})
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join(timeout=5)

    assert not errors
    assert not thread.is_alive()


def test_poll_operations_drains_queue_and_invokes_handlers(main_window):
    """`_poll_operations`, run on the main thread, drains queued progress
    and result updates and forwards them to the registered handlers, in
    order."""

    received_progress: list[object] = []
    received_results: list[object] = []

    operation_id = __import__("uuid").uuid4()
    on_progress_callback, on_complete_callback = main_window.register_operation(
        operation_id,
        on_progress=received_progress.append,
        on_complete=received_results.append,
    )

    def _worker() -> None:
        on_progress_callback("progress-1")
        on_progress_callback("progress-2")
        on_complete_callback("result-1")

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join(timeout=5)

    # Nothing should be delivered to the handlers before polling runs.
    assert received_progress == []
    assert received_results == []

    main_window._poll_operations(reschedule=False)

    assert received_progress == ["progress-1", "progress-2"]
    assert received_results == ["result-1"]


def test_unregister_operation_stops_future_delivery(main_window):
    """After `unregister_operation`, previously queued-but-undelivered
    updates are dropped and no longer reach the handlers."""

    received_progress: list[object] = []

    operation_id = __import__("uuid").uuid4()
    on_progress_callback, _ = main_window.register_operation(
        operation_id,
        on_progress=received_progress.append,
    )

    on_progress_callback("progress-before-unregister")
    main_window.unregister_operation(operation_id)

    main_window._poll_operations(reschedule=False)

    assert received_progress == []


def test_poll_operations_reschedules_itself_via_after(main_window, monkeypatch):
    """The polling loop reschedules itself via `self.after(ms, callback)`
    so it keeps draining queues periodically while the window exists."""

    after_calls: list[tuple[int, object]] = []
    original_after = main_window.after

    def _recording_after(ms, callback=None, *args):
        after_calls.append((ms, callback))
        # Avoid actually scheduling on the real Tkinter event loop so the
        # test does not depend on running mainloop().
        return original_after(0, lambda: None)

    monkeypatch.setattr(main_window, "after", _recording_after)

    main_window._poll_operations(reschedule=True)

    assert len(after_calls) == 1
    ms, callback = after_calls[0]
    assert ms == main_window._poll_interval_ms
    assert callback == main_window._poll_operations
