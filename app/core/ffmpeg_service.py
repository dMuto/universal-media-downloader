from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegError(Exception):
    """Raised when an FFmpeg operation cannot be completed."""


class FFmpegService:
    """Provides a small interface for FFmpeg operations."""

    def __init__(self, ffmpeg_path: Path | str | None = None) -> None:
        self._ffmpeg_path = self._resolve_ffmpeg_path(ffmpeg_path)

    @property
    def executable(self) -> Path:
        """Return the resolved FFmpeg executable path."""
        return self._ffmpeg_path

    def is_available(self) -> bool:
        """Return whether FFmpeg is available."""
        return self._ffmpeg_path.is_file()

    def merge(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Merge video and audio without re-encoding when possible.
        """
        video_path = Path(video_path)
        audio_path = Path(audio_path)
        output_path = Path(output_path)

        self._validate_input_file(video_path, "vídeo")
        self._validate_input_file(audio_path, "áudio")

        if not self.is_available():
            raise FFmpegError(
                "FFmpeg não foi encontrado."
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        command = [
            str(self._ffmpeg_path),
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            str(output_path),
        ]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as exc:
            raise FFmpegError(
                f"Não foi possível executar o FFmpeg: {exc}"
            ) from exc

        if process.returncode != 0:
            error = process.stderr.strip()

            raise FFmpegError(
                "O FFmpeg falhou durante o merge."
                + (f" Detalhes: {error}" if error else "")
            )

        if not output_path.is_file():
            raise FFmpegError(
                "O FFmpeg terminou, mas o arquivo final não foi criado."
            )

        return output_path

    @staticmethod
    def _resolve_ffmpeg_path(
        ffmpeg_path: Path | str | None,
    ) -> Path:
        """
        Resolve FFmpeg from an explicit path or the system PATH.
        """
        if ffmpeg_path is not None:
            path = Path(ffmpeg_path)

            if not path.is_file():
                raise FFmpegError(
                    f"O caminho do FFmpeg não é válido: {path}"
                )

            return path.resolve()

        executable = shutil.which("ffmpeg")

        if executable is None:
            raise FFmpegError(
                "FFmpeg não foi encontrado no PATH do sistema."
            )

        return Path(executable).resolve()

    @staticmethod
    def _validate_input_file(
        file_path: Path,
        description: str,
    ) -> None:
        """Validate an input media file."""
        if not file_path.is_file():
            raise FFmpegError(
                f"O arquivo de {description} não existe: {file_path}"
            )