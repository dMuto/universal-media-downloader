"""Janela raiz da GUI (CustomTkinter).

`MainWindow` é responsável por montar a janela principal do aplicativo e
por manter o único ponto de contato seguro entre as worker threads do
`DownloadService` e a thread principal (thread da GUI/Tkinter).

Conforme o design (`design.md`, seção "Threading e comunicação com a GUI"):
`DownloadService.analyze`/`start_download` invocam `on_progress`/
`on_complete` diretamente da worker thread que executa a operação. A GUI
nunca pode tocar em um widget Tkinter fora da thread principal, então o
padrão adotado aqui é:

1. Os callbacks entregues ao `DownloadService` (`on_progress`/
   `on_complete`) fazem apenas `queue.put(...)`, uma operação thread-safe,
   sem tocar em nenhum widget.
2. `MainWindow` agenda `_poll_operations` via `self.after(ms, callback)`,
   que roda periodicamente **na thread principal**. A cada execução, ele
   drena as filas pendentes de todas as operações registradas e só então
   invoca os handlers (`on_progress`/`on_complete`) fornecidos por quem
   registrou a operação (ex.: `DownloadPanel`, nas tarefas 17.2+), que são
   os únicos pontos autorizados a atualizar widgets.

Esta classe não importa nada de `app.core`: apenas `app.services` e
`app.models`, conforme o Requisito 12.8.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import customtkinter

from app.services.config_service import ConfigService
from app.services.download_service import DownloadService
from app.services.history_service import HistoryService

#: Intervalo padrão, em milissegundos, entre drenagens sucessivas das
#: filas de progresso/resultado das operações ativas.
DEFAULT_POLL_INTERVAL_MS = 100


@dataclass
class _RegisteredOperation:
    """Estado interno mantido por `MainWindow` para uma operação registrada
    via `register_operation`.

    As filas são preenchidas (via `.put`) pelos callbacks retornados por
    `register_operation`, chamados pela worker thread do `DownloadService`.
    Os handlers `on_progress`/`on_complete` são invocados exclusivamente a
    partir de `_poll_operations`, ou seja, na thread principal.
    """

    progress_queue: "queue.Queue[Any]" = field(default_factory=queue.Queue)
    complete_queue: "queue.Queue[Any]" = field(default_factory=queue.Queue)
    on_progress: Callable[[Any], None] | None = None
    on_complete: Callable[[Any], None] | None = None


class MainWindow(customtkinter.CTk):
    """Janela raiz do aplicativo.

    Monta a estrutura básica da janela (`content_frame`, onde os painéis
    das tarefas 17.2/17.4 — `DownloadPanel` e `HistoryPanel` — serão
    posicionados) e mantém o laço de polling que drena progresso/resultado
    das operações ativas na thread principal.

    `download_service`/`config_service`/`history_service` podem ser
    informados (útil em testes, com fakes/stubs) ou, se omitidos, são
    construídos com seus valores padrão — a GUI nunca instancia
    `Downloader`, `FormatSelector` ou `FFmpegService` diretamente.
    """

    def __init__(
        self,
        download_service: DownloadService | None = None,
        config_service: ConfigService | None = None,
        history_service: HistoryService | None = None,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        auto_poll: bool = True,
    ) -> None:
        super().__init__()

        self.download_service = (
            download_service if download_service is not None else DownloadService()
        )
        self.config_service = (
            config_service if config_service is not None else ConfigService()
        )
        self.history_service = (
            history_service if history_service is not None else HistoryService()
        )

        self._poll_interval_ms = poll_interval_ms

        # Protege `_operations` contra acesso concorrente: é lido/escrito
        # pela thread principal (register/unregister/poll) e as filas
        # internas de cada operação são escritas pelas worker threads do
        # `DownloadService` via os callbacks retornados por
        # `register_operation`.
        self._operations_lock = threading.Lock()
        self._operations: dict[UUID, _RegisteredOperation] = {}

        self.title("Universal Media Downloader")

        # Container genérico onde `DownloadPanel`/`HistoryPanel` (tarefas
        # 17.2/17.4) serão montados. Mantido aqui para que esta subtarefa
        # já deixe um ponto de extensão estável, sem precisar antecipar a
        # implementação desses painéis.
        self.content_frame = customtkinter.CTkFrame(self)
        self.content_frame.pack(fill="both", expand=True)

        if auto_poll:
            self._schedule_poll()

    def register_operation(
        self,
        operation_id: UUID,
        on_progress: Callable[[Any], None] | None = None,
        on_complete: Callable[[Any], None] | None = None,
    ) -> tuple[Callable[[Any], None], Callable[[Any], None]]:
        """Registra os handlers de UI para `operation_id` e retorna o par
        de callbacks thread-safe a ser passado como `on_progress`/
        `on_complete` ao `DownloadService` (ex.: em
        `DownloadService.analyze`/`start_download`).

        Os callbacks retornados apenas colocam o valor recebido em uma
        fila interna; eles podem ser chamados com segurança a partir de
        qualquer worker thread. `on_progress`/`on_complete` (os handlers
        fornecidos aqui) só são efetivamente invocados mais tarde, a
        partir de `_poll_operations`, na thread principal.
        """
        registered = _RegisteredOperation(
            on_progress=on_progress,
            on_complete=on_complete,
        )
        with self._operations_lock:
            self._operations[operation_id] = registered

        def progress_callback(progress: Any) -> None:
            registered.progress_queue.put(progress)

        def complete_callback(result: Any) -> None:
            registered.complete_queue.put(result)

        return progress_callback, complete_callback

    def unregister_operation(self, operation_id: UUID) -> None:
        """Remove o registro de `operation_id`, se existir.

        É um no-op silencioso quando `operation_id` não está registrado,
        para que painéis possam limpar operações já finalizadas sem
        precisar verificar previamente se o registro ainda existe.
        """
        with self._operations_lock:
            self._operations.pop(operation_id, None)

    def _schedule_poll(self) -> None:
        """Agenda a próxima execução de `_poll_operations` na thread
        principal, via o mecanismo de agendamento do Tkinter."""
        self.after(self._poll_interval_ms, self._poll_operations)

    def _poll_operations(self, reschedule: bool = True) -> None:
        """Drena as filas de progresso/resultado de todas as operações
        registradas e invoca os handlers correspondentes.

        Executado na thread principal: é seguro atualizar widgets a
        partir dos handlers `on_progress`/`on_complete` chamados aqui.

        `reschedule=False` é usado apenas por testes, para drenar as
        filas uma única vez sem criar um novo agendamento via
        `self.after`.
        """
        with self._operations_lock:
            operations = list(self._operations.items())

        for _operation_id, registered in operations:
            while True:
                try:
                    progress = registered.progress_queue.get_nowait()
                except queue.Empty:
                    break
                if registered.on_progress is not None:
                    registered.on_progress(progress)

            while True:
                try:
                    result = registered.complete_queue.get_nowait()
                except queue.Empty:
                    break
                if registered.on_complete is not None:
                    registered.on_complete(result)

        if reschedule:
            self._schedule_poll()
