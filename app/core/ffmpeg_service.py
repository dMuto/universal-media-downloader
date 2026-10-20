from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegError(Exception):
    """Levantada quando uma operação do FFmpeg não pode ser concluída."""


SUPPORTED_MP3_BITRATES: frozenset[int] = frozenset({128, 192, 256, 320})


class FFmpegService:
    """Fornece uma pequena interface para operações do FFmpeg."""

    def __init__(self, ffmpeg_path: Path | str | None = None) -> None:
        self._ffmpeg_path = self._resolve_ffmpeg_path(ffmpeg_path)

    @property
    def executable(self) -> Path:
        """Retorna o caminho resolvido do executável do FFmpeg."""
        return self._ffmpeg_path

    def is_available(self) -> bool:
        """Retorna se o FFmpeg está disponível."""
        return self._ffmpeg_path.is_file()

    def merge(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Faz o merge de vídeo e áudio sem recodificação quando possível.
        """
        video_path = Path(video_path)
        audio_path = Path(audio_path)
        output_path = Path(output_path)

        self._validate_input_file(video_path, "vídeo")
        self._validate_input_file(audio_path, "áudio")

        if not self.is_available():
            raise FFmpegError("FFmpeg não foi encontrado.")

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
            raise FFmpegError(f"Não foi possível executar o FFmpeg: {exc}") from exc

        if process.returncode != 0:
            error = process.stderr.strip()

            raise FFmpegError(
                "O FFmpeg falhou durante o merge."
                + (f" Detalhes: {error}" if error else "")
            )

        if not output_path.is_file():
            raise FFmpegError("O FFmpeg terminou, mas o arquivo final não foi criado.")

        return output_path

    def convert_to_mp3(
        self,
        audio_path: Path,
        output_path: Path,
        bitrate: int,
    ) -> Path:
        """
        Converte um arquivo de áudio para MP3 no bitrate informado.

        Levanta FFmpegError se:
        - bitrate não estiver em SUPPORTED_MP3_BITRATES (sem invocar o FFmpeg);
        - audio_path não existir;
        - o FFmpeg não estiver disponível;
        - o processo do FFmpeg retornar código != 0;
        - o arquivo de saída não existir após execução com sucesso.
        """
        if bitrate not in SUPPORTED_MP3_BITRATES:
            raise FFmpegError(
                f"Bitrate de MP3 não suportado: {bitrate}. "
                f"Valores suportados: {sorted(SUPPORTED_MP3_BITRATES)}"
            )

        audio_path = Path(audio_path)
        output_path = Path(output_path)

        self._validate_input_file(audio_path, "áudio")

        if not self.is_available():
            raise FFmpegError("FFmpeg não foi encontrado.")

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        command = [
            str(self._ffmpeg_path),
            "-y",
            "-i",
            str(audio_path),
            "-c:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate}k",
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
            raise FFmpegError(f"Não foi possível executar o FFmpeg: {exc}") from exc

        if process.returncode != 0:
            error = process.stderr.strip()

            raise FFmpegError(
                "O FFmpeg falhou durante a conversão para MP3."
                + (f" Detalhes: {error}" if error else "")
            )

        if not output_path.is_file():
            raise FFmpegError("O FFmpeg terminou, mas o arquivo final não foi criado.")

        return output_path

    @staticmethod
    def _resolve_ffmpeg_path(
        ffmpeg_path: Path | str | None,
    ) -> Path:
        """
        Resolve o FFmpeg a partir de um caminho explícito ou do PATH do
        sistema.
        """
        if ffmpeg_path is not None:
            path = Path(ffmpeg_path)

            if not path.is_file():
                raise FFmpegError(f"O caminho do FFmpeg não é válido: {path}")

            return path.resolve()

        executable = shutil.which("ffmpeg")

        if executable is None:
            raise FFmpegError("FFmpeg não foi encontrado no PATH do sistema.")

        return Path(executable).resolve()

    @staticmethod
    def _validate_input_file(
        file_path: Path,
        description: str,
    ) -> None:
        """Valida um arquivo de mídia de entrada."""
        if not file_path.is_file():
            raise FFmpegError(f"O arquivo de {description} não existe: {file_path}")
