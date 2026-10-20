from __future__ import annotations

import json
import os
from pathlib import Path

from app.models.config import AppConfig
from app.models.download import DownloadType
from app.services.log_service import LogService

_APP_DIR_NAME = "UniversalMediaDownloader"
_CONFIG_FILE_NAME = "config.json"


def _default_config_path() -> Path:
    """Resolve the default configuration file path for the current user/OS.

    On Windows this resolves under ``%APPDATA%``; elsewhere it falls back to
    ``~/.config``. The resulting directory is not created here — that only
    happens when ``save`` actually needs to write the file.
    """
    appdata = os.environ.get("APPDATA")
    base_dir = Path(appdata) if appdata else Path.home() / ".config"
    return base_dir / _APP_DIR_NAME / _CONFIG_FILE_NAME


class ConfigService:
    """Carrega e persiste AppConfig em um arquivo JSON no diretório de
    configuração do usuário (ex.: %APPDATA%/UniversalMediaDownloader)."""

    def __init__(
        self,
        config_path: Path | None = None,
        log_service: LogService | None = None,
    ) -> None:
        self._config_path = Path(config_path) if config_path is not None else _default_config_path()
        self._log_service = log_service if log_service is not None else LogService()

    @property
    def config_path(self) -> Path:
        """Return the resolved path to the configuration file."""
        return self._config_path

    def load(self) -> AppConfig:
        """
        Retorna a Configuração persistida. Se o arquivo não existir,
        estiver corrompido ou ilegível, retorna AppConfig com valores
        padrão, sem lançar exceção.
        """
        try:
            raw_text = self._config_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            return self._parse_config(data)
        except Exception as exc:
            self._log_service.write(
                "ConfigService.load falhou ao ler/interpretar o arquivo de "
                f"configuração em {self._config_path}. Usando valores "
                f"padrão. Tipo da exceção: {type(exc).__name__}. Detalhe: {exc!r}"
            )
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        """Persiste a Configuração em disco, criando diretórios
        necessários."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._serialize_config(config)
        self._config_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _serialize_config(config: AppConfig) -> dict:
        return {
            "default_destination": str(config.default_destination),
            "default_download_type": config.default_download_type.value,
            "preferred_resolution": config.preferred_resolution,
            "default_audio_bitrate": config.default_audio_bitrate,
            "ffmpeg_path": (str(config.ffmpeg_path) if config.ffmpeg_path is not None else None),
            "theme": config.theme,
        }

    @staticmethod
    def _parse_config(data: object) -> AppConfig:
        """Build an `AppConfig` from decoded JSON data.

        Raises `ValueError` for any structural or type mismatch so that
        `load()` can fall back to defaults without ever propagating the
        error to the caller.
        """
        if not isinstance(data, dict):
            raise ValueError("O conteúdo da configuração deve ser um objeto JSON.")

        kwargs: dict = {}

        if "default_destination" in data:
            value = data["default_destination"]
            if not isinstance(value, str):
                raise ValueError("default_destination deve ser uma string.")
            kwargs["default_destination"] = Path(value)

        if "default_download_type" in data:
            value = data["default_download_type"]
            if not isinstance(value, str):
                raise ValueError("default_download_type deve ser uma string.")
            kwargs["default_download_type"] = DownloadType(value)

        if "preferred_resolution" in data:
            value = data["preferred_resolution"]
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError("preferred_resolution deve ser um inteiro ou nulo.")
            kwargs["preferred_resolution"] = value

        if "default_audio_bitrate" in data:
            value = data["default_audio_bitrate"]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("default_audio_bitrate deve ser um inteiro.")
            kwargs["default_audio_bitrate"] = value

        if "ffmpeg_path" in data:
            value = data["ffmpeg_path"]
            if value is not None and not isinstance(value, str):
                raise ValueError("ffmpeg_path deve ser uma string ou nulo.")
            kwargs["ffmpeg_path"] = Path(value) if value is not None else None

        if "theme" in data:
            value = data["theme"]
            if not isinstance(value, str):
                raise ValueError("theme deve ser uma string.")
            kwargs["theme"] = value

        return AppConfig(**kwargs)
