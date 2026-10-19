"""Script de teste manual (NÃO faz parte do app em produção/GUI).

Lê a lista de URLs de `app/utils/links para teste.txt`, analisa e tenta
baixar cada uma usando o Core do app (`Downloader` + `FormatSelector`),
registrando um log detalhado — sucesso ou falha, com o motivo — tanto no
console quanto em um arquivo `.txt` dentro de `downloads/`, para
identificar quais sites/links são suportados pelo yt-dlp.

Cada link é tratado de forma independente: uma falha de análise, seleção
de formato ou download em um link nunca interrompe o teste dos links
seguintes.

Uso (rodar manualmente, quando quiser):
    python testar_links.py

Este script não é chamado por nenhum outro módulo do app nem é executado
automaticamente — só roda quando você o invoca diretamente.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from app.core.downloader import Downloader, MediaAnalysisError
from app.core.format_selector import FormatSelectionError, FormatSelector
from app.models import DownloadOptions, DownloadType

# --- Configuração do teste ---------------------------------------------------

#: Arquivo com uma URL por linha (linhas vazias ou iniciadas com `#` são
#: ignoradas, então o arquivo pode ser comentado livremente).
LINKS_FILE = Path(__file__).parent / "app" / "utils" / "links para teste.txt"

#: Pasta onde os vídeos baixados com sucesso são salvos.
DOWNLOADS_DIR = Path(__file__).parent / "downloads"

#: Arquivo de log deste teste (um arquivo novo por execução, identificado
#: pelo timestamp de início, para não sobrescrever logs de execuções
#: anteriores).
LOG_FILE = DOWNLOADS_DIR / f"teste_links_{datetime.now():%Y%m%d_%H%M%S}.txt"

#: Altura máxima de vídeo usada no teste, para evitar baixar arquivos
#: muito grandes (4K etc.) quando o objetivo é apenas verificar quais
#: links funcionam. Defina como `None` para sempre usar a melhor
#: qualidade disponível em cada link.
MAX_HEIGHT: int | None = 720


# --- Infraestrutura de log ---------------------------------------------------


def _log(message: str) -> None:
    """Imprime `message` no console e acrescenta ao arquivo de log, com
    timestamp, no formato `[YYYY-MM-DD HH:MM:SS] mensagem`."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")


def _read_links(links_file: Path) -> list[str]:
    """Lê e retorna as URLs não vazias/não comentadas de `links_file`.

    Linhas vazias e linhas iniciadas com `#` são ignoradas, permitindo
    organizar ou comentar o arquivo de teste livremente.
    """
    if not links_file.is_file():
        raise FileNotFoundError(f"Arquivo de links não encontrado: {links_file}")

    raw_lines = links_file.read_text(encoding="utf-8").splitlines()

    links: list[str] = []
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        links.append(line)

    return links


# --- Teste de um único link ---------------------------------------------------


def _test_single_link(
    url: str,
    index: int,
    total: int,
    downloader: Downloader,
    format_selector: FormatSelector,
) -> bool:
    """Analisa e baixa `url`; retorna `True` em caso de sucesso, `False`
    em qualquer tipo de falha.

    Nunca lança exceção: qualquer erro (análise, seleção de formato ou
    download) é capturado e registrado no log, para que o teste sempre
    continue para o próximo link da lista.
    """
    _log(f"[{index}/{total}] Iniciando teste: {url}")
    start_time = time.monotonic()

    try:
        media = downloader.analyze(url)
    except MediaAnalysisError as exc:
        _log(f"[{index}/{total}] FALHA (análise): {url} -> {exc}")
        return False
    except Exception as exc:  # noqa: BLE001 - diagnóstico: nunca interromper o laço
        _log(f"[{index}/{total}] FALHA (análise, erro inesperado): {url} -> {exc}")
        return False

    _log(
        f"[{index}/{total}] Análise OK: {url} -> título={media.title!r}, "
        f"{len(media.formats)} formato(s) encontrado(s)"
    )

    options = DownloadOptions(
        url=url,
        download_type=DownloadType.VIDEO,
        max_height=MAX_HEIGHT,
        destination=DOWNLOADS_DIR,
    )

    try:
        selection = format_selector.select(media, options)
    except FormatSelectionError as exc:
        _log(f"[{index}/{total}] FALHA (seleção de formato): {url} -> {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        _log(
            f"[{index}/{total}] FALHA (seleção de formato, erro inesperado): "
            f"{url} -> {exc}"
        )
        return False

    result = downloader.download(options, selection)
    elapsed = time.monotonic() - start_time

    if result.success:
        _log(
            f"[{index}/{total}] SUCESSO: {url} -> arquivo={result.file_path}, "
            f"tamanho={result.file_size} bytes, tempo={elapsed:.1f}s"
        )
        return True

    _log(
        f"[{index}/{total}] FALHA (download): {url} -> {result.error_message} "
        f"(tempo={elapsed:.1f}s)"
    )
    return False


# --- Execução principal -------------------------------------------------------


def main() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    _log(f"=== Teste de links iniciado. Arquivo de log: {LOG_FILE} ===")

    try:
        links = _read_links(LINKS_FILE)
    except FileNotFoundError as exc:
        _log(str(exc))
        sys.exit(1)

    if not links:
        _log(f"Nenhum link encontrado em {LINKS_FILE}.")
        sys.exit(0)

    _log(f"{len(links)} link(s) encontrados em {LINKS_FILE}.")

    downloader = Downloader()
    format_selector = FormatSelector()

    successes: list[str] = []
    failures: list[str] = []

    for index, url in enumerate(links, start=1):
        succeeded = _test_single_link(
            url, index, len(links), downloader, format_selector
        )
        if succeeded:
            successes.append(url)
        else:
            failures.append(url)

    _log("=== Resumo do teste ===")
    _log(f"Total: {len(links)} | Sucesso: {len(successes)} | Falha: {len(failures)}")

    if successes:
        _log("--- Links com SUCESSO ---")
        for url in successes:
            _log(f"  OK: {url}")

    if failures:
        _log("--- Links com FALHA ---")
        for url in failures:
            _log(f"  FALHOU: {url}")

    _log(f"=== Teste de links concluído. Log completo em: {LOG_FILE} ===")


if __name__ == "__main__":
    main()
