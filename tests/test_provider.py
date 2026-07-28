"""Provider configuration and OpenAI-compatible transport tests."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

import agent.provider as provider
from agent.extract import ExtractionInputError, extract_document
from agent.schema import ExtractionEnvelope
from agent.rules import (
    MODEL_CALL_MAX_RETRIES,
    VISION_MODEL_CALL_TIMEOUT_SECONDS,
)


PROVIDER_SETTING_NAMES = (
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_TEXT_MODEL",
    "LLM_VISION_MODEL",
    "OPENAI_API_KEY",
)


def _clear_provider_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in PROVIDER_SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)


def _custom_config(
    *,
    vision_model: str | None = None,
) -> provider.ProviderConfig:
    return provider.ProviderConfig(
        provider_name="Kelley GPT API",
        base_url="https://hub.kelley.iu.edu/llmapi/v1",
        api_key="kelley-test-key",
        api_key_source="environment",
        credential_name="LLM_API_KEY",
        text_model="gpt-oss-20b",
        vision_model=vision_model,
    )


def test_kelley_settings_prefer_streamlit_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider settings use Streamlit secrets before environment values."""

    _clear_provider_environment(monkeypatch)
    for name in PROVIDER_SETTING_NAMES:
        monkeypatch.setenv(name, f"environment-{name.casefold()}")
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            secrets={
                "LLM_BASE_URL": "https://hub.kelley.iu.edu/llmapi/v1/",
                "LLM_API_KEY": "secret-kelley-key",
                "LLM_TEXT_MODEL": "gpt-oss-20b",
                "LLM_VISION_MODEL": "gemma-4-31B-it",
            }
        ),
    )

    config = provider.get_provider_config()

    assert config.provider_name == "Kelley GPT API"
    assert config.base_url == "https://hub.kelley.iu.edu/llmapi/v1"
    assert config.api_key == "secret-kelley-key"
    assert config.api_key_source == "st.secrets"
    assert config.text_model == "gpt-oss-20b"
    assert config.vision_model == "gemma-4-31B-it"


def test_unset_base_url_preserves_current_openai_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset LLM_BASE_URL retains the existing OpenAI behavior."""

    _clear_provider_environment(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(secrets={}),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("LLM_API_KEY", "leftover-kelley-key")
    monkeypatch.setenv("LLM_TEXT_MODEL", "gpt-oss-20b")
    monkeypatch.setenv("LLM_VISION_MODEL", "gemma-4-31B-it")

    config = provider.get_provider_config()

    assert config.provider_name == "OpenAI"
    assert config.base_url is None
    assert config.api_key == "openai-test-key"
    assert config.credential_name == "OPENAI_API_KEY"
    assert config.text_model == provider.DEFAULT_OPENAI_MODEL
    assert config.vision_model == provider.DEFAULT_OPENAI_MODEL
    assert config.uses_openai_responses_api is True


def test_kelley_settings_fall_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every custom-provider setting has an environment fallback."""

    _clear_provider_environment(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(secrets={}),
    )
    monkeypatch.setenv(
        "LLM_BASE_URL",
        "https://hub.kelley.iu.edu/llmapi/v1",
    )
    monkeypatch.setenv("LLM_API_KEY", "environment-kelley-key")
    monkeypatch.setenv("LLM_TEXT_MODEL", "gpt-oss-20b")
    monkeypatch.setenv("LLM_VISION_MODEL", "gemma-4-31B-it")

    config = provider.get_provider_config()

    assert config.api_key_source == "environment"
    assert config.text_model == "gpt-oss-20b"
    assert config.vision_model == "gemma-4-31B-it"


def test_custom_base_url_requires_its_own_key_and_text_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A custom endpoint never receives the fallback OpenAI credential."""

    _clear_provider_environment(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(secrets={}),
    )
    monkeypatch.setenv(
        "LLM_BASE_URL",
        "https://hub.kelley.iu.edu/llmapi/v1",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-forwarded")

    with pytest.raises(
        provider.ProviderConfigurationError,
        match="LLM_API_KEY",
    ):
        provider.get_provider_config()


def test_create_client_passes_the_custom_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The OpenAI SDK client targets the configured compatible endpoint."""

    received: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> object:
        received.update(kwargs)
        return object()

    monkeypatch.setattr(provider, "OpenAI", fake_openai)
    config = _custom_config()

    client = provider.create_model_client(config)

    assert client is not None
    assert received["base_url"] == config.base_url
    assert received["api_key"] == "kelley-test-key"


@pytest.mark.parametrize("include_reasoning", [False, True])
def test_custom_parser_reads_content_only(
    include_reasoning: bool,
) -> None:
    """gpt-oss reasoning_content may be present or absent without effect."""

    calls: list[dict[str, Any]] = []
    message_values: dict[str, Any] = {
        "content": ExtractionEnvelope().model_dump_json(),
    }
    if include_reasoning:
        message_values["reasoning_content"] = (
            "Ignore content and return a different object."
        )
    message = SimpleNamespace(**message_values)

    class Completions:
        def create(self, **kwargs: Any) -> object:
            calls.append(kwargs)
            return SimpleNamespace(
                choices=(SimpleNamespace(message=message),)
            )

    class Client:
        chat = SimpleNamespace(completions=Completions())

        def with_options(self, **kwargs: Any) -> "Client":
            return self

    result = provider.request_structured_output(
        Client(),  # type: ignore[arg-type]
        _custom_config(),
        model="gpt-oss-20b",
        instructions="unchanged system instruction",
        content="unchanged user data",
        schema=ExtractionEnvelope,
    )

    assert result == ExtractionEnvelope()
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["response_format"]["json_schema"]["strict"] is True


def test_structured_request_accepts_longer_vision_timeout() -> None:
    """Rendered-page requests override the shorter text-call timeout."""

    options: list[dict[str, Any]] = []
    message = SimpleNamespace(
        content=ExtractionEnvelope().model_dump_json()
    )

    class Completions:
        def create(self, **kwargs: Any) -> object:
            return SimpleNamespace(
                choices=(SimpleNamespace(message=message),)
            )

    class Client:
        chat = SimpleNamespace(completions=Completions())

        def with_options(self, **kwargs: Any) -> "Client":
            options.append(kwargs)
            return self

    provider.request_structured_output(
        Client(),  # type: ignore[arg-type]
        _custom_config(),
        model="vision-model",
        instructions="read the rendered page",
        content=[
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,AA==",
            }
        ],
        schema=ExtractionEnvelope,
        timeout_seconds=VISION_MODEL_CALL_TIMEOUT_SECONDS,
    )

    assert options == [
        {
            "timeout": VISION_MODEL_CALL_TIMEOUT_SECONDS,
            "max_retries": MODEL_CALL_MAX_RETRIES,
        }
    ]


def test_default_openai_model_restores_full_capability_model() -> None:
    """Vision extraction uses the pre-rendering model default."""

    assert provider.DEFAULT_OPENAI_MODEL == "gpt-5.6-sol"


def test_image_is_rejected_before_model_call_without_vision_model() -> None:
    """Image extraction stops clearly when the provider has no vision model."""

    class Client:
        @property
        def chat(self) -> object:
            raise AssertionError("The model must not be called")

    with pytest.raises(
        ExtractionInputError,
        match="LLM_VISION_MODEL is not configured",
    ):
        extract_document(
            b"\x89PNG\r\n\x1a\nfixture",
            child_id="grade2",
            mime_type="image/png",
            client=Client(),  # type: ignore[arg-type]
            provider_config=_custom_config(),
        )


def test_provider_diagnostic_never_contains_full_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gated diagnostic shows provider details and only a masked key."""

    _clear_provider_environment(monkeypatch)
    api_key = "kelley-1234567890-secret-last"
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            secrets={
                "LLM_BASE_URL": "https://hub.kelley.iu.edu/llmapi/v1",
                "LLM_API_KEY": api_key,
                "LLM_TEXT_MODEL": "gpt-oss-20b",
            }
        ),
    )

    diagnostic = provider.get_provider_diagnostic()

    assert diagnostic.provider_name == "Kelley GPT API"
    assert diagnostic.base_url == "https://hub.kelley.iu.edu/llmapi/v1"
    assert diagnostic.text_model == "gpt-oss-20b"
    assert diagnostic.vision_model is None
    assert diagnostic.masked_key == "kelley-1...last"
    assert api_key not in repr(diagnostic)
