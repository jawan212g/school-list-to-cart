"""Import-safe structural checks for the Streamlit application."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

import app
from agent.match import StructuredSuitabilityJudge
from agent.pipeline import ListInput, PipelineResult, PipelineSession, run_pipeline
from agent.schema import ExtractionEnvelope, Requirement
from data.loader import Offer, Store


@dataclass(frozen=True)
class _ParsedResponse:
    output_parsed: object


class _StructuredResponses:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def parse(self, **kwargs: object) -> _ParsedResponse:
        assert kwargs["text_format"] is ExtractionEnvelope
        return _ParsedResponse(output_parsed=self.payload)


class _StructuredExtractionClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.responses = _StructuredResponses(payload)


def _real_pipeline_result(stated_grade: str) -> PipelineResult:
    """Run the actual extraction and pipeline contracts without a model call."""

    payload: dict[str, object] = {
        "stated_grades": [stated_grade],
        "stated_teachers": ["Ms. Rivera"],
        "requirements": [
            {
                "req_id": "pencils",
                "child_id": "model-output",
                "raw_text": "1 pencil",
                "canonical_item": "pencils",
                "quantity": 1,
                "quantity_is_range": False,
                "quantity_max": None,
                "unit_type": "each",
                "brand_lock": None,
                "exclusions": [],
                "is_required": True,
                "is_purchasable": True,
                "requirement_type": "required",
                "attributes": {},
                "extraction_confidence": 1.0,
            }
        ],
        "manual_review_required": False,
        "review_reasons": [],
        "deferred_review_reasons": [],
    }
    store = Store(
        store_id="S",
        name="Fixture Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="PENCIL-ONE",
        store_id="S",
        brand="Generic",
        title="Single Pencil",
        category="pencils",
        pack_size=1,
        unit_price=100,
        pack_price=100,
        stock_qty=5,
        is_returnable=True,
        attributes={},
    )
    return run_pipeline(
        PipelineSession(
            session_id="app-contract",
            children=("child-1",),
            budget_total=1_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        (ListInput(child_id="child-1", source="Grade list"),),
        stores=(store,),
        offers=(offer,),
        model_client=_StructuredExtractionClient(payload),  # type: ignore[arg-type]
        suitability_judge=StructuredSuitabilityJudge(),
    )


def test_money_and_tax_inputs_convert_at_the_interface_boundary() -> None:
    """E-37/BR-02: valid inputs become integer cents and basis points."""

    assert app.money_to_cents("75") == 7_500
    assert app.money_to_cents("$1,234.56") == 123_456
    assert app.tax_percent_to_basis_points("7.0") == 700
    assert app.tax_percent_to_basis_points("7.125") == 713
    assert app.format_money(300) == "$3.00"
    assert app.format_streamlit_money(300) == r"\$3.00"
    assert app.escape_streamlit_dollars(
        r"Adds \$3.00 and $0.20"
    ) == r"Adds \$3.00 and \$0.20"


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.001"])
def test_invalid_budget_input_has_a_clear_validation_error(value: str) -> None:
    """E-37: invalid budgets stop before any pipeline work."""

    with pytest.raises(ValueError, match="Budget|budget"):
        app.money_to_cents(value)


def test_upload_validation_checks_type_size_and_file_signature() -> None:
    """FR-06/E-35: only validated PDF, JPG, PNG, and TXT reach extraction."""

    assert (
        app.validate_uploaded_document("list.pdf", b"%PDF-1.7")
        == "application/pdf"
    )
    assert (
        app.validate_uploaded_document("list.jpg", b"\xff\xd8\xffdata")
        == "image/jpeg"
    )
    assert (
        app.validate_uploaded_document(
            "list.png",
            b"\x89PNG\r\n\x1a\ndata",
        )
        == "image/png"
    )
    assert (
        app.validate_uploaded_document("list.txt", b"2 pencils")
        == "text/plain"
    )
    with pytest.raises(ValueError, match="valid PDF"):
        app.validate_uploaded_document("malware.pdf", b"MZ executable")
    with pytest.raises(ValueError, match="PDF, JPG, PNG, or TXT"):
        app.validate_uploaded_document("list.exe", b"MZ")


def test_radius_table_explains_pickup_scope_and_delivery_exception() -> None:
    """FR-04: intake scope is visible and delivery ignores pickup distance."""

    pickup_store = Store(
        store_id="P",
        name="Pickup Store",
        distance_miles=8.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    online_store = Store(
        store_id="D",
        name="Online Store",
        distance_miles=100.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
        pickup_available=False,
    )

    pickup_rows = app.store_radius_rows(
        [pickup_store, online_store],
        5.0,
        "pickup",
    )
    delivery_rows = app.store_radius_rows(
        [pickup_store, online_store],
        5.0,
        "delivery",
    )

    assert pickup_rows[0]["Pickup trip"] == "Outside radius"
    assert pickup_rows[0]["Current scope"] == "Not included"
    assert pickup_rows[1]["Current scope"] == "Not included"
    assert delivery_rows[0]["Current scope"] == (
        "Included for delivery; radius does not apply"
    )
    assert delivery_rows[1]["Current scope"] == (
        "Included for delivery; radius does not apply"
    )


def test_openai_probe_makes_one_minimal_model_lookup() -> None:
    """Development diagnostic checks the configured model exactly once."""

    calls: list[str] = []

    class Models:
        def retrieve(self, model_name: str) -> object:
            calls.append(model_name)
            return object()

    success, message = app.probe_openai_connection(
        SimpleNamespace(models=Models())
    )

    assert success is True
    assert calls == [app.MODEL_NAME]
    assert app.MODEL_NAME in message


def test_openai_probe_reports_the_exact_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Development diagnostic preserves the exception type and message."""

    class Models:
        def retrieve(self, model_name: str) -> object:
            try:
                raise OSError("DNS lookup failed")
            except OSError as cause:
                raise RuntimeError(
                    f"network blocked for {model_name}"
                ) from cause

    success, message = app.probe_openai_connection(
        SimpleNamespace(models=Models())
    )

    assert success is False
    assert message == (
        f"RuntimeError: network blocked for {app.MODEL_NAME} | "
        "caused by OSError: DNS lookup failed"
    )
    assert "network blocked" in caplog.text
    assert "DNS lookup failed" in caplog.text


def test_development_diagnostic_is_hidden_without_explicit_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployment diagnostics stay off the normal landing page."""

    monkeypatch.delenv(app.DEVELOPMENT_DEBUG_ENV, raising=False)
    assert app.development_diagnostics_enabled(
        SimpleNamespace(query_params={})
    ) is False
    assert app.development_diagnostics_enabled(
        SimpleNamespace(query_params={"debug": "1"})
    ) is True

    monkeypatch.setenv(app.DEVELOPMENT_DEBUG_ENV, "true")
    assert app.development_diagnostics_enabled(
        SimpleNamespace(query_params={})
    ) is True


def test_wrong_list_grade_warns_before_cart_build() -> None:
    """A real extraction result warns on a grade mismatch before cart build."""

    mismatch_result = _real_pipeline_result("Grade 5")
    extraction = mismatch_result.extractions["child-1"]
    children = (
        {
            "child_id": "child-1",
            "label": "Sam",
            "grade": "2",
        },
    )

    warnings = app.detect_list_identity_warnings(
        {"child-1": extraction},
        children,
    )

    assert len(warnings) == 1
    assert warnings[0].message == (
        "This list appears to be for grade 5, but you entered grade 2. "
        "Continue anyway?"
    )
    assert warnings[0].stated_teachers == ("Ms. Rivera",)
    assert type(extraction) is ExtractionEnvelope
    assert tuple(type(extraction).model_fields) == (
        "stated_grades",
        "stated_teachers",
        "requirements",
        "manual_review_required",
        "review_reasons",
        "deferred_review_reasons",
    )

    matching_result = _real_pipeline_result("Grade 2")
    assert app.detect_list_identity_warnings(
        matching_result.extractions,
        children,
    ) == ()


def test_prior_schema_extraction_cannot_crash_identity_check() -> None:
    """A pre-metadata Pydantic session object is upgraded at the boundary."""

    class PriorExtractionEnvelope(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        requirements: tuple[Requirement, ...] = ()
        manual_review_required: bool = False
        review_reasons: tuple[str, ...] = ()
        deferred_review_reasons: tuple[str, ...] = ()

    warnings = app.detect_list_identity_warnings(
        {"child-1": PriorExtractionEnvelope()},
        (
            {
                "child_id": "child-1",
                "label": "Sam",
                "grade": "2",
            },
        ),
    )

    assert warnings == ()


def test_working_screen_renders_grade_warning_from_real_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The post-extraction working screen renders without a schema error."""

    result = _real_pipeline_result("Grade 5")

    def unexpected_build(*args: object, **kwargs: object) -> object:
        raise AssertionError("cart build must wait for mismatch confirmation")

    monkeypatch.setattr(
        app,
        "_run_pipeline_from_cached_extractions",
        unexpected_build,
    )

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {
                "intake": {
                    "children": (
                        {
                            "child_id": "child-1",
                            "label": "Sam",
                            "grade": "2",
                        },
                    )
                },
                "list_inputs": (
                    ListInput(child_id="child-1", source="Grade list"),
                ),
                "extracted_lists": result.extractions,
                "extraction_errors": {},
                "extraction_cache_ready": True,
                "list_identity_confirmed": False,
                "result": None,
                "approval_outcomes": {},
                "screen": "working",
            }
            self.headers: list[str] = []
            self.warnings: list[str] = []
            self.rerun_count = 0

        def __enter__(self) -> FakeStreamlit:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            return None

        def header(self, value: str) -> None:
            self.headers.append(value)

        def write(self, value: str) -> None:
            del value

        def warning(self, value: str) -> None:
            self.warnings.append(value)

        def caption(self, value: str) -> None:
            del value

        def container(self, **kwargs: object) -> FakeStreamlit:
            del kwargs
            return self

        def form(self, name: str) -> FakeStreamlit:
            del name
            return self

        def columns(self, count: int) -> tuple[FakeStreamlit, ...]:
            return tuple(self for _ in range(count))

        def form_submit_button(
            self,
            label: str,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            return False

        def rerun(self) -> None:
            self.rerun_count += 1

    st = FakeStreamlit()

    app._render_working(st)

    assert st.headers == ["Check the list details"]
    assert st.warnings == [
        (
            "Sam: This list appears to be for grade 5, but you entered "
            "grade 2. Continue anyway?"
        )
    ]
    assert st.rerun_count == 0


def test_child_display_uses_parent_label_not_internal_id() -> None:
    """Parent-facing tables never fall back to raw child identifiers."""

    labels = {"child-1": "Grade 2"}

    assert app._child_display_label("child-1", labels) == "Grade 2"
    assert app._child_display_label("child-2", labels) == "Unknown entry"


def test_working_screen_reuses_cached_pipeline_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Widget reruns route the stored result without rebuilding the pipeline."""

    def unexpected_rebuild(*args: object, **kwargs: object) -> object:
        raise AssertionError("pipeline should not be recomputed")

    monkeypatch.setattr(
        app,
        "_run_pipeline_from_cached_extractions",
        unexpected_rebuild,
    )
    result = _real_pipeline_result("Grade 2")

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {
                "intake": {
                    "children": (
                        {
                            "child_id": "child-1",
                            "label": "Grade 2",
                            "grade": "2",
                        },
                    )
                },
                "list_inputs": (
                    ListInput(child_id="child-1", source="Grade list"),
                ),
                "result": result,
                "approval_outcomes": {},
                "screen": "working",
            }
            self.rerun_count = 0

        def rerun(self) -> None:
            self.rerun_count += 1

    st = FakeStreamlit()

    app._render_working(st)

    assert st.session_state["result"] is result
    assert st.session_state["screen"] == "summary"
    assert st.rerun_count == 1
