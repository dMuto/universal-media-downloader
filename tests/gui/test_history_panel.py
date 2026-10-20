"""Example-based tests for the `HistoryPanel` GUI component.

These tests exercise `HistoryPanel` using a fake `HistoryService`, without
opening a real window. They cover:

- 14.2: a `HistoryPanel` rendering the persisted entries returned by
  `HistoryService.list_entries()`.
- 14.3: an entry whose referenced file no longer exists being visually
  indicated by the panel, without raising an execution error.

At this phase (Fase 1 - RED), `app/gui/history_panel.py` does not exist yet,
so these tests are expected to fail with `ImportError`.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.gui.history_panel import HistoryPanel


@dataclass(frozen=True)
class FakeHistoryEntry:
    """Lightweight stand-in for `app.models.history.HistoryEntry`.

    Mirrors the fields described in the design document for `HistoryEntry`,
    including the calculated `file_exists` property, so it can be used as a
    drop-in fake without depending on the (not yet implemented) real model.
    """

    url: str
    title: str | None
    download_type: str
    status: str
    file_path: Path | None
    timestamp: datetime
    error_message: str | None = None

    @property
    def file_exists(self) -> bool:
        return self.file_path is not None and self.file_path.is_file()


class FakeHistoryService:
    """Fake `HistoryService` exposing only `list_entries()`."""

    def __init__(self, entries: list[FakeHistoryEntry]):
        self._entries = list(entries)

    def list_entries(self) -> list[FakeHistoryEntry]:
        return list(self._entries)


def test_history_panel_lists_persisted_entries(tmp_path):
    """14.2: HistoryPanel renders every entry returned by list_entries()."""

    existing_file = tmp_path / "video.mp4"
    existing_file.write_bytes(b"fake video content")

    entries = [
        FakeHistoryEntry(
            url="https://example.com/watch?v=1",
            title="First Video",
            download_type="video",
            status="completed",
            file_path=existing_file,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        ),
        FakeHistoryEntry(
            url="https://example.com/watch?v=2",
            title="Second Video",
            download_type="audio",
            status="completed",
            file_path=None,
            timestamp=datetime(2024, 1, 2, 12, 0, 0),
        ),
    ]
    service = FakeHistoryService(entries)

    panel = HistoryPanel(history_service=service)
    panel.refresh()

    rendered_urls = [entry.url for entry in panel.displayed_entries()]
    assert rendered_urls == [entries[0].url, entries[1].url]


def test_history_panel_indicates_missing_file_without_error(tmp_path):
    """14.3: entries whose file no longer exists are flagged, not errored."""

    missing_file = tmp_path / "deleted_video.mp4"
    # Intentionally not created: this path does not exist on disk.

    entry = FakeHistoryEntry(
        url="https://example.com/watch?v=missing",
        title="Deleted Video",
        download_type="video",
        status="completed",
        file_path=missing_file,
        timestamp=datetime(2024, 1, 3, 12, 0, 0),
    )
    service = FakeHistoryService([entry])

    panel = HistoryPanel(history_service=service)

    # Rendering an entry referencing a missing file must not raise.
    panel.refresh()

    displayed = panel.displayed_entries()
    assert len(displayed) == 1
    assert displayed[0].file_exists is False
