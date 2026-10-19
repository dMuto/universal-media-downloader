"""Tradução de exceções técnicas internas em mensagens amigáveis.

`translate_error` é uma função pura (sem efeitos colaterais) usada por
`Downloader` e `DownloadService` para compor o `error_message` final de
um `DownloadResult`/callback de erro, cobrindo os casos mais comuns de
falha (link não suportado, vídeo privado/indisponível, falta de
conexão, FFmpeg ausente, permissão de escrita, etc.) com uma frase clara
em português, em vez de repassar a string crua de uma exceção do
yt-dlp/FFmpeg/sistema operacional.

Quando nenhum padrão conhecido é reconhecido, a mensagem original da
exceção é preservada (comportamento idêntico ao anterior) — esta função
nunca torna uma mensagem existente mais confusa, apenas mais clara nos
casos que já conseguimos identificar. O detalhe técnico completo (
inclusive para os casos já traduzidos) continua disponível no arquivo de
log via `LogService` (ver `app/services/log_service.py`), para
diagnóstico.
"""

from __future__ import annotations

# Cada item é (palavras-chave, mensagem amigável). A primeira
# correspondência (busca por substring, sem diferenciar maiúsculas de
# minúsculas) na mensagem da exceção é usada.
_ERROR_PATTERNS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("ffmpeg não foi encontrado", "ffmpeg not found", "ffmpeg não é válido"),
        (
            "FFmpeg não foi encontrado. Instale o FFmpeg ou configure o "
            "caminho correto nas configurações do aplicativo."
        ),
    ),
    (
        ("unsupported url",),
        (
            "Este link não é suportado pelo aplicativo. Verifique se o "
            "endereço está correto."
        ),
    ),
    (
        ("video unavailable", "this video is unavailable", "content isn't available"),
        (
            "Este vídeo não está disponível. Ele pode ter sido removido ou "
            "tornado privado pelo autor."
        ),
    ),
    (
        ("private video", "this video is private"),
        "Este vídeo é privado e não pode ser baixado.",
    ),
    (
        ("members-only", "join this channel"),
        "Este conteúdo é exclusivo para membros do canal e não pode ser baixado.",
    ),
    (
        ("sign in to confirm", "login required", "age-restricted", "confirm your age"),
        (
            "Este conteúdo exige login ou verificação de idade no site de "
            "origem; o download não é possível sem autenticação."
        ),
    ),
    (
        ("http error 404", "404: not found"),
        (
            "O conteúdo não foi encontrado (erro 404). Verifique se o link "
            "ainda está disponível."
        ),
    ),
    (
        ("http error 403", "403: forbidden"),
        (
            "O acesso a este conteúdo foi negado pelo site (erro 403). Ele "
            "pode estar bloqueado para a sua região."
        ),
    ),
    (
        ("http error 429", "too many requests"),
        (
            "O site bloqueou temporariamente novas solicitações por excesso "
            "de downloads. Aguarde alguns minutos e tente novamente."
        ),
    ),
    (
        (
            "name or service not known",
            "failed to resolve",
            "getaddrinfo failed",
            "temporary failure in name resolution",
            "network is unreachable",
        ),
        (
            "Não foi possível conectar à internet. Verifique sua conexão e "
            "tente novamente."
        ),
    ),
    (
        ("connection refused", "connection timed out", "connection reset", "timed out"),
        (
            "A conexão com o servidor falhou ou expirou. Verifique sua "
            "internet e tente novamente."
        ),
    ),
    (
        ("no space left on device",),
        "Não há espaço suficiente em disco para salvar o arquivo.",
    ),
    (
        ("permission denied", "[winerror 5]", "access is denied"),
        (
            "Sem permissão para salvar o arquivo neste local. Escolha outra "
            "pasta de destino."
        ),
    ),
    (
        ("unable to extract", "no video formats found", "no formats found"),
        (
            "Não foi possível extrair informações deste link. O site pode "
            "ter mudado ou o conteúdo não é suportado."
        ),
    ),
)


def translate_error(exc: BaseException, *, default: str | None = None) -> str:
    """Return a user-friendly Portuguese message describing `exc`.

    When a known pattern matches, the friendly message is returned with
    the original technical detail appended in parentheses — this keeps
    the message approachable while still preserving the raw diagnostic
    text (useful for support/debugging, and so existing callers that
    looked for a substring of the raw exception message keep finding it).

    Falls back to `str(exc)` (or `default`/the exception's type name when
    that is empty) when no known pattern matches, so callers never lose a
    non-empty, descriptive message — just like before this helper existed.
    """
    raw_message = str(exc).strip()
    lowered = raw_message.lower()

    for keywords, friendly_message in _ERROR_PATTERNS:
        if any(keyword in lowered for keyword in keywords):
            if raw_message:
                return f"{friendly_message} (detalhe técnico: {raw_message})"
            return friendly_message

    if raw_message:
        return raw_message

    return default or type(exc).__name__
