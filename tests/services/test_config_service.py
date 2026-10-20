"""Property tests for `ConfigService`.

These tests target `app/services/config_service.py` and `app/models/config.py`,
which do not exist yet at this stage of the TDD plan (Phase 1 / RED). They are
expected to fail with an `ImportError` until task 11.1 (Phase 2) creates the
`ConfigService` module (and task 4.1 creates `AppConfig`).
"""

import json
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.ffmpeg_service import FFmpegService
from app.models.config import AppConfig
from app.models.download import DownloadType
from app.services.config_service import ConfigService
from app.services.log_service import LogService


def _app_configs() -> st.SearchStrategy[AppConfig]:
    """Build a Hypothesis strategy that generates valid `AppConfig` instances.

    Each field is varied within its documented valid domain.
    """

    destination_names = st.lists(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
            ),
            min_size=1,
            max_size=10,
        ),
        min_size=1,
        max_size=3,
    )

    ffmpeg_path_names = st.one_of(
        st.none(),
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
            min_size=1,
            max_size=10,
        ),
    )

    return st.builds(
        AppConfig,
        default_destination=destination_names.map(
            lambda parts: Path(*parts) if parts else Path("Downloads")
        ),
        default_download_type=st.sampled_from(list(DownloadType)),
        preferred_resolution=st.one_of(st.none(), st.integers(min_value=144, max_value=4320)),
        default_audio_bitrate=st.integers(min_value=32, max_value=320),
        ffmpeg_path=ffmpeg_path_names.map(lambda name: Path(name) if name is not None else None),
        theme=st.sampled_from(["system", "light", "dark"]),
    )


@given(config=_app_configs())
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_config_round_trip(tmp_path: Path, config: AppConfig) -> None:
    """`ConfigService.save` followed by `.load` SHALL return an equal `AppConfig`.

    # Feature: media-downloader-app, Property 15: Round-trip de Configuração e tolerância a corrupção
    Validates: Requirements 13.3, 13.4
    """

    config_path = tmp_path / "config.json"
    service = ConfigService(config_path=config_path)

    service.save(config)
    loaded = service.load()

    assert loaded == config


@given(
    content=st.one_of(
        # Malformed JSON strings.
        st.sampled_from(
            [
                "{",
                "not json at all",
                '{"theme": "dark"',
                "[1, 2, 3",
                "",
            ]
        ),
        # Valid JSON with incorrect types for expected fields.
        st.sampled_from(
            [
                json.dumps({"default_audio_bitrate": "not-an-int"}),
                json.dumps({"preferred_resolution": ["not", "an", "int"]}),
                json.dumps({"theme": 12345}),
                json.dumps([1, 2, 3]),
                json.dumps("just a string"),
                json.dumps(None),
            ]
        ),
        # Arbitrary bytes that may not even be valid UTF-8/JSON.
        st.binary(min_size=0, max_size=50),
    )
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_config_load_tolerates_corruption(tmp_path: Path, content) -> None:
    """`ConfigService.load` SHALL return a default `AppConfig` on invalid content.

    No matter the invalid content found at the configuration path (malformed
    JSON, valid JSON with wrong types, or arbitrary bytes), `load()` SHALL
    return an `AppConfig` with default values instead of raising.

    # Feature: media-downloader-app, Property 15: Round-trip de Configuração e tolerância a corrupção
    Validates: Requirements 13.3, 13.4
    """

    config_path = tmp_path / "config.json"

    if isinstance(content, bytes):
        config_path.write_bytes(content)
    else:
        config_path.write_text(content, encoding="utf-8")

    service = ConfigService(config_path=config_path)

    loaded: AppConfig | None = service.load()

    assert loaded == AppConfig()


def test_config_service_loads_persisted_config(tmp_path: Path) -> None:
    """`ConfigService.load` SHALL return the previously persisted `AppConfig`.

    When a valid configuration file already exists at `config_path`, `load()`
    must reflect the persisted values instead of falling back to defaults.

    Validates: Requirements 13.1
    """

    config_path = tmp_path / "config.json"
    destination = tmp_path / "MyDownloads"

    persisted = {
        "default_destination": str(destination),
        "default_download_type": DownloadType.AUDIO.value,
        "preferred_resolution": 720,
        "default_audio_bitrate": 256,
        "ffmpeg_path": None,
        "theme": "dark",
    }
    config_path.write_text(json.dumps(persisted), encoding="utf-8")

    service = ConfigService(config_path=config_path)
    loaded = service.load()

    assert loaded.default_destination == destination
    assert loaded.default_download_type == DownloadType.AUDIO
    assert loaded.preferred_resolution == 720
    assert loaded.default_audio_bitrate == 256
    assert loaded.ffmpeg_path is None
    assert loaded.theme == "dark"


def test_config_service_returns_defaults_when_no_config_exists(tmp_path: Path) -> None:
    """`ConfigService.load` SHALL return default `AppConfig` when no file exists.

    Validates: Requirements 13.2
    """

    config_path = tmp_path / "nonexistent_config.json"
    assert not config_path.exists()

    service = ConfigService(config_path=config_path)
    loaded = service.load()

    assert loaded == AppConfig()


def test_ffmpeg_service_uses_configured_path_instead_of_system_path(
    tmp_path: Path, monkeypatch
) -> None:
    """`FFmpegService` built with `config.ffmpeg_path` SHALL use that path.

    When an `AppConfig.ffmpeg_path` is set, constructing `FFmpegService` with
    it must use the explicit path rather than searching the system PATH.

    Validates: Requirements 13.5
    """

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_text("fake ffmpeg binary", encoding="utf-8")

    config = AppConfig(ffmpeg_path=fake_ffmpeg)

    def _fail_if_called(name: str) -> None:
        raise AssertionError("shutil.which should not be called when ffmpeg_path is explicit")

    monkeypatch.setattr("shutil.which", _fail_if_called)

    service = FFmpegService(ffmpeg_path=config.ffmpeg_path)

    assert service.executable == config.ffmpeg_path.resolve()


def test_config_load_logs_exception_type_and_path_on_corrupted_file(
    tmp_path: Path,
) -> None:
    """`ConfigService.load` SHALL log the exception type and the affected
    file path when the configuration file cannot be read/parsed, while
    still returning default values instead of raising.

    Validates: Requirements (tarefa 25 - logging em tratamentos de exceção)
    """

    config_path = tmp_path / "config.json"
    config_path.write_text("{not valid json", encoding="utf-8")

    log_path = tmp_path / "log.txt"
    log_service = LogService(log_path=log_path)

    service = ConfigService(config_path=config_path, log_service=log_service)
    loaded = service.load()

    assert loaded == AppConfig()

    log_contents = log_path.read_text(encoding="utf-8")
    assert str(config_path) in log_contents
    assert "JSONDecodeError" in log_contents
