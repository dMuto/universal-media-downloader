from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yt_dlp

from app.core.error_messages import translate_error
from app.core.ffmpeg_service import FFmpegError, FFmpegService
from app.core.format_selector import FormatSelectionError
from app.core.ytdlp_compat_patches import apply_compatibility_patches
from app.models import (
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    DownloadStatus,
    DownloadType,
    FormatInfo,
    FormatSelection,
    MediaInfo,
    MediaType,
)


class MediaAnalysisError(Exception):
    """Levantada quando uma URL de mídia não pode ser analisada."""


class DownloadError(Exception):
    """Levantada quando um download de mídia não pode ser concluído."""


class _DownloadCancelled(Exception):
    """
    Exceção interna de controle de fluxo usada para interromper
    cooperativamente um download quando `cancel_event` é sinalizado.

    Ela nunca escapa de `Downloader.download()`: é sempre capturada e
    traduzida em um `DownloadResult(success=False, ...)`.
    """


class Downloader:
    """Fornece análise e download de mídia através do yt-dlp."""

    def __init__(
        self,
        ffmpeg_service: FFmpegService | None = None,
    ) -> None:
        self._ffmpeg_service = ffmpeg_service
        # Corrige bugs pontuais e conhecidos de extratores específicos do
        # yt-dlp (ver `app.core.ytdlp_compat_patches`) antes de qualquer
        # uso de `yt_dlp.YoutubeDL` por esta instância.
        apply_compatibility_patches()

    def analyze(self, url: str) -> MediaInfo:
        """
        Analisa uma URL de mídia e retorna as informações de mídia no
        nível da aplicação.

        Este método apenas extrai metadados e formatos disponíveis.
        Ele não baixa nenhuma mídia.
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
            raise MediaAnalysisError(translate_error(exc)) from exc

        except Exception as exc:
            raise MediaAnalysisError(
                translate_error(
                    exc, default="Ocorreu um erro inesperado ao analisar a mídia."
                )
            ) from exc

        if not info:
            raise MediaAnalysisError("O yt-dlp não retornou informações sobre a mídia.")

        return self._build_media_info(info)

    def download(
        self,
        options: DownloadOptions,
        selection: FormatSelection,
        progress_hook: Callable[[DownloadProgress], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> DownloadResult:
        """
        Baixa os formatos selecionados usando o yt-dlp.

        Quando vídeo e áudio estão separados, eles são baixados em
        arquivos temporários e unidos (merge) usando o FFmpegService.

        Quando `progress_hook` é informado, ele é invocado com um
        `DownloadProgress` adaptado a partir dos próprios dicionários de
        `progress_hooks` do yt-dlp conforme o download avança. Apenas os
        campos presentes no dicionário subjacente do yt-dlp são
        preenchidos; campos ausentes são deixados como `None` em vez de
        assumir um valor.

        Quando `cancel_event` é informado, ele é verificado
        cooperativamente em pontos seguros (antes de iniciar o download
        de cada stream, dentro do progress hook do yt-dlp, e antes de
        iniciar o merge). Uma vez confirmado o cancelamento, nenhum
        arquivo final é escrito/sobrescrito no diretório de destino a
        partir de dados parciais, quaisquer arquivos temporários ou
        parciais criados pela operação são removidos, e um
        `DownloadResult(success=False, ...)` descrevendo o cancelamento
        é retornado em vez de uma exceção ser levantada.
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
                    cancel_event=cancel_event,
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
                cancel_event=cancel_event,
            )

            if (
                options.download_type == DownloadType.AUDIO
                and options.audio_bitrate is not None
            ):
                file_path = self._convert_to_mp3(
                    audio_path=file_path,
                    bitrate=options.audio_bitrate,
                )

            return DownloadResult(
                success=True,
                file_path=file_path,
                file_size=self._get_file_size(file_path),
            )

        except _DownloadCancelled:
            return DownloadResult(
                success=False,
                error_message="Operação cancelada.",
            )

        except yt_dlp.utils.DownloadError as exc:
            return DownloadResult(
                success=False,
                error_message=translate_error(exc),
            )

        except FFmpegError as exc:
            return DownloadResult(
                success=False,
                error_message=translate_error(exc),
            )

        except FormatSelectionError as exc:
            return DownloadResult(
                success=False,
                error_message=translate_error(exc),
            )

        except OSError as exc:
            return DownloadResult(
                success=False,
                error_message=translate_error(exc),
            )

        except Exception as exc:
            return DownloadResult(
                success=False,
                error_message=translate_error(
                    exc, default="Ocorreu um erro inesperado durante o download."
                ),
            )

    @staticmethod
    def _build_media_info(
        info: dict[str, Any],
    ) -> MediaInfo:
        """Converte as informações brutas do yt-dlp em um modelo MediaInfo."""
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
        """Converte um formato bruto do yt-dlp em um modelo FormatInfo."""
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
        """Normaliza os valores de codec do yt-dlp."""
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
        """Determina o tipo de mídia a partir dos codecs disponíveis."""
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
        """Retorna se um formato do yt-dlp representa um stream de mídia."""
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
        progress_hook: Callable[[DownloadProgress], None] | None,
        cancel_event: threading.Event | None = None,
    ) -> Callable[[dict[str, Any]], None]:
        """
        Constrói um progress hook compatível com o yt-dlp que adapta o
        dicionário bruto de progresso do yt-dlp em um DownloadProgress
        antes de delegar ao progress_hook fornecido pelo chamador.

        Quando `cancel_event` está sinalizado, o hook levanta
        `_DownloadCancelled` em vez de delegar, o que interrompe
        limpamente o download em curso do yt-dlp (a exceção se propaga
        através de `extract_info`/`download` sem ser engolida pelo
        yt-dlp, já que a própria invocação do progress hook do yt-dlp
        não captura exceções arbitrárias levantadas por hooks fornecidos
        pelo chamador).
        """

        def yt_dlp_hook(raw_progress: dict[str, Any]) -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise _DownloadCancelled()

            if progress_hook is not None:
                progress_hook(
                    Downloader._build_download_progress(raw_progress),
                )

        return yt_dlp_hook

    @staticmethod
    def _check_cancelled(
        cancel_event: threading.Event | None,
    ) -> None:
        """Levanta `_DownloadCancelled` se `cancel_event` tiver sido sinalizado."""
        if cancel_event is not None and cancel_event.is_set():
            raise _DownloadCancelled()

    @staticmethod
    def _build_download_progress(
        raw_progress: dict[str, Any],
    ) -> DownloadProgress:
        """
        Converte um dicionário bruto de progress_hooks do yt-dlp em um
        DownloadProgress.

        Apenas os campos presentes em `raw_progress` são preenchidos;
        campos ausentes no dicionário de origem são mantidos como
        `None`, sem presumir um valor.
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
        """Mapeia o status bruto de progresso do yt-dlp para DownloadStatus."""
        if raw_status == "error":
            return DownloadStatus.FAILED

        return DownloadStatus.DOWNLOADING

    @staticmethod
    def _get_downloaded_file_path(
        ydl: yt_dlp.YoutubeDL,
        info: dict[str, Any],
    ) -> Path | None:
        """Determina o caminho do arquivo baixado."""
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
        """Retorna o tamanho do arquivo baixado, quando disponível."""
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
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Baixa um único formato do yt-dlp."""
        self._check_cancelled(cancel_event)

        ydl_options = {
            "format": format_id,
            "outtmpl": str(destination / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        if progress_hook is not None or cancel_event is not None:
            ydl_options["progress_hooks"] = [
                self._make_yt_dlp_progress_hook(
                    progress_hook,
                    cancel_event=cancel_event,
                ),
            ]

        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(
                    url.strip(),
                    download=True,
                )

                file_path = self._get_downloaded_file_path(
                    ydl,
                    info,
                )

        except _DownloadCancelled:
            self._remove_partial_files(destination)
            raise

        if file_path is None or not file_path.is_file():
            raise OSError("Não foi possível determinar o arquivo baixado.")

        return self._sanitize_downloaded_file_name(file_path)

    def _convert_to_mp3(
        self,
        audio_path: Path,
        bitrate: int,
    ) -> Path:
        """
        Converte o arquivo de áudio baixado para MP3 no bitrate
        solicitado, removendo em seguida o arquivo de áudio intermediário
        (não convertido).

        O arquivo MP3 resultante é escrito ao lado do arquivo
        intermediário, reaproveitando seu stem e trocando a extensão
        para `.mp3`.
        """
        if self._ffmpeg_service is None:
            self._ffmpeg_service = FFmpegService()

        output_path = audio_path.with_suffix(".mp3")

        final_path = self._ffmpeg_service.convert_to_mp3(
            audio_path=audio_path,
            output_path=output_path,
            bitrate=bitrate,
        )

        if final_path != audio_path:
            audio_path.unlink(missing_ok=True)

        return final_path

    @staticmethod
    def _sanitize_downloaded_file_name(
        file_path: Path,
    ) -> Path:
        """
        Renomeia um arquivo baixado para que seu nome final seja
        sanitizado, espelhando a sanitização já aplicada ao nome de
        saída do caminho de merge.

        O stem (nome do arquivo sem extensão) é sanitizado; a extensão
        e o diretório pai são preservados. Quando o stem sanitizado é
        idêntico ao original, o arquivo é deixado intocado.
        """
        sanitized_stem = Downloader._sanitize_filename(file_path.stem)

        if sanitized_stem == file_path.stem:
            return file_path

        sanitized_path = file_path.with_name(f"{sanitized_stem}{file_path.suffix}")

        file_path.replace(sanitized_path)

        return sanitized_path

    def _download_and_merge(
        self,
        options: DownloadOptions,
        selection: FormatSelection,
        destination: Path,
        progress_hook: Callable[[DownloadProgress], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> DownloadResult:
        """Baixa streams separados de vídeo/áudio e faz o merge entre eles."""
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

        # `TemporaryDirectory` remove `temp_directory` (e tudo que está
        # dentro dele) ao sair, independentemente de o bloco terminar
        # normalmente ou levantar uma exceção, então quaisquer streams
        # parciais de vídeo/áudio criados antes de um cancelamento
        # confirmado são removidos automaticamente.
        with TemporaryDirectory(
            prefix="umd_",
            dir=destination,
        ) as temp_directory:
            temp_path = Path(temp_directory)

            self._check_cancelled(cancel_event)

            video_path = self._download_to_directory(
                url=options.url,
                format_id=video_format.format_id,
                directory=temp_path,
                prefix="video",
                progress_hook=progress_hook,
                cancel_event=cancel_event,
            )

            self._check_cancelled(cancel_event)

            audio_path = self._download_to_directory(
                url=options.url,
                format_id=audio_format.format_id,
                directory=temp_path,
                prefix="audio",
                progress_hook=progress_hook,
                cancel_event=cancel_event,
            )

            self._check_cancelled(cancel_event)

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
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Baixa um stream selecionado para um diretório temporário."""
        self._check_cancelled(cancel_event)

        ydl_options = {
            "format": format_id,
            "outtmpl": str(directory / f"{prefix}_%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        if progress_hook is not None or cancel_event is not None:
            ydl_options["progress_hooks"] = [
                self._make_yt_dlp_progress_hook(
                    progress_hook,
                    cancel_event=cancel_event,
                ),
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
    def _remove_partial_files(
        directory: Path,
    ) -> None:
        """
        Remove arquivos parciais/temporários (por exemplo, os arquivos
        auxiliares `.part`/`.ytdl` do yt-dlp) deixados em `directory` por
        um download interrompido, sem tocar em nenhum outro arquivo não
        relacionado.
        """
        for pattern in ("*.part", "*.ytdl"):
            for partial_file in directory.glob(pattern):
                try:
                    partial_file.unlink()
                except OSError:
                    pass

    @staticmethod
    def _get_merge_extension(
        audio_codec: str | None,
        video_extension: str | None,
    ) -> str:
        """
        Seleciona um contêiner capaz de preservar os streams
        selecionados sem transcodificação desnecessária.
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
        """
        Remove caracteres inválidos para nomes de arquivo no Windows.

        Garantia contra path traversal: como `/` e `\\` fazem parte do
        conjunto de caracteres inválidos substituídos abaixo, o valor
        retornado é sempre um único segmento de caminho e nunca pode
        conter um separador de diretório. Isso também impede que o
        resultado codifique um caminho absoluto (POSIX `/etc/passwd`,
        Windows `C:\\...`) ou um caminho UNC (`\\\\servidor\\share\\...`),
        já que todos esses formatos dependem de separadores que são
        removidos.

        O único caso remanescente é um resultado que se reduz a `..` ou
        a uma sequência de pontos (por exemplo, uma entrada `"..."` ou
        `"../"` após a substituição dos separadores). O laço de remoção
        de pontos/espaços finais abaixo reduz qualquer um desses valores
        a uma string vazia, que então recai no nome padrão `"media"` em
        vez de uma referência ao diretório pai.

        Como consequência, para qualquer entrada, juntar o nome
        retornado a um diretório de destino (ex.: `destino /
        nome_sanitizado`) sempre resolve para um caminho dentro desse
        diretório — nunca é possível escapar dele via segmentos `..`,
        caminhos absolutos ou caminhos UNC.
        """
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
