from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.ffmpeg_service import FFmpegError, FFmpegService

from app.models import (
    DownloadOptions,
    DownloadType,
    FormatInfo,
    FormatSelection,
    MediaInfo,
    MediaType,
)


class FormatSelectionError(Exception):
    """Raised when a suitable format cannot be selected."""


class FormatSelector:
    """Selects media formats based on download options."""

    def select(
        self,
        media: MediaInfo,
        options: DownloadOptions,
    ) -> FormatSelection:
        """
        Select suitable formats for the requested download.

        This method only selects formats. It does not download,
        merge, convert, or modify any media.
        """
        if not media.formats:
            raise FormatSelectionError(
                "Nenhum formato está disponível para esta mídia."
            )

        if not options.url.strip():
            raise FormatSelectionError(
                "A URL do download não pode estar vazia."
            )

        if options.download_type == DownloadType.VIDEO:
            return self._select_video(media.formats, options)

        if options.download_type == DownloadType.AUDIO:
            return self._select_audio(media.formats)

        raise FormatSelectionError(
            f"Tipo de download não suportado: {options.download_type}"
        )

    def _select_video(
        self,
        formats: list[FormatInfo],
        options: DownloadOptions,
    ) -> FormatSelection:
        """Select a video format and, if necessary, a separate audio format."""
        video_formats = [
            format_info
            for format_info in formats
            if format_info.has_video
        ]

        if not video_formats:
            raise FormatSelectionError(
                "Nenhum formato de vídeo está disponível."
            )

        candidates = self._filter_by_max_height(
            video_formats,
            options.max_height,
        )

        if not candidates:
            if options.max_height is not None:
                raise FormatSelectionError(
                    "Nenhum formato de vídeo atende à qualidade solicitada."
                )

            raise FormatSelectionError(
                "Nenhum formato de vídeo adequado foi encontrado."
            )

        selected_video = max(
            candidates,
            key=self._video_score,
        )

        if selected_video.has_audio:
            return FormatSelection(video_format=selected_video)

        audio_formats = [
            format_info
            for format_info in formats
            if format_info.media_type == MediaType.AUDIO
        ]

        if not audio_formats:
            raise FormatSelectionError(
                "O vídeo selecionado não possui áudio e "
                "nenhum formato de áudio separado está disponível."
            )

        selected_audio = max(
            audio_formats,
            key=self._audio_score,
        )

        return FormatSelection(
            video_format=selected_video,
            audio_format=selected_audio,
        )

    def _select_audio(
        self,
        formats: list[FormatInfo],
    ) -> FormatSelection:
        """Select the best audio-only format."""
        audio_formats = [
            format_info
            for format_info in formats
            if format_info.media_type == MediaType.AUDIO
        ]

        if not audio_formats:
            raise FormatSelectionError(
                "Nenhum formato de áudio está disponível."
            )

        selected_audio = max(
            audio_formats,
            key=self._audio_score,
        )

        return FormatSelection(audio_format=selected_audio)

    @staticmethod
    def _filter_by_max_height(
        formats: list[FormatInfo],
        max_height: int | None,
    ) -> list[FormatInfo]:
        """Keep formats that do not exceed the requested height."""
        if max_height is None:
            return formats

        return [
            format_info
            for format_info in formats
            if format_info.height is not None
            and format_info.height <= max_height
        ]

    @staticmethod
    def _video_score(
        format_info: FormatInfo,
    ) -> tuple[int, int, float, int]:
        """
        Score a video format.

        Priority:
        1. resolution
        2. video + audio
        3. bitrate
        4. MP4 preference
        """
        height = format_info.height or 0
        has_audio = int(format_info.has_audio)
        bitrate = format_info.bitrate or 0

        mp4_preference = int(
            (format_info.extension or "").lower() == "mp4"
        )

        return (
            height,
            has_audio,
            bitrate,
            mp4_preference,
        )

    @staticmethod
    def _audio_score(
        format_info: FormatInfo,
    ) -> tuple[float, int]:
        """
        Score an audio format.

        Priority:
        1. bitrate
        2. common MP4-family audio format
        """
        bitrate = format_info.bitrate or 0

        extension = (format_info.extension or "").lower()
        compatibility_preference = int(extension in {"m4a", "mp4"})

        return (
            bitrate,
            compatibility_preference,
        )