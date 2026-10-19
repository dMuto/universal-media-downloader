"""Painel de download (CustomTkinter).

`DownloadPanel` concentra os controles de entrada do usuário (URL, tipo de
download, qualidade de vídeo/bitrate de áudio, diretório de destino) e os
botões de ação ("Analisar", "Baixar", "Cancelar"), delegando toda a
lógica de análise/download/cancelamento ao `DownloadService` recebido
via injeção de dependência.

Não importa nada de `app.core` (Requisito 12.8): depende apenas de
`app.services`/`app.models`, `customtkinter` e módulos padrão do Python
(`tkinter.filedialog`, `os`).

Conforme design.md (seção "`app/gui` (novo)"):
> `DownloadPanel`: campo de URL, botão "Analisar" (chama
> `DownloadService.analyze`), exibição de título/uploader/thumbnail
> quando disponíveis, seletor de Tipo_De_Download, altura máxima (vídeo)
> ou Bitrate_De_Áudio (áudio) e diretório de destino, botão "Baixar" e
> botão "Cancelar".

**Validates: Requirements 12.2, 12.3, 12.4, 12.6**

Melhorias adicionadas sobre o design original (a pedido do usuário):
- Botão "Procurar..." ao lado do destino, abrindo o explorador de
  arquivos nativo (`tkinter.filedialog.askdirectory`) em vez de exigir
  que o caminho seja colado manualmente.
- Seletor de qualidade de vídeo e de bitrate de áudio como menus
  (dropdown) em vez de campos de texto livre. O menu de qualidade de
  vídeo é povoado dinamicamente com as resoluções realmente disponíveis
  na mídia analisada (mais a opção "Melhor disponível").
- Mensagens de erro mais claras: o texto exibido já vem traduzido pelo
  `DownloadService`/`Downloader` (ver `app.core.error_messages`), e o
  rótulo de erro agora quebra linha em vez de cortar o texto.
- Botão "Ver log" que abre o arquivo `.txt` com o log completo do
  processo (análise, seleção de formato, download, merge, conversão e
  erros), escrito pelo `LogService`.
"""

from __future__ import annotations

import os
import tkinter
from pathlib import Path
from tkinter import filedialog
from uuid import UUID

import customtkinter

from app.gui.progress_widget import ProgressWidget
from app.models import (
    DownloadOptions,
    DownloadProgress,
    DownloadResult,
    DownloadType,
    MediaInfo,
)

#: Opção de qualidade de vídeo que deixa o `FormatSelector` escolher a
#: maior resolução disponível (equivalente a `max_height=None`).
_BEST_QUALITY_LABEL = "Melhor disponível"

#: Bitrates de áudio oferecidos no seletor. Mantidos em sincronia
#: manualmente com `FFmpegService.SUPPORTED_MP3_BITRATES` (não importado
#: aqui para preservar a regra de que `app/gui` nunca depende de
#: `app/core`, Requisito 12.8).
_AUDIO_BITRATE_OPTIONS = (128, 192, 256, 320)


class DownloadPanel(customtkinter.CTkFrame):
    """Painel com os controles de análise/download de uma mídia.

    `download_service` é qualquer objeto que implemente a API pública de
    `DownloadService` (`analyze`, `start_download`, `cancel`,
    `get_progress`) — em testes, um fake/stub é injetado no lugar da
    implementação real.
    """

    def __init__(self, master, download_service) -> None:
        super().__init__(master)

        self.download_service = download_service

        self._media: MediaInfo | None = None
        self._operation_id: UUID | None = None

        self._title_text = ""
        self._uploader_text = ""
        self._thumbnail_text = ""
        self._error_text = ""

        # --- Variáveis vinculadas aos widgets de entrada ---
        self.url_var = tkinter.StringVar(value="")
        self.download_type_var = tkinter.StringVar(value=DownloadType.VIDEO.value)
        self.max_height_var = tkinter.IntVar(value=0)
        self.audio_bitrate_var = tkinter.IntVar(value=0)
        self.destination_var = tkinter.StringVar(value="")

        # Variáveis de exibição dos menus de qualidade/bitrate — traduzidas
        # para `max_height_var`/`audio_bitrate_var` a cada seleção, para que
        # `on_download` continue lendo apenas essas duas variáveis
        # numéricas (compatível com quem define `max_height_var`/
        # `audio_bitrate_var` diretamente, sem passar pelo menu).
        self.quality_display_var = tkinter.StringVar(value=_BEST_QUALITY_LABEL)
        self.bitrate_display_var = tkinter.StringVar(
            value=f"{_AUDIO_BITRATE_OPTIONS[1]} kbps"
        )

        self._build_widgets()

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        # URL + botão "Analisar"
        url_frame = customtkinter.CTkFrame(self)
        url_frame.pack(fill="x", padx=10, pady=(10, 5))

        customtkinter.CTkLabel(url_frame, text="URL:").pack(side="left", padx=(0, 5))
        self.url_entry = customtkinter.CTkEntry(url_frame, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.analyze_button = customtkinter.CTkButton(
            url_frame, text="Analisar", command=self.on_analyze
        )
        self.analyze_button.pack(side="left")

        # Metadados exibidos após a análise
        metadata_frame = customtkinter.CTkFrame(self)
        metadata_frame.pack(fill="x", padx=10, pady=5)

        self.title_label = customtkinter.CTkLabel(metadata_frame, text="")
        self.title_label.pack(fill="x", anchor="w")

        self.uploader_label = customtkinter.CTkLabel(metadata_frame, text="")
        self.uploader_label.pack(fill="x", anchor="w")

        self.thumbnail_label = customtkinter.CTkLabel(metadata_frame, text="")
        self.thumbnail_label.pack(fill="x", anchor="w")

        # Opções de download
        options_frame = customtkinter.CTkFrame(self)
        options_frame.pack(fill="x", padx=10, pady=5)

        customtkinter.CTkLabel(options_frame, text="Tipo:").pack(
            side="left", padx=(0, 5)
        )
        self.download_type_menu = customtkinter.CTkOptionMenu(
            options_frame,
            values=[DownloadType.VIDEO.value, DownloadType.AUDIO.value],
            variable=self.download_type_var,
        )
        self.download_type_menu.pack(side="left", padx=(0, 10))

        customtkinter.CTkLabel(options_frame, text="Qualidade:").pack(
            side="left", padx=(0, 5)
        )
        self.quality_menu = customtkinter.CTkOptionMenu(
            options_frame,
            values=[_BEST_QUALITY_LABEL],
            variable=self.quality_display_var,
            command=self._on_quality_selected,
            width=140,
        )
        self.quality_menu.pack(side="left", padx=(0, 10))

        customtkinter.CTkLabel(options_frame, text="Bitrate de áudio:").pack(
            side="left", padx=(0, 5)
        )
        self.bitrate_menu = customtkinter.CTkOptionMenu(
            options_frame,
            values=[f"{bitrate} kbps" for bitrate in _AUDIO_BITRATE_OPTIONS],
            variable=self.bitrate_display_var,
            command=self._on_bitrate_selected,
            width=120,
        )
        self.bitrate_menu.pack(side="left")

        # Aplica o valor inicial do menu de bitrate a `audio_bitrate_var`,
        # para que um download de áudio disparado sem nenhuma interação
        # prévia com o menu já envie um bitrate válido.
        self._on_bitrate_selected(self.bitrate_display_var.get())

        # Diretório de destino
        destination_frame = customtkinter.CTkFrame(self)
        destination_frame.pack(fill="x", padx=10, pady=5)

        customtkinter.CTkLabel(destination_frame, text="Destino:").pack(
            side="left", padx=(0, 5)
        )
        self.destination_entry = customtkinter.CTkEntry(
            destination_frame, textvariable=self.destination_var
        )
        self.destination_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.browse_button = customtkinter.CTkButton(
            destination_frame, text="Procurar...", width=100, command=self.on_browse
        )
        self.browse_button.pack(side="left")

        # Barra/rótulo de progresso
        self.progress_widget = ProgressWidget(self)
        self.progress_widget.pack(fill="x", padx=10, pady=5)

        # Botões "Baixar"/"Cancelar"/"Ver log"
        actions_frame = customtkinter.CTkFrame(self)
        actions_frame.pack(fill="x", padx=10, pady=5)

        self.download_button = customtkinter.CTkButton(
            actions_frame, text="Baixar", command=self.on_download
        )
        self.download_button.pack(side="left", padx=(0, 10))

        self.cancel_button = customtkinter.CTkButton(
            actions_frame, text="Cancelar", command=self.on_cancel
        )
        self.cancel_button.pack(side="left", padx=(0, 10))

        self.view_log_button = customtkinter.CTkButton(
            actions_frame, text="Ver log", command=self.on_view_log
        )
        self.view_log_button.pack(side="left")

        # Mensagem de erro (multilinha: quebra em vez de cortar o texto)
        self.error_label = customtkinter.CTkLabel(
            self,
            text="",
            text_color="red",
            justify="left",
            anchor="w",
            wraplength=640,
        )
        self.error_label.pack(fill="x", padx=10, pady=(0, 10))

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def on_analyze(self) -> None:
        """Dispara a análise da URL atualmente informada em `url_var`."""
        url = self.url_var.get()
        handle = self.download_service.analyze(
            url, on_complete=self._on_analyze_complete
        )
        self._operation_id = handle.operation_id

    def _on_analyze_complete(self, media: MediaInfo | None, error: str | None) -> None:
        if media is not None:
            self._media = media
            self._title_text = f"Título: {media.title}"
            self._uploader_text = f"Canal: {media.uploader}" if media.uploader else ""
            self._thumbnail_text = (
                f"Thumbnail: {media.thumbnail}" if media.thumbnail else ""
            )

            self.title_label.configure(text=self._title_text)
            self.uploader_label.configure(text=self._uploader_text)
            self.thumbnail_label.configure(text=self._thumbnail_text)

            self._update_quality_options(media)

        if error is not None:
            self._set_error(error)

    def _update_quality_options(self, media: MediaInfo) -> None:
        """Povoa `quality_menu` com as resoluções de vídeo realmente
        disponíveis em `media`, do maior para o menor, mais a opção
        "Melhor disponível" (sem restrição de altura).

        Quando a mídia não possui nenhum formato de vídeo com altura
        conhecida (ex.: mídia só de áudio), o menu mantém apenas a opção
        "Melhor disponível".
        """
        heights = sorted(
            {
                format_info.height
                for format_info in media.formats
                if format_info.has_video and format_info.height
            },
            reverse=True,
        )

        values = [_BEST_QUALITY_LABEL] + [f"{height}p" for height in heights]
        self.quality_menu.configure(values=values)

        self.quality_display_var.set(_BEST_QUALITY_LABEL)
        self.max_height_var.set(0)

    def _on_quality_selected(self, choice: str) -> None:
        """Traduz a opção escolhida no menu de qualidade para
        `max_height_var` (0 significa "sem restrição", igual ao
        comportamento original do campo numérico)."""
        if choice == _BEST_QUALITY_LABEL:
            self.max_height_var.set(0)
            return

        try:
            self.max_height_var.set(int(choice.rstrip("p")))
        except ValueError:
            self.max_height_var.set(0)

    def _on_bitrate_selected(self, choice: str) -> None:
        """Traduz a opção escolhida no menu de bitrate para
        `audio_bitrate_var`."""
        try:
            self.audio_bitrate_var.set(int(choice.split()[0]))
        except (ValueError, IndexError):
            self.audio_bitrate_var.set(_AUDIO_BITRATE_OPTIONS[1])

    def on_browse(self) -> None:
        """Abre o explorador de arquivos nativo para escolher a pasta de
        destino, preenchendo `destination_var` com o caminho escolhido.

        Se o usuário cancelar a seleção, `destination_var` permanece
        inalterada. O campo de texto continua editável normalmente para
        quem preferir colar o caminho manualmente.
        """
        initial_dir = self.destination_var.get() or str(Path.home())

        chosen_directory = filedialog.askdirectory(
            initialdir=initial_dir if Path(initial_dir).is_dir() else str(Path.home()),
            title="Escolher pasta de destino",
        )

        if chosen_directory:
            self.destination_var.set(chosen_directory)

    def on_download(self) -> None:
        """Constrói uma `DownloadOptions` a partir dos campos atuais e
        dispara o download via `DownloadService.start_download`.

        Qualquer falha ao montar a solicitação (ex.: valor inválido em
        `download_type_var`, ou nenhuma mídia ainda analisada em
        `self._media`) é capturada aqui e convertida em uma atualização de
        `error_text` com uma mensagem amigável, nunca propagada como uma
        exceção Python crua para o chamador (Requisito 12.7) — por exemplo,
        para o laço de eventos do Tkinter.
        """
        try:
            if self._media is None:
                self._set_error(
                    "Nenhuma mídia analisada. Analise uma URL antes de baixar."
                )
                return

            download_type = DownloadType(self.download_type_var.get())

            max_height = self.max_height_var.get() or None
            audio_bitrate = self.audio_bitrate_var.get() or None

            options = DownloadOptions(
                url=self.url_var.get(),
                download_type=download_type,
                max_height=max_height if download_type == DownloadType.VIDEO else None,
                audio_bitrate=audio_bitrate
                if download_type == DownloadType.AUDIO
                else None,
                destination=self._destination_path(),
            )

            self._set_error("")

            handle = self.download_service.start_download(
                self._media,
                options,
                on_progress=self._on_progress,
                on_complete=self._on_download_complete,
            )
            self._operation_id = handle.operation_id
        except Exception as exc:  # noqa: BLE001 - nunca propagar exceção crua à GUI
            self._set_error(str(exc).strip() or type(exc).__name__)

    def _destination_path(self):
        destination = self.destination_var.get()
        return Path(destination) if destination else Path(".")

    def _on_progress(self, progress: DownloadProgress) -> None:
        self.progress_widget.update_progress(progress)

    def _on_download_complete(self, result: DownloadResult) -> None:
        if not result.success:
            self._set_error(result.error_message or "")

    def on_cancel(self) -> None:
        """Solicita o cancelamento da operação atualmente rastreada."""
        if self._operation_id is not None:
            self.download_service.cancel(self._operation_id)

    def on_view_log(self) -> None:
        """Abre o arquivo `.txt` com o log completo do processo no
        aplicativo padrão do sistema (Bloco de Notas, por exemplo).

        Qualquer falha (serviço injetado não expõe `get_log_path`, arquivo
        ainda não criado, ausência de aplicativo associado etc.) é
        convertida em uma mensagem amigável via `_set_error`, nunca
        propagada como exceção crua.
        """
        try:
            get_log_path = getattr(self.download_service, "get_log_path", None)
            if get_log_path is None:
                self._set_error("O log do processo não está disponível.")
                return

            log_path = Path(get_log_path())

            if not log_path.is_file():
                self._set_error(f"Ainda não há log registrado em: {log_path}")
                return

            os.startfile(log_path)
        except Exception as exc:  # noqa: BLE001 - nunca propagar exceção crua à GUI
            self._set_error(f"Não foi possível abrir o arquivo de log: {exc}")

    def _set_error(self, message: str) -> None:
        self._error_text = message
        self.error_label.configure(text=self._error_text)

    # ------------------------------------------------------------------
    # Propriedades somente-leitura expostas para os testes/consumo externo
    # ------------------------------------------------------------------
    @property
    def title_text(self) -> str:
        return self._title_text

    @property
    def uploader_text(self) -> str:
        return self._uploader_text

    @property
    def thumbnail_text(self) -> str:
        return self._thumbnail_text

    @property
    def error_text(self) -> str:
        return self._error_text
