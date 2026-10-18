from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.downloader import Downloader, MediaAnalysisError
from app.core.ffmpeg_service import FFmpegService
from app.core.format_selector import FormatSelector
from app.models import (
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    DownloadStatus,
    DownloadType,
    HistoryEntry,
    MediaInfo,
)
from app.services.config_service import ConfigService
from app.services.history_service import HistoryService


def _format_error_message(exc: Exception) -> str:
    """Traduz uma exceção interna arbitrária (yt_dlp, subprocess, threading
    ou qualquer outra) em uma `error_message` textual garantidamente não
    vazia, adequada para `DownloadResult`/`on_complete` (Requisitos 9.4,
    10.4).

    A maioria das exceções relevantes (`yt_dlp.utils.DownloadError`,
    `FFmpegError`, `FormatSelectionError`, `OSError`, etc.) stringificam
    para a mensagem descritiva que receberam na construção, então
    `str(exc)` já é suficiente na prática. Esta função apenas cobre o caso
    degenerado em que `str(exc)` é vazio (ex.: `RuntimeError()` sem
    argumentos), recorrendo ao nome do tipo da exceção para que o texto
    nunca fique vazio.
    """
    message = str(exc).strip()
    if message:
        return message
    return type(exc).__name__


@dataclass(frozen=True)
class DownloadHandle:
    """Identificador de uma operação de análise ou download em curso."""

    operation_id: UUID


@dataclass
class _OperationState:
    """Estado interno rastreado por `DownloadService` para uma operação
    (análise ou download) em curso ou já concluída.

    `progress` é o `DownloadProgress` mais recente conhecido para a
    operação, consultável via `get_progress(operation_id)`. `cancel_event`
    é o evento cooperativo de cancelamento associado, sinalizado por
    `cancel(operation_id)`. `future` é a tarefa agendada no
    `ThreadPoolExecutor` que executa a operação em background; tarefas
    futuras (15.2+) a utilizam para orquestrar a execução assíncrona.
    """

    progress: DownloadProgress = field(default_factory=DownloadProgress)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: object | None = None


class DownloadService:
    """
    Orquestra Downloader, FormatSelector e FFmpegService, expondo uma
    API única e assíncrona para a GUI. Usa ConfigService para valores
    padrão e HistoryService para registrar o desfecho de cada operação.

    A GUI nunca precisa conhecer `Downloader`, `FormatSelector` ou
    `FFmpegService` diretamente: `DownloadService` os compõe internamente,
    construindo instâncias padrão para qualquer colaborador não informado.
    """

    def __init__(
        self,
        downloader: Downloader | None = None,
        format_selector: FormatSelector | None = None,
        ffmpeg_service: FFmpegService | None = None,
        config_service: ConfigService | None = None,
        history_service: HistoryService | None = None,
    ) -> None:
        self._downloader = downloader if downloader is not None else Downloader()
        self._format_selector = (
            format_selector if format_selector is not None else FormatSelector()
        )
        self._ffmpeg_service = (
            ffmpeg_service if ffmpeg_service is not None else FFmpegService()
        )
        self._config_service = (
            config_service if config_service is not None else ConfigService()
        )
        self._history_service = (
            history_service if history_service is not None else HistoryService()
        )

        # Rastreamento interno de operações em curso/concluídas, protegido
        # por `_operations_lock` pois `get_progress`/`cancel` são chamados
        # pela thread principal enquanto o worker em background atualiza o
        # progresso de uma mesma operação concorrentemente.
        self._operations: dict[UUID, _OperationState] = {}
        self._operations_lock = threading.Lock()

        # Executor compartilhado que roda cada operação (análise, download)
        # em uma worker thread, garantindo que `analyze`/`start_download`
        # nunca bloqueiem a thread chamadora (Requisitos 9.1, 10.1).
        self._executor = ThreadPoolExecutor(thread_name_prefix="DownloadService")

    def _set_progress(self, operation_id: UUID, status: DownloadStatus) -> None:
        """Atualiza o `status` do `DownloadProgress` rastreado para
        `operation_id`, se a operação ainda estiver registrada."""
        with self._operations_lock:
            operation_state = self._operations.get(operation_id)
            if operation_state is not None:
                operation_state.progress.status = status

    def get_progress(self, operation_id: UUID) -> DownloadProgress | None:
        """Consulta o progresso mais recente de uma operação."""
        with self._operations_lock:
            operation_state = self._operations.get(operation_id)
            return operation_state.progress if operation_state is not None else None

    def cancel(self, operation_id: UUID) -> None:
        """Sinaliza o `cancel_event` associado a `operation_id`, solicitando
        o cancelamento cooperativo da operação.

        É um no-op silencioso, sem lançar exceção, quando `operation_id`
        não está registrado ou quando a operação já está em um estado
        terminal (`COMPLETED`, `FAILED` ou `CANCELLED`): nesses casos o
        `cancel_event` não é sinalizado.
        """
        with self._operations_lock:
            operation_state = self._operations.get(operation_id)
            if operation_state is None:
                return
            if operation_state.progress.status in (
                DownloadStatus.COMPLETED,
                DownloadStatus.FAILED,
                DownloadStatus.CANCELLED,
            ):
                return
            operation_state.cancel_event.set()

    def analyze(
        self,
        url: str,
        on_complete: Callable[[MediaInfo | None, str | None], None] | None = None,
    ) -> DownloadHandle:
        """Inicia a análise de uma URL em background.

        Retorna imediatamente um `DownloadHandle`, sem bloquear a thread
        chamadora: `Downloader.analyze` é executado em uma worker thread do
        `ThreadPoolExecutor`, e `on_complete(media_info, error_message)` é
        invocado a partir dessa mesma worker thread ao terminar, com
        exatamente um dos dois argumentos não-`None`.
        """
        operation_id = uuid4()

        with self._operations_lock:
            self._operations[operation_id] = _OperationState(
                progress=DownloadProgress(status=DownloadStatus.PENDING),
            )

        def _run_analysis() -> None:
            self._set_progress(operation_id, DownloadStatus.ANALYZING)

            try:
                media_info = self._downloader.analyze(url)
            except MediaAnalysisError as exc:
                self._set_progress(operation_id, DownloadStatus.FAILED)
                if on_complete is not None:
                    on_complete(None, _format_error_message(exc))
                return
            except Exception as exc:  # noqa: BLE001 - nunca deixar escapar da worker
                self._set_progress(operation_id, DownloadStatus.FAILED)
                if on_complete is not None:
                    on_complete(None, _format_error_message(exc))
                return

            self._set_progress(operation_id, DownloadStatus.COMPLETED)
            if on_complete is not None:
                on_complete(media_info, None)

        future = self._executor.submit(_run_analysis)
        with self._operations_lock:
            operation_state = self._operations.get(operation_id)
            if operation_state is not None:
                operation_state.future = future

        return DownloadHandle(operation_id=operation_id)

    def _apply_config_defaults(self, options: DownloadOptions) -> DownloadOptions:
        """Preenche campos não informados de `options` com os valores
        padrão da `Configuração` persistida (Requisitos 6.6, 13.1),
        retornando uma nova `DownloadOptions` em vez de mutar a original
        (que é `frozen` e pode ser retida pelo chamador/GUI).

        Apenas os seguintes campos recebem um valor padrão, e somente
        quando ausentes/falsos em `options`:
        - `destination`: usa `config.default_destination` quando não
          informado (`DownloadOptions.destination` tem como valor próprio
          `Path(".")`, então qualquer destino "vazio" equivalente a esse
          caminho relativo padrão do dataclass é substituído).
        - `download_type`: usa `config.default_download_type` quando
          `options.download_type` é `None`.
        - `audio_bitrate`: usa `config.default_audio_bitrate` quando
          `options.audio_bitrate is None` e o download é de áudio, já que
          esse campo só é relevante nesse caso (Requisito 6.6).
        """
        config = self._config_service.load()

        overrides: dict[str, Any] = {}

        if not options.destination or options.destination == Path("."):
            overrides["destination"] = config.default_destination

        if options.download_type is None:
            overrides["download_type"] = config.default_download_type

        effective_download_type = overrides.get("download_type", options.download_type)
        if (
            options.audio_bitrate is None
            and effective_download_type == DownloadType.AUDIO
        ):
            overrides["audio_bitrate"] = config.default_audio_bitrate

        if not overrides:
            return options
        return replace(options, **overrides)

    def start_download(
        self,
        media: MediaInfo,
        options: DownloadOptions,
        on_progress: Callable[[DownloadProgress], None] | None = None,
        on_complete: Callable[[DownloadResult], None] | None = None,
    ) -> DownloadHandle:
        """Inicia a seleção de formato e o download de uma mídia em background.

        Retorna imediatamente um `DownloadHandle`, sem bloquear a thread
        chamadora: a seleção de formato (via `FormatSelector.select`, sem
        reimplementar sua lógica) e o download (via `Downloader.download`)
        são executados em uma worker thread do `ThreadPoolExecutor`,
        associada a um `cancel_event` próprio desta operação.

        `on_progress(progress)` é invocado, a partir da worker thread, a
        cada atualização de `DownloadProgress`, respeitando a ordem de
        fases `PENDING -> DOWNLOADING -> PROCESSING -> estado terminal`
        (`COMPLETED`, `FAILED` ou `CANCELLED`, nessa ordem de prioridade:
        sucesso é `COMPLETED`; caso contrário, `CANCELLED` se o
        `cancel_event` desta operação estiver sinalizado, senão `FAILED`).

        `on_complete(result)` é invocado exatamente uma vez, com o
        `DownloadResult` final. Nenhuma exceção interna (seleção de
        formato, download, merge/conversão) escapa desta worker: qualquer
        falha é traduzida em um `DownloadResult(success=False, ...)`.
        """
        operation_id = uuid4()

        effective_options = self._apply_config_defaults(options)

        with self._operations_lock:
            operation_state = _OperationState(
                progress=DownloadProgress(status=DownloadStatus.PENDING),
            )
            self._operations[operation_id] = operation_state
            cancel_event = operation_state.cancel_event

        def _emit(progress: DownloadProgress) -> None:
            with self._operations_lock:
                current_state = self._operations.get(operation_id)
                if current_state is not None:
                    current_state.progress = progress
            if on_progress is not None:
                on_progress(progress)

        def _progress_hook(raw_progress: Any) -> None:
            # `Downloader.download` adapts yt-dlp's raw progress dicts into
            # a `DownloadProgress` before invoking this hook in production,
            # but tests substitute `Downloader` with a fake that may invoke
            # this hook directly with the raw yt-dlp dict. Handle both
            # without duplicating the conversion logic, which already
            # lives in `Downloader._build_download_progress`.
            if isinstance(raw_progress, DownloadProgress):
                progress = raw_progress
            else:
                progress = Downloader._build_download_progress(raw_progress)

            _emit(progress)

        def _terminal_status(succeeded: bool) -> DownloadStatus:
            if succeeded:
                return DownloadStatus.COMPLETED
            if cancel_event.is_set():
                return DownloadStatus.CANCELLED
            return DownloadStatus.FAILED

        def _finalize(result: DownloadResult) -> None:
            """Ponto único de conclusão de `_run_download`: emite o
            `DownloadProgress` terminal, registra a `HistoryEntry`
            correspondente no `HistoryService` (Requisito 14.1) e invoca
            `on_complete(result)`, nessa ordem — para TODOS os desfechos
            (sucesso, falha ou cancelamento), independentemente de qual dos
            pontos de saída de `_run_download` o atingiu.
            """
            status = _terminal_status(succeeded=result.success)
            _emit(DownloadProgress(status=status))

            self._history_service.add_entry(
                HistoryEntry(
                    url=effective_options.url,
                    title=media.title,
                    download_type=effective_options.download_type,
                    status=status,
                    file_path=result.file_path
                    if status == DownloadStatus.COMPLETED
                    else None,
                    timestamp=datetime.now(),
                    error_message=result.error_message
                    if status != DownloadStatus.COMPLETED
                    else None,
                )
            )

            if on_complete is not None:
                on_complete(result)

        def _run_download() -> None:
            _emit(DownloadProgress(status=DownloadStatus.DOWNLOADING))

            try:
                selection = self._format_selector.select(media, effective_options)
            except Exception as exc:  # noqa: BLE001 - nunca deixar escapar da worker
                _finalize(
                    DownloadResult(
                        success=False, error_message=_format_error_message(exc)
                    )
                )
                return

            try:
                result = self._downloader.download(
                    effective_options,
                    selection,
                    progress_hook=_progress_hook,
                    cancel_event=cancel_event,
                )
            except Exception as exc:  # noqa: BLE001 - nunca deixar escapar da worker
                _finalize(
                    DownloadResult(
                        success=False, error_message=_format_error_message(exc)
                    )
                )
                return

            # `Downloader.download` performs the merge step synchronously
            # as part of a single blocking call, so there is no separate
            # hook invocation to observe that sub-phase from here. A
            # `PROCESSING` state is synthesized right after the call
            # returns successfully (and before the terminal state) whenever
            # the selection required a merge, which keeps the overall
            # sequence non-decreasing: every `DOWNLOADING` progress emitted
            # through the hook happens before this point.
            if selection.requires_merge and result.success:
                _emit(DownloadProgress(status=DownloadStatus.PROCESSING))

            _finalize(result)

        future = self._executor.submit(_run_download)
        with self._operations_lock:
            operation_state = self._operations.get(operation_id)
            if operation_state is not None:
                operation_state.future = future

        return DownloadHandle(operation_id=operation_id)
