"""Configuration and structured-output transport for model providers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, TypeVar
from urllib.parse import urlparse

from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from agent.rules import MODEL_CALL_MAX_RETRIES, MODEL_CALL_TIMEOUT_SECONDS


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"
KELLEY_HOSTNAME = "hub.kelley.iu.edu"

SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class ProviderConfigurationError(RuntimeError):
    """Raised when the selected model provider is not fully configured."""


class StructuredOutputError(ValueError):
    """Raised when a provider returns no usable structured-output content."""


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved model provider settings with the credential hidden from repr."""

    provider_name: str
    base_url: str | None
    api_key: str = field(repr=False)
    api_key_source: str
    credential_name: str
    text_model: str
    vision_model: str | None

    @property
    def display_base_url(self) -> str:
        """Return the endpoint shown in the development diagnostic."""

        return self.base_url or DEFAULT_OPENAI_BASE_URL

    @property
    def uses_openai_responses_api(self) -> bool:
        """Preserve the existing OpenAI Responses API behavior by default."""

        return self.base_url is None


@dataclass(frozen=True)
class ProviderDiagnostic:
    """Credential-safe provider metadata for the gated development panel."""

    found: bool
    source: str | None
    masked_key: str | None
    credential_name: str
    provider_name: str
    base_url: str
    text_model: str | None
    vision_model: str | None
    configuration_error: str | None = None


def _setting(name: str) -> tuple[str | None, str | None]:
    """Read one setting from Streamlit secrets, then the environment."""

    try:
        import streamlit as st
    except ModuleNotFoundError:
        secret_value = None
    else:
        try:
            secret_value = st.secrets[name]
        except Exception:
            secret_value = None
    if secret_value is not None and str(secret_value).strip():
        return str(secret_value).strip(), "st.secrets"

    environment_value = os.getenv(name)
    if environment_value is not None and environment_value.strip():
        return environment_value.strip(), "environment"
    return None, None


def _provider_name(base_url: str | None) -> str:
    if base_url is None:
        return "OpenAI"
    if urlparse(base_url).hostname == KELLEY_HOSTNAME:
        return "Kelley GPT API"
    return "OpenAI-compatible provider"


def _normalized_base_url(base_url: str | None) -> str | None:
    if base_url is None:
        return None
    return base_url.rstrip("/")


def _mask_api_key(api_key: str) -> str:
    if len(api_key) <= 12:
        return "<configured; too short to preview safely>"
    return f"{api_key[:8]}...{api_key[-4:]}"


def default_openai_config(api_key: str = "<caller-supplied>") -> ProviderConfig:
    """Return the legacy OpenAI request defaults for injected test clients."""

    return ProviderConfig(
        provider_name="OpenAI",
        base_url=None,
        api_key=api_key,
        api_key_source="caller",
        credential_name="OPENAI_API_KEY",
        text_model=DEFAULT_OPENAI_MODEL,
        vision_model=DEFAULT_OPENAI_MODEL,
    )


def get_provider_config() -> ProviderConfig:
    """Resolve provider settings without ever logging or displaying the key."""

    configured_base_url, _ = _setting("LLM_BASE_URL")
    base_url = _normalized_base_url(configured_base_url)
    provider_name = _provider_name(base_url)
    configured_text_model, _ = _setting("LLM_TEXT_MODEL")
    configured_vision_model, _ = _setting("LLM_VISION_MODEL")

    if base_url is not None:
        api_key, api_key_source = _setting("LLM_API_KEY")
        if api_key is None or api_key_source is None:
            raise ProviderConfigurationError(
                "LLM_API_KEY is required when LLM_BASE_URL is configured"
            )
        if configured_text_model is None:
            raise ProviderConfigurationError(
                "LLM_TEXT_MODEL is required when LLM_BASE_URL is configured"
            )
        return ProviderConfig(
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            api_key_source=api_key_source,
            credential_name="LLM_API_KEY",
            text_model=configured_text_model,
            vision_model=configured_vision_model,
        )

    openai_api_key, openai_api_key_source = _setting("OPENAI_API_KEY")
    if openai_api_key is None or openai_api_key_source is None:
        raise ProviderConfigurationError(
            "OPENAI_API_KEY is missing from Streamlit secrets and the "
            "environment"
        )
    return ProviderConfig(
        provider_name=provider_name,
        base_url=None,
        api_key=openai_api_key,
        api_key_source=openai_api_key_source,
        credential_name="OPENAI_API_KEY",
        text_model=DEFAULT_OPENAI_MODEL,
        vision_model=DEFAULT_OPENAI_MODEL,
    )


def get_provider_diagnostic() -> ProviderDiagnostic:
    """Return provider settings with only a deliberately masked credential."""

    base_url, _ = _setting("LLM_BASE_URL")
    normalized_base_url = _normalized_base_url(base_url)
    provider_name = _provider_name(normalized_base_url)
    text_model, _ = _setting("LLM_TEXT_MODEL")
    vision_model, _ = _setting("LLM_VISION_MODEL")
    credential_name = (
        "LLM_API_KEY" if normalized_base_url is not None else "OPENAI_API_KEY"
    )
    if normalized_base_url is None:
        api_key, source = _setting("OPENAI_API_KEY")
        text_model = DEFAULT_OPENAI_MODEL
        vision_model = DEFAULT_OPENAI_MODEL
    else:
        api_key, source = _setting("LLM_API_KEY")

    error: str | None = None
    if api_key is None:
        error = f"{credential_name} is not configured"
    elif normalized_base_url is not None and text_model is None:
        error = "LLM_TEXT_MODEL is not configured"

    return ProviderDiagnostic(
        found=api_key is not None,
        source=source,
        masked_key=_mask_api_key(api_key) if api_key is not None else None,
        credential_name=credential_name,
        provider_name=provider_name,
        base_url=normalized_base_url or DEFAULT_OPENAI_BASE_URL,
        text_model=text_model,
        vision_model=vision_model,
        configuration_error=error,
    )


def create_model_client(
    config: ProviderConfig | None = None,
) -> OpenAI:
    """Create a bounded OpenAI-compatible client for the active provider."""

    active_config = config or get_provider_config()
    options: dict[str, Any] = {
        "api_key": active_config.api_key,
        "timeout": MODEL_CALL_TIMEOUT_SECONDS,
        "max_retries": MODEL_CALL_MAX_RETRIES,
    }
    if active_config.base_url is not None:
        options["base_url"] = active_config.base_url
    return OpenAI(**options)


def configured_model_client(
    client: OpenAI,
    *,
    timeout_seconds: float = MODEL_CALL_TIMEOUT_SECONDS,
) -> OpenAI:
    """Apply the same timeout and retry policy to an injected client."""

    with_options = getattr(client, "with_options", None)
    if not callable(with_options):
        return client
    return with_options(
        timeout=timeout_seconds,
        max_retries=MODEL_CALL_MAX_RETRIES,
    )


def _chat_content(
    content: str | list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    converted: list[dict[str, Any]] = []
    for item in content:
        if item["type"] == "input_text":
            converted.append({"type": "text", "text": item["text"]})
            continue
        if item["type"] == "input_image":
            image_url: dict[str, Any] = {"url": item["image_url"]}
            if "detail" in item:
                image_url["detail"] = item["detail"]
            converted.append(
                {
                    "type": "image_url",
                    "image_url": image_url,
                }
            )
            continue
        raise StructuredOutputError(
            f"Unsupported model content type: {item['type']}"
        )
    return converted


def _parse_chat_content(
    response: Any,
    schema: type[SchemaModel],
) -> SchemaModel:
    """Parse only message.content; reasoning_content is intentionally ignored."""

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError) as error:
        raise StructuredOutputError(
            "The provider returned no assistant message content"
        ) from error
    if not isinstance(content, str) or not content.strip():
        raise StructuredOutputError(
            "The provider returned no assistant message content"
        )
    return schema.model_validate_json(content)


def request_structured_output(
    client: OpenAI,
    config: ProviderConfig,
    *,
    model: str,
    instructions: str,
    content: str | list[dict[str, Any]],
    schema: type[SchemaModel],
    timeout_seconds: float = MODEL_CALL_TIMEOUT_SECONDS,
) -> SchemaModel:
    """Request schema-validated output through the active provider transport."""

    active_client = configured_model_client(
        client,
        timeout_seconds=timeout_seconds,
    )
    if config.uses_openai_responses_api:
        response = active_client.responses.parse(
            model=model,
            instructions=instructions,
            input=(
                [{"role": "user", "content": content}]
                if isinstance(content, list)
                else content
            ),
            text_format=schema,
            reasoning={"effort": "low"},
            store=False,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise StructuredOutputError(
                "The model returned no schema-validated content"
            )
        return schema.model_validate(parsed)

    response = active_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": _chat_content(content)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": to_strict_json_schema(schema),
            },
        },
    )
    return _parse_chat_content(response, schema)
