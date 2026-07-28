"""Import-safe structural checks for the Streamlit application."""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

import app
from agent.aggregate import UnitNeed
from agent.match import StructuredSuitabilityJudge
from agent.normalize import NormalizationResult, NormalizedRequirement
from agent.pipeline import ListInput, PipelineResult, PipelineSession, run_pipeline
from agent.schema import (
    DocumentSelection,
    DocumentSection,
    DocumentStructureEnvelope,
    ExtractionEnvelope,
    Requirement,
    SupplyItemReview,
)
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


def test_shortfall_state_renders_the_plain_summary_headings() -> None:
    """A budget shortfall switches the whole summary to the plain register."""

    result = _real_pipeline_result("Grade 2")
    shortfall_cart = replace(
        result.proposed_cart,
        budget_cents=result.proposed_cart.landed_cost - 1,
        within_budget=False,
        shortfall_cents=1,
    )
    result = replace(result, proposed_cart=shortfall_cart)
    tone_state = app.tone_state_from_session(
        {
            "result": result,
            "approved_optimization": None,
            "approval_outcomes": {},
            "budget_action_ids": (),
            "ui_error_active": False,
        }
    )
    copy = app.select_copy_set(tone_state)
    events: list[tuple[str, str]] = []

    class MetricColumn:
        def metric(self, label: str, value: str) -> None:
            events.append((f"metric:{label}", value))

    class HeadlineStreamlit:
        def error(self, value: str) -> None:
            events.append(("error", value))

        def header(self, value: str) -> None:
            events.append(("header", value))

        def caption(self, value: str) -> None:
            events.append(("caption", value))

        def columns(self, count: int) -> tuple[MetricColumn, ...]:
            return tuple(MetricColumn() for _ in range(count))

    app._render_summary_headline(
        HeadlineStreamlit(),
        shortfall_cart,
        shortfall_cart.landed_cost - 1,
        True,
        copy,
    )

    assert copy.register == "plain"
    assert events[0][0] == "error"
    assert ("header", "Shopping plan") in events
    assert ("caption", "Plan status") in events
    assert all(
        "ready" not in value.casefold()
        for kind, value in events
        if kind in {"header", "caption"}
    )


def test_visible_navigation_uses_four_required_stages() -> None:
    """Every internal screen maps to one of the four required stages."""

    assert app.screen_phase_label("intake") == (
        "Stage 1 of 4 · Upload and organize my list"
    )
    assert app.screen_phase_label("lists") == (
        "Stage 1 of 4 · Upload and organize my list"
    )
    assert (
        app.screen_phase_label("working", "reading the lists")
        == "Stage 3 of 4 · reading the lists"
    )
    assert app.screen_phase_label("review") == (
        "Stage 2 of 4 · Review extracted items"
    )
    assert app.screen_phase_label("approval") == (
        "Stage 4 of 4 · Approve final plan"
    )
    assert app.screen_phase_label("summary") == (
        "Stage 4 of 4 · Approve final plan"
    )


def test_resolved_assumptions_do_not_create_a_needs_attention_heading() -> None:
    """A complete plan keeps duplicate assumptions in one collapsed detail row."""

    result = _real_pipeline_result("Grade 2")
    sources = tuple(
        Requirement(
            req_id=f"paper-{index}",
            child_id=child_id,
            raw_text="1 pack notebook paper",
            canonical_item="notebook_paper",
            quantity=1,
            extraction_confidence=1.0,
        )
        for index, child_id in enumerate(
            ("child-1", "child-2"),
            start=1,
        )
    )
    normalized = tuple(
        NormalizedRequirement(
            source=source,
            canonical_item="notebook_paper",
            quantity=150,
            quantity_is_range=False,
            quantity_max=None,
            unit_type="each",
            attributes={},
            assumption_flags=("standard_pack_count_assumed:150",),
            is_cart_eligible=True,
            is_budget_eligible=True,
            is_display_only=False,
            manual_review_required=False,
            review_deferred=False,
        )
        for source in sources
    )
    result = replace(
        result,
        normalization=NormalizationResult(requirements=normalized),
        purchase_needs=(
            UnitNeed(
                canonical_item="notebook_paper",
                quantity=300,
                brand_lock=None,
                unit_type="each",
                exclusions=(),
                is_required=True,
                attributes={},
                allocated_to={"child-1": 150, "child-2": 150},
                source_requirement_ids=tuple(
                    source.req_id for source in sources
                ),
            ),
        ),
    )

    assert app._has_genuine_attention(
        result,
        result.proposed_cart,
        result.matches,
        (),
    ) is False

    tables: list[tuple[dict[str, str], ...]] = []

    class AssumptionStreamlit:
        def write(self, value: str) -> None:
            del value

        def table(self, rows: tuple[dict[str, str], ...]) -> None:
            tables.append(rows)

    app._render_assumptions_and_notes(
        AssumptionStreamlit(),
        result,
        {"child-1": "Grade 2", "child-2": "Grade 5"},
    )

    assert tables == [
        (
            {
                "Item": "Notebook paper",
                "For": "Grade 2 and Grade 5",
                "Assumption": (
                    "Assumed a standard package contains 150 units."
                ),
            },
        )
    ]


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.001"])
def test_invalid_budget_input_has_a_clear_validation_error(value: str) -> None:
    """E-37: invalid budgets stop before any pipeline work."""

    with pytest.raises(ValueError, match="Budget|budget"):
        app.money_to_cents(value)


def test_budget_entry_validation_reports_before_continue() -> None:
    """E-37: the intake can show validation as soon as the field changes."""

    assert app.budget_entry_error("85") is None
    assert app.budget_entry_error("0") == "Budget must be greater than zero."
    assert app.budget_entry_error("abc") == (
        "Enter a budget such as 150 or 75.50."
    )


def test_upload_validation_checks_type_size_and_file_signature() -> None:
    """FR-06/E-35: only validated supported files reach extraction."""

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
    assert app.validate_uploaded_document("list.docx", b"PK\x03\x04") == (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    )
    with pytest.raises(ValueError, match="valid PDF"):
        app.validate_uploaded_document("malware.pdf", b"MZ executable")
    with pytest.raises(ValueError, match="DOCX, PDF, JPG"):
        app.validate_uploaded_document("list.exe", b"MZ")


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("list.pdf", b"%PDF-1.7"),
        ("list.png", b"\x89PNG\r\n\x1a\ndata"),
    ],
)
def test_upload_validation_rejects_visual_input_without_vision_model(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    data: bytes,
) -> None:
    """PDF/image uploads fail early when the provider has no vision model."""

    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            secrets={
                "LLM_BASE_URL": "https://hub.kelley.iu.edu/llmapi/v1",
                "LLM_API_KEY": "test-key",
                "LLM_TEXT_MODEL": "gpt-oss-20b",
            }
        ),
    )
    monkeypatch.delenv("LLM_VISION_MODEL", raising=False)

    with pytest.raises(
        ValueError,
        match="LLM_VISION_MODEL is not configured",
    ):
        app.validate_uploaded_document(filename, data)


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
    assert pickup_rows[0]["Simulated distance"] == "8.0 miles"
    assert pickup_rows[0]["Current scope"] == "Not included"
    assert pickup_rows[1]["Simulated distance"] == "Online only"
    assert pickup_rows[1]["Current scope"] == "Not included"
    assert delivery_rows[0]["Current scope"] == (
        "Included for delivery; radius does not apply"
    )
    assert delivery_rows[1]["Current scope"] == (
        "Included for delivery; radius does not apply"
    )


def test_openai_probe_makes_one_minimal_model_lookup() -> None:
    """Development diagnostic checks the configured model exactly once."""

    calls = 0

    class Models:
        def list(self) -> object:
            nonlocal calls
            calls += 1
            return SimpleNamespace(
                data=(SimpleNamespace(id=app.MODEL_NAME),)
            )

    success, message = app.probe_openai_connection(
        SimpleNamespace(models=Models())
    )

    assert success is True
    assert calls == 1
    assert app.MODEL_NAME in message


def test_connection_probe_uses_configured_provider_models() -> None:
    """The diagnostic checks Kelley text and vision models in one call."""

    calls = 0

    class Models:
        def list(self) -> object:
            nonlocal calls
            calls += 1
            return SimpleNamespace(
                data=(
                    SimpleNamespace(id="gpt-oss-20b"),
                    SimpleNamespace(id="gemma-4-31B-it"),
                )
            )

    config = app.ProviderConfig(
        provider_name="Kelley GPT API",
        base_url="https://hub.kelley.iu.edu/llmapi/v1",
        api_key="test-key",
        api_key_source="environment",
        credential_name="LLM_API_KEY",
        text_model="gpt-oss-20b",
        vision_model="gemma-4-31B-it",
    )
    success, message = app.probe_openai_connection(
        SimpleNamespace(models=Models()),
        config,
    )

    assert success is True
    assert calls == 1
    assert message == (
        "Kelley GPT API connection succeeded. "
        "Text model gpt-oss-20b is available."
    )


def test_openai_probe_reports_the_exact_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Development diagnostic preserves the exception type and message."""

    class Models:
        def list(self) -> object:
            try:
                raise OSError("DNS lookup failed")
            except OSError as cause:
                raise RuntimeError("network blocked for model list") from cause

    success, message = app.probe_openai_connection(
        SimpleNamespace(models=Models())
    )

    assert success is False
    assert message == (
        "RuntimeError: network blocked for model list | "
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
        "document_selection",
        "uninterpreted_lines",
        "skipped_lines",
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
                "structure_cache_ready": True,
                "document_structures": {},
                "document_selections": {},
                "structure_errors": {},
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


def test_review_editor_preserves_scope_provided_and_condition_fields() -> None:
    """Real review models carry parent answers through the app boundary."""

    item = SupplyItemReview(
        review_id="child-1:bags",
        req_id="bags",
        child_id="child-1",
        item_name="zip_top_bags",
        required_quantity=1,
        supply_scope="shared",
        provided_by_school=False,
        condition="Last Name A-G",
        condition_applies=None,
        source_section="Shared supplies",
        source_page=2,
        source_language="English",
        source_text="Ziploc bags — Last Name A-G",
        confidence=0.9,
        review_status="pending",
        issue_codes=("conditional_item",),
    )
    rows = app._review_editor_rows((item,), {"child-1": "Taylor"})
    assert rows[0]["Condition applies"] == "Choose above"
    rows[0]["Confirmed"] = True

    parsed = app._review_items_from_editor(
        rows,
        (item,),
        (
            {
                "child_id": "child-1",
                "label": "Taylor",
                "grade": "2",
            },
        ),
    )
    parsed = app.apply_conditional_answers(
        parsed,
        {"condition:child-1:bags": "no"},
    )

    assert parsed[0].supply_scope == "shared"
    assert parsed[0].condition == "Last Name A-G"
    assert parsed[0].condition_applies is False
    assert parsed[0].is_purchasable is False
    assert parsed[0].source_section == "Shared supplies"
    assert parsed[0].source_page == 2
    assert parsed[0].source_text == "Ziploc bags — Last Name A-G"


def test_grade_section_defaults_and_selection_reach_real_extractor_contract() -> None:
    """FR-06: structure choice happens before and scopes item extraction."""

    structure = DocumentStructureEnvelope(
        layouts=("grade_matrix",),
        sections=(
            DocumentSection(
                section_id="grade-2",
                label="Second Grade",
                grades=("Grade 2",),
                page_numbers=(1,),
                column_label="SECOND GRADE",
            ),
            DocumentSection(
                section_id="grade-5",
                label="Fifth Grade",
                grades=("Grade 5",),
                page_numbers=(2,),
                column_label="FIFTH GRADE",
            ),
        ),
    )
    selection = app.build_document_selection(structure, ("grade-2",))
    received: list[DocumentSelection] = []

    def extractor(
        source: str,
        **kwargs: object,
    ) -> ExtractionEnvelope:
        del source
        received.append(
            kwargs["section_selection"]  # type: ignore[arg-type]
        )
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id="child-1",
                    raw_text="24 pencils | SECOND GRADE: 24",
                    canonical_item="pencils",
                    quantity=24,
                    extraction_confidence=1.0,
                ),
            )
        )

    extractions, errors = app._extract_list_inputs(
        (ListInput(child_id="child-1", source="district list"),),
        extractor=extractor,
        selections={"child-1": selection},
    )

    assert app.section_picker_default_ids(structure, "2") == ("grade-2",)
    assert errors == {}
    assert tuple(extractions) == ("child-1",)
    assert received == [selection]
    assert received[0].selected_page_numbers == (1,)
    assert received[0].selected_column_labels == ("SECOND GRADE",)
    assert received[0].ignored_section_labels == ("Fifth Grade",)


def test_section_picker_uses_only_section_choices_when_details_add_nothing() -> None:
    """A simple grade picker does not render a redundant evidence table."""

    structure = DocumentStructureEnvelope(
        languages=("English",),
        sections=(
            DocumentSection(
                section_id="grade-2",
                label="2nd Grade",
                grades=("2nd Grade",),
                page_numbers=(1,),
                language="English",
            ),
            DocumentSection(
                section_id="grade-5",
                label="5th Grade",
                grades=("5th Grade",),
                page_numbers=(1,),
                language="English",
            ),
        ),
    )

    rows = app.document_section_rows(structure)

    assert rows == (
        {"Section": "2nd Grade"},
        {"Section": "5th Grade"},
    )
    assert app.document_sections_need_table(rows) is False
    assert app._join_names(()) == ""


def test_section_table_is_sparse_and_explains_translated_duplicates() -> None:
    """Only meaningful varying metadata appears in a multilingual table."""

    structure = DocumentStructureEnvelope(
        languages=("English", "Spanish"),
        sections=(
            DocumentSection(
                section_id="grade-2-en",
                label="Grade 2",
                grades=("Grade 2",),
                named_sections=("Individual", "Shared"),
                page_numbers=(1,),
                language="English",
            ),
            DocumentSection(
                section_id="grade-5-en",
                label="Grade 5",
                grades=("Grade 5",),
                page_numbers=(2,),
                language="English",
            ),
            DocumentSection(
                section_id="grade-2-es",
                label="Grade 2",
                grades=("Grade 2",),
                page_numbers=(1,),
                language="Spanish",
                duplicate_of_section_id="grade-2-en",
            ),
        ),
    )

    rows = app.document_section_rows(structure)

    assert app.document_sections_need_table(rows) is True
    assert tuple(rows[0]) == ("Section", "Includes", "Page", "Language")
    assert rows[0] == {
        "Section": "Grade 2",
        "Includes": "Individual and Shared",
        "Page": "1",
        "Language": "English",
    }
    assert rows[1]["Includes"] == ""
    assert rows[2]["Language"] == (
        "Spanish — translated copy of Grade 2"
    )
    assert all("Teacher" not in row for row in rows)
    assert all("Status" not in row for row in rows)
    assert all(
        "the selected entries" not in value
        for row in rows
        for value in row.values()
    )


def test_grade_preselection_handles_ordinals_and_preserves_parent_changes() -> None:
    """The keyed widget starts at the entered grade but remains changeable."""

    structure = DocumentStructureEnvelope(
        sections=(
            DocumentSection(
                section_id="grade-2",
                label="Second Grade",
            ),
            DocumentSection(
                section_id="grade-5",
                label="5th Grade",
            ),
        ),
    )
    state: dict[str, object] = {}
    defaults = app.section_picker_default_ids(structure, "grade 2")

    assert defaults == ("grade-2",)
    assert app.initialize_section_picker_state(
        state,
        "document_sections_child-1",
        defaults,
    )
    assert state["document_sections_child-1"] == ["grade-2"]

    state["document_sections_child-1"] = ["grade-5"]
    assert not app.initialize_section_picker_state(
        state,
        "document_sections_child-1",
        defaults,
    )
    assert state["document_sections_child-1"] == ["grade-5"]


def test_summary_names_read_ignored_and_uninterpreted_source() -> None:
    """Summary evidence states what was read, ignored, and not interpreted."""

    result = _real_pipeline_result("Grade 2")
    extraction = result.extractions["child-1"].model_copy(
        update={
            "document_selection": DocumentSelection(
                selected_section_ids=("grade-2-en",),
                selected_section_labels=("Grade 2 — English",),
                ignored_section_ids=("grade-5", "grade-2-es"),
                ignored_section_labels=(
                    "Grade 5 — English",
                    "Grade 2 — Spanish",
                ),
            ),
            "uninterpreted_lines": (
                "Bring an item for the class project if assigned.",
            ),
            "skipped_lines": (
                "Repeated translation: Grade 2 — Spanish",
            ),
        }
    )
    updated = replace(
        result,
        extractions={"child-1": extraction},
    )

    scope_rows = app.document_scope_rows(
        updated,
        {"child-1": "Taylor"},
    )
    source_rows = app.source_interpretation_rows(
        updated,
        {"child-1": "Taylor"},
    )
    unread_rows = app.uninterpreted_source_rows(
        updated,
        {"child-1": "Taylor"},
    )
    skipped_rows = app.skipped_source_rows(
        updated,
        {"child-1": "Taylor"},
    )

    assert scope_rows == (
        {
            "For": "Taylor",
            "Document section": "Grade 2 — English",
            "Treatment": "Read",
        },
        {
            "For": "Taylor",
            "Document section": "Grade 5 — English",
            "Treatment": "Not read",
        },
        {
            "For": "Taylor",
            "Document section": "Grade 2 — Spanish",
            "Treatment": "Not read",
        },
    )
    assert source_rows[0]["Exact source line"] == "1 pencil"
    assert source_rows[0]["Status"] == "Read for the proposed cart"
    assert unread_rows == (
        {
            "For": "Taylor",
            "Source content": (
                "Bring an item for the class project if assigned."
            ),
            "Treatment": "Could not interpret — not purchased",
        },
    )
    assert skipped_rows == (
        {
            "For": "Taylor",
            "Source content": (
                "Repeated translation: Grade 2 — Spanish"
            ),
            "Treatment": "Deliberately skipped — not purchased",
        },
    )


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
