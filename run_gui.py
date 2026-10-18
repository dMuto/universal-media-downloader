"""Ponto de entrada da GUI (CustomTkinter) do Universal Media Downloader.

Este script é o alvo usado pelo PyInstaller (`media_downloader.spec`) para
gerar o executável Windows: ele apenas constrói `MainWindow` (que, por sua
vez, compõe `DownloadService`/`ConfigService`/`HistoryService` com seus
valores padrão) e inicia o loop de eventos do Tkinter/CustomTkinter.

Requirements: 16.2, 16.3
"""

from __future__ import annotations

from app.gui.main_window import MainWindow


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
