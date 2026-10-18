"""Tests for `app.services.history_service.HistoryService`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models import DownloadStatus, DownloadType
from app.models.history import HistoryEntry
from app.services.history_service import HistoryService

_url_strategy = st.text(min_size=1, max_size=50).map(
    lambda suffix: f"https://example.com/{suffix}"
)

_optional_title_strategy = st.one_of(st.none(), st.text(max_size=50))

_download_type_strategy = st.sampled_from(list(DownloadType))

_download_status_strategy = st.sampled_from(list(DownloadStatus))

_optional_error_message_strategy = st.one_of(st.none(), st.text(max_size=100))

_timestamp_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
)

_file_path_choice_strategy = st.sampled_from(["none", "existing", "missing"])


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    url=_url_strategy,
    title=_optional_title_strategy,
    download_type=_download_type_strategy,
    status=_download_status_strategy,
    file_path_choice=_file_path_choice_strategy,
    timestamp=_timestamp_strategy,
    error_message=_optional_error_message_strategy,
)
def test_added_entry_is_retrievable_with_matching_fields(
    tmp_path: Path,
    url: str,
    title: str | None,
    download_type: DownloadType,
    status: DownloadStatus,
    file_path_choice: str,
    timestamp: datetime,
    error_message: str | None,
) -> None:
    # Feature: media-downloader-app, Property 16: Toda operação finalizada gera exatamente uma entrada de histórico consistente
    # `tmp_path` is a function-scoped fixture shared across every Hypothesis
    # example (and shrink attempt) within this test invocation, so the
    # history file must be reset at the start of each example to keep
    # them isolated from one another.
    history_path = tmp_path / "history.json"
    if history_path.exists():
        history_path.unlink()

    file_path: Path | None
    if file_path_choice == "none":
        file_path = None
    elif file_path_choice == "existing":
        file_path = tmp_path / "downloaded_file.mp4"
        file_path.write_bytes(b"fake content")
    else:
        file_path = tmp_path / "missing_file.mp4"

    entry = HistoryEntry(
        url=url,
        title=title,
        download_type=download_type,
        status=status,
        file_path=file_path,
        timestamp=timestamp,
        error_message=error_message,
    )

    service = HistoryService(history_path=history_path)
    service.add_entry(entry)

    entries = service.list_entries()

    matching_entries = [
        stored
        for stored in entries
        if stored.url == entry.url
        and stored.download_type == entry.download_type
        and stored.status == entry.status
        and stored.file_path == entry.file_path
    ]

    assert len(matching_entries) == 1


def test_history_persists_across_service_instances(tmp_path: Path) -> None:
    """14.2: histórico persiste entre instâncias/execuções simuladas de `HistoryService`."""
    history_path = tmp_path / "history.json"

    first_entry = HistoryEntry(
        url="https://example.com/video-1",
        title="Video 1",
        download_type=DownloadType.VIDEO,
        status=DownloadStatus.COMPLETED,
        file_path=None,
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
        error_message=None,
    )
    second_entry = HistoryEntry(
        url="https://example.com/video-2",
        title="Video 2",
        download_type=DownloadType.AUDIO,
        status=DownloadStatus.COMPLETED,
        file_path=None,
        timestamp=datetime(2023, 1, 2, 12, 0, 0),
        error_message=None,
    )

    # Primeira "execução" do app: cria o serviço e adiciona entradas.
    first_run_service = HistoryService(history_path=history_path)
    first_run_service.add_entry(first_entry)
    first_run_service.add_entry(second_entry)

    # Segunda "execução" do app: nova instância apontando para o mesmo arquivo.
    second_run_service = HistoryService(history_path=history_path)
    entries = second_run_service.list_entries()

    urls = [entry.url for entry in entries]
    assert first_entry.url in urls
    assert second_entry.url in urls


def test_history_entry_with_missing_file_reports_file_exists_false(
    tmp_path: Path,
) -> None:
    """14.3: entrada cujo arquivo referenciado não existe mais é identificável via `file_exists` sem erro."""
    history_path = tmp_path / "history.json"
    missing_file_path = tmp_path / "no_longer_here.mp4"

    entry = HistoryEntry(
        url="https://example.com/missing-file-video",
        title="Missing File Video",
        download_type=DownloadType.VIDEO,
        status=DownloadStatus.COMPLETED,
        file_path=missing_file_path,
        timestamp=datetime.now(),
        error_message=None,
    )

    service = HistoryService(history_path=history_path)
    service.add_entry(entry)

    entries = service.list_entries()

    matching = [stored for stored in entries if stored.url == entry.url]
    assert len(matching) == 1
    assert matching[0].file_exists is False
