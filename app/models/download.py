from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class DownloadType(str, Enum):
    """Type of download requested by the user."""

    VIDEO = "video"
    AUDIO = "audio"


class DownloadStatus(str, Enum):
    """Current status of a download operation."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DownloadOptions:
    """Options selected by the user for a download."""

    url: str
    download_type: DownloadType

    format_id: Optional[str] = None
    max_height: Optional[int] = None
    audio_bitrate: Optional[int] = None

    destination: Path = Path(".")


@dataclass
class DownloadProgress:
    """Represents the current progress of a download."""

    status: DownloadStatus = DownloadStatus.PENDING

    percentage: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None

    speed: Optional[float] = None
    eta: Optional[float] = None

    filename: Optional[str] = None


@dataclass(frozen=True)
class DownloadResult:
    """Represents the final result of a download operation."""

    success: bool

    file_path: Optional[Path] = None
    file_size: Optional[int] = None

    error_message: Optional[str] = None