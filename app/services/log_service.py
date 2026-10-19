from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path

_APP_DIR_NAME = "UniversalMediaDownloader"
_LOG_FILE_NAME = "log.txt"


def _default_log_path() -> Path:
    """Resolve o caminho padrão do arquivo de log para o usuário/SO atual.

    No Windows resolve sob ``%LOCALAPPDATA%``; nos demais, cai para
    ``~/.local/share``. O diretório resultante não é criado aqui — isso só
    acontece quando `write` precisa, de fato, gravar uma linha.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    base_dir = Path(local_appdata) if local_appdata else Path.home() / ".local" / "share"
    return base_dir / _APP_DIR_NAME / _LOG_FILE_NAME


class LogService:
    """Registra o andamento completo das operações (análise, seleção de
    formato, download, merge, conversão para MP3, cancelamento e erros)
    em um arquivo de texto (`.txt`) no diretório de dados do usuário.

    Existe para que uma falha possa ser diagnosticada em detalhe (mensagem
    técnica completa, não apenas o resumo amigável mostrado na GUI) mesmo
    depois que a janela do aplicativo foi fechada. Grava em modo "append":
    cada execução do aplicativo acrescenta ao arquivo existente em vez de
    substituí-lo, preservando o histórico entre sessões.

    Nunca lança exceção: uma falha ao gravar (disco cheio, permissão
    negada, caminho inválido) é silenciosamente ignorada, para que o log
    nunca interrompa o fluxo principal da aplicação. Protegido por um lock
    porque `DownloadService`/`Downloader` podem gravar a partir de
    múltiplas worker threads concorrentes.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = Path(log_path) if log_path is not None else _default_log_path()
        self._lock = threading.Lock()

    @property
    def log_path(self) -> Path:
        """Retorna o caminho resolvido do arquivo de log `.txt`."""
        return self._log_path

    def write(self, message: str) -> None:
        """Acrescenta `message` ao arquivo de log, prefixada com um
        timestamp (`YYYY-MM-DD HH:MM:SS`)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with self._log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(line)
        except OSError:
            pass
