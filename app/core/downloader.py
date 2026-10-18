from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yt_dlp

from app.core.ffmpeg_service import FFmpegError, FFmpegService
from app.models import (
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    DownloadStatus,
    FormatInfo,
    FormatSelection,
    MediaInfo,
    MediaType,
)


class MediaAnalysisError(Exception):
    """Raised when a media URL cannot be analyzed."""


class DownloadError(Exception):
    """Raised when a media download cannot be completed."""


class Downloader:
    """Provides media analysis and download through yt-dlp."""

    def __init__(
        self,
        ffmpeg_service: FFmpegService | None = None,
    ) -> None:
        self._ffmpeg_service = ffmpeg_service

    def analyze(self, url: str) -> MediaInfo:
        """
        Analyze a media URL and return application-level media information.

        This method only extracts metadata and available formats.
        It does not download any media.
        """
        if not url or not url.strip():
            raise MediaAnalysisError("A URL não pode estar vazia.")

        options = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    url.strip(),
                    download=False,
                )

        except yt_dlp.utils.DownloadError as exc:
            raise MediaAnalysisError(f"Não foi possível analisar a URL: {exc}") from exc

        except Exception as exc:
            raise MediaAnalysisError(
                "Ocorreu um erro inesperado ao analisar a mídia."
            ) from exc

        if not info:
            raise MediaAnalysisError("O yt-dlp não retornou informações sobre a mídia.")

        return self._build_media_info(info)

    def download(
        self,
        options: DownloadOptions,
        selection: FormatSelection,
        progress_hook: Callable[[DownloadProgress], None] | None = None,
    ) -> DownloadResult:
        """
        Download the selected formats using yt-dlp.

        When video and audio are separate, they are downloaded into
        temporary files and merged using FFmpegService.

        When `progress_hook` is provided, it is invoked with a
        `DownloadProgress` adapted from yt-dlp's own `progress_hooks`
        dictionaries as the download advances. Only the fields present
        in the underlying yt-dlp dictionary are populated; fields that
        are absent are left as `None` rather than assuming a value.
        """
        if not options.url or not options.url.strip():
            return DownloadResult(
                success=False,
                error_message="A URL não pode estar vazia.",
            )

        if not selection.video_format and not selection.audio_format:
            return DownloadResult(
                success=False,
                error_message="Nenhum formato foi selecionado.",
            )

        destination = Path(options.destination)

        try:
            destination.mkdir(
                parents=True,
                exist_ok=True,
            )

        except OSError as exc:
            return DownloadResult(
                success=False,
                error_message=(f"Não foi possível criar a pasta de destino: {exc}"),
            )

        try:
            if selection.requires_merge:
                return self._download_and_merge(
                    options=options,
                    selection=selection,
                    destination=destination,
                    progress_hook=progress_hook,
                )

            selected_format = selection.video_format or selection.audio_format

            if selected_format is None:
                return DownloadResult(
                    success=False,
                    error_message=("Não foi possível determinar o formato."),
                )

            file_path = self._download_single_format(
                url=options.url,
                format_id=selected_format.format_id,
                destination=destination,
                progress_hook=progress_hook,
            )

            return DownloadResult(
                success=True,
                file_path=file_path,
                file_size=self._get_file_size(file_path),
            )

        except yt_dlp.utils.DownloadError as exc:
            return DownloadResult(
                success=False,
                error_message=f"Erro durante o download: {exc}",
            )

        except FFmpegError as exc:
            return DownloadResult(
                success=False,
                error_message=f"Erro no FFmpeg: {exc}",
            )

        except OSError as exc:
            return DownloadResult(
                success=False,
                error_message=f"Erro ao acessar arquivos: {exc}",
            )

        except Exception as exc:
            return DownloadResult(
                success=False,
                error_message=(f"Ocorreu um erro inesperado durante o download: {exc}"),
            )

    @staticmethod
    def _build_media_info(
        info: dict[str, Any],
    ) -> MediaInfo:
        """Convert raw yt-dlp information into a MediaInfo model."""
        formats = [
            Downloader._build_format_info(format_data)
            for format_data in info.get("formats", [])
            if Downloader._is_media_format(format_data)
        ]

        return MediaInfo(
            title=info.get("title") or "Sem título",
            duration=info.get("duration"),
            uploader=info.get("uploader") or info.get("channel"),
            thumbnail=info.get("thumbnail"),
            original_url=(info.get("webpage_url") or info.get("original_url") or ""),
            formats=formats,
        )

    @staticmethod
    def _build_format_info(
        format_data: dict[str, Any],
    ) -> FormatInfo:
        """Convert a raw yt-dlp format into a FormatInfo model."""
        video_codec = Downloader._normalize_codec(format_data.get("vcodec"))

        audio_codec = Downloader._normalize_codec(format_data.get("acodec"))

        return FormatInfo(
            format_id=str(format_data.get("format_id", "")),
            extension=format_data.get("ext"),
            width=format_data.get("width"),
            height=format_data.get("height"),
            fps=format_data.get("fps"),
            video_codec=video_codec,
            audio_codec=audio_codec,
            bitrate=(format_data.get("tbr") or format_data.get("abr")),
            size=(format_data.get("filesize") or format_data.get("filesize_approx")),
            media_type=Downloader._get_media_type(
                video_codec=video_codec,
                audio_codec=audio_codec,
            ),
        )

    @staticmethod
    def _normalize_codec(
        codec: Any,
    ) -> str | None:
        """Normalize yt-dlp codec values."""
        if codec is None:
            return None

        codec = str(codec).strip()

        if not codec or codec.lower() == "none":
            return None

        return codec

    @staticmethod
    def _get_media_type(
        video_codec: str | None,
        audio_codec: str | None,
    ) -> MediaType:
        """Determine media type from available codecs."""
        has_video = video_codec is not None
        has_audio = audio_codec is not None

        if has_video and has_audio:
            return MediaType.VIDEO_AUDIO

        if has_video:
            return MediaType.VIDEO

        return MediaType.AUDIO

    @staticmethod
    def _is_media_format(
        format_data: dict[str, Any],
    ) -> bool:
        """Return whether a yt-dlp format represents a media stream."""
        format_id = format_data.get("format_id")

        if format_id is None:
            return False

        video_codec = format_data.get("vcodec")
        audio_codec = format_data.get("acodec")

        has_video = video_codec not in (
            None,
            "",
            "none",
        )

        has_audio = audio_codec not in (
            None,
            "",
            "none",
        )

        return has_video or has_audio

    @staticmethod
    def _make_yt_dlp_progress_hook(
        progress_hook: Callable[[DownloadProgress], None],
    ) -> Callable[[dict[str, Any]], None]:
        """
        Build a yt-dlp-compatible progress hook that adapts yt-dlp's raw
        progress dictionary into a DownloadProgress before delegating to
        the caller-supplied progress_hook.
        """

        def yt_dlp_hook(raw_progress: dict[str, Any]) -> None:
            progress_hook(
                Downloader._build_download_progress(raw_progress),
            )

        return yt_dlp_hook

    @staticmethod
    def _build_download_progress(
        raw_progress: dict[str, Any],
    ) -> DownloadProgress:
        """
        Convert a raw yt-dlp progress_hooks dictionary into a
        DownloadProgress.

        Only the fields present in `raw_progress` are populated;
        fields absent from the source dictionary are kept as `None`,
        without presuming a value.
        """
        downloaded_bytes = raw_progress.get("downloaded_bytes")
        total_bytes = raw_progress.get("total_bytes")
        speed = raw_progress.get("speed")
        eta = raw_progress.get("eta")
        filename = raw_progress.get("filename")

        percentage = 0.0

        if downloaded_bytes is not None and total_bytes:
            percentage = (downloaded_bytes / total_bytes) * 100

        return DownloadProgress(
            status=Downloader._map_progress_status(raw_progress.get("status")),
            percentage=percentage,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            speed=speed,
            eta=eta,
            filename=filename,
        )

    @staticmethod
    def _map_progress_status(
        raw_status: Any,
    ) -> DownloadStatus:
        """Map yt-dlp's raw progress status to DownloadStatus."""
        if raw_status == "error":
            return DownloadStatus.FAILED

        return DownloadStatus.DOWNLOADING

    @staticmethod
    def _get_downloaded_file_path(
        ydl: yt_dlp.YoutubeDL,
        info: dict[str, Any],
    ) -> Path | None:
        """Determine the path of the downloaded file."""
        requested_downloads = info.get("requested_downloads")

        if requested_downloads:
            filepath = requested_downloads[0].get("filepath")

            if filepath:
                return Path(filepath)

        filepath = ydl.prepare_filename(info)

        if filepath:
            return Path(filepath)

        return None

    @staticmethod
    def _get_file_size(
        file_path: Path,
    ) -> int | None:
        """Return the downloaded file size when available."""
        try:
            return file_path.stat().st_size
        except OSError:
            return None

    def _download_single_format(
        self,
        url: str,
        format_id: str,
        destination: Path,
        progress_hook: Callable[[DownloadProgress], None] | None = None,
    ) -> Path:
        """Download a single yt-dlp format."""
        ydl_options = {
            "format": format_id,
            "outtmpl": str(destination / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        if progress_hook is not None:
            ydl_options["progress_hooks"] = [
                self._make_yt_dlp_progress_hook(progress_hook),
            ]

        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(
                url.strip(),
                download=True,
            )

            file_path = self._get_downloaded_file_path(
                ydl,
                info,
            )

        if file_path is None or not file_path.is_file():
            raise OSError("Não foi possível determinar o arquivo baixado.")

        return file_path

    def _download_and_merge(
        self,
        options: DownloadOptions,
        selection: FormatSelection,
        destination: Path,
        progress_hook: Callable[[DownloadProgress], None] | None = None,
    ) -> DownloadResult:
        """Download separate video/audio streams and merge them."""
        if selection.video_format is None:
            raise FFmpegError(
                "A seleção requer merge, mas não possui formato de vídeo."
            )

        if selection.audio_format is None:
            raise FFmpegError(
                "A seleção requer merge, mas não possui formato de áudio."
            )

        if self._ffmpeg_service is None:
            self._ffmpeg_service = FFmpegService()

        video_format = selection.video_format
        audio_format = selection.audio_format

        with TemporaryDirectory(
            prefix="umd_",
            dir=destination,
        ) as temp_directory:
            temp_path = Path(temp_directory)

            video_path = self._download_to_directory(
                url=options.url,
                format_id=video_format.format_id,
                directory=temp_path,
                prefix="video",
                progress_hook=progress_hook,
            )

            audio_path = self._download_to_directory(
                url=options.url,
                format_id=audio_format.format_id,
                directory=temp_path,
                prefix="audio",
                progress_hook=progress_hook,
            )

            output_extension = self._get_merge_extension(
                audio_codec=audio_format.audio_codec,
                video_extension=video_format.extension,
            )

            output_name = self._sanitize_filename(
                video_path.stem,
            )

            output_path = destination / (f"{output_name}{output_extension}")

            final_path = self._ffmpeg_service.merge(
                video_path=video_path,
                audio_path=audio_path,
                output_path=output_path,
            )

        return DownloadResult(
            success=True,
            file_path=final_path,
            file_size=self._get_file_size(final_path),
        )

    def _download_to_directory(
        self,
        url: str,
        format_id: str,
        directory: Path,
        prefix: str,
        progress_hook: Callable[[DownloadProgress], None] | None = None,
    ) -> Path:
        """Download one selected stream into a temporary directory."""
        ydl_options = {
            "format": format_id,
            "outtmpl": str(directory / f"{prefix}_%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        if progress_hook is not None:
            ydl_options["progress_hooks"] = [
                self._make_yt_dlp_progress_hook(progress_hook),
            ]

        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(
                url.strip(),
                download=True,
            )

            file_path = self._get_downloaded_file_path(
                ydl,
                info,
            )

        if file_path is None or not file_path.is_file():
            raise OSError(
                f"Não foi possível localizar o arquivo temporário "
                f"do formato {format_id}."
            )

        return file_path

    @staticmethod
    def _get_merge_extension(
        audio_codec: str | None,
        video_extension: str | None,
    ) -> str:
        """
        Select a container that can preserve the selected streams
        without unnecessary transcoding.
        """
        audio_codec = (audio_codec or "").lower()
        video_extension = (video_extension or "").lower()

        if video_extension == "mp4" and audio_codec.startswith("mp4a"):
            return ".mp4"

        return ".mkv"

    @staticmethod
    def _sanitize_filename(
        filename: str,
    ) -> str:
        """Remove Windows-invalid filename characters."""
        invalid_characters = '<>:"/\\|?*'

        sanitized = "".join(
            "_" if character in invalid_characters else character
            for character in filename
        )

        previous_sanitized = None

        while previous_sanitized != sanitized:
            previous_sanitized = sanitized
            sanitized = sanitized.strip().rstrip(".")

        return sanitized or "media"
