"""Import-safe structural checks for the Streamlit application."""

from __future__ import annotations

import inspect
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


def test_state_selection_prefills_general_rate_without_overwriting_override() -> None:
    """BR-02: state defaults are editable and exclude local-rate guessing."""

    state: dict[str, object] = {}

    app.initialize_state_tax_prefill(state, "California")
    assert state == {
        "tax_rate_text": "7.25",
        "tax_prefill_state": "California",
    }

    state["tax_rate_text"] = "8.75"
    app.initialize_state_tax_prefill(state, "California")
    assert state["tax_rate_text"] == "8.75"

    app.initialize_state_tax_prefill(state, "Indiana")
    assert state["tax_rate_text"] == "7.0"
    assert app.state_tax_rate_percent("Oregon") == "0.0"


def test_student_and_classroom_fields_preserve_grade_context() -> None:
    """FR-01/FR-05: classrooms retain grade and quantity context."""

    assert app.student_input_errors("", "") == (
        "Enter a student name or nickname.",
        "Enter the student's grade.",
    )
    assert app.student_input_errors("Sam", "Grade 2") == ()
    assert app.GRADE_OPTIONS == (
        "Pre-K",
        "Kindergarten",
        "Grade 1",
        "Grade 2",
        "Grade 3",
        "Grade 4",
        "Grade 5",
        "Grade 6",
        "Grade 7",
        "Grade 8",
        "Grade 9",
        "Grade 10",
        "Grade 11",
        "Grade 12",
    )

    classroom = app._intake_students_from_state(
        {
            "child_label_0": "Ms. Rivera's class",
            "child_grade_0": "Grade 3",
            "entity_type_0": "Classroom",
            "student_count_0": 24,
        },
        1,
    )
    assert classroom[0]["entity_type"] == "classroom"
    assert classroom[0]["grade"] == "Grade 3"
    assert classroom[0]["student_count"] == 24
    structure = DocumentStructureEnvelope(
        sections=(
            DocumentSection(
                section_id="grade-3",
                label="Third Grade",
                grades=("Grade 3",),
            ),
            DocumentSection(
                section_id="grade-4",
                label="Fourth Grade",
                grades=("Grade 4",),
            ),
        )
    )
    assert app.section_picker_default_ids(
        structure,
        classroom[0]["grade"],
    ) == ("grade-3",)


def test_student_and_classroom_display_counters_are_separate_only_in_ui() -> None:
    """FR-01/FR-05: labels count by type while internal IDs stay unique."""

    state = {
        "entity_type_0": "Student",
        "child_label_0": "Maya",
        "child_grade_0": "Grade 2",
        "entity_type_1": "Classroom",
        "child_label_1": "Ms. Rivera",
        "child_grade_1": "Grade 3",
        "student_count_1": 20,
        "entity_type_2": "Student",
        "child_label_2": "Noah",
        "child_grade_2": "Grade 5",
        "entity_type_3": "Classroom",
        "child_label_3": "Mr. Chen",
        "child_grade_3": "Grade 4",
        "student_count_3": 24,
    }

    assert app.intake_entry_display_number(state, 0, "Student") == 1
    assert app.intake_entry_display_number(state, 1, "Classroom") == 1
    assert app.intake_entry_display_number(state, 2, "Student") == 2
    assert app.intake_entry_display_number(state, 3, "Classroom") == 2
    assert tuple(
        entry["child_id"]
        for entry in app._intake_students_from_state(state, 4)
    ) == ("child-1", "child-2", "child-3", "child-4")


def test_removed_intake_entry_returns_blank_when_count_increases() -> None:
    """FR-01: reducing the count deletes rather than hides entry state."""

    state: dict[str, object] = {
        "entity_type_0": "Student",
        "child_label_0": "Maya",
        "child_grade_0": "Grade 2",
        "entity_type_1": "Student",
        "intake_previous_entity_type_1": "Student",
        "child_label_1": "Jesse",
        "student_name_1": "Jesse",
        "child_grade_1": "Grade 5",
        "budget_1": "75.00",
        "list_mode_1": "Paste text",
        "list_paste_1": "2 pencils",
    }

    app.clear_inactive_intake_entries(state, 1)
    app.clear_inactive_intake_entries(state, 2)

    assert state == {
        "entity_type_0": "Student",
        "child_label_0": "Maya",
        "child_grade_0": "Grade 2",
    }
    new_entries = app._intake_students_from_state(state, 2)
    assert new_entries[1]["label"] == ""
    assert new_entries[1]["grade"] == ""
    assert "entity_type_1" not in state


@pytest.mark.parametrize(
    ("previous_type", "new_type"),
    (
        ("Classroom", "Student"),
        ("Student", "Classroom"),
    ),
)
def test_switching_entry_type_clears_previous_fields(
    previous_type: str,
    new_type: str,
) -> None:
    """FR-05: Student and Classroom values never leak across a type change."""

    state: dict[str, object] = {
        "entity_type_0": new_type,
        "intake_previous_entity_type_0": previous_type,
        "child_label_0": "Previous name",
        "student_name_0": "Jesse",
        "teacher_name_0": "Ms. Rivera",
        "child_grade_0": "Grade 3",
        "student_count_0": 20,
        "budget_0": "200.00",
        "list_mode_0": "Paste text",
        "list_paste_0": "2 pencils",
        "navigation_saved::student_name_0": "Jesse",
        "navigation_saved::teacher_name_0": "Ms. Rivera",
        "navigation_saved::child_grade_0": "Grade 3",
        "navigation_saved::budget_0": "200.00",
        "navigation_saved::list_paste_0": "2 pencils",
    }

    changed = app.reset_intake_entry_after_type_change(
        state,
        0,
        new_type,
    )

    assert changed is True
    assert state == {
        "entity_type_0": new_type,
        "intake_previous_entity_type_0": new_type,
    }


def test_backward_intake_navigation_preserves_all_section_values() -> None:
    """FR-01–FR-04: Back reviews prior values instead of resetting them."""

    state: dict[str, object] = {
        "intake_step": 1,
        "child_count": 1,
        "entity_type_0": "Student",
        "intake_previous_entity_type_0": "Student",
        "child_label_0": "Jesse",
        "student_name_0": "Jesse",
        "child_grade_0": "Grade 5",
        "budget_mode_label": "A budget for each student or classroom",
        "budget_0": "85.00",
        "shopping_preference_label": "Lowest landed cost",
        "store_radius_miles": 7.5,
        "fulfillment_label": "Pickup",
        "sales_tax_state": "Indiana",
        "tax_rate_text": "7.0",
        "list_mode_0": "Paste text",
        "list_paste_0": "24 pencils",
        "clear:child-1:pencils:item": "pencils",
    }
    widget_keys = (
        "entity_type_0",
        "student_name_0",
        "child_grade_0",
        "budget_mode_label",
        "budget_0",
        "shopping_preference_label",
        "store_radius_miles",
        "fulfillment_label",
        "sales_tax_state",
        "tax_rate_text",
        "list_mode_0",
        "list_paste_0",
        "clear:child-1:pencils:item",
    )

    app.preserve_navigation_state(state)
    state["intake_step"] = 2
    for key in widget_keys:
        state.pop(key)
    app.preserve_navigation_state(state)
    state["intake_step"] = 1

    assert {key: state[key] for key in widget_keys} == {
        "entity_type_0": "Student",
        "student_name_0": "Jesse",
        "child_grade_0": "Grade 5",
        "budget_mode_label": "A budget for each student or classroom",
        "budget_0": "85.00",
        "shopping_preference_label": "Lowest landed cost",
        "store_radius_miles": 7.5,
        "fulfillment_label": "Pickup",
        "sales_tax_state": "Indiana",
        "tax_rate_text": "7.0",
        "list_mode_0": "Paste text",
        "list_paste_0": "24 pencils",
        "clear:child-1:pencils:item": "pencils",
    }
    restored = app._intake_students_from_state(state, 1)
    assert restored[0]["label"] == "Jesse"
    assert restored[0]["grade"] == "Grade 5"
    assert restored[0]["entity_type"] == "student"


def test_deliberate_removal_clears_saved_navigation_values() -> None:
    """FR-01: navigation snapshots cannot resurrect a removed entry."""

    state: dict[str, object] = {
        "entity_type_1": "Student",
        "student_name_1": "Jesse",
        "child_label_1": "Jesse",
        "child_grade_1": "Grade 5",
        "budget_1": "85.00",
        "list_mode_1": "Paste text",
        "list_paste_1": "24 pencils",
    }
    app.preserve_navigation_state(state)

    app.clear_inactive_intake_entries(state, 1)
    app.preserve_navigation_state(state)

    assert not any(
        key.endswith("_1")
        for key in state
    )


def test_uploaded_list_draft_survives_setup_and_review_navigation() -> None:
    """FR-06: a selected file remains usable after leaving the lists screen."""

    state: dict[str, object] = {
        "shared_list_for_all": False,
        "list_mode_0": "Upload a file",
        "list_upload_0": SimpleNamespace(
            name="grade5.txt",
            getvalue=lambda: b"24 pencils",
        ),
    }
    app._remember_upload_draft(
        state,
        "list_upload_draft_0",
        state["list_upload_0"],
    )
    state.pop("list_upload_0")
    st = SimpleNamespace(session_state=state)

    inputs = app._build_list_inputs(
        st,
        (
            {
                "child_id": "child-1",
                "label": "Jesse",
            },
        ),
    )

    assert len(inputs) == 1
    assert inputs[0].child_id == "child-1"
    assert inputs[0].source == b"24 pencils"
    assert inputs[0].mime_type == "text/plain"


def test_individual_budgets_include_students_and_classrooms() -> None:
    """FR-03/FR-05: every intake entry receives an allocation."""

    students = app._intake_students_from_state(
        {
            "entity_type_0": "Student",
            "child_label_0": "Maya",
            "child_grade_0": "Grade 2",
            "entity_type_1": "Classroom",
            "child_label_1": "Ms. Rivera",
            "child_grade_1": "Grade 3",
            "student_count_1": 20,
        },
        2,
    )

    mode, total, allocations = app._budget_from_intake_state(
        {
            "budget_mode_label": (
                "A budget for each student or classroom"
            ),
            "budget_0": "50.00",
            "budget_1": "250.00",
        },
        students,
    )

    assert mode == "per_child"
    assert total == 30_000
    assert allocations == {
        "child-1": 5_000,
        "child-2": 25_000,
    }
    session = app._pipeline_session(
        {
            "session_id": "mixed-entry-budgets",
            "children": students,
            "budget_total": total,
            "budget_mode": mode,
            "budget_allocations": allocations,
            "shopping_mode": "budget",
            "store_radius_miles": 10.0,
            "allowed_stores": None,
            "fulfillment_pref": "pickup",
            "tax_basis_points": 0,
            "max_stores": None,
        }
    )
    assert session.children == ("child-1", "child-2")
    assert session.budget_total == 30_000
    assert session.budget_allocations == {
        "child-1": 5_000,
        "child-2": 25_000,
    }


def test_budget_step_renders_one_field_for_every_intake_entry() -> None:
    """FR-03/FR-05: mixed entry types produce two visible budget widgets."""

    rendered_fields: list[tuple[str, str]] = []

    class ButtonColumn:
        @staticmethod
        def button(*args: object, **kwargs: object) -> bool:
            del args, kwargs
            return False

    class BudgetStreamlit:
        session_state: dict[str, object] = {
            "child_count": 2,
            "entity_type_0": "Student",
            "child_label_0": "Maya",
            "child_grade_0": "Grade 2",
            "entity_type_1": "Classroom",
            "child_label_1": "Ms. Rivera",
            "child_grade_1": "Grade 3",
            "student_count_1": 20,
            "budget_mode_label": (
                "A budget for each student or classroom"
            ),
            "budget_validation_attempted": False,
        }

        @staticmethod
        def caption(value: str) -> None:
            del value

        @classmethod
        def radio(
            cls,
            label: str,
            options: tuple[str, ...],
            **kwargs: object,
        ) -> str:
            del label, options, kwargs
            return str(cls.session_state["budget_mode_label"])

        @classmethod
        def text_input(
            cls,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del kwargs
            rendered_fields.append((label, key))
            return str(cls.session_state[key])

        @staticmethod
        def info(value: str) -> None:
            del value

        @staticmethod
        def error(value: str) -> None:
            del value

        @staticmethod
        def columns(specification: object) -> tuple[ButtonColumn, ButtonColumn]:
            del specification
            return ButtonColumn(), ButtonColumn()

    app._render_budget_step(BudgetStreamlit())

    assert tuple(key for _, key in rendered_fields) == (
        "budget_0",
        "budget_1",
    )
    assert "Maya budget" in rendered_fields[0][0]
    assert "Ms. Rivera budget" in rendered_fields[1][0]
    assert app.budget_entry_fields(
        app._intake_students_from_state(
            BudgetStreamlit.session_state,
            2,
        )
    ) == (
        (0, "child-1", "Maya", "budget_0"),
        (1, "child-2", "Ms. Rivera", "budget_1"),
    )


def test_no_budget_intake_has_no_ceiling_or_allocations() -> None:
    """No-budget intake stays explicit and is never the default option."""

    students = app._intake_students_from_state(
        {
            "entity_type_0": "Student",
            "child_label_0": "Maya",
            "child_grade_0": "Grade 2",
        },
        1,
    )
    mode, total, allocations = app._budget_from_intake_state(
        {
            "budget_mode_label": "No set budget",
        },
        students,
    )
    budget_source = inspect.getsource(app._render_budget_step)

    assert mode == "none"
    assert total is None
    assert allocations == {}
    assert budget_source.index('"One combined budget"') < (
        budget_source.index(
            "NO_SET_BUDGET_LABEL"
        )
    )


def test_intake_uses_guided_student_language_and_debug_only_demo_mode() -> None:
    """The parent intake hides development controls and internal vocabulary."""

    intake_source = inspect.getsource(app._render_intake)
    diagnostic_source = inspect.getsource(app._render_development_diagnostic)
    student_source = inspect.getsource(app._render_student_step)
    budget_source = inspect.getsource(app._render_budget_step)
    preferences_source = inspect.getsource(app._render_preferences_step)
    main_source = inspect.getsource(app.main)

    assert "if debug_enabled" in intake_source
    assert 'st.session_state["demo_mode"] = False' in intake_source
    assert "Use stable offline demo mode" not in intake_source
    assert "Use stable offline demo mode" in diagnostic_source
    assert 'st.subheader("Students")' not in student_source
    assert "Step 1" not in student_source
    assert "Student name or nickname" in student_source
    assert "Teacher name" in student_source
    assert 'else "Maya"' in student_source
    assert "Ms. Rivera" in student_source
    assert "GRADE_OPTIONS" in student_source
    assert "Select a grade" in student_source
    assert "Who are you adding?" in student_source
    assert "Students in this classroom" in student_source
    assert (
        "Every quantity on the supply list will be multiplied "
        in student_source
    )
    assert (
        "How many students or classrooms are you shopping for?"
        in student_source
    )
    assert student_source.index("Who are you adding?") < (
        student_source.index("text_input")
    )
    assert "index=None" in student_source
    assert student_source.index("if entity_type is None") < (
        student_source.index("text_input")
    )
    assert "Choose Student or Classroom." in student_source
    assert '"Shopping for"' not in student_source
    assert "student_validation_attempted" in student_source
    assert "if validation_attempted" in student_source
    assert "disabled=" not in student_source
    assert "continue_column.button" in student_source
    assert "use_container_width=True" in student_source
    assert 'st.subheader("Budget")' not in budget_source
    assert "Step 2" not in budget_source
    assert "A budget for each student or classroom" in budget_source
    assert "NO_SET_BUDGET_LABEL" in budget_source
    assert app.NO_SET_BUDGET_LABEL == "No set budget"
    assert "budget_validation_attempted" in budget_source
    assert "disabled=" not in budget_source
    assert "forward.button" in budget_source
    assert "use_container_width=True" in budget_source
    assert 'st.subheader("Shopping preferences")' not in preferences_source
    assert "Step 3" not in preferences_source
    assert '"Shopping preferences"' in preferences_source
    assert "Advanced shopping and tax options" in preferences_source
    assert "preferences_validation_attempted" in preferences_source
    assert "disabled=" not in preferences_source
    assert "forward.button" in preferences_source
    assert "use_container_width=True" in preferences_source
    assert "Shopping mode" not in preferences_source
    assert "_navigation_button_columns(st)" in student_source
    assert "_navigation_button_columns(st)" in budget_source
    assert "_navigation_button_columns(st)" in preferences_source
    assert 'back.button("Back to students", use_container_width=True)' in (
        budget_source
    )
    assert 'back.button("Back to budget", use_container_width=True)' in (
        preferences_source
    )
    assert main_source.index(
        "preserve_navigation_state(st.session_state)"
    ) < main_source.index("_initialize_state(st)")


def test_navigation_button_columns_are_equal_width() -> None:
    """Paired navigation actions share the same amount of horizontal space."""

    first = object()
    second = object()

    class FakeStreamlit:
        @staticmethod
        def columns(specification: object) -> tuple[object, object]:
            assert specification == 2
            return first, second

    assert app._navigation_button_columns(FakeStreamlit()) == (
        first,
        second,
    )
    paired_navigation_renderers = (
        app._render_budget_step,
        app._render_preferences_step,
        app._render_lists,
        app._render_sections,
        app._render_review,
        app._render_summary,
    )
    for renderer in paired_navigation_renderers:
        source = inspect.getsource(renderer)
        assert "_navigation_button_columns(st)" in source
        assert source.count("use_container_width=True") >= 2


def test_visual_system_keeps_notebook_pattern_behind_opaque_cards() -> None:
    """Decorative paper never sits directly behind application body copy."""

    css_source = inspect.getsource(app._apply_custom_css).casefold()

    assert "repeating-linear-gradient" in css_source
    assert "--rss-chalkboard" in css_source
    assert ".block-container" in css_source
    assert "background-color: var(--rss-card)" in css_source
    assert ".rss-stepper" in css_source
    assert '.rss-stepper__item--current' in css_source
    assert '[data-baseweb="input"]' in css_source
    assert "div:has(> input)" in css_source
    assert "border: 1.5px solid" in css_source
    assert "box-shadow: inset" in css_source
    assert "@keyframes rss-card-in" in css_source
    assert "@keyframes rss-fields-in" in css_source
    assert "@keyframes rss-celebrate-in" in css_source
    assert "prefers-reduced-motion: reduce" in css_source
    assert "@media (max-width: 700px)" in css_source
    assert 'button[kind="primary"] *' in css_source
    assert "color: #ffffff !important" in css_source


def test_landing_keeps_context_in_one_collapsed_explainer() -> None:
    """Purpose, process, limitations, and privacy share one compact place."""

    title_source = inspect.getsource(app._render_app_title)
    main_source = inspect.getsource(app.main)
    events: list[tuple[str, object]] = []

    class ExpanderContext:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            return None

    class ExplainerStreamlit:
        @staticmethod
        def expander(label: str, expanded: bool) -> ExpanderContext:
            events.append(("expander", (label, expanded)))
            return ExpanderContext()

        @staticmethod
        def write(value: str) -> None:
            events.append(("write", value))

        @staticmethod
        def markdown(value: str) -> None:
            events.append(("markdown", value))

    app._persistent_notice(ExplainerStreamlit())

    assert app.APP_TAGLINE == "Sorted before the first bell."
    assert "rss-title__ready" in title_source
    assert "rss-title__set" in title_source
    assert "rss-title__school" in title_source
    assert events == [
        ("expander", ("How Ready, Set, School works", False)),
        (
            "write",
            "Ready, Set, School turns a school supply list into a shopping "
            "plan you control.",
        ),
        ("markdown", "**How it works**"),
        (
            "write",
            "Add your students, upload their lists, personalize what goes in "
            "the cart, and get a plan with prices, stores, and totals.",
        ),
        ("markdown", "**What's real and what isn't**"),
        (
            "write",
            "A language model reads the list. Everything after that — "
            "quantities, package sizes, prices, tax, totals — is calculated, "
            "not guessed. The catalog, stores, prices, and distances are "
            "simulated for this demonstration.",
        ),
        ("markdown", "**Your privacy**"),
        (
            "write",
            "We don't store anything about your kids. Close the tab and it's "
            "gone. Checkout is simulated and never asks for payment.",
        ),
    ]
    assert all(
        "tax holidays" not in str(value).casefold()
        for _, value in events
    )
    assert "_render_intake_walkthrough" not in main_source
    assert not hasattr(app, "_render_intake_walkthrough")


def test_decision_log_copy_uses_student_terminology() -> None:
    """Decision explanations shown or exported never expose Child/Entry copy."""

    visible = app._humanize_internal_text(
        "Children share this child entry.",
        (),
        (),
    )

    assert visible == "students share this student."
    assert "child" not in visible.casefold()
    assert "entry" not in visible.casefold()


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


def test_complete_plan_gets_one_nonblocking_celebration() -> None:
    """A complete, within-budget warm plan receives the ready-state moment."""

    result = _real_pipeline_result("Grade 2")
    optimization = result.proposed_cart
    events: list[tuple[str, str]] = []

    class MetricColumn:
        def metric(self, label: str, value: str) -> None:
            events.append((f"metric:{label}", value))

    class HeadlineStreamlit:
        def error(self, value: str) -> None:
            events.append(("error", value))

        def markdown(
            self,
            value: str,
            unsafe_allow_html: bool,
        ) -> None:
            assert unsafe_allow_html is True
            events.append(("markdown", value))

        def header(self, value: str) -> None:
            events.append(("header", value))

        def caption(self, value: str) -> None:
            events.append(("caption", value))

        def columns(self, count: int) -> tuple[MetricColumn, ...]:
            return tuple(MetricColumn() for _ in range(count))

    app._render_summary_headline(
        HeadlineStreamlit(),
        optimization,
        optimization.landed_cost + 100,
        True,
        app.WARM_COPY,
    )

    celebrations = [
        value
        for kind, value in events
        if kind == "markdown" and "rss-plan-ready" in value
    ]
    assert len(celebrations) == 1
    assert "All set — your shopping plan is ready." in celebrations[0]


def test_no_budget_summary_shows_cost_without_budget_comparison() -> None:
    """A no-budget plan never implies that a ceiling was met."""

    result = _real_pipeline_result("Grade 2")
    optimization = replace(
        result.proposed_cart,
        budget_cents=None,
        within_budget=None,
        shortfall_cents=0,
    )
    events: list[tuple[str, str]] = []
    column_counts: list[int] = []

    class MetricColumn:
        def metric(self, label: str, value: str) -> None:
            events.append((f"metric:{label}", value))

    class HeadlineStreamlit:
        def error(self, value: str) -> None:
            events.append(("error", value))

        def markdown(
            self,
            value: str,
            unsafe_allow_html: bool,
        ) -> None:
            assert unsafe_allow_html is True
            events.append(("markdown", value))

        def header(self, value: str) -> None:
            events.append(("header", value))

        def caption(self, value: str) -> None:
            events.append(("caption", value))

        def columns(self, count: int) -> tuple[MetricColumn, ...]:
            column_counts.append(count)
            return tuple(MetricColumn() for _ in range(count))

    app._render_summary_headline(
        HeadlineStreamlit(),
        optimization,
        None,
        True,
        app.WARM_COPY,
    )

    assert column_counts == [2]
    assert ("caption", "No budget comparison selected.") in events
    assert any(kind == "metric:Landed cost" for kind, _ in events)
    assert not any(
        kind in {"metric:Budget remaining", "metric:Budget shortfall"}
        for kind, _ in events
    )
    no_budget_result = replace(
        result,
        session=replace(
            result.session,
            budget_total=None,
            budget_mode="none",
        ),
        proposed_cart=optimization,
    )
    export = app.build_text_summary(
        no_budget_result,
        optimization,
        result.matches,
        (
            Store(
                store_id="S",
                name="Fixture Store",
                distance_miles=1.0,
                pickup_fee=0,
                pickup_minimum=0,
                delivery_fee=0,
                delivery_minimum=0,
                tax_applies=False,
            ),
        ),
        {"child-1": "Maya"},
        {},
        (),
        (),
    )

    assert "BUDGET: NO SET BUDGET" in export
    assert "BUDGET REMAINING" not in export
    assert "BUDGET SHORTFALL" not in export
    assert "lines.append" not in inspect.getsource(app._render_review)


def test_visible_navigation_uses_four_required_stages() -> None:
    """Every internal screen maps to one of the four required stages."""

    intake_sections_source = inspect.getsource(
        app._render_intake_step_progress
    )
    assert app.JOURNEY_STAGES == (
        "Your students",
        "Their lists",
        "Personalize",
        "Your shopping plan",
    )
    assert app.screen_phase_label("intake") == "Your students"
    assert app.screen_phase_label("lists") == "Their lists"
    assert (
        app.screen_phase_label("working", "reading the lists")
        == "Your shopping plan"
    )
    assert app.screen_phase_label("sections") == "Their lists"
    assert app.screen_phase_label("review") == "Personalize"
    assert app.screen_phase_label("approval") == "Your shopping plan"
    assert app.screen_phase_label("summary") == "Your shopping plan"
    assert "st.progress" not in intake_sections_source
    assert "rss-intake-sections" in intake_sections_source

    rendered: list[tuple[str, bool]] = []

    class StepperStreamlit:
        @staticmethod
        def markdown(value: str, unsafe_allow_html: bool) -> None:
            rendered.append((value, unsafe_allow_html))

    app._screen_progress(StepperStreamlit(), "review")

    assert len(rendered) == 1
    assert rendered[0][1] is True
    assert "rss-stepper" in rendered[0][0]
    assert rendered[0][0].count('aria-current="step"') == 1
    assert (
        'rss-stepper__item rss-stepper__item--current" '
        'aria-current="step">Personalize'
    ) in rendered[0][0]


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


def test_review_understanding_leads_with_plain_item_and_quantity() -> None:
    """The comparison row says what was understood without internal fields."""

    item = SupplyItemReview(
        review_id="child-1:pencils",
        req_id="pencils",
        child_id="child-1",
        item_name="pencils",
        required_quantity=24,
        brand="Ticonderoga",
        brand_required=True,
        source_text="48 Ticonderoga sharpened pencils - #2 | 2nd: 24",
        confidence=1.0,
    )

    assert app.review_understanding_text(item) == (
        "24 Ticonderoga pencils, brand required"
    )


def test_review_framing_names_cart_choices_and_uncertainty() -> None:
    """The personalization screen leads with the parent's cart choices."""

    envelope = ExtractionEnvelope(
        document_selection=DocumentSelection(
            selected_section_ids=("grade-2",),
            selected_section_labels=("2nd Grade list",),
        )
    )
    items = (
        SupplyItemReview(
            review_id="child-1:pencils",
            req_id="pencils",
            child_id="child-1",
            item_name="pencils",
            required_quantity=24,
            source_text="24 pencils",
            confidence=1.0,
        ),
        SupplyItemReview(
            review_id="child-1:paper",
            req_id="paper",
            child_id="child-1",
            item_name="notebook_paper",
            required_quantity=1,
            unit="pack",
            source_text="1 pack paper",
            confidence=0.6,
            issue_codes=("low_confidence",),
        ),
        SupplyItemReview(
            review_id="child-1:note",
            req_id="note",
            child_id="child-1",
            item_name="non_purchasable",
            required_quantity=1,
            is_purchasable=False,
            source_text="Label everything",
            confidence=1.0,
        ),
    )

    assert app.review_child_framing(
        "child-1",
        "Grade 2",
        envelope,
        items,
    ) == (
        "2nd Grade list: 1 item is ready for the cart. "
        "Choose how to handle 1 item before moving on."
    )


def test_personalize_screen_keeps_source_beside_cart_choice() -> None:
    """The primary path is compact source, cart choice, and confirmation."""

    source = inspect.getsource(app._render_review)

    assert "data_editor" not in source
    assert "Personalize what goes in your cart" in source
    assert source.index("From the list") < source.index("For your cart")
    assert source.index("For your cart") < source.index("Choose")
    assert "Products and prices come next" in source
    assert "Confirm the readings" not in source
    assert "Notes from the teacher" in source
    assert "Already provided by school" in source


def test_one_uploaded_document_builds_inputs_for_every_child() -> None:
    """A district-wide upload is supplied once and scoped per child later."""

    class Upload:
        name = "district-list.txt"

        @staticmethod
        def getvalue() -> bytes:
            return b"Grade 2: pencils\\nGrade 5: binders"

    st = SimpleNamespace(
        session_state={
            "shared_list_for_all": True,
            "shared_list_mode": "Upload a file",
            "shared_list_upload": Upload(),
        }
    )
    children = (
        {"child_id": "child-1", "label": "Grade 2", "grade": "2"},
        {"child_id": "child-2", "label": "Grade 5", "grade": "5"},
    )

    inputs = app._build_list_inputs(st, children)

    assert tuple(item.child_id for item in inputs) == (
        "child-1",
        "child-2",
    )
    assert inputs[0].source == inputs[1].source
    assert inputs[0].mime_type == inputs[1].mime_type == "text/plain"


def test_shared_document_structure_is_inspected_only_once() -> None:
    """One upload reuses structure while each child keeps a separate choice."""

    source = b"%PDF-shared-fixture"
    inputs = (
        ListInput("child-1", source, "application/pdf"),
        ListInput("child-2", source, "application/pdf"),
    )
    children = (
        {"child_id": "child-1", "label": "Grade 2", "grade": "2"},
        {"child_id": "child-2", "label": "Grade 5", "grade": "5"},
    )
    calls: list[bytes] = []

    def inspector(
        document: bytes,
        *,
        mime_type: str | None,
    ) -> DocumentStructureEnvelope:
        assert mime_type == "application/pdf"
        calls.append(document)
        return DocumentStructureEnvelope(
            sections=(
                DocumentSection(
                    section_id="grade-2",
                    label="Grade 2",
                    grades=("Grade 2",),
                ),
                DocumentSection(
                    section_id="grade-5",
                    label="Grade 5",
                    grades=("Grade 5",),
                ),
            )
        )

    structures, errors = app._inspect_list_inputs(
        inputs,
        children,
        inspector=inspector,
    )

    assert errors == {}
    assert calls == [source]
    assert tuple(structures) == ("child-1", "child-2")
    assert structures["child-1"] is structures["child-2"]


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


def test_student_display_uses_parent_name_not_internal_id() -> None:
    """Parent-facing tables never fall back to raw internal identifiers."""

    labels = {"child-1": "Grade 2"}

    assert app._child_display_label("child-1", labels) == "Grade 2"
    assert app._child_display_label("child-2", labels) == "Unknown student"


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
