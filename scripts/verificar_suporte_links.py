"""Script de teste manual (NÃO faz parte do app em produção/GUI).

Lê a lista de URLs de `app/utils/links para teste.txt` e verifica, para
cada uma, se existe um extrator específico do site dentro da própria
biblioteca `yt-dlp` — sem fazer nenhuma requisição de rede, sem analisar
metadados e sem baixar nada. É uma verificação "estática", muito mais
rápida que `testar_links.py`, útil para descobrir rapidamente quais
links nem chegam a ter suporte na lib (antes de gastar tempo tentando
analisar/baixar).

Como funciona:
- O `yt-dlp` mantém uma lista interna de "extratores" (uma classe Python
  por site/grupo de sites suportado, ex. `YoutubeIE`, `TiktokIE`,
  `InstagramIE`). Cada extrator sabe dizer, via `suitable(url)`, se
  reconhece aquele link como "seu", comparando a URL com um padrão
  (regex) — essa comparação é local, não acessa a internet.
- Se pelo menos um extrator *específico* (diferente do extrator
  genérico `Generic`) reconhecer a URL, o link tem suporte dedicado.
- Se somente o extrator `Generic` reconhecer a URL, o yt-dlp vai tentar
  baixar via um mecanismo genérico (procura por tags `<video>`/arquivos
  de mídia na página) — funciona para links diretos de arquivo, mas é
  bem menos confiável para páginas de sites de vídeo.
- Se nenhum extrator reconhecer a URL (raro, já que `Generic` aceita
  qualquer `http(s)://`), o link não tem suporte algum.

Importante: esta verificação NÃO garante que o download vá funcionar de
fato (o site pode ter mudado sua estrutura, exigir login, bloquear por
região, etc.) — ela só confirma se existe código dedicado para aquele
site dentro do yt-dlp instalado. Para a verificação completa (que de
fato tenta analisar e baixar), use `testar_links.py`.

Uso (rodar manualmente, quando quiser, a partir da raiz do repositório):
    python scripts/verificar_suporte_links.py

Este script não é chamado por nenhum outro módulo do app nem é executado
automaticamente — só roda quando você o invoca diretamente.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import yt_dlp.extractor as yt_dlp_extractors

# --- Configuração do teste ---------------------------------------------------

#: Raiz do repositório (este script vive em `scripts/`, um nível abaixo).
_REPO_ROOT = Path(__file__).parent.parent

#: Arquivo com uma URL por linha (linhas vazias ou iniciadas com `#` são
#: ignoradas, então o arquivo pode ser comentado livremente). O mesmo
#: arquivo usado por `testar_links.py`.
LINKS_FILE = _REPO_ROOT / "app" / "utils" / "links para teste.txt"

#: Pasta onde o log desta verificação é salvo.
DOWNLOADS_DIR = _REPO_ROOT / "downloads"

#: Arquivo de log desta verificação (um arquivo novo por execução,
#: identificado pelo timestamp de início).
LOG_FILE = DOWNLOADS_DIR / f"verificacao_suporte_{datetime.now():%Y%m%d_%H%M%S}.txt"

#: Nome do extrator genérico do yt-dlp (usado como fallback para
#: qualquer URL http(s) que nenhum extrator específico reconheça).
_GENERIC_EXTRACTOR_NAME = "generic"


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
    """Lê e retorna as URLs não vazias/não comentadas de `links_file`."""
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


# --- Verificação de suporte ---------------------------------------------------


def _find_matching_extractor_names(url: str) -> list[str]:
    """Retorna os nomes (`IE_NAME`) de todos os extratores do yt-dlp que
    reconhecem `url` como "sua" (via `suitable(url)`), sem fazer nenhuma
    requisição de rede.

    Mais de um extrator pode reconhecer a mesma URL (ex.: um extrator
    específico de playlist e outro de vídeo único do mesmo site); todos
    são retornados, na ordem em que o yt-dlp os expõe.
    """
    matching_names: list[str] = []

    for extractor_class in yt_dlp_extractors.gen_extractor_classes():
        try:
            is_match = extractor_class.suitable(url)
        except Exception:
            # Alguns extratores podem levantar excessões ao avaliar uma
            # URL malformada; tratamos isso como "não reconhecida" em vez
            # de interromper a verificação dos demais extratores.
            continue

        if is_match:
            matching_names.append(extractor_class.IE_NAME)

    return matching_names


def _classify_support(matching_names: list[str]) -> str:
    """Classifica o nível de suporte de uma URL a partir dos nomes de
    extratores que a reconheceram.

    Retorna uma das strings: "especifico", "generico" ou "sem_suporte".
    """
    specific_names = [
        name for name in matching_names if name.lower() != _GENERIC_EXTRACTOR_NAME
    ]

    if specific_names:
        return "especifico"

    if any(name.lower() == _GENERIC_EXTRACTOR_NAME for name in matching_names):
        return "generico"

    return "sem_suporte"


def _check_single_link(url: str, index: int, total: int) -> str:
    """Verifica `url` e registra o resultado no log.

    Retorna a classificação ("especifico", "generico" ou "sem_suporte"),
    usada pelo resumo final.
    """
    matching_names = _find_matching_extractor_names(url)
    classification = _classify_support(matching_names)

    if classification == "especifico":
        specific_names = [
            name for name in matching_names if name.lower() != _GENERIC_EXTRACTOR_NAME
        ]
        _log(
            f"[{index}/{total}] SUPORTE ESPECÍFICO: {url} -> "
            f"extrator(es): {', '.join(specific_names)}"
        )
    elif classification == "generico":
        _log(
            f"[{index}/{total}] SUPORTE GENÉRICO (fallback): {url} -> "
            f"nenhum extrator dedicado reconheceu este link; o yt-dlp vai "
            f"tentar extrair mídia da página de forma genérica, sem "
            f"garantia de sucesso."
        )
    else:
        _log(
            f"[{index}/{total}] SEM SUPORTE: {url} -> nenhum extrator do "
            f"yt-dlp (nem o genérico) reconheceu este link."
        )

    return classification


# --- Execução principal -------------------------------------------------------


def main() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    _log(f"=== Verificação de suporte iniciada. Arquivo de log: {LOG_FILE} ===")
    _log(f"Versão do yt-dlp: {yt_dlp_extractors.__name__}")

    try:
        links = _read_links(LINKS_FILE)
    except FileNotFoundError as exc:
        _log(str(exc))
        sys.exit(1)

    if not links:
        _log(f"Nenhum link encontrado em {LINKS_FILE}.")
        sys.exit(0)

    _log(f"{len(links)} link(s) encontrados em {LINKS_FILE}.")

    specific_links: list[str] = []
    generic_links: list[str] = []
    unsupported_links: list[str] = []

    for index, url in enumerate(links, start=1):
        classification = _check_single_link(url, index, len(links))

        if classification == "especifico":
            specific_links.append(url)
        elif classification == "generico":
            generic_links.append(url)
        else:
            unsupported_links.append(url)

    _log("=== Resumo da verificação ===")
    _log(
        f"Total: {len(links)} | Suporte específico: {len(specific_links)} | "
        f"Suporte genérico (incerto): {len(generic_links)} | "
        f"Sem suporte: {len(unsupported_links)}"
    )

    if specific_links:
        _log("--- Links com SUPORTE ESPECÍFICO (devem funcionar) ---")
        for url in specific_links:
            _log(f"  OK: {url}")

    if generic_links:
        _log("--- Links com SUPORTE GENÉRICO (podem falhar) ---")
        for url in generic_links:
            _log(f"  INCERTO: {url}")

    if unsupported_links:
        _log("--- Links SEM SUPORTE ---")
        for url in unsupported_links:
            _log(f"  SEM SUPORTE: {url}")

    _log(f"=== Verificação de suporte concluída. Log completo em: {LOG_FILE} ===")


if __name__ == "__main__":
    main()
