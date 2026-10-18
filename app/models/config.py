from dataclasses import dataclass, field
from pathlib import Path

from .download import DownloadType


@dataclass(frozen=True)
class AppConfig:
    """Persistent application preferences."""

    default_destination: Path = field(default_factory=lambda: Path.home() / "Downloads")
    default_download_type: DownloadType = DownloadType.VIDEO
    preferred_resolution: int | None = 1080
    default_audio_bitrate: int = 192
    ffmpeg_path: Path | None = None
    theme: str = "system"  # "system" | "light" | "dark"
