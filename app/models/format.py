from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MediaType(str, Enum):
    """Type of media contained in a format."""

    VIDEO = "video"
    AUDIO = "audio"
    VIDEO_AUDIO = "video_audio"


@dataclass(frozen=True)
class FormatInfo:
    """Represents a media format available for download."""

    format_id: str
    extension: Optional[str] = None

    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None

    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None

    bitrate: Optional[float] = None
    size: Optional[int] = None

    media_type: MediaType = MediaType.VIDEO_AUDIO

    @property
    def has_video(self) -> bool:
        """Return whether this format contains a video stream."""
        return self.media_type in {
            MediaType.VIDEO,
            MediaType.VIDEO_AUDIO,
        }

    @property
    def has_audio(self) -> bool:
        """Return whether this format contains an audio stream."""
        return self.media_type in {
            MediaType.AUDIO,
            MediaType.VIDEO_AUDIO,
        }