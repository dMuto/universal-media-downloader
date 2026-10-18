from datetime import datetime
from pathlib import Path

from app.models import DownloadStatus, DownloadType
from app.models.history import HistoryEntry


def _make_entry(file_path, **overrides):
    defaults = dict(
        url="https://example.com/video",
        title="Example video",
        download_type=DownloadType.VIDEO,
        status=DownloadStatus.COMPLETED,
        file_path=file_path,
        timestamp=datetime.now(),
        error_message=None,
    )
    defaults.update(overrides)
    return HistoryEntry(**defaults)


def test_file_exists_true_when_file_path_points_to_existing_file(tmp_path):
    existing_file = tmp_path / "downloaded_video.mp4"
    existing_file.write_bytes(b"fake video content")

    entry = _make_entry(file_path=existing_file)

    assert entry.file_exists is True


def test_file_exists_false_when_file_path_is_none():
    entry = _make_entry(file_path=None)

    assert entry.file_exists is False


def test_file_exists_false_when_file_path_does_not_exist(tmp_path):
    missing_file = tmp_path / "does_not_exist.mp4"

    entry = _make_entry(file_path=missing_file)

    assert entry.file_exists is False
