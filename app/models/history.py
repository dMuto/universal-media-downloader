from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .download import DownloadStatus, DownloadType


@dataclass(frozen=True)
class HistoryEntry:
    """Uma entrada do Histórico_De_Downloads."""

    url: str
    title: str | None
    download_type: DownloadType
    status: DownloadStatus
    file_path: Path | None
    timestamp: datetime
    error_message: str | None = None

    @property
    def file_exists(self) -> bool:
        """Calculado em tempo de consulta, não persistido."""
        return self.file_path is not None and self.file_path.is_file()
