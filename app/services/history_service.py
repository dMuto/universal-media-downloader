from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from app.models.download import DownloadStatus, DownloadType
from app.models.history import HistoryEntry

_APP_DIR_NAME = "UniversalMediaDownloader"
_HISTORY_FILE_NAME = "history.json"


def _default_history_path() -> Path:
    """Resolve the default history file path for the current user/OS.

    On Windows this resolves under ``%LOCALAPPDATA%``; elsewhere it falls
    back to ``~/.local/share``. The resulting directory is not created
    here — that only happens when ``add_entry`` actually needs to write
    the file.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    base_dir = Path(local_appdata) if local_appdata else Path.home() / ".local" / "share"
    return base_dir / _APP_DIR_NAME / _HISTORY_FILE_NAME


class HistoryService:
    """Registra e consulta o Histórico_De_Downloads, persistido em um
    arquivo JSON (lista de entradas) no diretório de dados do usuário.

    JSON foi escolhido em vez de SQLite por simplicidade: o volume de
    entradas é baixo (uso pessoal, não concorrente entre processos) e
    não há necessidade de consultas relacionais."""

    def __init__(self, history_path: Path | None = None) -> None:
        self._history_path = Path(history_path) if history_path is not None else _default_history_path()

    @property
    def history_path(self) -> Path:
        """Return the resolved path to the history file."""
        return self._history_path

    def add_entry(self, entry: HistoryEntry) -> None:
        """Acrescenta uma entrada e persiste imediatamente."""
        entries = self._load_entries()
        entries.append(entry)
        self._save_entries(entries)

    def list_entries(self) -> list[HistoryEntry]:
        """
        Retorna as entradas na ordem de inserção (cronológica),
        indicando via HistoryEntry.file_exists se o arquivo referenciado
        ainda existe no sistema de arquivos.
        """
        return self._load_entries()

    def _load_entries(self) -> list[HistoryEntry]:
        try:
            raw_text = self._history_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            if not isinstance(data, list):
                return []
            entries: list[HistoryEntry] = []
            for item in data:
                try:
                    entries.append(self._parse_entry(item))
                except Exception:
                    continue
            return entries
        except Exception:
            return []

    def _save_entries(self, entries: list[HistoryEntry]) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [self._serialize_entry(entry) for entry in entries]
        self._history_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _serialize_entry(entry: HistoryEntry) -> dict:
        return {
            "url": entry.url,
            "title": entry.title,
            "download_type": entry.download_type.value,
            "status": entry.status.value,
            "file_path": str(entry.file_path) if entry.file_path is not None else None,
            "timestamp": entry.timestamp.isoformat(),
            "error_message": entry.error_message,
        }

    @staticmethod
    def _parse_entry(data: object) -> HistoryEntry:
        """Build a `HistoryEntry` from decoded JSON data.

        Raises `ValueError`/`TypeError` for any structural or type
        mismatch so that `_load_entries` can skip the malformed entry
        without ever propagating the error to the caller.
        """
        if not isinstance(data, dict):
            raise ValueError("Cada entrada do histórico deve ser um objeto JSON.")

        url = data["url"]
        if not isinstance(url, str):
            raise ValueError("url deve ser uma string.")

        title = data.get("title")
        if title is not None and not isinstance(title, str):
            raise ValueError("title deve ser uma string ou nulo.")

        download_type = DownloadType(data["download_type"])
        status = DownloadStatus(data["status"])

        file_path_value = data.get("file_path")
        if file_path_value is not None and not isinstance(file_path_value, str):
            raise ValueError("file_path deve ser uma string ou nulo.")
        file_path = Path(file_path_value) if file_path_value is not None else None

        timestamp = datetime.fromisoformat(data["timestamp"])

        error_message = data.get("error_message")
        if error_message is not None and not isinstance(error_message, str):
            raise ValueError("error_message deve ser uma string ou nulo.")

        return HistoryEntry(
            url=url,
            title=title,
            download_type=download_type,
            status=status,
            file_path=file_path,
            timestamp=timestamp,
            error_message=error_message,
        )
