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


def test_small_model_prompt_requires_calibrated_evidence_only_output() -> None:
    """FR-09/FR-12/FR-13: the prompt addresses observed small-model defects."""

    instruction = extraction.SYSTEM_INSTRUCTION

    assert "1.0 only when" in instruction
    assert "0.65 or lower" in instruction
    assert "Any invented field, lost text, or guessed value" in instruction
    assert "quantity_max=null" in instruction
    assert "no mechanical pencils" in instruction
    assert 'requirement_type="donation"' in instruction
    assert 'neither character="#2" nor size="standard"' in instruction
    assert "never stop or truncate raw_text at a quote" in instruction


def test_raw_text_with_inch_quote_round_trips_without_truncation() -> None:
    """FR-07: quote characters remain intact through schema JSON validation."""

    raw_text = '1 plastic pencil box (approx. 8" — no oversized boxes)'
    requirement = Requirement(
        req_id="pencil-box",
        child_id="grade2",
        raw_text=raw_text,
        canonical_item="pencil_boxes",
        quantity=1,
        exclusions=("oversized boxes",),
        attributes={"material": "plastic", "size": "approx. 8 inches"},
        extraction_confidence=1.0,
    )

    round_tripped = Requirement.model_validate_json(
        requirement.model_dump_json()
    )

    assert round_tripped.raw_text == raw_text


def test_source_line_repairs_model_truncation_at_inch_quote() -> None:
    """FR-07/BR-11: source-proven text repair lowers confidence for review."""

    complete = '1 plastic pencil box (approx. 8" — no oversized boxes)'
    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="pencil-box",
                child_id="grade2",
                raw_text="1 plastic pencil box (approx. 8",
                canonical_item="pencil_boxes",
                quantity=1,
                extraction_confidence=0.9,
            ),
        )
    )

    restored = extraction._restore_complete_raw_text(
        envelope,
        extraction._text_content(complete),
    )

    assert restored.requirements[0].raw_text == complete
    assert restored.requirements[0].extraction_confidence == 0.69


def test_source_line_restores_html_encoded_quote_and_changed_dash() -> None:
    """FR-07: transport-altered punctuation is restored from the source."""

    complete = '1 plastic pencil box (approx. 8" — no oversized boxes)'
    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="pencil-box",
                child_id="grade2",
                raw_text=(
                    "1 plastic pencil box "
                    "(approx. 8&#34; � no oversized boxes)"
                ),
                canonical_item="pencil_boxes",
                quantity=1,
                extraction_confidence=1.0,
            ),
        )
    )

    restored = extraction._restore_complete_raw_text(
        envelope,
        extraction._text_content(complete),
    )

    assert restored.requirements[0].raw_text == complete
    assert restored.requirements[0].extraction_confidence == 0.69


def test_nonempty_document_with_empty_model_result_fails_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-33: a schema-valid empty response cannot silently erase a list."""

    monkeypatch.setattr(
        extraction,
        "_call_model_with_service_errors",
        lambda *args, **kwargs: ExtractionEnvelope(requirements=()),
    )

    with pytest.raises(
        extraction.EmptyExtractionError,
        match="No supply requirements were found",
    ):
        extraction.extract_document(
            "12 pencils",
            child_id="child",
            mime_type="text/plain",
            client=object(),  # type: ignore[arg-type]
        )


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
        stated_grades=("Grade 5",),
        stated_teachers=("Ms. Rivera",),
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
    assert secured.stated_grades == ("Grade 5",)
    assert secured.stated_teachers == ("Ms. Rivera",)


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


def test_txt_input_extracts_readable_content_without_mutation() -> None:
    """FR-06: UTF-8 TXT content reaches the delimited model input."""

    content = extraction._document_content(
        b"2 boxes of tissues\n12 pencils",
        "text/plain",
    )

    assert len(content) == 1
    assert "2 boxes of tissues\n12 pencils" in content[0]["text"]


def test_docx_input_extracts_paragraphs_bullets_and_tables(
    docx_list_bytes: bytes,
) -> None:
    """FR-06: readable DOCX blocks become delimited extraction text."""

    content = extraction._document_content(
        docx_list_bytes,
        (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )
    text = content[0]["text"]

    assert "2 boxes of tissues" in text
    assert "12 pencils" in text
    assert "Item | 4 glue sticks" in text


@pytest.mark.parametrize(
    ("fixture_name", "mime_type", "expected_prefix"),
    [
        ("png_list_bytes", "image/png", "data:image/png;base64,"),
        ("jpeg_list_bytes", "image/jpeg", "data:image/jpeg;base64,"),
    ],
)
def test_repeatable_image_fixtures_build_multimodal_content(
    request: pytest.FixtureRequest,
    fixture_name: str,
    mime_type: str,
    expected_prefix: str,
) -> None:
    """FR-06: stable image fixtures reach the image-capable model path."""

    content = extraction._document_content(
        request.getfixturevalue(fixture_name),
        mime_type,
    )

    assert [block["type"] for block in content] == [
        "input_text",
        "input_image",
        "input_text",
    ]
    assert content[1]["image_url"].startswith(expected_prefix)
