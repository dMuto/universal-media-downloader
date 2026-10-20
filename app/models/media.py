from dataclasses import dataclass, field
from typing import Optional

from .format import FormatInfo


@dataclass(frozen=True)
class MediaInfo:
    """Represents information about a media resource."""

    title: str
    duration: Optional[float] = None
    uploader: Optional[str] = None
    thumbnail: Optional[str] = None
    original_url: str = ""

    formats: list[FormatInfo] = field(default_factory=list)
