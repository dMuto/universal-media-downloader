from dataclasses import dataclass
from typing import Optional

from .format import FormatInfo


@dataclass(frozen=True)
class FormatSelection:
    """Represents the formats selected for a download."""

    video_format: Optional[FormatInfo] = None
    audio_format: Optional[FormatInfo] = None

    @property
    def requires_merge(self) -> bool:
        """Return whether video and audio need to be combined."""
        return self.video_format is not None and self.audio_format is not None