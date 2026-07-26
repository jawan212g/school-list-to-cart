"""Model-free tests for deterministic extraction security and review gating."""

import logging
import sys
from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

import agent.extract as extraction
from agent.extract import _apply_security_filters
from agent.schema import ExtractionEnvelope, Requirement


def _requirement(
    *,
    req_id: str,
    requirement_type: str,
    confidence: float,
) -> Requirement:
    return Requirement(
        req_id=req_id,
        child_id="model-child",
        raw_text=f"{requirement_type} item",
        canonical_item="tissues",
        quantity=1,
        unit_type="box",
        is_required=requirement_type == "required",
        is_purchasable=True,
        requirement_type=requirement_type,  # type: ignore[arg-type]
        extraction_confidence=confidence,
    )


def test_optional_model_review_flag_is_deferred_by_deterministic_gate() -> None:
    """BR-10: model-proposed add-on review cannot interrupt the base cart."""

    model_output = ExtractionEnvelope(
        requirements=(
            _requirement(
                req_id="donation",
                requirement_type="donation",
                confidence=0.69,
            ),
        ),
        manual_review_required=True,
        review_reasons=("Wish-list packaging is uncertain.",),
    )

    secured = _apply_security_filters(model_output, "child-a")

    assert secured.manual_review_required is False
    assert secured.review_reasons == ()
    assert secured.deferred_review_reasons == (
        "Low-confidence extraction requires review: donation item",
    )


def test_required_low_confidence_review_remains_immediate() -> None:
    """FR-12: required low-confidence extraction still interrupts."""

    model_output = ExtractionEnvelope(
        requirements=(
            _requirement(
                req_id="required",
                requirement_type="required",
                confidence=0.69,
            ),
        ),
    )

    secured = _apply_security_filters(model_output, "child-a")

    assert secured.manual_review_required is True
    assert secured.review_reasons == (
        "Low-confidence extraction requires review: required item",
    )
    assert secured.deferred_review_reasons == ()


def _status_error(
    error_type: type[AuthenticationError]
    | type[RateLimitError]
    | type[BadRequestError],
    status_code: int,
    message: str,
) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request)
    return error_type(message, response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            _status_error(
                AuthenticationError,
                401,
                "underlying-auth",
            ),
            "OpenAI authentication failed",
        ),
        (
            _status_error(
                RateLimitError,
                429,
                "underlying-rate-limit",
            ),
            "rate limit or quota was reached",
        ),
        (
            APIConnectionError(
                message="underlying-connection",
                request=httpx.Request(
                    "POST",
                    "https://api.openai.com/v1/responses",
                ),
            ),
            "Streamlit Cloud could not connect to OpenAI",
        ),
        (
            _status_error(
                BadRequestError,
                400,
                "underlying-bad-request",
            ),
            "OpenAI rejected the extraction request",
        ),
    ],
)
def test_openai_failures_are_logged_and_become_actionable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_message: str,
) -> None:
    """FR-07: service failures retain logs and expose useful next actions."""

    def fail_call(*args: object, **kwargs: object) -> ExtractionEnvelope:
        raise error

    monkeypatch.setattr(extraction, "_call_model", fail_call)
    with caplog.at_level(logging.ERROR, logger="agent.extract"):
        with pytest.raises(
            extraction.ExtractionServiceError,
            match=expected_message,
        ):
            extraction._call_model_with_service_errors(  # type: ignore[arg-type]
                object(),
                [],
                False,
            )

    assert str(error) in caplog.text


def test_api_key_diagnostic_masks_secret_and_reports_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-2: diagnostics reveal only a partial key and its source."""

    secret_key = "sk-live-1234567890abcdefghijklmnopwxyz"
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key-not-selected")
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(secrets={"OPENAI_API_KEY": secret_key}),
    )

    diagnostic = extraction.get_api_key_diagnostic()

    assert diagnostic.found is True
    assert diagnostic.source == "st.secrets"
    assert diagnostic.masked_key == "sk-live-...wxyz"
    assert secret_key not in diagnostic.masked_key


def test_api_key_diagnostic_reports_environment_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-2: environment fallback is distinguished from Streamlit secrets."""

    environment_key = "env-key-1234567890abcdefghijklmnoplast"
    monkeypatch.setenv("OPENAI_API_KEY", environment_key)
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(secrets={}),
    )

    diagnostic = extraction.get_api_key_diagnostic()

    assert diagnostic.found is True
    assert diagnostic.source == "environment"
    assert diagnostic.masked_key == "env-key-...last"
    assert environment_key not in diagnostic.masked_key
