"""Property tests for `app.core.downloader.Downloader._sanitize_filename`."""

from __future__ import annotations

from pathlib import Path

import pytest
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
    assert not any(character in _INVALID_CHARACTERS for character in sanitized)

    # (b) The result is never empty.
    assert sanitized != ""

    # (c) Sanitizing an already-sanitized result produces the same value.
    assert Downloader._sanitize_filename(sanitized) == sanitized


# Strategy mixing path-traversal building blocks (parent-directory
# references, path separators, drive letters) so Hypothesis can assemble
# adversarial path-like inputs beyond the literal examples below.
_path_traversal_strategy = st.text(
    alphabet=st.sampled_from(
        list("..//\\\\::abAB") + ["\\"],
    ),
    min_size=0,
    max_size=40,
)


def _assert_confined_to_destination(sanitized: str, destination: Path) -> None:
    """Assert that joining `sanitized` under `destination` cannot escape it."""
    resolved_destination = destination.resolve()
    joined = (resolved_destination / sanitized).resolve()

    assert joined.is_relative_to(resolved_destination)
    # The sanitized name must also be a single path segment: it cannot
    # itself introduce additional directory levels once joined.
    assert joined.parent == resolved_destination


@pytest.mark.parametrize(
    "malicious_filename",
    [
        "../../etc/passwd",
        "..\\..\\Windows\\System32",
        "../../../../../../etc/shadow",
        "..",
        "../",
        "..\\",
        "....",
        "/etc/passwd",
        "C:\\Windows\\System32\\config",
        "\\\\server\\share\\file",
        "\\\\?\\C:\\Windows\\System32",
        "a/../../b",
        "..foo",
        "foo..",
    ],
)
def test_sanitize_filename_defends_against_path_traversal(
    malicious_filename: str,
    tmp_path: Path,
) -> None:
    """
    **Validates: Requirements 11.1**

    No input — including `..` sequences, absolute POSIX/Windows paths or
    UNC paths — may cause a file to be written outside the destination
    directory once the sanitized name is joined to it.
    """
    sanitized = Downloader._sanitize_filename(malicious_filename)

    assert not any(character in _INVALID_CHARACTERS for character in sanitized)
    assert sanitized != ""

    _assert_confined_to_destination(sanitized, tmp_path)


@settings(max_examples=200)
@given(filename=_path_traversal_strategy)
def test_sanitize_filename_path_traversal_building_blocks_stay_confined(
    filename: str,
) -> None:
    """
    **Validates: Requirements 11.1**

    Property: for any combination of `.`, `/`, `\\`, `:` and letters
    (the building blocks of path-traversal and absolute/UNC paths), the
    sanitized name, once joined with a destination directory, always
    resolves to a path inside that directory.
    """
    # A fixed, non-existent destination is enough here: `Path.resolve()`
    # does not require the path to exist, and no files are written.
    destination = (
        Path("C:/destination") if Path().resolve().drive else Path("/destination")
    )

    sanitized = Downloader._sanitize_filename(filename)

    _assert_confined_to_destination(sanitized, destination)
