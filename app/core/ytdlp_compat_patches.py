"""Correções locais ("patches") para bugs pontuais de extratores do yt-dlp.

Alguns extratores do yt-dlp (um por site/grupo de sites) têm bugs que só
afetam casos específicos e que, em algum momento, serão corrigidos pelos
mantenedores oficiais do projeto — mas, até lá, impedem o download de
determinados links. Em vez de reescrever o extrator inteiro (trabalho
grande e frágil, como discutido), este módulo aplica correções mínimas e
isoladas em tempo de execução ("monkey patch"), tocando apenas no método
específico que tem o bug, sem alterar os arquivos da biblioteca `yt_dlp`
instalada (que seriam sobrescritos/perdidos na próxima atualização via
`pip install --upgrade yt-dlp`).

Cada patch é:
- Isolado: só afeta a classe do extrator problemático (via atribuição
  direta no `__dict__` da própria classe), nunca a classe-base
  `InfoExtractor` usada pelos ~1700 outros extratores.
- Defensivo: se a estrutura interna do yt-dlp mudar numa atualização
  futura (classe renomeada/removida, método inexistente), o patch
  correspondente é pulado silenciosamente (com um aviso) em vez de
  quebrar a inicialização do aplicativo.
- Idempotente: pode ser chamado mais de uma vez sem efeito colateral
  (reaplicar o mesmo patch não causa problema).

Patches atualmente aplicados:

1. `OdnoklassnikiIE` (ok.ru / odnoklassniki.ru) — "the JSON object must be
   str, bytes or bytearray, not dict".

   Causa raiz (ver `_real_extract`/`_extract_desktop` em
   `yt_dlp/extractor/odnoklassniki.py`): para alguns vídeos, o site
   incorpora os metadados do player (`flashvars['metadata']`) já como um
   dicionário, em vez da string JSON que o extrator sempre espera. O
   extrator chama `self._parse_json(metadata, video_id)`, que internamente
   faz `json.loads(metadata)` — e `json.loads` só aceita `str`/`bytes`/
   `bytearray`, nunca um `dict` já decodificado, daí o erro.

   Correção aplicada: substitui apenas `OdnoklassnikiIE._parse_json` por
   uma versão tolerante, que primeiro verifica se o valor recebido já é
   um `dict`/`list` (ou seja, já está "parseado") e, nesse caso, o
   retorna diretamente, sem tentar decodificá-lo de novo. Quando o valor
   é uma string (o caso normal), o comportamento original de
   `InfoExtractor._parse_json` é usado sem nenhuma alteração.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)

#: Evita reaplicar os patches em chamadas repetidas de
#: `apply_compatibility_patches()` (ex.: múltiplas instâncias de
#: `Downloader` dentro do mesmo processo).
_patches_applied = False


def _patch_odnoklassniki_json_bug() -> None:
    """Corrige `OdnoklassnikiIE` para tolerar `flashvars['metadata']` (e
    qualquer outro campo passado a `_parse_json`) já vindo como `dict`/
    `list` em vez de uma string JSON.

    Ver a explicação completa da causa raiz no docstring do módulo.
    """
    try:
        from yt_dlp.extractor.odnoklassniki import OdnoklassnikiIE
    except ImportError:
        # Estrutura interna do yt-dlp mudou (classe renomeada/removida
        # numa atualização futura); não há o que corrigir, e isso não
        # deve impedir o resto do aplicativo de funcionar.
        _logger.warning(
            "Não foi possível localizar OdnoklassnikiIE para aplicar o "
            "patch de compatibilidade; o bug do ok.ru pode persistir."
        )
        return

    original_parse_json = OdnoklassnikiIE._parse_json

    def _tolerant_parse_json(self, json_string, video_id, *args, **kwargs):
        # Já é um objeto Python decodificado (o bug observado no site):
        # devolve como está, sem tentar `json.loads` de novo.
        if isinstance(json_string, (dict, list)):
            return json_string

        return original_parse_json(self, json_string, video_id, *args, **kwargs)

    OdnoklassnikiIE._parse_json = _tolerant_parse_json


def apply_compatibility_patches() -> None:
    """Aplica todos os patches de compatibilidade conhecidos.

    Seguro para chamar múltiplas vezes (idempotente) e nunca lança
    exceção: uma falha ao aplicar um patch específico é registrada via
    `logging` e não impede os demais patches (nem o restante do
    aplicativo) de continuarem funcionando normalmente.
    """
    global _patches_applied

    if _patches_applied:
        return

    for patch_function in (_patch_odnoklassniki_json_bug,):
        try:
            patch_function()
        except Exception:  # noqa: BLE001 - nunca deixar um patch quebrar o app
            _logger.exception(
                "Falha ao aplicar o patch de compatibilidade %r.",
                patch_function.__name__,
            )

    _patches_applied = True
