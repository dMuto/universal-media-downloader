"""Property tests for `app.core.downloader.Downloader._sanitize_filename`."""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from app.core.downloader import Downloader

_INVALID_CHARACTERS = '<>:"/\\|?*'

# Strategy covering regular text, control characters and the Windows
# invalid filename character set, so sanitization is exercised against a
# wide variety of adversarial inputs.
_filename_strategy = st.one_of(
    st.text(),
    st.text(alphabet=st.characters(max_codepoint=0x1F)),
    st.text(alphabet=_INVALID_CHARACTERS, min_size=0, max_size=20),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
        )
        | st.sampled_from(_INVALID_CHARACTERS),
    ),
)


@settings(max_examples=100)
@given(filename=_filename_strategy)
@example("")
@example(" ")
@example(".")
@example("   ")
@example("...")
@example(" . . ")
@example('<>:"/\\|?*')
def test_sanitize_filename_is_safe_and_idempotent(filename: str) -> None:
    # Feature: media-downloader-app, Property 6: Sanitização de nome de arquivo é segura e idempotente
    sanitized = Downloader._sanitize_filename(filename)

    # (a) The result never contains any Windows-invalid character.
    assert not any(
        character in _INVALID_CHARACTERS for character in sanitized
    )

    # (b) The result is never empty.
    assert sanitized != ""

    # (c) Sanitizing an already-sanitized result produces the same value.
    assert Downloader._sanitize_filename(sanitized) == sanitized
