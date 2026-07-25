"""Model-free tests for deterministic extraction security and review gating."""

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
