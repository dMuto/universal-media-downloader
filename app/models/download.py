from dataclasses import dataclass
from enum import Enum
from pathlib import Path


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

    format_id: str | None = None
    max_height: int | None = None
    audio_bitrate: int | None = None

    destination: Path = Path(".")


@dataclass
class DownloadProgress:
    """Represents the current progress of a download."""

    status: DownloadStatus = DownloadStatus.PENDING

    percentage: float = 0.0
    downloaded_bytes: int | None = None
    total_bytes: int | None = None

    speed: float | None = None
    eta: float | None = None

    filename: str | None = None


@dataclass(frozen=True)
class DownloadResult:
    """Represents the final result of a download operation."""

    success: bool

    file_path: Path | None = None
    file_size: int | None = None

    error_message: str | None = None
