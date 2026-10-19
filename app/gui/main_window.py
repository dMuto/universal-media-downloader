"""Janela raiz da GUI (CustomTkinter).

`MainWindow` monta a janela principal e mantem o unico ponto de contato
seguro entre as worker threads do `DownloadService` e a thread principal.

Padrao de threading (design.md, secao "Threading e comunicacao com a GUI"):
1. Callbacks entregues ao `DownloadService` (`on_progress`/`on_complete`)
   apenas enfileiram o valor recebido (`queue.put`), sem tocar em widgets.
2. `MainWindow` agenda `_poll_operations` via `self.after(ms, callback)`,
   que roda periodicamente na thread principal, drena as filas pendentes
   e so entao invoca os handlers reais, que podem tocar em widgets.

Esta classe nao importa nada de `app.core`: apenas `app.services` e
`app.models` (Requisito 12.8).

`MainWindow` monta `DownloadPanel` e `HistoryPanel` dentro de
`content_frame` (design.md, secao "app/gui (novo)"). Em vez de passar o
`DownloadService` real diretamente ao `DownloadPanel`, injeta um
`_MainThreadDownloadService`, que envolve `analyze`/`start_download` com
`register_operation`, garantindo que os callbacks do painel so sejam
chamados a partir de `_poll_operations`, na thread principal.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import customtkinter

from app.gui.download_panel import DownloadPanel
from app.gui.history_panel import HistoryPanel
from app.services.config_service import ConfigService
from app.services.download_service import DownloadService
from app.services.history_service import HistoryService
from app.services.log_service import LogService

DEFAULT_POLL_INTERVAL_MS = 100


@dataclass
class _RegisteredOperation:
    progress_queue: queue.Queue[Any] = field(default_factory=queue.Queue)
    complete_queue: queue.Queue[Any] = field(default_factory=queue.Queue)
    on_progress: Callable[[Any], None] | None = None
    on_complete: Callable[[Any], None] | None = None


class _MainThreadDownloadService:
    """Adapta `DownloadService` para que `on_progress`/`on_complete`
    sejam invocados somente a partir de `_poll_operations`, na thread
    principal, via `register_operation`."""

    def __init__(
        self, main_window: MainWindow, download_service: DownloadService
    ) -> None:
        self._main_window = main_window
        self._download_service = download_service

    def analyze(self, url, on_complete=None):
        local_id = uuid4()

        def _handle_complete(payload):
            media, error = payload
            try:
                if on_complete is not None:
                    on_complete(media, error)
            finally:
                self._main_window.unregister_operation(local_id)

        _, complete_callback = self._main_window.register_operation(
            local_id, on_complete=_handle_complete
        )

        return self._download_service.analyze(
            url,
            on_complete=lambda media, error: complete_callback((media, error)),
        )

    def start_download(self, media, options, on_progress=None, on_complete=None):
        local_id = uuid4()

        def _handle_complete(result):
            try:
                if on_complete is not None:
                    on_complete(result)
            finally:
                self._main_window.refresh_history()
                self._main_window.unregister_operation(local_id)

        progress_callback, complete_callback = self._main_window.register_operation(
            local_id, on_progress=on_progress, on_complete=_handle_complete
        )

        return self._download_service.start_download(
            media,
            options,
            on_progress=progress_callback,
            on_complete=complete_callback,
        )

    def cancel(self, operation_id):
        self._download_service.cancel(operation_id)

    def get_progress(self, operation_id):
        return self._download_service.get_progress(operation_id)

    def get_log_path(self):
        return self._download_service.get_log_path()


class MainWindow(customtkinter.CTk):
    """Janela raiz do aplicativo: monta `content_frame` com `DownloadPanel`
    e `HistoryPanel`, e mantem o laco de polling thread-safe."""

    def __init__(
        self,
        download_service: DownloadService | None = None,
        config_service: ConfigService | None = None,
        history_service: HistoryService | None = None,
        log_service: LogService | None = None,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        auto_poll: bool = True,
        build_panels: bool = True,
    ) -> None:
        super().__init__()

        self.log_service = log_service if log_service is not None else LogService()
        self.config_service = (
            config_service if config_service is not None else ConfigService()
        )
        self.history_service = (
            history_service if history_service is not None else HistoryService()
        )
        self.download_service = (
            download_service
            if download_service is not None
            else DownloadService(
                config_service=self.config_service,
                history_service=self.history_service,
                log_service=self.log_service,
            )
        )

        self._poll_interval_ms = poll_interval_ms

        self._operations_lock = threading.Lock()
        self._operations: dict[UUID, _RegisteredOperation] = {}

        self.title("Universal Media Downloader")
        self.geometry("720x640")

        self.content_frame = customtkinter.CTkFrame(self)
        self.content_frame.pack(fill="both", expand=True)

        self.download_panel: DownloadPanel | None = None
        self.history_panel: HistoryPanel | None = None

        if build_panels:
            proxy_service = _MainThreadDownloadService(self, self.download_service)
            self.download_panel = DownloadPanel(self.content_frame, proxy_service)
            self.download_panel.pack(fill="x", padx=10, pady=(10, 5))

            self.history_panel = HistoryPanel(
                self.content_frame, history_service=self.history_service
            )
            self.history_panel.refresh()

        if auto_poll:
            self._schedule_poll()

    def refresh_history(self) -> None:
        if self.history_panel is not None:
            self.history_panel.refresh()

    def register_operation(self, operation_id, on_progress=None, on_complete=None):
        registered = _RegisteredOperation(
            on_progress=on_progress,
            on_complete=on_complete,
        )
        with self._operations_lock:
            self._operations[operation_id] = registered

        def progress_callback(progress):
            registered.progress_queue.put(progress)

        def complete_callback(result):
            registered.complete_queue.put(result)

        return progress_callback, complete_callback

    def unregister_operation(self, operation_id) -> None:
        with self._operations_lock:
            self._operations.pop(operation_id, None)

    def _schedule_poll(self) -> None:
        self.after(self._poll_interval_ms, self._poll_operations)

    def _poll_operations(self, reschedule: bool = True) -> None:
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
