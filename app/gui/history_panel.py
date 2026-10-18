"""Painel de histórico de downloads (CustomTkinter).

`HistoryPanel` lista as entradas retornadas por
`HistoryService.list_entries()`, indicando visualmente quando o arquivo
referenciado por uma entrada não existe mais no sistema de arquivos — sem
nunca sinalizar isso como um erro de execução (Requisito 14.3).

Não importa nada de `app.core` (Requisito 12.8): depende apenas de
`app.services` e `app.models`.

A lógica de dados (`refresh()`/`displayed_entries()`) é inteiramente
independente de qualquer widget real do CustomTkinter, para que o painel
possa ser instanciado e exercitado em testes headless (sem `master` e sem
nenhuma janela real), conforme `tests/gui/test_history_panel.py`. Quando
`master` é fornecido, a montagem da UI (lista de entradas) é feita
normalmente, atualizada a cada `refresh()`.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.services.history_service import HistoryService

#: Texto exibido junto a uma entrada cujo arquivo referenciado não existe
#: mais no sistema de arquivos.
MISSING_FILE_TEXT = "Arquivo não encontrado"


class HistoryPanel:
    """Lista as entradas de `HistoryService.list_entries()`.

    `master` é opcional: quando omitido (ou `None`), nenhum widget real do
    CustomTkinter é criado, e apenas a lógica de dados (`refresh`,
    `displayed_entries`) fica disponível — é o modo usado pelos testes,
    que rodam em ambiente headless, sem display.

    Quando `master` é fornecido, a UI (um `CTkFrame` contendo uma linha
    por entrada) é montada e atualizada a cada chamada de `refresh()`.
    """

    def __init__(self, master: Any | None = None, *, history_service: HistoryService) -> None:
        self._master = master
        self._history_service = history_service
        self._entries: list[Any] = []

        self.frame: Any | None = None
        self._row_widgets: list[Any] = []

        if self._master is not None:
            self._build_ui()

    def _build_ui(self) -> None:
        """Monta o container da lista. Importa `customtkinter` apenas aqui,
        para que a classe permaneça utilizável sem essa dependência quando
        `master` não é fornecido (ex.: em testes headless)."""
        import customtkinter

        self.frame = customtkinter.CTkFrame(self._master)
        self.frame.pack(fill="both", expand=True)

    def refresh(self) -> None:
        """Recarrega as entradas a partir de `HistoryService.list_entries()`
        e, se houver widgets reais, redesenha a lista.

        Nunca lança exceção por causa de uma entrada cujo arquivo não
        existe mais: `entry.file_exists` é apenas uma indicação visual.
        """
        self._entries = list(self._history_service.list_entries())

        if self.frame is not None:
            self._render_entries()

    def displayed_entries(self) -> Sequence[Any]:
        """Retorna as entradas carregadas pelo último `refresh()`, na mesma
        ordem retornada por `HistoryService.list_entries()`."""
        return list(self._entries)

    def _render_entries(self) -> None:
        """Redesenha a lista de entradas no `self.frame`, indicando
        visualmente (sem erro) quando `entry.file_exists` é `False`."""
        import customtkinter

        for widget in self._row_widgets:
            widget.destroy()
        self._row_widgets = []

        for entry in self._entries:
            title = entry.title if entry.title is not None else entry.url
            status_text = f"{title} - {entry.status}"
            if not entry.file_exists:
                status_text = f"{status_text} ({MISSING_FILE_TEXT})"

            row = customtkinter.CTkLabel(self.frame, text=status_text)
            row.pack(fill="x", padx=10, pady=2)
            self._row_widgets.append(row)
