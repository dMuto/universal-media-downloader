"""Widget de progresso de download (CustomTkinter).

`ProgressWidget` exibe uma barra de progresso e um rótulo de estado,
atualizados a partir de um `DownloadProgress` (`app.models`). Não importa
nada de `app.core` (Requisito 12.8): depende apenas de `app.models` e de
`customtkinter`.

Conforme design.md (seção "`app/gui` (novo)"):
> `ProgressWidget`: barra de progresso + rótulo de estado, atualizado a
> partir de `DownloadProgress`.

**Validates: Requirements 12.5**
"""

from __future__ import annotations

import customtkinter

from app.models import DownloadProgress


class ProgressWidget(customtkinter.CTkFrame):
    """Barra de progresso + rótulo de estado, atualizados a partir de um
    `DownloadProgress`.

    `percentage_text`/`status_text` refletem o último `DownloadProgress`
    aplicado via `update_progress`, antes mesmo de qualquer chamada
    (começam com o estado inicial padrão `DownloadProgress()`).
    """

    def __init__(self, master) -> None:
        super().__init__(master)

        self.progressbar = customtkinter.CTkProgressBar(self)
        self.progressbar.set(0)
        self.progressbar.pack(fill="x", padx=10, pady=(10, 5))

        self.status_label = customtkinter.CTkLabel(self, text="")
        self.status_label.pack(fill="x", padx=10, pady=(0, 10))

        # Aplica o estado inicial padrão (pendente, 0%).
        self.update_progress(DownloadProgress())

    def update_progress(self, progress: DownloadProgress) -> None:
        """Atualiza a barra de progresso e o rótulo de estado a partir de
        `progress`.

        A barra usa uma fração entre 0 e 1 (`CTkProgressBar.set`), por
        isso `progress.percentage` (0-100) é dividido por 100. O rótulo
        de estado combina o status (em minúsculas) com o percentual
        formatado.
        """
        fraction = max(0.0, min(progress.percentage, 100.0)) / 100
        self.progressbar.set(fraction)

        self._percentage_text = f"{progress.percentage:g}%"
        self._status_text = f"{progress.status.value.lower()} - {self._percentage_text}"

        self.status_label.configure(text=self._status_text)

    @property
    def percentage_text(self) -> str:
        """String contendo o percentual do último `DownloadProgress` aplicado
        (ex.: ``"42.5%"``)."""
        return self._percentage_text

    @property
    def status_text(self) -> str:
        """String (em minúsculas) contendo o estado do último
        `DownloadProgress` aplicado (ex.: ``"downloading - 42.5%"``)."""
        return self._status_text
