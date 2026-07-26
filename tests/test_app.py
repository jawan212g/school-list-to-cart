"""Import-safe structural checks for the Streamlit application."""

from types import SimpleNamespace

import pytest

import app
from agent.gate import ApprovalBatch
from agent.schema import ExtractionEnvelope
from data.loader import Store


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
    """List metadata warns on a grade mismatch without blocking continuation."""

    extraction = ExtractionEnvelope(
        stated_grades=("Grade 5",),
        stated_teachers=("Ms. Rivera",),
    )
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
    assert app.detect_list_identity_warnings(
        {
            "child-1": extraction.model_copy(
                update={"stated_grades": ("Grade 2",)}
            )
        },
        children,
    ) == ()


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
    result = SimpleNamespace(
        extractions={"child-1": ExtractionEnvelope()},
        extraction_failures={},
        approval_batch=ApprovalBatch(interrupts=()),
    )

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {
                "intake": {
                    "children": (
                        {
                            "child_id": "child-1",
                            "label": "Grade 2",
                        },
                    )
                },
                "list_inputs": (
                    SimpleNamespace(child_id="child-1"),
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
