"""Import-safe structural checks for the Streamlit application."""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

import app
from agent.aggregate import UnitNeed
from agent.match import StructuredSuitabilityJudge
from agent.normalize import NormalizationResult, NormalizedRequirement
from agent.pipeline import ListInput, PipelineResult, PipelineSession, run_pipeline
from agent.requirement_merge import (
    consolidate_extractions,
    consolidate_requirements,
    item_decisions,
    resolve_item_decision_state,
)
from agent.review import (
    confirmed_requirements,
    organize_extractions,
    review_flag_groups,
)
from agent.rules import SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY
from agent.schema import (
    CatalogUnavailableItem,
    DocumentSelection,
    DocumentSection,
    DocumentStructureEnvelope,
    ExtractionEnvelope,
    Requirement,
    RequirementSource,
    SupplyItemReview,
)
from data.loader import Offer, Store, load_catalog


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


def _mark_personalize_review_cache_current(
    state: dict[str, object],
) -> None:
    """Give hand-built review-screen fixtures a production cache fingerprint."""

    extractions = state["extracted_lists"]
    assert isinstance(extractions, dict)
    state[app.PERSONALIZE_REVIEW_SOURCE_FINGERPRINTS_KEY] = (
        app._extraction_envelope_fingerprints(extractions)
    )


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
    assert app.money_to_cents("$85.50") == 8_550
    assert app.money_to_cents("85.50") == 8_550
    assert app.money_to_cents("1,200") == 120_000
    assert app.tax_percent_to_basis_points("7.0") == 700
    assert app.tax_percent_to_basis_points("7.125") == 713
    assert app.format_money(300) == "$3.00"
    assert app.format_streamlit_money(300) == r"\$3.00"
    assert app.escape_streamlit_dollars(
        r"Adds \$3.00 and $0.20"
    ) == r"Adds \$3.00 and \$0.20"


@pytest.mark.parametrize("symbol", ("£", "€", "¥", "¢"))
def test_budget_rejects_non_us_currency_symbols(symbol: str) -> None:
    """E-37: budget entry accepts dollars and names other currencies clearly."""

    with pytest.raises(ValueError, match="Amounts are in US dollars"):
        app.money_to_cents(f"{symbol}85.50")


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


def test_delivery_disables_pickup_radius_and_return_resets_ten_miles() -> None:
    """FR-04: pickup distance is irrelevant for delivery-only shopping."""

    initial_state = SimpleNamespace(session_state={})
    app._initialize_state(initial_state)
    assert initial_state.session_state["store_radius_miles"] == 10.0
    first_render_state: dict[str, object] = {
        "store_radius_miles": 0.0,
        "sales_tax_state": app.DEFAULT_TAX_STATE_OPTION,
        "tax_rate_text": "",
        "tax_prefill_state": app.DEFAULT_TAX_STATE_OPTION,
    }
    app.initialize_preference_defaults(first_render_state)
    assert first_render_state["store_radius_miles"] == 10.0
    assert first_render_state["tax_rate_text"] == "7.0"

    state: dict[str, object] = {
        "store_radius_miles": 4.5,
    }

    assert app.update_pickup_radius_for_fulfillment(
        state,
        "pickup",
    ) is False
    assert state["store_radius_miles"] == 4.5
    assert app.update_pickup_radius_for_fulfillment(
        state,
        "delivery",
    ) is True
    assert state["store_radius_miles"] == 4.5
    assert app.update_pickup_radius_for_fulfillment(
        state,
        "either",
    ) is False
    assert state["store_radius_miles"] == app.DEFAULT_RADIUS_MILES == 10.0
    assert state[
        app.NAVIGATION_STATE_PREFIX + "store_radius_miles"
    ] == 10.0


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
                source_line="THIRD GRADE",
            ),
            DocumentSection(
                section_id="grade-4",
                label="Fourth Grade",
                grades=("Grade 4",),
                source_line="FOURTH GRADE",
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
        "student_grade_0": "Grade 3",
        "classroom_grade_0": "Grade 3",
        "student_count_0": 20,
        "budget_0": "200.00",
        "list_mode_0": "Paste text",
        "list_paste_0": "2 pencils",
        "navigation_saved::student_name_0": "Jesse",
        "navigation_saved::teacher_name_0": "Ms. Rivera",
        "navigation_saved::child_grade_0": "Grade 3",
        "navigation_saved::student_grade_0": "Grade 3",
        "navigation_saved::classroom_grade_0": "Grade 3",
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
    assert "child_grade_0" not in state
    assert "student_grade_0" not in state
    assert "classroom_grade_0" not in state
    assert "navigation_saved::child_grade_0" not in state
    assert "navigation_saved::student_grade_0" not in state
    assert "navigation_saved::classroom_grade_0" not in state


def test_empty_type_change_has_no_discarded_details_notice() -> None:
    """FR-05: untouched defaults are not described as discarded details."""

    empty_state: dict[str, object] = {
        "child_label_1": "",
        "student_name_1": "",
        "teacher_name_1": "",
        "student_grade_1": None,
        "classroom_grade_1": None,
        "student_count_1": 20,
    }

    assert app.entry_type_change_discards_details(empty_state, 1) is False
    empty_state["teacher_name_1"] = "Ms. Rivera"
    assert app.entry_type_change_discards_details(empty_state, 1) is True


def test_intake_widget_defaults_live_outside_streamlit_widget_state() -> None:
    """FR-03/FR-04: widget cleanup cannot delete a displayed default."""

    state: dict[str, object] = {}
    temporary_key = app.mount_intake_widget_value(
        state,
        "combined_budget_text",
        app.DEFAULT_BUDGET_TEXT,
    )
    assert temporary_key == app.intake_widget_key("combined_budget_text")
    assert state["combined_budget_text"] == "75.00"
    assert state[temporary_key] == "75.00"

    state.pop(temporary_key)
    app.mount_intake_widget_value(
        state,
        "combined_budget_text",
        "",
    )
    assert state["combined_budget_text"] == "75.00"
    assert state[temporary_key] == "75.00"


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
        "student_grade_0": "Grade 5",
    }
    student_keys = (
        "entity_type_0",
        "student_name_0",
        "child_grade_0",
        "student_grade_0",
    )

    app.navigate_intake_step(state, 2)
    for key in student_keys:
        state.pop(key)
    app.preserve_navigation_state(state)
    assert state["intake_step"] == 2
    assert state["student_name_0"] == "Jesse"
    assert state["student_grade_0"] == "Grade 5"

    state.update(
        {
            "budget_mode_label": (
                "A budget for each student or classroom"
            ),
            "budget_0": "85.00",
        }
    )
    budget_keys = ("budget_mode_label", "budget_0")
    app.navigate_intake_step(state, 3)
    for key in budget_keys:
        state.pop(key)
    app.preserve_navigation_state(state)
    assert state["intake_step"] == 3
    assert state["budget_mode_label"] == (
        "A budget for each student or classroom"
    )
    assert state["budget_0"] == "85.00"

    state.update(
        {
            "shopping_preference_label": "Lowest total cost",
            "store_radius_miles": 7.5,
            "fulfillment_label": "Best available",
            "sales_tax_state": "Indiana",
            "tax_rate_text": "7.0",
        }
    )
    preference_keys = (
        "shopping_preference_label",
        "store_radius_miles",
        "fulfillment_label",
        "sales_tax_state",
        "tax_rate_text",
    )

    app.navigate_intake_step(state, 2)
    for key in preference_keys:
        state.pop(key)
    app.preserve_navigation_state(state)
    assert state["intake_step"] == 2
    assert state["budget_0"] == "85.00"
    assert state["store_radius_miles"] == 7.5
    assert state["fulfillment_label"] == "Best available"

    app.navigate_intake_step(state, 1)
    for key in budget_keys:
        state.pop(key)
    app.preserve_navigation_state(state)
    assert state["intake_step"] == 1
    assert state["student_name_0"] == "Jesse"
    assert state["student_grade_0"] == "Grade 5"
    assert state["budget_0"] == "85.00"
    assert state["shopping_preference_label"] == "Lowest total cost"
    assert state["store_radius_miles"] == 7.5
    assert state["fulfillment_label"] == "Best available"
    restored = app._intake_students_from_state(state, 1)
    assert restored[0]["label"] == "Jesse"
    assert restored[0]["grade"] == "Grade 5"
    assert restored[0]["entity_type"] == "student"


def test_banner_navigation_preserves_every_completed_stage_value() -> None:
    """FR-01-FR-06: a banner jump changes location and nothing else."""

    list_inputs = (
        ListInput(child_id="child-1", source="24 pencils"),
    )
    state: dict[str, object] = {
        "screen": "summary",
        "intake_step": 3,
        "max_stage_reached": 4,
        "max_intake_step_reached": 3,
        "entity_type_0": "Student",
        "student_name_0": "Maya",
        "child_grade_0": "Grade 2",
        "student_grade_0": "Grade 2",
        "combined_budget_text": "150.00",
        "shopping_preference_label": "Lowest total cost",
        "store_radius_miles": 10.0,
        "fulfillment_label": "Best available",
        "list_inputs": list_inputs,
        "document_selections": {"child-1": object()},
    }
    preserved = {
        key: value
        for key, value in state.items()
        if key not in {"screen", "intake_step"}
    }

    app.navigate_to_journey_stage(state, 1)

    assert state["screen"] == "intake"
    assert state["intake_step"] == 1
    assert {
        key: state[key]
        for key in preserved
    } == preserved
    app.navigate_intake_step(state, 3)
    assert state["intake_step"] == 3
    assert state["student_name_0"] == "Maya"
    assert state["combined_budget_text"] == "150.00"
    assert state["list_inputs"] == list_inputs

    class RerunSignal(Exception):
        pass

    class IntakeSectionColumn:
        def __init__(self, section: int) -> None:
            self.section = section

        def button(self, label: str, **kwargs: object) -> bool:
            del label, kwargs
            return self.section == 1

    class IntakeBannerStreamlit:
        session_state = state

        @staticmethod
        def columns(count: int) -> tuple[IntakeSectionColumn, ...]:
            return tuple(
                IntakeSectionColumn(section)
                for section in range(1, count + 1)
            )

        @staticmethod
        def rerun() -> None:
            raise RerunSignal

    with pytest.raises(RerunSignal):
        app._render_intake_step_progress(IntakeBannerStreamlit(), 3)
    assert state["intake_step"] == 1
    assert state["student_name_0"] == "Maya"
    assert state["combined_budget_text"] == "150.00"
    assert state["list_inputs"] == list_inputs

    with pytest.raises(ValueError, match="not been reached"):
        app.navigate_to_journey_stage(
            {"max_stage_reached": 2},
            3,
        )


def test_preferences_renderer_builds_intake_from_durable_values() -> None:
    """FR-03/FR-04: the display boundary builds intake from durable values."""

    class ExpanderContext:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            del args

    class NavigationColumn:
        def __init__(self, forward: bool) -> None:
            self.forward = forward

        def button(self, label: str, **kwargs: object) -> bool:
            if self.forward and label == "Continue to the lists":
                callback = kwargs["on_click"]
                callback(*kwargs.get("args", ()))  # type: ignore[operator]
            return False

    class PreferencesStreamlit:
        session_state: dict[str, object] = {
            "screen": "intake",
            "intake_step": 1,
            "max_intake_step_reached": 3,
            "max_stage_reached": 1,
            "last_rendered_intake_step": 1,
            "child_count": 1,
            "entity_type_0": "Student",
            "child_label_0": "Maya",
            "student_name_0": "Maya",
            "child_grade_0": "Grade 2",
            "student_grade_0": "Grade 2",
            "budget_mode_label": "One combined budget",
            "previous_budget_mode_label": "One combined budget",
            "combined_budget_text": "85.50",
            "shopping_preference_label": "Lowest total cost",
            "store_radius_miles": 10.0,
            "fulfillment_label": "Best available",
            "sales_tax_state": app.DEFAULT_TAX_STATE_OPTION,
            "tax_rate_text": "7.0",
            "tax_prefill_state": app.DEFAULT_TAX_STATE_OPTION,
            "preferences_defaults_initialized": True,
            "preferences_validation_attempted": False,
            "demo_mode": False,
        }

        @staticmethod
        def caption(value: str) -> None:
            del value

        @staticmethod
        def info(value: str) -> None:
            del value

        @staticmethod
        def error(value: str) -> None:
            raise AssertionError(value)

        @staticmethod
        def expander(label: str) -> ExpanderContext:
            del label
            return ExpanderContext()

        @classmethod
        def selectbox(
            cls,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, options, kwargs
            return str(cls.session_state[key])

        @classmethod
        def number_input(
            cls,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> float:
            del label, kwargs
            return float(cls.session_state[key])

        @classmethod
        def text_input(
            cls,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(cls.session_state[key])

        @staticmethod
        def dataframe(*args: object, **kwargs: object) -> None:
            del args, kwargs

        @staticmethod
        def columns(specification: object) -> tuple[
            NavigationColumn,
            NavigationColumn,
        ]:
            del specification
            return NavigationColumn(False), NavigationColumn(True)

    state = PreferencesStreamlit.session_state

    app._render_preferences_step(PreferencesStreamlit())

    assert state["screen"] == "lists"
    assert state["intake"]["budget_total"] == 8_550
    assert state["intake"]["store_radius_miles"] == 10.0
    assert state["intake"]["tax_basis_points"] == 700


def test_budget_screen_buttons_render_before_callback_validation() -> None:
    """Setup: the production Budget screen mounts both unchanged buttons."""

    class NavigationColumn:
        def __init__(self) -> None:
            self.buttons: list[tuple[str, dict[str, object]]] = []

        def button(self, label: str, **kwargs: object) -> bool:
            self.buttons.append((label, dict(kwargs)))
            return False

    back_column = NavigationColumn()
    forward_column = NavigationColumn()

    class BudgetStreamlit:
        session_state: dict[str, object] = {
            "intake_step": 2,
            "max_intake_step_reached": 2,
            "max_stage_reached": 1,
            "child_count": 1,
            "entity_type_0": "Student",
            "child_label_0": "Maya",
            "student_name_0": "Maya",
            "child_grade_0": "Grade 2",
            "student_grade_0": "Grade 2",
            "budget_mode_label": "One combined budget",
            "previous_budget_mode_label": "One combined budget",
            "combined_budget_text": "0",
            "intake_widget_touched::combined_budget_text": True,
            "budget_validation_attempted": False,
            "budget_validation_errors": {},
        }

        @staticmethod
        def caption(value: object) -> None:
            del value

        @staticmethod
        def info(value: object) -> None:
            del value

        @staticmethod
        def error(value: object) -> None:
            del value

        @classmethod
        def radio(
            cls,
            label: str,
            options: object,
            *,
            key: str,
            **kwargs: object,
        ) -> object:
            del label, options, kwargs
            return cls.session_state[key]

        @classmethod
        def text_input(
            cls,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(cls.session_state[key])

        @staticmethod
        def columns(specification: object) -> tuple[
            NavigationColumn,
            NavigationColumn,
        ]:
            assert specification == 2
            return back_column, forward_column

        @staticmethod
        def rerun() -> None:
            raise AssertionError("Setup callbacks must not request another rerun")

    app._render_budget_step(BudgetStreamlit())

    assert [label for label, _ in back_column.buttons] == [
        "Back to students"
    ]
    assert [label for label, _ in forward_column.buttons] == [
        "Continue to shopping preferences"
    ]
    continue_kwargs = forward_column.buttons[0][1]
    assert "key" not in continue_kwargs
    callback = continue_kwargs["on_click"]
    callback(*continue_kwargs["args"])  # type: ignore[operator]
    assert BudgetStreamlit.session_state["intake_step"] == 2
    assert BudgetStreamlit.session_state["budget_validation_attempted"] is True
    assert BudgetStreamlit.session_state["budget_validation_errors"]

    BudgetStreamlit.session_state["combined_budget_text"] = "150.00"
    callback(*continue_kwargs["args"])  # type: ignore[operator]
    assert BudgetStreamlit.session_state["intake_step"] == 3


def test_removing_entry_clears_only_its_budget_and_list() -> None:
    """FR-01/FR-03: roster removal leaves independent session values intact."""

    maya_list = ListInput(child_id="child-1", source="2 pencils")
    noah_list = ListInput(child_id="child-2", source="1 binder")
    maya_selection = object()
    noah_selection = object()
    state: dict[str, object] = {
        "max_stage_reached": 4,
        "max_intake_step_reached": 3,
        "entity_type_0": "Student",
        "child_label_0": "Maya",
        "student_name_0": "Maya",
        "child_grade_0": "Grade 2",
        "budget_0": "60.00",
        "entity_type_1": "Student",
        "child_label_1": "Noah",
        "student_name_1": "Noah",
        "child_grade_1": "Grade 5",
        "budget_1": "90.00",
        "combined_budget_text": "150.00",
        "intake": {
            "children": (
                {"child_id": "child-1", "label": "Maya"},
                {"child_id": "child-2", "label": "Noah"},
            ),
            "budget_mode": "combined",
            "budget_total": 15_000,
            "budget_allocations": {
                "child-1": 6_000,
                "child-2": 9_000,
            },
        },
        "list_inputs": (maya_list, noah_list),
        "document_selections": {
            "child-1": maya_selection,
            "child-2": noah_selection,
        },
    }

    notices = app.clear_inactive_intake_entries(state, 1)

    assert "Noah's individual budget no longer applies." in notices
    assert "Noah's supply list was removed." in notices
    assert "budget_1" not in state
    assert state["budget_0"] == "60.00"
    assert state["combined_budget_text"] == "150.00"
    assert state["intake"]["budget_total"] == 15_000
    assert state["intake"]["budget_allocations"] == {
        "child-1": 6_000,
    }
    assert tuple(
        child["child_id"] for child in state["intake"]["children"]
    ) == ("child-1",)
    assert state["list_inputs"] == (maya_list,)
    assert state["document_selections"] == {
        "child-1": maya_selection,
    }
    assert state["max_stage_reached"] == 1
    assert state["max_intake_step_reached"] == 1


def test_grade_change_clears_only_that_entry_section_selection() -> None:
    """FR-05/FR-06: a grade edit preserves files and other selections."""

    list_inputs = (
        ListInput(child_id="child-1", source="Maya list"),
        ListInput(child_id="child-2", source="Noah list"),
    )
    noah_selection = object()
    state: dict[str, object] = {
        "max_stage_reached": 4,
        "intake_previous_grade_0": "Grade 2",
        "document_sections_child-1": ("grade-2",),
        "navigation_saved::document_sections_child-1": ("grade-2",),
        "document_selections": {
            "child-1": object(),
            "child-2": noah_selection,
        },
        "list_inputs": list_inputs,
        "extraction_cache_ready": True,
        "organized_list_confirmed": True,
    }

    notices = app.clear_section_selection_after_grade_change(
        state,
        0,
        "Grade 3",
        "Maya",
    )

    assert notices == (
        "Because Maya's grade changed, choose the matching part of the "
        "supply list again.",
    )
    assert state["document_selections"] == {
        "child-2": noah_selection,
    }
    assert "document_sections_child-1" not in state
    assert "navigation_saved::document_sections_child-1" not in state
    assert state["list_inputs"] == list_inputs
    assert state["max_stage_reached"] == 2


def test_budget_mode_drafts_seed_exactly_and_clear_only_on_continue() -> None:
    """FR-03/BR-09: reversible budget drafts never lose or invent cents."""

    state: dict[str, object] = {
        "previous_budget_mode_label": "One combined budget",
        "combined_budget_text": "100.00",
        "max_stage_reached": 4,
    }

    app.prepare_budget_mode_drafts(
        state,
        "A budget for each student or classroom",
        3,
    )

    assert (
        app.money_to_cents(str(state["budget_0"])),
        app.money_to_cents(str(state["budget_1"])),
        app.money_to_cents(str(state["budget_2"])),
    ) == (3_334, 3_333, 3_333)
    assert sum(
        app.money_to_cents(str(state[f"budget_{index}"]))
        for index in range(3)
    ) == 10_000
    assert state["combined_budget_text"] == "100.00"
    assert state["max_stage_reached"] == 3
    notices = app.commit_budget_mode_drafts(
        state,
        "A budget for each student or classroom",
        3,
    )
    assert notices == ()
    assert "combined_budget_text" not in state
    assert state["budget_0"] == "33.34"
    assert state["budget_1"] == "33.33"
    assert state["budget_2"] == "33.33"


def test_per_entry_drafts_seed_empty_combined_without_overwriting() -> None:
    """FR-03: an existing combined figure always remains parent-controlled."""

    state: dict[str, object] = {
        "previous_budget_mode_label": (
            "A budget for each student or classroom"
        ),
        "budget_0": "$40.00",
        "budget_1": "45.50",
        "combined_budget_text": "",
    }

    app.prepare_budget_mode_drafts(
        state,
        "One combined budget",
        2,
    )

    assert state["combined_budget_text"] == "85.50"
    state["previous_budget_mode_label"] = (
        "A budget for each student or classroom"
    )
    state["combined_budget_text"] = "90.00"
    app.prepare_budget_mode_drafts(
        state,
        "One combined budget",
        2,
    )
    assert state["combined_budget_text"] == "90.00"
    empty_state: dict[str, object] = {
        "combined_budget_text": "",
    }
    assert app.commit_budget_mode_drafts(
        empty_state,
        "One combined budget",
        2,
    ) == ()


def test_budget_cleanup_names_only_parent_entered_amounts() -> None:
    """FR-03: the production cleanup distinguishes edits from seeded values."""

    untouched_state: dict[str, object] = {
        "budget_0": "75.00",
        "navigation_saved::budget_0": "75.00",
    }
    assert app.commit_budget_mode_drafts(
        untouched_state,
        "One combined budget",
        1,
    ) == ()

    entered_allocations: dict[str, object] = {
        "budget_0": "42.00",
        "intake_widget_touched::budget_0": True,
    }
    assert app.commit_budget_mode_drafts(
        entered_allocations,
        "One combined budget",
        1,
    ) == (
        "The individual amounts you entered no longer apply because you "
        "chose one combined budget.",
    )

    entered_combined: dict[str, object] = {
        "combined_budget_text": "125.00",
        "intake_widget_touched::combined_budget_text": True,
    }
    assert app.commit_budget_mode_drafts(
        entered_combined,
        "A budget for each student or classroom",
        1,
    ) == (
        "The combined amount you entered no longer applies because you chose "
        "a budget for each student or classroom.",
    )


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
    assert inputs[0].source == "24 pencils"
    assert inputs[0].mime_type == "text/plain"
    assert inputs[0].input_kind == "uploaded"
    assert inputs[0].source_page_texts == ("24 pencils",)


def test_uploaded_text_source_popover_renders_the_retained_text() -> None:
    """BR-64: uploaded TXT uses the same viewable text pages as pasted input."""

    state: dict[str, object] = {
        "shared_list_for_all": False,
        "list_mode_0": "Upload a file",
        "list_upload_0": SimpleNamespace(
            name="grade5.txt",
            getvalue=lambda: b"24 pencils\n1 box of tissues\n",
        ),
    }
    (list_input,) = app._build_list_inputs(
        SimpleNamespace(session_state=state),
        ({"child_id": "child-1", "label": "Jesse"},),
    )

    class Popover:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            del args

    class SourceControl:
        session_state: dict[str, object] = {}
        captions: list[str] = []
        text_pages: list[str] = []
        info_messages: list[str] = []

        @staticmethod
        def popover(label: str, **kwargs: object) -> Popover:
            del label, kwargs
            return Popover()

        @classmethod
        def caption(cls, value: str) -> None:
            cls.captions.append(value)

        @classmethod
        def code(
            cls,
            value: str,
            *,
            language: str | None,
            wrap_lines: bool,
        ) -> None:
            assert language is None
            assert wrap_lines is False
            cls.text_pages.append(value)

        @staticmethod
        def image(value: bytes, **kwargs: object) -> None:
            del value, kwargs
            raise AssertionError("TXT must render as retained text")

        @classmethod
        def info(cls, value: str) -> None:
            cls.info_messages.append(value)

    app._render_source_reference(
        SourceControl(),
        list_input,
        page_number=1,
        source_line="24 pencils",
        key="uploaded-text",
    )

    assert SourceControl.captions == [
        "Cited line on this page: 24 pencils"
    ]
    assert SourceControl.text_pages == [
        "24 pencils\n1 box of tissues\n"
    ]
    assert SourceControl.info_messages == []


def test_docx_source_fallback_names_the_format_and_action() -> None:
    """An unrenderable DOCX never calls its filename a cited source line."""

    class SourceContentRecorder:
        captions: list[str] = []
        info_messages: list[str] = []

        @classmethod
        def caption(cls, value: str) -> None:
            cls.captions.append(value)

        @classmethod
        def info(cls, value: str) -> None:
            cls.info_messages.append(value)

    app._render_source_reference_content(
        SourceContentRecorder(),
        app.SourceReference(
            document_name="grade5.docx",
            page_number=1,
            source_line="grade5.docx",
            rendered_page=None,
            text_page=None,
            mime_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        ),
    )

    assert SourceContentRecorder.captions == [
        "Source document: grade5.docx · page 1"
    ]
    assert SourceContentRecorder.info_messages == [
        "A preview of this DOCX file is unavailable. Open the original file "
        "on your device, or upload it as a PDF or TXT file to preview it here."
    ]


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

    rendered_fields: list[tuple[str, str, object]] = []

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
            rendered_fields.append((label, key, kwargs.get("help")))
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

    assert tuple(key for _, key, _ in rendered_fields) == (
        app.intake_widget_key("budget_0"),
        app.intake_widget_key("budget_1"),
    )
    assert BudgetStreamlit.session_state["budget_0"] == "75.00"
    assert BudgetStreamlit.session_state["budget_1"] == "1,500.00"
    assert "Maya budget" in rendered_fields[0][0]
    assert "Ms. Rivera budget" in rendered_fields[1][0]
    assert tuple(help_text for _, _, help_text in rendered_fields) == (
        app.escape_streamlit_dollars(app.PER_ENTRY_BUDGET_HELP),
        None,
    )
    assert app.budget_entry_fields(
        app._intake_students_from_state(
            BudgetStreamlit.session_state,
            2,
        )
    ) == (
        (0, "child-1", "Maya", "budget_0"),
        (1, "child-2", "Ms. Rivera", "budget_1"),
    )


def test_budget_screen_scales_untouched_starting_values_by_student_count() -> None:
    """BR-71: the production Budget screen scales only untouched defaults."""

    rendered_help: list[object] = []

    class ButtonColumn:
        @staticmethod
        def button(*args: object, **kwargs: object) -> bool:
            del args, kwargs
            return False

    class BudgetStreamlit:
        session_state: dict[str, object] = {}

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
            del label
            rendered_help.append(kwargs.get("help"))
            return str(cls.session_state[key])

        @staticmethod
        def info(value: str) -> None:
            del value

        @staticmethod
        def error(value: str) -> None:
            del value

        @staticmethod
        def columns(
            specification: object,
        ) -> tuple[ButtonColumn, ButtonColumn]:
            assert specification == 2
            return ButtonColumn(), ButtonColumn()

    combined_cases = (
        (
            {
                "child_count": 1,
                "entity_type_0": "Student",
                "child_label_0": "Maya",
                "child_grade_0": "Grade 2",
            },
            "75.00",
        ),
        (
            {
                "child_count": 2,
                "entity_type_0": "Student",
                "child_label_0": "Maya",
                "child_grade_0": "Grade 2",
                "entity_type_1": "Student",
                "child_label_1": "Noah",
                "child_grade_1": "Grade 5",
            },
            "150.00",
        ),
        (
            {
                "child_count": 1,
                "entity_type_0": "Classroom",
                "child_label_0": "Ms. Rivera",
                "child_grade_0": "Grade 3",
                "student_count_0": 10,
            },
            "750.00",
        ),
        (
            {
                "child_count": 2,
                "entity_type_0": "Student",
                "child_label_0": "Maya",
                "child_grade_0": "Grade 2",
                "entity_type_1": "Classroom",
                "child_label_1": "Ms. Rivera",
                "child_grade_1": "Grade 3",
                "student_count_1": 10,
            },
            "825.00",
        ),
    )
    for entry_state, expected in combined_cases:
        BudgetStreamlit.session_state = {
            **entry_state,
            "budget_mode_label": "One combined budget",
            "previous_budget_mode_label": "One combined budget",
            "budget_validation_attempted": False,
            "budget_validation_errors": {},
        }
        app._render_budget_step(BudgetStreamlit())
        assert (
            BudgetStreamlit.session_state["combined_budget_text"] == expected
        )

    BudgetStreamlit.session_state = {
        **combined_cases[-1][0],
        "budget_mode_label": "A budget for each student or classroom",
        "previous_budget_mode_label": (
            "A budget for each student or classroom"
        ),
        "budget_validation_attempted": False,
        "budget_validation_errors": {},
    }
    app._render_budget_step(BudgetStreamlit())
    assert BudgetStreamlit.session_state["budget_0"] == "75.00"
    assert BudgetStreamlit.session_state["budget_1"] == "750.00"
    assert rendered_help == [
        app.escape_streamlit_dollars(app.COMBINED_BUDGET_HELP),
        app.escape_streamlit_dollars(app.COMBINED_BUDGET_HELP),
        app.escape_streamlit_dollars(app.COMBINED_BUDGET_HELP),
        app.escape_streamlit_dollars(app.COMBINED_BUDGET_HELP),
        app.escape_streamlit_dollars(app.PER_ENTRY_BUDGET_HELP),
        None,
    ]


def test_budget_screen_recalculates_defaults_but_preserves_parent_edits() -> None:
    """BR-71: roster edits cannot overwrite a parent-controlled budget."""

    class ButtonColumn:
        @staticmethod
        def button(*args: object, **kwargs: object) -> bool:
            del args, kwargs
            return False

    class BudgetStreamlit:
        session_state: dict[str, object] = {
            "child_count": 1,
            "entity_type_0": "Classroom",
            "child_label_0": "Ms. Rivera",
            "child_grade_0": "Grade 3",
            "student_count_0": 10,
            "budget_mode_label": "One combined budget",
            "previous_budget_mode_label": "One combined budget",
            "budget_validation_attempted": False,
            "budget_validation_errors": {},
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
            del label, kwargs
            return str(cls.session_state[key])

        @staticmethod
        def info(value: str) -> None:
            del value

        @staticmethod
        def error(value: str) -> None:
            del value

        @staticmethod
        def columns(
            specification: object,
        ) -> tuple[ButtonColumn, ButtonColumn]:
            assert specification == 2
            return ButtonColumn(), ButtonColumn()

    app._render_budget_step(BudgetStreamlit())
    assert BudgetStreamlit.session_state["combined_budget_text"] == "750.00"

    BudgetStreamlit.session_state["student_count_0"] = 12
    app._render_budget_step(BudgetStreamlit())
    assert BudgetStreamlit.session_state["combined_budget_text"] == "900.00"

    BudgetStreamlit.session_state["combined_budget_text"] = "800.00"
    BudgetStreamlit.session_state[
        "intake_widget_touched::combined_budget_text"
    ] = True
    BudgetStreamlit.session_state["student_count_0"] = 15
    app._render_budget_step(BudgetStreamlit())
    assert BudgetStreamlit.session_state["combined_budget_text"] == "800.00"


def test_budget_screen_renders_entry_aware_mode_labels() -> None:
    """FR-03: the production Budget screen removes a redundant one-entry mode."""

    rendered_options: list[tuple[str, ...]] = []

    class ButtonColumn:
        @staticmethod
        def button(*args: object, **kwargs: object) -> bool:
            del args, kwargs
            return False

    class BudgetStreamlit:
        session_state: dict[str, object] = {}

        @staticmethod
        def caption(value: str) -> None:
            del value

        @classmethod
        def radio(
            cls,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label
            formatter = kwargs["format_func"]
            rendered_options.append(
                tuple(formatter(option) for option in options)
            )
            return str(cls.session_state[key])

        @classmethod
        def text_input(
            cls,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(cls.session_state[key])

        @staticmethod
        def info(value: str) -> None:
            del value

        @staticmethod
        def error(value: str) -> None:
            del value

        @staticmethod
        def columns(
            specification: object,
        ) -> tuple[ButtonColumn, ButtonColumn]:
            assert specification == 2
            return ButtonColumn(), ButtonColumn()

    cases = (
        ("Kevin", "Student", 1, ("Kevin's budget", "No set budget")),
        (
            "Grade 2 homeroom",
            "Classroom",
            10,
            ("Grade 2 homeroom's budget", "No set budget"),
        ),
        ("James", "Student", 1, ("James' budget", "No set budget")),
        (
            "",
            "Student",
            1,
            ("Budget for this student or classroom", "No set budget"),
        ),
    )
    for label, entity_type, student_count, expected_options in cases:
        rendered_options.clear()
        BudgetStreamlit.session_state = {
            "child_count": 1,
            "entity_type_0": entity_type,
            "child_label_0": label,
            "child_grade_0": "Grade 2",
            "student_count_0": student_count,
            "budget_mode_label": "One combined budget",
            "previous_budget_mode_label": "One combined budget",
            "budget_validation_attempted": False,
            "budget_validation_errors": {},
        }

        app._render_budget_step(BudgetStreamlit())

        assert rendered_options == [expected_options]

    rendered_options.clear()
    BudgetStreamlit.session_state = {
        "child_count": 2,
        "entity_type_0": "Student",
        "child_label_0": "Kevin",
        "child_grade_0": "Grade 2",
        "entity_type_1": "Student",
        "child_label_1": "Maya",
        "child_grade_1": "Grade 5",
        "budget_mode_label": "One combined budget",
        "previous_budget_mode_label": "One combined budget",
        "budget_validation_attempted": False,
        "budget_validation_errors": {},
    }

    app._render_budget_step(BudgetStreamlit())

    assert rendered_options == [
        (
            "A budget for each student or classroom",
            "One combined budget",
            "No set budget",
        )
    ]


def test_first_budget_visit_selects_per_entry_then_preserves_parent_mode() -> None:
    """FR-03: only the first multi-entry Budget visit changes selection."""

    state: dict[str, object] = {
        "child_count": 2,
        "entity_type_0": "Student",
        "student_name_0": "Kevin",
        "student_grade_0": "Grade 2",
        "entity_type_1": "Student",
        "student_name_1": "Maya",
        "student_grade_1": "Grade 5",
        "intake_step": 1,
        "max_intake_step_reached": 1,
        "budget_mode_label": "One combined budget",
    }

    app._continue_from_students(state, 2)

    assert state["budget_mode_label"] == (
        "A budget for each student or classroom"
    )
    assert state["intake_step"] == 2
    assert state["max_intake_step_reached"] == 2

    state["intake_step"] = 1
    state["budget_mode_label"] = "One combined budget"
    state[
        app.NAVIGATION_STATE_PREFIX + "budget_mode_label"
    ] = "One combined budget"
    app._continue_from_students(state, 2)

    assert state["budget_mode_label"] == "One combined budget"
    assert state[
        app.NAVIGATION_STATE_PREFIX + "budget_mode_label"
    ] == "One combined budget"


def test_budget_screen_maps_entry_count_changes_without_losing_amount() -> None:
    """FR-03: one/many option changes retain the parent's durable amount."""

    rendered_options: list[tuple[str, ...]] = []

    class ButtonColumn:
        @staticmethod
        def button(*args: object, **kwargs: object) -> bool:
            del args, kwargs
            return False

    class BudgetStreamlit:
        session_state: dict[str, object] = {
            "child_count": 1,
            "entity_type_0": "Student",
            "child_label_0": "Kevin",
            "child_grade_0": "Grade 2",
            "budget_mode_label": "One combined budget",
            "previous_budget_mode_label": "One combined budget",
            "combined_budget_text": "123.45",
            "intake_widget_touched::combined_budget_text": True,
            "budget_validation_attempted": False,
            "budget_validation_errors": {},
        }

        @staticmethod
        def caption(value: str) -> None:
            del value

        @classmethod
        def radio(
            cls,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label
            formatter = kwargs["format_func"]
            rendered_options.append(
                tuple(formatter(option) for option in options)
            )
            return str(cls.session_state[key])

        @classmethod
        def text_input(
            cls,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(cls.session_state[key])

        @staticmethod
        def info(value: str) -> None:
            del value

        @staticmethod
        def error(value: str) -> None:
            del value

        @staticmethod
        def columns(
            specification: object,
        ) -> tuple[ButtonColumn, ButtonColumn]:
            assert specification == 2
            return ButtonColumn(), ButtonColumn()

    app._render_budget_step(BudgetStreamlit())
    assert BudgetStreamlit.session_state["combined_budget_text"] == "123.45"

    BudgetStreamlit.session_state.update(
        {
            "child_count": 2,
            "entity_type_1": "Student",
            "child_label_1": "Maya",
            "child_grade_1": "Grade 5",
        }
    )
    rendered_options.clear()
    app._render_budget_step(BudgetStreamlit())
    assert rendered_options[0] == (
        "A budget for each student or classroom",
        "One combined budget",
        "No set budget",
    )
    assert BudgetStreamlit.session_state["budget_mode_label"] == (
        "One combined budget"
    )
    assert BudgetStreamlit.session_state["combined_budget_text"] == "123.45"

    BudgetStreamlit.session_state["budget_mode_label"] = (
        "A budget for each student or classroom"
    )
    app._render_budget_step(BudgetStreamlit())
    BudgetStreamlit.session_state["budget_0"] = "50.00"
    BudgetStreamlit.session_state[
        "intake_widget_touched::budget_0"
    ] = True
    app.clear_inactive_intake_entries(BudgetStreamlit.session_state, 1)
    BudgetStreamlit.session_state["child_count"] = 1
    rendered_options.clear()

    app._render_budget_step(BudgetStreamlit())

    assert rendered_options[0] == ("Kevin's budget", "No set budget")
    assert BudgetStreamlit.session_state["budget_mode_label"] == (
        "One combined budget"
    )
    assert BudgetStreamlit.session_state["combined_budget_text"] == "50.00"
    assert BudgetStreamlit.session_state[
        "intake_widget_touched::combined_budget_text"
    ] is True
    assert "budget_0" not in BudgetStreamlit.session_state

    BudgetStreamlit.session_state.update(
        {
            "child_count": 2,
            "entity_type_1": "Student",
            "child_label_1": "Maya",
            "child_grade_1": "Grade 5",
        }
    )
    rendered_options.clear()
    app._render_budget_step(BudgetStreamlit())
    assert BudgetStreamlit.session_state["budget_mode_label"] == (
        "One combined budget"
    )
    assert BudgetStreamlit.session_state["combined_budget_text"] == "50.00"


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
    assert mode == "none"
    assert total is None
    assert allocations == {}


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
    assert "key=active_grade_widget_key" in student_source
    assert "commit_intake_widget_value" in student_source
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
    assert "student_validation_errors" in student_source
    assert "disabled=" not in student_source
    assert "continue_column.button" in student_source
    assert "use_container_width=True" in student_source
    assert 'st.subheader("Budget")' not in budget_source
    assert "Step 2" not in budget_source
    assert "A budget for each student or classroom" in budget_source
    assert app.NO_SET_BUDGET_LABEL == "No set budget"
    assert "budget_validation_attempted" in budget_source
    assert "disabled=" not in budget_source
    assert app.COMBINED_BUDGET_HELP == (
        "Enter the total you want to spend, for example 75 or $85.50."
    )
    assert app.PER_ENTRY_BUDGET_HELP == (
        "Enter the amount you want to spend for this student or classroom, "
        "for example 75 or $85.50."
    )
    assert "COMBINED_BUDGET_HELP" in budget_source
    assert "PER_ENTRY_BUDGET_HELP" in budget_source
    assert "tight budget" not in budget_source
    assert "forward.button" in budget_source
    assert "use_container_width=True" in budget_source
    assert 'st.subheader("Shopping preferences")' not in preferences_source
    assert "Step 3" not in preferences_source
    assert '"Shopping preferences"' in preferences_source
    assert "Advanced shopping and tax options" in preferences_source
    assert "preferences_validation_attempted" in preferences_source
    assert "disabled=radius_disabled" in preferences_source
    assert "Not needed for delivery." in preferences_source
    assert preferences_source.index("fulfillment_label = st.selectbox") < (
        preferences_source.index("radius = float")
    )
    assert "Adjust distance, pickup or delivery, and tax." in (
        preferences_source
    )
    assert "forward.button" in preferences_source
    assert "use_container_width=True" in preferences_source
    assert "Shopping mode" not in preferences_source
    assert "_navigation_button_columns(st)" in student_source
    assert "_navigation_button_columns(st)" in budget_source
    assert "_navigation_button_columns(st)" in preferences_source
    assert "SETUP_BACK_NAVIGATION[2]" in budget_source
    assert "SETUP_BACK_NAVIGATION[3]" in preferences_source
    assert "on_click=_continue_from_students" in student_source
    assert "on_click=_continue_from_budget" in budget_source
    assert "on_click=_continue_from_preferences" in preferences_source
    assert ".rerun()" not in student_source
    assert ".rerun()" not in budget_source
    assert ".rerun()" not in preferences_source
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

    rendered_css: list[str] = []

    class CssRecorder:
        @staticmethod
        def markdown(value: str, **kwargs: object) -> None:
            assert kwargs.get("unsafe_allow_html") is True
            rendered_css.append(value)

    app._apply_custom_css(CssRecorder())
    css_source = "\n".join(rendered_css).casefold()

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
    assert '[data-testid="stheaderactionelements"]' in css_source
    assert "display: none !important" in css_source
    assert '[data-testid="sttextarea"] textarea' in css_source
    assert "border: 2px solid #6e8d9e !important" in css_source


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

    assert app.APP_TAGLINE == (
        "School supplies sorted before the first bell."
    )
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


def test_forward_scroll_targets_streamlit_page_top_and_app_title() -> None:
    """Successful transitions target the real Streamlit scroller and title."""

    script = app._page_top_scroll_script()
    main_source = inspect.getsource(app.main)

    assert 'section[data-testid="stMain"]' in script
    assert '[data-testid="stAppViewContainer"]' in script
    assert 'getElementById("rss-app-title")' in script
    assert "querySelectorAll(" in script
    assert "getComputedStyle(ancestor)" in script
    assert "scrollTargets.forEach" in script
    assert "target.scrollTop = 0" in script
    assert "scrollingElement.scrollTop = 0" in script
    assert "title.scrollIntoView" in script
    assert 'behavior: "auto"' in script
    assert "window.parent" in script
    assert main_source.index("_render_app_title(st)") < main_source.index(
        "_render_requested_next_task_scroll(st)"
    )


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
    assert any(kind == "metric:Total cost" for kind, _ in events)
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
    """Reached stages are clickable while current and future stages are not."""

    intake_sections_source = inspect.getsource(
        app._render_intake_step_progress
    )
    assert app.JOURNEY_STAGES == (
        "Your students",
        "Their lists",
        "Personalize your cart",
        "Your shopping plan",
    )
    assert app.screen_phase_label("intake") == "Your students"
    assert app.screen_phase_label("lists") == "Their lists"
    assert (
        app.screen_phase_label("working", "reading the lists")
        == "Your shopping plan"
    )
    assert app.screen_phase_label("sections") == "Their lists"
    assert app.screen_phase_label("review") == "Personalize your cart"
    assert app.screen_phase_label("approval") == "Your shopping plan"
    assert app.screen_phase_label("summary") == "Your shopping plan"
    assert "st.progress" not in intake_sections_source
    assert "intake_section_navigation_" in intake_sections_source
    assert '"●"' not in intake_sections_source
    assert '"○"' not in intake_sections_source

    rendered: list[tuple[str, dict[str, object]]] = []

    class StageColumn:
        @staticmethod
        def button(label: str, **kwargs: object) -> bool:
            rendered.append((label, dict(kwargs)))
            return False

    class StepperStreamlit:
        session_state: dict[str, object] = {
            "max_stage_reached": 3,
        }

        @staticmethod
        def columns(count: int) -> tuple[StageColumn, ...]:
            return tuple(StageColumn() for _ in range(count))

    app._screen_progress(StepperStreamlit(), "review")

    assert len(rendered) == 4
    assert [options["disabled"] for _, options in rendered] == [
        False,
        False,
        True,
        True,
    ]
    assert [options["type"] for _, options in rendered] == [
        "secondary",
        "secondary",
        "primary",
        "secondary",
    ]
    assert all("●" not in label and "○" not in label for label, _ in rendered)
    assert rendered[0][0].startswith("✓ ")
    assert rendered[1][0].startswith("✓ ")
    assert not rendered[2][0].startswith("✓ ")
    assert not rendered[3][0].startswith("✓ ")
    assert rendered[2][0].endswith("Personalize your cart")
    assert app.journey_stage_statuses(3, 3) == (
        "completed",
        "completed",
        "current",
        "unavailable",
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
            "catalog_unavailable_items",
        )

    matching_result = _real_pipeline_result("Grade 2")
    assert app.detect_list_identity_warnings(
        matching_result.extractions,
        children,
    ) == ()


def test_identity_warning_uses_whole_document_and_explicit_scope_resolves() -> None:
    """BR-18: whole-document grades inform context; a chosen scope proceeds."""

    extraction = ExtractionEnvelope(
        stated_grades=("Grade 5", "Grade 6", "Grade 7", "Grade 8"),
        requirements=(),
    )
    structure = DocumentStructureEnvelope(
        sections=tuple(
            DocumentSection(
                section_id=f"grade-{grade}",
                label=f"Grade {grade}",
                grades=(f"Grade {grade}",),
                page_numbers=(1 if grade < 5 else 2,),
                source_line=f"Grade {grade}",
            )
            for grade in range(1, 9)
        )
    )
    children = (
        {"child_id": "child-1", "label": "Maya", "grade": "Pre-K"},
    )

    warnings = app.detect_list_identity_warnings(
        {"child-1": extraction},
        children,
        {"child-1": structure},
    )

    assert len(warnings) == 1
    assert warnings[0].stated_grades == tuple(
        f"Grade {grade}" for grade in range(1, 9)
    )

    selected = extraction.model_copy(
        update={
            "document_selection": DocumentSelection(
                selected_section_ids=("grade-5",),
                selected_section_labels=("Grade 5",),
            )
        }
    )
    assert app.detect_list_identity_warnings(
        {"child-1": selected},
        children,
        {"child-1": structure},
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


def test_review_understanding_keeps_literal_paper_ruling_visible() -> None:
    """A stated ruling distinguishes otherwise identical paper decisions."""

    requirement = Requirement(
        req_id="college-paper",
        child_id="child-1",
        raw_text="1 Package of College-Ruled Paper",
        canonical_item="notebook_paper",
        quantity=1,
        unit_type="pack",
        extraction_confidence=1.0,
    )
    item = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=(requirement,),
            )
        }
    )[0]

    assert requirement.attributes.ruling == "college-ruled"
    assert requirement.extraction_confidence == 1.0
    assert item.issue_codes == ("ambiguous_package_size",)
    assert app.review_understanding_text(item) == (
        "1 pack of 150 notebook paper, college-ruled"
    )


def test_split_source_context_names_every_companion_requirement() -> None:
    """BR-65: each split-line card names the other item read from that line."""

    source = "1 Three-Ring Binder with Dividers"
    binder = SupplyItemReview(
        review_id="child-1:binder",
        req_id="binder",
        child_id="child-1",
        item_name="binders",
        required_quantity=1,
        source_text=source,
        source_document="Kevin's supply list",
        source_page=1,
        required_attributes={"connector": "three-ring"},
        confidence=1.0,
    )
    dividers = SupplyItemReview(
        review_id="child-1:dividers",
        req_id="dividers",
        child_id="child-1",
        item_name="dividers",
        required_quantity=1,
        source_text=source,
        source_document="Kevin's supply list",
        source_page=1,
        confidence=1.0,
    )

    context = app.review_split_source_context((binder, dividers))

    assert context[binder.review_id] == (
        'From the same list line, "1 Three-Ring Binder with Dividers", '
        "we also read 1 set of dividers.",
    )
    assert context[dividers.review_id] == (
        'From the same list line, "1 Three-Ring Binder with Dividers", '
        "we also read 1 binder, three-ring.",
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


def test_personalize_screen_groups_sources_in_student_summary() -> None:
    """BR-29: routine rows use the student summary instead of source noise."""

    source = inspect.getsource(app._render_review)

    assert "data_editor" not in source
    assert "Personalize what goes in your cart" in source
    assert "_personalize_source_summary" in source
    assert "Needs your decision" in source
    assert "Optional — your call" in source
    assert "In your cart" in source
    assert "Left out" in source
    assert "Not available from these stores" not in source
    assert "_render_personalize_unavailable" in source
    assert "Products and prices come next" in source
    assert "Confirm the readings" not in source
    assert "Notes from the teacher" in source


def test_personalize_navigation_round_trip_uses_non_widget_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BR-52: the production screen survives every tab and item-jump route."""

    rows = (
        SupplyItemReview(
            review_id="clear",
            req_id="clear",
            child_id="child-1",
            item_name="pencils",
            required_quantity=12,
            source_text="12 pencils",
            confidence=1.0,
        ),
        SupplyItemReview(
            review_id="flagged",
            req_id="flagged",
            child_id="child-1",
            item_name="notebook_paper",
            required_quantity=1,
            unit="pack",
            package_quantity_state="assumed",
            package_size=150,
            issue_codes=("ambiguous_package_size",),
            source_text="1 pack notebook paper",
            confidence=0.8,
        ),
        SupplyItemReview(
            review_id="owned",
            req_id="owned",
            child_id="child-1",
            item_name="backpacks",
            required_quantity=0,
            already_owned=True,
            source_text="1 backpack",
            confidence=1.0,
        ),
        SupplyItemReview(
            review_id="removed",
            req_id="removed",
            child_id="child-1",
            item_name="folders",
            required_quantity=0,
            review_status="deleted",
            source_text="2 folders",
            confidence=1.0,
        ),
        SupplyItemReview(
            review_id="optional",
            req_id="optional",
            child_id="child-1",
            item_name="tissues",
            required_quantity=1,
            optional=True,
            source_text="1 optional box of tissues",
            confidence=1.0,
        ),
    )
    class WidgetAwareState(dict[str, object]):
        """Enforce Streamlit's widget and stricter button state rules."""

        def __init__(self, values: dict[str, object]) -> None:
            super().__init__(values)
            self.widget_keys: set[str] = set()
            self.button_keys: set[str] = set()
            self.application_assignments: set[str] = set()

        def __setitem__(self, key: str, value: object) -> None:
            self.application_assignments.add(key)
            if key in self.button_keys:
                raise AssertionError(
                    f"Application assigned button-owned key {key}"
                )
            if key in self.widget_keys:
                raise AssertionError(
                    f"Application assigned widget-owned key {key}"
                )
            super().__setitem__(key, value)

        def set_widget(self, key: str, value: object) -> None:
            dict.__setitem__(self, key, value)

        def register_button(self, key: str) -> None:
            if key in self.application_assignments:
                raise AssertionError(
                    f"Button key was assigned before render: {key}"
                )
            self.button_keys.add(key)

        def register_widget(self, key: str) -> None:
            self.widget_keys.add(key)

    assigned_before_button = WidgetAwareState({})
    assigned_before_button["future-button"] = False
    with pytest.raises(
        AssertionError,
        match="assigned before render",
    ):
        assigned_before_button.register_button("future-button")

    assigned_after_button = WidgetAwareState({})
    assigned_after_button.register_button("rendered-button")
    with pytest.raises(
        AssertionError,
        match="button-owned",
    ):
        assigned_after_button["rendered-button"] = False

    state = WidgetAwareState({
        "intake": {
            "children": (
                {"child_id": "child-1", "label": "Jawan"},
            )
        },
        "extracted_lists": {
            "child-1": ExtractionEnvelope(
                requirements=(
                    Requirement(
                        req_id="clear",
                        child_id="child-1",
                        raw_text="12 pencils",
                        canonical_item="pencils",
                        quantity=12,
                        extraction_confidence=1.0,
                    ),
                    Requirement(
                        req_id="flagged",
                        child_id="child-1",
                        raw_text="1 pack notebook paper",
                        canonical_item="notebook_paper",
                        quantity=1,
                        unit_type="pack",
                        package_quantity_state="assumed",
                        extraction_confidence=0.8,
                    ),
                    Requirement(
                        req_id="owned",
                        child_id="child-1",
                        raw_text="1 backpack",
                        canonical_item="backpacks",
                        quantity=1,
                        extraction_confidence=1.0,
                    ),
                    Requirement(
                        req_id="removed",
                        child_id="child-1",
                        raw_text="2 folders",
                        canonical_item="folders",
                        quantity=2,
                        extraction_confidence=1.0,
                    ),
                    Requirement(
                        req_id="optional",
                        child_id="child-1",
                        raw_text="1 optional box of tissues",
                        canonical_item="tissues",
                        quantity=1,
                        is_required=False,
                        requirement_type="optional",
                        extraction_confidence=1.0,
                    ),
                ),
                catalog_unavailable_items=(
                    CatalogUnavailableItem(
                        child_id="child-1",
                        item_name="graphing_calculator",
                        source_line="1 graphing calculator",
                    ),
                ),
            )
        },
        "review_items": rows,
        "parent_added_review_items": (),
        "extraction_errors": {},
        "list_inputs": (),
        app.PERSONALIZE_SELECTED_VIEW_KEY: "summary",
    })
    _mark_personalize_review_cache_current(state)

    class ReviewScreenRecorder:
        def __init__(self) -> None:
            self.session_state = state
            self.messages: list[str] = []
            self.writes: list[str] = []
            self.buttons: list[str] = []
            self.tab_labels: tuple[str, ...] = ()
            self.radio_callback: tuple[object, tuple[object, ...]] | None = None
            self.radio_key: str | None = None
            self.radio_selected: str | None = None
            self.button_callbacks: dict[
                str, tuple[object, tuple[object, ...]]
            ] = {}
            self.checkbox_callbacks: dict[
                str, tuple[str, object, tuple[object, ...]]
            ] = {}
            self.radio_label_visibility: str | None = None
            self.column_specs: list[object] = []
            self.container_keys: list[str] = []
            self.expanders: list[tuple[str, bool | None]] = []
            self.events: list[tuple[str, str]] = []
            self.components = SimpleNamespace(
                v1=SimpleNamespace(html=lambda *args, **kwargs: None)
            )

        def __enter__(self) -> "ReviewScreenRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def columns(
            self,
            spec: object,
            **kwargs: object,
        ) -> tuple["ReviewScreenRecorder", ...]:
            del kwargs
            self.column_specs.append(spec)
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def container(self, **kwargs: object) -> "ReviewScreenRecorder":
            key = kwargs.get("key")
            if isinstance(key, str):
                self.container_keys.append(key)
                self.events.append(("container", key))
            return self

        def expander(
            self,
            label: str,
            **kwargs: object,
        ) -> "ReviewScreenRecorder":
            self.expanders.append(
                (label, kwargs.get("expanded"))
            )
            return self

        def popover(
            self,
            label: str,
            **kwargs: object,
        ) -> "ReviewScreenRecorder":
            del kwargs
            self.events.append(("popover", label))
            return self

        def header(self, value: object) -> None:
            self.messages.append(str(value))

        def subheader(self, value: object) -> None:
            self.messages.append(str(value))

        def caption(self, value: object) -> None:
            self.messages.append(str(value))

        def markdown(self, value: object, **kwargs: object) -> None:
            del kwargs
            self.messages.append(str(value))
            self.events.append(("markdown", str(value)))

        def warning(self, value: object) -> None:
            self.messages.append(str(value))

        def success(self, value: object) -> None:
            self.messages.append(str(value))

        def error(self, value: object) -> None:
            self.messages.append(str(value))

        def write(self, value: object) -> None:
            self.writes.append(str(value))
            self.events.append(("write", str(value)))

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            format_func: object | None = None,
            index: int | None = 0,
            on_change: object | None = None,
            args: tuple[object, ...] = (),
            **kwargs: object,
        ) -> str:
            self.radio_label_visibility = str(
                kwargs.get("label_visibility")
            )
            if format_func is not None:
                self.tab_labels = tuple(
                    format_func(option) for option in options  # type: ignore[operator]
                )
            if key not in self.session_state:
                selected_index = 0 if index is None else index
                self.session_state.set_widget(
                    key,
                    options[selected_index],
                )
            self.session_state.register_widget(key)
            self.radio_key = key
            self.radio_selected = str(self.session_state[key])
            if on_change is not None:
                self.radio_callback = (on_change, args)
            return str(self.session_state[key])

        def button(
            self,
            label: str,
            *,
            on_click: object | None = None,
            args: tuple[object, ...] = (),
            **kwargs: object,
        ) -> bool:
            key = kwargs.get("key")
            if isinstance(key, str):
                self.session_state.register_button(key)
            self.buttons.append(label)
            self.events.append(("button", label))
            if on_click is not None:
                self.button_callbacks[label] = (on_click, args)
            return False

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            value: bool = False,
            on_change: object | None = None,
            args: tuple[object, ...] = (),
            **kwargs: object,
        ) -> bool:
            del kwargs
            if key not in self.session_state:
                self.session_state.set_widget(key, value)
            self.session_state.register_widget(key)
            if on_change is not None:
                self.checkbox_callbacks[label] = (
                    key,
                    on_change,
                    args,
                )
            self.events.append(("checkbox", label))
            return bool(self.session_state[key])

        def rerun(self) -> None:
            raise AssertionError("Navigation callbacks do not request reruns")

        def select_view(self, view: str) -> None:
            assert self.radio_callback is not None
            assert self.radio_key is not None
            callback, args = self.radio_callback
            self.session_state.set_widget(
                self.radio_key,
                view,
            )
            callback(*args)  # type: ignore[operator]

        def click(self, label: str) -> None:
            callback, args = self.button_callbacks[label]
            callback(*args)  # type: ignore[operator]

        def check(self, label: str) -> None:
            key, callback, args = self.checkbox_callbacks[label]
            self.session_state.set_widget(key, True)
            callback(*args)  # type: ignore[operator]

    monkeypatch.setattr(
        app,
        "_render_compact_review_row",
        lambda st, members, *args, **kwargs: (
            {item.review_id: item for item in members},
            False,
        ),
    )
    monkeypatch.setattr(
        app,
        "_render_settled_review_row",
        lambda st, item, *args, **kwargs: item,
    )
    monkeypatch.setattr(
        app,
        "_render_excluded_review_row",
        lambda st, item, *args, **kwargs: item,
    )
    monkeypatch.setattr(
        app,
        "_render_optional_review_row",
        lambda st, item, *args, **kwargs: item,
    )
    monkeypatch.setattr(
        app,
        "_render_personalize_unavailable",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_personalize_source_summary",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_new_review_item_from_controls",
        lambda *args, **kwargs: None,
    )

    summary = ReviewScreenRecorder()
    app._render_review(summary)
    assert summary.tab_labels == ("Summary", "Jawan  [1]")
    assert summary.radio_label_visibility == "collapsed"
    assert "1 decision remains." in summary.messages
    assert "Approve all AI recommendations" in summary.buttons
    assert "Open Jawan" in summary.buttons
    count_messages = (
        "**1**  \nIn cart",
        "**1**  \nNeeds a decision",
        "**1**  \nOptional",
    )
    assert all(message in summary.messages for message in count_messages)
    count_positions = tuple(
        summary.messages.index(message) for message in count_messages
    )
    assert count_positions == tuple(sorted(count_positions))
    assert ("Review 1 decision", False) in summary.expanders
    assert ("popover", "Notebook paper") not in summary.events
    assert ("popover", "Tissues, optional") not in summary.events
    assert ("popover", "Pencils") not in summary.events
    assert [4.8, 1.2] in summary.column_specs
    assert 3 in summary.column_specs
    assert ("Left out of cart (2)", None) in summary.expanders
    assert "**Already owned (1)**" in summary.messages
    assert "**Removed from cart (1)**" in summary.messages
    assert any(
        message.startswith("**Jawan:")
        for message in summary.messages
    )

    summary.select_view("child-1")
    student = ReviewScreenRecorder()
    app._render_review(student)
    assert state[app.PERSONALIZE_SELECTED_VIEW_KEY] == "child-1"
    assert "**Optional — your call (1)**" in student.messages
    add_index = student.messages.index("**Need to add something?**")
    optional_index = student.messages.index("**Optional — your call (1)**")
    assert add_index < optional_index

    student.select_view("summary")
    returned_summary = ReviewScreenRecorder()
    app._render_review(returned_summary)
    assert state[app.PERSONALIZE_SELECTED_VIEW_KEY] == "summary"

    returned_summary.click("Approve all AI recommendations")
    final_summary = ReviewScreenRecorder()
    app._render_review(final_summary)
    assert any(
        key.startswith(f"{app.PERSONALIZE_VIEW_WIDGET_KEY}:")
        for key in state.widget_keys
    )
    assert "personalize_active_tab" not in state

    assert state[app.PERSONALIZE_CONFIRMED_GROUP_IDS_KEY] == frozenset(
        {"review-flag-1"}
    )
    assert "Nothing left to decide." in final_summary.messages
    assert "Approve all AI recommendations" not in final_summary.buttons


def test_personalize_student_cards_render_each_decision_before_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-12/BR-52: the production student view makes every flag actionable."""

    rows = (
        SupplyItemReview(
            review_id="missing-quantity",
            req_id="missing-quantity",
            child_id="child-1",
            item_name="pencils",
            required_quantity=1,
            source_text="Pencils",
            confidence=0.9,
            issue_codes=("missing_quantity",),
        ),
        SupplyItemReview(
            review_id="uncertain",
            req_id="uncertain",
            child_id="child-1",
            item_name="scissors",
            required_quantity=1,
            source_text="1 blunt-tip scissors",
            confidence=0.6,
            issue_codes=("low_confidence",),
        ),
        SupplyItemReview(
            review_id="range",
            req_id="range",
            child_id="child-1",
            item_name="tissues",
            required_quantity=2,
            quantity_is_range=True,
            quantity_max=3,
            source_text="2-3 boxes of tissues",
            confidence=0.9,
            issue_codes=("quantity_range",),
        ),
        SupplyItemReview(
            review_id="package",
            req_id="package",
            child_id="child-1",
            item_name="notebook_paper",
            required_quantity=1,
            unit="pack",
            package_size=150,
            package_quantity_state="assumed",
            source_text="1 pack of notebook paper",
            confidence=0.9,
            issue_codes=("ambiguous_package_size",),
        ),
        SupplyItemReview(
            review_id="item",
            req_id="item",
            child_id="child-1",
            item_name="markers",
            required_quantity=1,
            source_text="1 writing set",
            confidence=0.9,
            issue_codes=("ambiguous_item",),
        ),
        SupplyItemReview(
            review_id="brand",
            req_id="brand",
            child_id="child-1",
            item_name="pencils",
            required_quantity=12,
            source_text="12 pencils, no substitutes",
            confidence=0.9,
            issue_codes=(
                app.AMBIGUOUS_UNNAMED_BRAND_REQUIREMENT_ISSUE,
            ),
        ),
        SupplyItemReview(
            review_id="other",
            req_id="other",
            child_id="child-1",
            item_name="folders",
            required_quantity=2,
            source_text="2 folders, color unclear",
            confidence=0.9,
            issue_codes=("ambiguous_color",),
        ),
        SupplyItemReview(
            review_id="settled",
            req_id="settled",
            child_id="child-1",
            item_name="erasers",
            required_quantity=2,
            source_text="2 erasers",
            confidence=1.0,
        ),
    )

    class WidgetAwareState(dict[str, object]):
        def __init__(self, values: dict[str, object]) -> None:
            super().__init__(values)
            self.widget_keys: set[str] = set()
            self.button_keys: set[str] = set()
            self.application_assignments: set[str] = set()

        def __setitem__(self, key: str, value: object) -> None:
            self.application_assignments.add(key)
            if key in self.button_keys:
                raise AssertionError(
                    f"Application assigned button-owned key {key}"
                )
            if key in self.widget_keys:
                raise AssertionError(
                    f"Application assigned widget-owned key {key}"
                )
            super().__setitem__(key, value)

        def set_widget(self, key: str, value: object) -> None:
            dict.__setitem__(self, key, value)

        def register_button(self, key: str) -> None:
            if key in self.application_assignments:
                raise AssertionError(
                    f"Button key was assigned before render: {key}"
                )
            self.button_keys.add(key)

    state = WidgetAwareState({
        "intake": {
            "children": (
                {"child_id": "child-1", "label": "Kevin"},
            )
        },
        "extracted_lists": {
            "child-1": ExtractionEnvelope(
                catalog_unavailable_items=(
                    CatalogUnavailableItem(
                        child_id="child-1",
                        item_name="graphing_calculator",
                        source_line="1 graphing calculator",
                    ),
                ),
            )
        },
        "review_items": rows,
        "parent_added_review_items": (),
        "extraction_errors": {},
        "list_inputs": (),
        app.PERSONALIZE_SELECTED_VIEW_KEY: "child-1",
    })
    _mark_personalize_review_cache_current(state)

    class DecisionScreenRecorder:
        def __init__(self) -> None:
            self.session_state = state
            self.events: list[tuple[str, str]] = []
            self.radio_options: dict[str, tuple[str, ...]] = {}
            self.checkbox_callbacks: list[
                tuple[str, str, object, tuple[object, ...]]
            ] = []
            self.button_callbacks: list[
                tuple[str, object, tuple[object, ...]]
            ] = []
            self.container_keys: list[str] = []
            self.components = SimpleNamespace(
                v1=SimpleNamespace(html=lambda *args, **kwargs: None)
            )

        def __enter__(self) -> "DecisionScreenRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def columns(
            self,
            spec: object,
            **kwargs: object,
        ) -> tuple["DecisionScreenRecorder", ...]:
            del kwargs
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def container(self, **kwargs: object) -> "DecisionScreenRecorder":
            key = kwargs.get("key")
            if isinstance(key, str):
                self.container_keys.append(key)
            return self

        def expander(
            self,
            label: str,
            **kwargs: object,
        ) -> "DecisionScreenRecorder":
            del kwargs
            self.events.append(("expander", label))
            return self

        def header(self, value: object) -> None:
            self.events.append(("header", str(value)))

        def subheader(self, value: object) -> None:
            self.events.append(("subheader", str(value)))

        def caption(self, value: object) -> None:
            self.events.append(("caption", str(value)))

        def markdown(self, value: object, **kwargs: object) -> None:
            del kwargs
            self.events.append(("markdown", str(value)))

        def warning(self, value: object) -> None:
            self.events.append(("warning", str(value)))

        def success(self, value: object) -> None:
            self.events.append(("success", str(value)))

        def error(self, value: object) -> None:
            self.events.append(("error", str(value)))

        def write(self, value: object) -> None:
            self.events.append(("write", str(value)))

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            index: int | None = 0,
            **kwargs: object,
        ) -> str:
            del kwargs
            selected_index = 0 if index is None else index
            if key not in self.session_state:
                self.session_state.set_widget(
                    key,
                    options[selected_index],
                )
            self.session_state.widget_keys.add(key)
            self.events.append(("radio", label))
            self.radio_options[label] = options
            return str(self.session_state[key])

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            value: bool = False,
            on_change: object | None = None,
            args: tuple[object, ...] = (),
            **kwargs: object,
        ) -> bool:
            del kwargs
            if key not in self.session_state:
                self.session_state.set_widget(key, value)
            self.session_state.widget_keys.add(key)
            self.events.append(("checkbox", label))
            if on_change is not None:
                self.checkbox_callbacks.append(
                    (label, key, on_change, args)
                )
            return bool(self.session_state[key])

        def number_input(
            self,
            label: str,
            *,
            key: str,
            value: int,
            **kwargs: object,
        ) -> int:
            del kwargs
            if key not in self.session_state:
                self.session_state.set_widget(key, value)
            self.session_state.widget_keys.add(key)
            self.events.append(("number_input", label))
            return int(self.session_state[key])

        def selectbox(
            self,
            label: str,
            *,
            options: tuple[str, ...],
            index: int = 0,
            key: str,
            **kwargs: object,
        ) -> str:
            del kwargs
            if key not in self.session_state:
                self.session_state.set_widget(key, options[index])
            self.session_state.widget_keys.add(key)
            self.events.append(("selectbox", label))
            return str(self.session_state[key])

        def text_input(
            self,
            label: str,
            *,
            key: str,
            value: str = "",
            **kwargs: object,
        ) -> str:
            del kwargs
            if key not in self.session_state:
                self.session_state.set_widget(key, value)
            self.session_state.widget_keys.add(key)
            self.events.append(("text_input", label))
            return str(self.session_state[key])

        def button(self, label: str, **kwargs: object) -> bool:
            key = kwargs.get("key")
            if isinstance(key, str):
                self.session_state.register_button(key)
            self.events.append(("button", label))
            on_click = kwargs.get("on_click")
            if on_click is not None:
                self.button_callbacks.append(
                    (
                        label,
                        on_click,
                        tuple(kwargs.get("args", ())),
                    )
                )
            return False

        def rerun(self) -> None:
            raise AssertionError("No control was clicked")

    monkeypatch.setattr(
        app,
        "_render_review_detail_controls",
        lambda st, item, **kwargs: item,
    )
    monkeypatch.setattr(
        app,
        "_render_settled_review_row",
        lambda st, item, **kwargs: item,
    )
    monkeypatch.setattr(
        app,
        "_personalize_source_summary",
        lambda *args, **kwargs: None,
    )
    recorder = DecisionScreenRecorder()
    app._render_review(recorder)
    events = recorder.events

    assert sum(
        event == ("button", "Approve this recommendation")
        for event in events
    ) == 7
    assert sum(
        event == ("button", "We already own this item")
        for event in events
    ) == 7
    assert sum(
        event == ("button", "Remove item from cart")
        for event in events
    ) == 7
    assert sum(
        event == ("button", "Change item or quantity")
        for event in events
    ) == 5
    assert ("button", "Change package quantity") in events
    assert ("button", "Change brand details") in events
    assert sum(
        event == ("button", "Send selection to cart")
        for event in events
    ) == 0
    assert (
        "checkbox",
        "I have checked this choice",
    ) not in events
    assert (
        "warning",
        "The list did not give a quantity for pencils. "
        "The AI recommended 1.",
    ) in events
    assert (
        "warning",
        "The list did not say how many notebook paper were in the package. "
        "The AI assumed 150 per package.",
    ) in events
    state.set_widget(
        "review-flag-1:decision-action",
        app.PERSONALIZE_EDIT_RECOMMENDATION_ACTION,
    )
    state.set_widget("review-flag-1:decision-quantity", 5)
    edited_recorder = DecisionScreenRecorder()
    app._render_review(edited_recorder)
    assert sum(
        event == ("button", "Send selection to cart")
        for event in edited_recorder.events
    ) == 1
    assert (
        "markdown",
        "**5 pencils**",
    ) in edited_recorder.events
    assert (
        "caption",
        "List requested: 1 pencil",
    ) in edited_recorder.events
    edited_send = next(
        callback
        for callback in edited_recorder.button_callbacks
        if callback[0] == "Send selection to cart"
    )
    edited_send[1](*edited_send[2])  # type: ignore[operator]
    assert state[app.PERSONALIZE_PARENT_EDITED_GROUP_IDS_KEY] == (
        frozenset({"review-flag-1"})
    )
    assert tuple(state["review_items"])[0].item_name == "pencils"
    assert tuple(state["review_items"])[0].required_quantity == 5

    accepting_default = [
        callback
        for callback in recorder.button_callbacks
        if callback[0] == "Approve this recommendation"
    ][1]
    accepting_default[1](*accepting_default[2])  # type: ignore[operator]
    assert state[app.PERSONALIZE_CONFIRMED_GROUP_IDS_KEY] == frozenset(
        {"review-flag-2"}
    )

    remove_action = next(
        callback
        for callback in recorder.button_callbacks
        if callback[0] == "Remove item from cart"
    )
    remove_action[1](*remove_action[2])  # type: ignore[operator]
    removed = tuple(state["review_items"])[0]
    assert removed.required_quantity == 0
    assert removed.review_status == "deleted"
    assert removed.already_owned is False

    unavailable_position = events.index(
        ("expander", "Not available from these stores (1)")
    )
    cart_position = events.index(("markdown", "**In your cart (1)**"))
    assert cart_position < unavailable_position
    assert "personalize-unavailable-student-child-1" in (
        recorder.container_keys
    )
    assert "add:child-1:add" in state.button_keys


def test_personalize_edit_updates_student_summary_and_detail_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BR-52: production Personalize uses one resolved item and quantity."""

    original = SupplyItemReview(
        review_id="crayon",
        req_id="crayon",
        child_id="child-1",
        item_name="crayons",
        required_quantity=1,
        brand="Crayola",
        source_text="1 Crayola crayon",
        confidence=1.0,
    )

    class StrictState(dict[str, object]):
        def __init__(self, values: dict[str, object]) -> None:
            super().__init__(values)
            self.widget_keys: set[str] = set()
            self.button_keys: set[str] = set()
            self.application_assignments: set[str] = set()

        def __setitem__(self, key: str, value: object) -> None:
            self.application_assignments.add(key)
            if key in self.button_keys or key in self.widget_keys:
                raise AssertionError(f"Application assigned widget key {key}")
            super().__setitem__(key, value)

        def set_widget(self, key: str, value: object) -> None:
            dict.__setitem__(self, key, value)

        def register_widget(self, key: str) -> None:
            self.widget_keys.add(key)

        def register_button(self, key: str) -> None:
            if key in self.application_assignments:
                raise AssertionError(
                    f"Button key was assigned before render: {key}"
                )
            self.button_keys.add(key)

    state = StrictState({
        "intake": {
            "children": (
                {"child_id": "child-1", "label": "Kevin"},
            )
        },
        "extracted_lists": {
            "child-1": ExtractionEnvelope(
                requirements=(
                    Requirement(
                        req_id="crayon",
                        child_id="child-1",
                        raw_text="1 Crayola crayon",
                        canonical_item="crayons",
                        quantity=1,
                        brand_hint="Crayola",
                        extraction_confidence=1.0,
                    ),
                )
            )
        },
        "review_items": (original,),
        "parent_added_review_items": (),
        "extraction_errors": {},
        "list_inputs": (),
        app.PERSONALIZE_SELECTED_VIEW_KEY: "child-1",
    })
    _mark_personalize_review_cache_current(state)

    class Recorder:
        def __init__(self) -> None:
            self.session_state = state
            self.messages: list[tuple[str, str]] = []
            self.buttons: list[str] = []
            self.popovers: list[str] = []
            self.input_values: dict[str, object] = {}
            self.components = SimpleNamespace(
                v1=SimpleNamespace(html=lambda *args, **kwargs: None)
            )

        def __enter__(self) -> "Recorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def columns(
            self,
            spec: object,
            **kwargs: object,
        ) -> tuple["Recorder", ...]:
            del kwargs
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def container(self, **kwargs: object) -> "Recorder":
            del kwargs
            return self

        def expander(self, label: str, **kwargs: object) -> "Recorder":
            del kwargs
            self.messages.append(("expander", label))
            return self

        def popover(self, label: str, **kwargs: object) -> "Recorder":
            del kwargs
            self.popovers.append(label)
            return self

        def _record(self, kind: str, value: object) -> None:
            self.messages.append((kind, str(value)))

        def header(self, value: object) -> None:
            self._record("header", value)

        def subheader(self, value: object) -> None:
            self._record("subheader", value)

        def caption(self, value: object) -> None:
            self._record("caption", value)

        def markdown(self, value: object, **kwargs: object) -> None:
            del kwargs
            self._record("markdown", value)

        def warning(self, value: object) -> None:
            self._record("warning", value)

        def success(self, value: object) -> None:
            self._record("success", value)

        def error(self, value: object) -> None:
            self._record("error", value)

        def write(self, value: object) -> None:
            self._record("write", value)

        def _widget(
            self,
            key: str,
            value: object,
        ) -> object:
            if key not in state:
                state.set_widget(key, value)
            state.register_widget(key)
            self.input_values[key] = state[key]
            return state[key]

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            index: int | None = 0,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            selected = options[0 if index is None else index]
            return str(self._widget(key, selected))

        def selectbox(
            self,
            label: str,
            *,
            options: tuple[str, ...],
            key: str,
            index: int = 0,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(self._widget(key, options[index]))

        def number_input(
            self,
            label: str,
            *,
            key: str,
            value: int,
            **kwargs: object,
        ) -> int:
            del label, kwargs
            return int(self._widget(key, value))

        def text_input(
            self,
            label: str,
            *,
            key: str,
            value: str = "",
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(self._widget(key, value))

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            value: bool = False,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            return bool(self._widget(key, value))

        def toggle(
            self,
            label: str,
            *,
            key: str,
            value: bool = False,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            return bool(self._widget(key, value))

        def button(self, label: str, **kwargs: object) -> bool:
            key = kwargs.get("key")
            if isinstance(key, str):
                state.register_button(key)
            self.buttons.append(label)
            return False

        def rerun(self) -> None:
            raise AssertionError("No control was clicked")

    monkeypatch.setattr(
        app,
        "_personalize_source_summary",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_new_review_item_from_controls",
        lambda *args, **kwargs: None,
    )

    first = Recorder()
    app._render_review(first)
    state.set_widget("settled:crayon:quantity", 2)
    state.set_widget("settled:crayon:more-options", True)
    state.set_widget("settled:crayon:item", "markers")

    edited_student = Recorder()
    app._render_review(edited_student)
    assert any(
        kind == "expander" and "2 Crayola markers" in text
        for kind, text in edited_student.messages
    )
    assert (
        "caption",
        "List requested: 1 Crayola crayon",
    ) in edited_student.messages
    assert edited_student.input_values["settled:crayon:quantity"] == 2
    assert edited_student.input_values["settled:crayon:item"] == "markers"

    app._select_personalize_tab(state, "summary")
    summary = Recorder()
    app._render_review(summary)
    assert "Crayola Markers" not in summary.buttons
    assert "Crayola Markers" not in summary.popovers
    assert (
        "markdown",
        "**1**  \nIn cart",
    ) in summary.messages
    assert (
        "markdown",
        "**0**  \nNeeds a decision",
    ) in summary.messages
    assert (
        "markdown",
        "**0**  \nOptional",
    ) in summary.messages


def test_personalize_summary_opens_typed_and_uploaded_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BR-52/BR-64: the production Summary opens both retained source types."""

    typed_text = "12 pencils\n1 box of tissues\n"
    pdf_path = (
        Path(__file__).parent
        / "sample_lists"
        / "Machiasschoolsupplylist 1.pdf"
    )
    typed_envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="typed-pencils",
                child_id="child-1",
                raw_text="12 pencils",
                canonical_item="pencils",
                quantity=12,
                extraction_confidence=1.0,
            ),
        ),
    )
    pdf_envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="pdf-backpack",
                child_id="child-2",
                raw_text="Backpack or book bag",
                canonical_item="backpacks",
                quantity=1,
                source_document=pdf_path.name,
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="pdf-pencils",
                child_id="child-2",
                raw_text="Ticonderoga #2 pencils",
                canonical_item="pencils",
                quantity=12,
                source_document=pdf_path.name,
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        ),
        document_selection=DocumentSelection(
            selected_section_ids=("grade-5", "highly-capable"),
            selected_section_labels=("5th Grade", "Highly Capable Class"),
            selected_page_numbers=(2, 3),
        ),
    )
    state: dict[str, object] = {
        "intake": {
            "children": (
                {"child_id": "child-1", "label": "Kevin"},
                {"child_id": "child-2", "label": "Maya"},
            )
        },
        "extracted_lists": {
            "child-1": typed_envelope,
            "child-2": pdf_envelope,
        },
        "review_items": organize_extractions(
            {"child-1": typed_envelope, "child-2": pdf_envelope}
        ),
        "parent_added_review_items": (),
        "extraction_errors": {},
        "list_inputs": (
            app._build_pasted_list_input(
                child_id="child-1",
                text=typed_text,
                document_name="Kevin's supply list",
            ),
            ListInput(
                child_id="child-2",
                source=pdf_path.read_bytes(),
                mime_type="application/pdf",
                document_name=pdf_path.name,
            ),
        ),
        app.PERSONALIZE_SELECTED_VIEW_KEY: "summary",
    }
    _mark_personalize_review_cache_current(state)

    monkeypatch.setattr(
        app,
        "_render_compact_review_row",
        lambda st, members, *args, **kwargs: (
            {item.review_id: item for item in members},
            False,
        ),
    )
    monkeypatch.setattr(
        app,
        "_render_settled_review_row",
        lambda st, item, *args, **kwargs: item,
    )

    class SourceScreenRecorder:
        def __init__(self) -> None:
            self.session_state = state
            self.messages: list[str] = []
            self.popovers: list[str] = []
            self.text_sources: list[str] = []
            self.pdf_pages: list[bytes] = []
            self.column_specs: list[object] = []

        def __enter__(self) -> "SourceScreenRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def columns(
            self,
            spec: object,
            **kwargs: object,
        ) -> tuple["SourceScreenRecorder", ...]:
            del kwargs
            self.column_specs.append(spec)
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def container(self, **kwargs: object) -> "SourceScreenRecorder":
            del kwargs
            return self

        def expander(
            self,
            label: str,
            **kwargs: object,
        ) -> "SourceScreenRecorder":
            del kwargs
            self.messages.append(str(label))
            return self

        def popover(
            self,
            label: str,
            **kwargs: object,
        ) -> "SourceScreenRecorder":
            del kwargs
            self.popovers.append(label)
            return self

        def header(self, value: object) -> None:
            self.messages.append(str(value))

        def caption(self, value: object) -> None:
            self.messages.append(str(value))

        def markdown(self, value: object, **kwargs: object) -> None:
            del kwargs
            self.messages.append(str(value))

        def warning(self, value: object) -> None:
            self.messages.append(str(value))

        def success(self, value: object) -> None:
            self.messages.append(str(value))

        def error(self, value: object) -> None:
            self.messages.append(str(value))

        def write(self, value: object) -> None:
            self.messages.append(str(value))

        def code(
            self,
            value: str,
            *,
            language: str | None,
            wrap_lines: bool,
        ) -> None:
            assert language is None
            assert wrap_lines is False
            self.text_sources.append(value)

        def image(self, value: bytes, **kwargs: object) -> None:
            del kwargs
            self.pdf_pages.append(value)

        def info(self, value: object) -> None:
            raise AssertionError(value)

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            index: int,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            self.session_state.setdefault(key, options[index])
            return str(self.session_state[key])

        def button(self, label: str, **kwargs: object) -> bool:
            del label, kwargs
            return False

        def rerun(self) -> None:
            raise AssertionError("No control was clicked")

    recorder = SourceScreenRecorder()
    app._render_review(recorder)

    assert recorder.popovers.count("Open source pages") == 2
    assert recorder.text_sources == [typed_text]
    assert len(recorder.pdf_pages) == 2
    assert recorder.column_specs.count([4.8, 1.2]) == 2
    assert recorder.column_specs.count(3) == 2
    assert "**Sources used**" not in recorder.messages
    assert any("Sections read: 5th Grade and Highly Capable Class" in message for message in recorder.messages)
    assert any(f"{pdf_path.name} · page 2" in message for message in recorder.messages)
    assert any(f"{pdf_path.name} · page 3" in message for message in recorder.messages)

    state["list_inputs"] = (state["list_inputs"][0],)
    pasted_only = SourceScreenRecorder()
    app._render_review(pasted_only)
    assert pasted_only.popovers.count("Open source pages") == 1
    assert pasted_only.text_sources == [typed_text]


def test_personalize_source_summary_extracts_scope_and_deduplicates_gaps() -> None:
    """BR-57/BR-58: production rendering names scope and one source gap."""

    class SourceRecorder:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {"list_inputs": ()}
            self.captions: list[str] = []
            self.writes: list[str] = []
            self.errors: list[str] = []
            self.expanders: list[str] = []

        def __enter__(self) -> "SourceRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def caption(self, value: object) -> None:
            self.captions.append(str(value))

        def write(self, value: object) -> None:
            self.writes.append(str(value))

        def markdown(self, value: object, **kwargs: object) -> None:
            del value, kwargs

        def error(self, value: object) -> None:
            self.errors.append(str(value))

        def warning(self, value: object) -> None:
            self.writes.append(str(value))

        def expander(self, label: str, **kwargs: object) -> object:
            del kwargs
            self.expanders.append(label)
            return self

    envelope = ExtractionEnvelope(
        document_selection=DocumentSelection(
            selected_section_ids=("grade-5",),
            selected_section_labels=("5th Grade",),
            ignored_section_ids=("grade-2", "grade-3"),
            ignored_section_labels=("2nd Grade", "3rd Grade"),
        ),
        catalog_unavailable_items=(
            CatalogUnavailableItem(
                child_id="child-1",
                item_name="tape",
                source_line="1 | Scotch tape",
                document_name="district.pdf",
                section_name="5th Grade",
                page_number=3,
            ),
            CatalogUnavailableItem(
                child_id="child-1",
                item_name="tape",
                source_line="1 | Scotch tape",
                document_name="district.pdf",
                section_name="Highly Capable",
                page_number=3,
            ),
        ),
    )
    recorder = SourceRecorder()

    app._personalize_source_summary(
        recorder,
        "child-1",
        envelope,
    )
    app._render_personalize_unavailable(
        recorder,
        "child-1",
        envelope,
        (),
    )

    assert recorder.captions == ["List section: 5th Grade"]
    assert recorder.errors == []
    assert recorder.writes == ["1 Scotch tape"]
    assert recorder.expanders == [
        "Not available from these stores (1)"
    ]


def test_personalize_typed_list_omits_page_count_and_names_skipped_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BR-52/BR-64: the production summary uses useful typed-list wording."""

    class Recorder:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {
                "list_inputs": (
                    ListInput(
                        child_id="child-1",
                        source="1 pencil\nBring on Monday",
                        mime_type="text/plain",
                        document_name="Kevin's supply list",
                        source_page_texts=(
                            "1 pencil\nBring on Monday",
                        ),
                    ),
                )
            }
            self.captions: list[str] = []
            self.markdowns: list[str] = []
            self.writes: list[str] = []

        def caption(self, value: object) -> None:
            self.captions.append(str(value))

        def markdown(self, value: object) -> None:
            self.markdowns.append(str(value))

        def write(self, value: object) -> None:
            self.writes.append(str(value))

        def warning(self, value: object) -> None:
            self.writes.append(str(value))

    monkeypatch.setattr(
        app,
        "_render_source_reference",
        lambda *args, **kwargs: None,
    )
    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="pencil",
                child_id="child-1",
                raw_text="1 pencil",
                canonical_item="pencils",
                quantity=1,
                source_document="Kevin's supply list",
                source_page=1,
                extraction_confidence=1.0,
            ),
        ),
        skipped_lines=("Teacher direction: Bring on Monday",),
    )
    recorder = Recorder()

    app._personalize_source_summary(recorder, "child-1", envelope)

    assert all("page" not in caption.casefold() for caption in recorder.captions)
    assert recorder.markdowns == ["**List lines not added to the cart (1)**"]
    assert recorder.writes == ["Teacher direction: Bring on Monday"]


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
                        source_line="Grade 2",
                    ),
                DocumentSection(
                        section_id="grade-5",
                        label="Grade 5",
                        grades=("Grade 5",),
                        source_line="Grade 5",
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
                source_line="SECOND GRADE",
            ),
            DocumentSection(
                section_id="grade-5",
                label="Fifth Grade",
                grades=("Grade 5",),
                page_numbers=(2,),
                column_label="FIFTH GRADE",
                source_line="FIFTH GRADE",
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
        (
            ListInput(
                child_id="child-1",
                source="district list",
                document_name="district-list.txt",
            ),
        ),
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
    assert (
        extractions["child-1"].requirements[0].source_document
        == "district-list.txt"
    )


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
                source_line="2nd Grade",
            ),
            DocumentSection(
                section_id="grade-5",
                label="5th Grade",
                grades=("5th Grade",),
                page_numbers=(1,),
                language="English",
                source_line="5th Grade",
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


def test_section_table_is_sparse_and_omits_translated_duplicates() -> None:
    """BR-16: translated copies are provenance, not selectable rows."""

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
                source_line="Grade 2",
            ),
            DocumentSection(
                section_id="grade-5-en",
                label="Grade 5",
                grades=("Grade 5",),
                page_numbers=(2,),
                language="English",
                source_line="Grade 5",
            ),
            DocumentSection(
                section_id="grade-2-es",
                label="Grade 2",
                grades=("Grade 2",),
                page_numbers=(1,),
                language="Spanish",
                source_line="Grado 2",
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
    assert len(rows) == 2
    assert all(row["Language"] == "English" for row in rows)
    assert all("Teacher" not in row for row in rows)
    assert all("Status" not in row for row in rows)
    assert all(
        "the selected entries" not in value
        for row in rows
        for value in row.values()
    )


def test_brand_choice_is_mutually_exclusive_in_production_shape() -> None:
    """BR-24: exact brand and equivalent brands cannot both be active."""

    item = SupplyItemReview(
        review_id="review",
        req_id="req",
        child_id="child-1",
        item_name="pencils",
        required_quantity=1,
        source_text="1 pencil",
        confidence=1.0,
        brand="Ticonderoga",
        brand_required=True,
        allow_equivalents=True,
    )

    assert item.brand_required is True
    assert item.allow_equivalents is False
    empty_brand = item.model_copy(
        update={"brand": None, "brand_required": True}
    )
    validated = SupplyItemReview.model_validate(empty_brand.model_dump())
    assert validated.brand_required is False
    assert validated.allow_equivalents is True
    source = inspect.getsource(app._render_review_detail_controls)
    assert 'radio(' in source
    assert '"Brand choice"' in source
    assert '"Exact brand required"' in source
    assert '"Allow equivalent brands"' not in source


def test_preferred_brand_populates_brand_without_creating_lock() -> None:
    """BR-24: a preferred brand is a visible hint with equivalents allowed."""

    requirement = Requirement(
        req_id="pencils",
        child_id="child-1",
        raw_text="48 Ticonderoga pencils preferred",
        canonical_item="pencils",
        quantity=48,
        brand_lock="Ticonderoga",
        attributes={"other_details": "Ticonderoga preferred"},
        extraction_confidence=1.0,
    )
    row = organize_extractions(
        {"child-1": ExtractionEnvelope(requirements=(requirement,))}
    )[0]

    assert requirement.brand_lock is None
    assert requirement.brand_hint == "Ticonderoga"
    assert requirement.attributes.other_details is None
    assert row.brand == "Ticonderoga"
    assert row.brand_required is False
    assert row.allow_equivalents is True


def test_already_owned_sets_visible_quantity_zero_and_excludes_cart() -> None:
    """FR-12: marking an item owned visibly zeroes and removes its cart need."""

    item = SupplyItemReview(
        review_id="review",
        req_id="pencils",
        child_id="child-1",
        item_name="pencils",
        required_quantity=24,
        source_text="24 pencils",
        confidence=1.0,
        review_status="confirmed",
    )

    updated = app._review_control_update(
        item,
        item_name="pencils",
        quantity=24,
        unit="each",
        package_size=None,
        brand="",
        brand_required=False,
        size="",
        material="",
        colors="",
        required_details="",
        optional=False,
        supply_scope="unspecified",
        allow_equivalents=True,
        already_owned=True,
            delete=False,
    )

    assert updated.required_quantity == 0
    assert app.review_understanding_text(updated) == "0 pencils"
    assert confirmed_requirements((updated,)) == ()


def test_merge_quick_choices_and_quantity_field_share_one_state() -> None:
    """BR-30: radio shortcuts and editable quantity are one selection state."""

    merged = consolidate_requirements(
        (
            Requirement(
                req_id="grade",
                child_id="child-1",
                raw_text="48 pencils",
                canonical_item="pencils",
                quantity=48,
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="capable",
                child_id="child-1",
                raw_text="36 pencils",
                canonical_item="pencils",
                quantity=36,
                source_document="district.pdf",
                source_section="Highly Capable",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )
    interrupt = merged.interrupts[0]
    choices = app.quantity_quick_choice_values(interrupt)
    total_label, largest_label = tuple(choices)[:2]
    assert total_label == (
        "**84** — Quantities from both lists added together"
    )
    assert largest_label == "**48** — Quantity from 5th Grade"
    assert app.quantity_quick_choice_default_label(
        interrupt,
        choices,
    ) == largest_label
    assert all("selected" not in label for label in choices)
    assert app.quantity_preselection_rationale(interrupt) == (
        "Adding both amounts would come to 84 pencils, which looked like more "
        "than one student would need, so we've preselected the larger single "
        "request of 48 instead."
    )
    state: dict[str, object] = {"choice": total_label, "quantity": 48}

    app.apply_merge_quick_choice(
        state,
        "choice",
        {interrupt.interrupt_id: "quantity"},
        choices,
    )
    assert state["quantity"] == 84

    state["quantity"] = 50
    app.mark_merge_quantities_custom(
        state,
        "choice",
        app.MERGE_CUSTOM_QUANTITY_LABEL,
    )
    assert state["choice"] == app.MERGE_CUSTOM_QUANTITY_LABEL

    state["choice"] = largest_label
    app.apply_merge_quick_choice(
        state,
        "choice",
        {interrupt.interrupt_id: "quantity"},
        choices,
    )
    assert state["quantity"] == 48


def test_durable_quantity_default_keeps_combined_choice_without_selecting_it() -> None:
    """BR-47: repeated backpacks default to one, with two still available."""

    merged = consolidate_requirements(
        (
            Requirement(
                req_id="grade",
                child_id="child-1",
                raw_text="1 Backpack",
                canonical_item="backpacks",
                quantity=1,
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="capable",
                child_id="child-1",
                raw_text="1 | Backpack or book bag",
                canonical_item="backpacks",
                quantity=1,
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )
    interrupt = merged.interrupts[0]
    choices = app.quantity_quick_choice_values(interrupt)

    assert tuple(choices.values())[0] == 2
    assert app.quantity_quick_choice_default_label(
        interrupt,
        choices,
    ) == "**1** — Quantity from 5th Grade"
    assert app.quantity_preselection_rationale(interrupt) == (
        "We think backpacks are more likely to be reused than used up, so "
        "we've preselected one instead of adding both requests together."
    )


def test_type_a_quantity_choices_do_not_repeat_source_text() -> None:
    """BR-30: Type A labels are concise and keep evidence in the table."""

    merged = consolidate_requirements(
        (
            Requirement(
                req_id="page-2",
                child_id="child-1",
                raw_text="4 boxes of tissues for the classroom",
                canonical_item="tissues",
                quantity=4,
                source_document="district.pdf",
                source_section="Grade 5",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="page-3",
                child_id="child-1",
                raw_text="1 box of tissues",
                canonical_item="tissues",
                quantity=1,
                source_document="district.pdf",
                source_section="Highly Capable",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )
    interrupt = item_decisions(merged)[0].quantity_interrupt
    assert interrupt is not None

    labels = tuple(app.quantity_quick_choice_values(interrupt))

    assert labels == (
        "**5** — Quantities from both lists added together",
        "**4** — Quantity from Grade 5",
        "**1** — Quantity from Highly Capable",
        "Enter my own",
    )
    assert all("selected" not in label for label in labels)
    assert all("page " not in label for label in labels)
    assert all("larger of the listed amounts" not in label for label in labels)
    assert all(
        label == "Enter my own" or label.startswith("**")
        for label in labels
    )
    assert all("tissues" not in label for label in labels)
    assert app.quantity_preselection_rationale(interrupt) == (
        "Both parts of the list ask for tissues. We expect tissues to get "
        "used up, so we've added the amounts together. Change it if that's "
        "more than you need."
    )
    assert app.visible_quantity_preselection_rationale(
        interrupt,
        labels[0],
        app.quantity_quick_choice_values(interrupt),
    ) is not None
    assert app.visible_quantity_preselection_rationale(
        interrupt,
        labels[1],
        app.quantity_quick_choice_values(interrupt),
    ) is None


def test_equal_quantity_source_choice_keeps_preselection_rationale() -> None:
    """BR-45 amended: equal-value source alternatives keep the rationale."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="grade",
                child_id="child-1",
                raw_text="1 pair scissors",
                canonical_item="scissors",
                quantity=1,
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="capable",
                child_id="child-1",
                raw_text="1 scissors",
                canonical_item="scissors",
                quantity=1,
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )
    interrupt = result.interrupts[0]
    choices = app.quantity_quick_choice_values(interrupt)
    equal_source_labels = tuple(
        label
        for label, quantity in choices.items()
        if quantity == interrupt.default_quantity
    )

    assert len(equal_source_labels) == 2
    assert all(
        app.visible_quantity_preselection_rationale(
            interrupt,
            label,
            choices,
        )
        is not None
        for label in equal_source_labels
    )


def test_exclusion_actions_zero_the_visible_quantity_state() -> None:
    """BR-56: conflict, owned, and delete controls all visibly set zero."""

    merge_state: dict[str, object] = {
        "exclude": True,
        "choice": "**1** — Quantity from Grade 5",
        "quantity": 1,
        "custom-pending": True,
    }
    app.apply_merge_item_exclusion(
        merge_state,
        "exclude",
        "choice",
        ("quantity",),
        "custom-pending",
    )

    assert merge_state["choice"] == app.MERGE_CUSTOM_QUANTITY_LABEL
    assert merge_state["quantity"] == 0
    assert merge_state["custom-pending"] is False

    variant_state: dict[str, object] = {
        "exclude": True,
        "graph": 0,
        "lined": 0,
    }
    app.mark_merge_quantity_confirmed(
        variant_state,
        "graph-confirmed",
        "exclude",
        ("graph", "lined"),
    )
    assert variant_state["exclude"] is True
    variant_state["graph"] = 1
    app.mark_merge_quantity_confirmed(
        variant_state,
        "graph-confirmed",
        "exclude",
        ("graph", "lined"),
    )
    assert variant_state["exclude"] is False

    for trigger in ("owned", "delete"):
        review_state: dict[str, object] = {
            trigger: True,
            "quantity": 3,
        }
        app.apply_review_exclusion_quantity(
            review_state,
            trigger,
            "quantity",
        )
        assert review_state["quantity"] == 0
        review_state[trigger] = False
        app.apply_review_exclusion_quantity(
            review_state,
            trigger,
            "quantity",
        )
        assert review_state["quantity"] == 3


@pytest.mark.parametrize("already_owned,delete", ((True, False), (False, True)))
def test_review_exclusions_persist_zero_in_production_item(
    already_owned: bool,
    delete: bool,
) -> None:
    """BR-56: the production review update cannot restore an excluded unit."""

    item = SupplyItemReview(
        review_id="review-scissors",
        req_id="scissors",
        child_id="child-1",
        item_name="scissors",
        required_quantity=1,
        source_text="1 scissors",
        confidence=1.0,
    )

    updated = app._review_control_update(
        item,
        item_name="scissors",
        quantity=1,
        unit="each",
        package_size=None,
        brand="",
        brand_required=False,
        size="",
        material="",
        colors="",
        required_details="",
        optional=False,
        allow_equivalents=True,
        already_owned=already_owned,
            delete=delete,
    )

    assert updated.required_quantity == 0


def test_package_preference_is_hidden_for_every_single_instance_item() -> None:
    """BR-54: reusable single-instance items have no package preference."""

    hidden = {
        item
        for item in app.SINGLE_INSTANCE_REQUIREMENT_ITEMS
        if not app.show_package_preference(item)
    }

    assert hidden == app.SINGLE_INSTANCE_REQUIREMENT_ITEMS
    assert app.show_package_preference("pencils")
    assert app.package_preference_labels() == {
        "minimum_cost_at_least": (
            "Extras are okay when they make the purchase cost less"
        ),
        "closest_quantity": "Avoid extra items, even if that costs more",
    }


def test_only_unresolved_wording_asks_identity_on_main_card() -> None:
    """BR-43: only unresolved residual wording asks on the main card."""

    quantity_only = item_decisions(
        consolidate_requirements(
            (
                Requirement(
                    req_id="one",
                    child_id="child-1",
                    raw_text="4 glue sticks",
                    canonical_item="glue_sticks",
                    quantity=4,
                    source_section="5th Grade",
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="two",
                    child_id="child-1",
                    raw_text="3 glue sticks",
                    canonical_item="glue_sticks",
                    quantity=3,
                    source_section="Highly Capable",
                    extraction_confidence=1.0,
                ),
            )
        )
    )[0]
    ambiguous = item_decisions(
        consolidate_requirements(
            (
                Requirement(
                    req_id="homework",
                    child_id="child-1",
                    raw_text="1 homework composition book",
                    canonical_item="composition_notebooks",
                    quantity=1,
                    source_section="5th Grade",
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="class",
                    child_id="child-1",
                    raw_text="4 class composition books",
                    canonical_item="composition_notebooks",
                    quantity=4,
                    source_section="Highly Capable",
                    extraction_confidence=1.0,
                ),
            )
        )
    )[0]

    assert not resolve_item_decision_state(
        quantity_only
    ).show_identity_on_main
    assert resolve_item_decision_state(ambiguous).show_identity_on_main


def test_identity_rationale_radio_and_quantity_share_resolved_state() -> None:
    """BR-44: stale widget state cannot contradict a Type B decision."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="cardboard",
                child_id="child-1",
                raw_text="3 cardboard pocket folders",
                canonical_item="folders",
                quantity=3,
                attributes={"material": "cardboard"},
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="plastic",
                child_id="child-1",
                raw_text="2 plastic pocket folders with fasteners",
                canonical_item="folders",
                quantity=2,
                attributes={
                    "material": "plastic",
                    "connector": "fasteners",
                },
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )
    decision = item_decisions(result)[0]
    identity_key = f"{decision.decision_id}:same-or-different"
    state: dict[str, object] = {
        identity_key: "The same product",
        f"{identity_key}:facts": "stale-fingerprint",
    }

    resolved = app.resolve_merge_identity_widget_state(
        state,
        decision,
        identity_key,
    )

    assert state[identity_key] == "Different products"
    assert resolved.selected_identity == "different"
    assert resolved.quantity_control == "variants"
    assert resolved.rationale == (
        "5th Grade asks for cardboard and Highly Capable Class asks for "
        "plastic. Those look like different folders to us, so we've kept "
        "them separate."
    )

    state[identity_key] = "The same product"
    overridden = app.resolve_merge_identity_widget_state(
        state,
        decision,
        identity_key,
    )

    assert overridden.selected_identity == "same"
    assert overridden.quantity_control == "combined"
    assert overridden.rationale is None


def test_same_product_override_remains_explained_in_personalize() -> None:
    """BR-44: the retained source-backed product remains visible afterward."""

    requirements = (
        Requirement(
            req_id="cardboard",
            child_id="child-1",
            raw_text="3 cardboard pocket folders",
            canonical_item="folders",
            quantity=3,
            attributes={"material": "cardboard"},
            source_document="district.pdf",
            source_section="5th Grade",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="plastic",
            child_id="child-1",
            raw_text="2 plastic pocket folders with fasteners",
            canonical_item="folders",
            quantity=2,
            attributes={
                "material": "plastic",
                "connector": "fasteners",
            },
            source_document="district.pdf",
            source_section="Highly Capable Class",
            source_page=3,
            extraction_confidence=1.0,
        ),
    )
    initial = consolidate_requirements(requirements)
    decision = item_decisions(initial)[0]
    resolved = consolidate_requirements(
        requirements,
        product_identity_choices={decision.decision_id: "same"},
    )
    review_item = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=resolved.requirements
            )
        }
    )[0]

    assert app.review_system_decision_messages(review_item) == (
        "We believe these 2 source lines describe one item; page 2 asks for "
        "3 and page 3 asks for 2. The cart uses 5. You chose one product, so "
        "the cart will use material: cardboard from 5th Grade. This keeps one "
        "real source description instead of mixing details from different "
        "products.",
    )


def test_conflict_rows_keep_production_exact_lines_separate_from_quantity() -> None:
    """BR-22/BR-36/BR-46: the actual renderer shows matrix item wording."""

    class RenderedMergeRecorder:
        def __init__(self) -> None:
            self.writes: list[str] = []
            self.headings: list[str] = []
            self.column_specs: list[tuple[float, ...]] = []

        def __enter__(self) -> "RenderedMergeRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def container(self, **kwargs: object) -> "RenderedMergeRecorder":
            del kwargs
            return self

        def columns(self, spec: object) -> tuple[RenderedColumn, ...]:
            assert isinstance(spec, list)
            self.column_specs.append(tuple(spec))
            return tuple(RenderedColumn(self) for _ in spec)

    class RenderedColumn:
        def __init__(self, recorder: RenderedMergeRecorder) -> None:
            self.recorder = recorder

        def markdown(self, value: object, **kwargs: object) -> None:
            del kwargs
            self.recorder.headings.append(str(value))

        def write(self, value: object) -> None:
            self.recorder.writes.append(str(value))

        def caption(self, value: object) -> None:
            del value

    def extractor(
        source: object,
        *,
        child_id: str,
        mime_type: str | None,
    ) -> ExtractionEnvelope:
        del source, mime_type
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="grade-five",
                    child_id=child_id,
                    raw_text=(
                        "Composition book (sewn binding) - graph paper "
                        "| 5th Grade: 1"
                    ),
                    canonical_item="composition_notebooks",
                    quantity=1,
                    attributes={"ruling": "graph"},
                    source_section="5th Grade",
                    source_page=2,
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="highly-capable",
                    child_id=child_id,
                    raw_text="4 | Regular composition books",
                    canonical_item="composition_notebooks",
                    quantity=4,
                    source_section="Highly Capable Class",
                    source_page=3,
                    extraction_confidence=1.0,
                ),
            )
        )

    extracted, errors = app._extract_list_inputs(
        (
            ListInput(
                child_id="child-1",
                source="rendered production document",
                mime_type="text/plain",
                document_name="district.pdf",
            ),
        ),
        extractor=extractor,
    )
    _, result = consolidate_extractions(extracted)
    decision = item_decisions(result)[0]
    recorder = RenderedMergeRecorder()
    app._render_merge_source_rows(
        recorder,
        decision,
        None,
        ("5th Grade", "Highly Capable Class"),
    )

    assert errors == {}
    assert tuple(source.exact_line for source in decision.sources) == (
        "Composition book (sewn binding) - graph paper | 5th Grade: 1",
        "4 | Regular composition books",
    )
    assert recorder.writes == [
        "1",
        "Composition book (sewn binding) - graph paper",
        "5th Grade",
        "4",
        "Regular composition books",
        "Highly Capable Class",
    ]
    assert recorder.headings == [
        "**Quantity**",
        "**What the list says**",
        "**Section**",
        "**Source**",
    ]
    assert recorder.column_specs == [
        (0.7, 3.2, 1.5, 2.8),
        (0.7, 3.2, 1.5, 2.8),
        (0.7, 3.2, 1.5, 2.8),
    ]

    ungraded_decision = replace(
        decision,
        sources=tuple(
            source.model_copy(update={"section_name": None})
            for source in decision.sources
        ),
    )
    ungraded_recorder = RenderedMergeRecorder()

    app._render_merge_source_rows(
        ungraded_recorder,
        ungraded_decision,
        None,
    )

    assert ungraded_recorder.writes == [
        "1",
        "Composition book (sewn binding) - graph paper",
        "",
        "4",
        "Regular composition books",
        "",
    ]


def test_lists_merge_screen_renders_parent_rationales_and_full_sections() -> None:
    """BR-40/BR-45/BR-47/BR-55: test the production Lists renderer."""

    requirements = (
        Requirement(
            req_id="backpack-grade",
            child_id="child-1",
            raw_text="1 backpack",
            canonical_item="backpacks",
            quantity=1,
            source_document="district.pdf",
            source_section="5th",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="backpack-capable",
            child_id="child-1",
            raw_text="1 book bag",
            canonical_item="backpacks",
            quantity=1,
            source_document="district.pdf",
            source_section="Highly Capable",
            source_page=3,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="tissues-grade",
            child_id="child-1",
            raw_text="4 boxes of tissues",
            canonical_item="tissues",
            quantity=4,
            source_document="district.pdf",
            source_section="5th",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="tissues-capable",
            child_id="child-1",
            raw_text="1 box of tissues",
            canonical_item="tissues",
            quantity=1,
            source_document="district.pdf",
            source_section="Highly Capable",
            source_page=3,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="pencils-grade",
            child_id="child-1",
            raw_text="48 pencils",
            canonical_item="pencils",
            quantity=48,
            source_document="district.pdf",
            source_section="5th",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="pencils-capable",
            child_id="child-1",
            raw_text="36 pencils",
            canonical_item="pencils",
            quantity=36,
            source_document="district.pdf",
            source_section="Highly Capable",
            source_page=3,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="folders-grade",
            child_id="child-1",
            raw_text="3 cardboard folders",
            canonical_item="folders",
            quantity=3,
            attributes={"material": "cardboard"},
            source_document="district.pdf",
            source_section="5th Grade",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="folders-capable",
            child_id="child-1",
            raw_text="2 plastic folders",
            canonical_item="folders",
            quantity=2,
            attributes={"material": "plastic"},
            source_document="district.pdf",
            source_section="Highly Capable Class",
            source_page=3,
            extraction_confidence=1.0,
        ),
    )
    envelope = ExtractionEnvelope(
        requirements=requirements,
        document_selection=DocumentSelection(
            selected_section_ids=("grade-five", "highly-capable"),
            selected_section_labels=(
                "5th Grade",
                "Highly Capable Class",
            ),
        ),
    )
    _, result = consolidate_extractions({"child-1": envelope})

    class ListsMergeRecorder:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {
                "requirement_merge_result": result,
                "unmerged_extracted_lists": {"child-1": envelope},
                "intake": {
                    "children": (
                        {"child_id": "child-1", "label": "Kevin"},
                    )
                },
                "list_inputs": (),
            }
            self.captions: list[str] = []
            self.events: list[tuple[str, str]] = []
            self.expander_labels: list[str] = []
            self.radio_options: list[tuple[str, ...]] = []
            self.writes: list[str] = []

        def __enter__(self) -> "ListsMergeRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def container(self, **kwargs: object) -> "ListsMergeRecorder":
            del kwargs
            return self

        def expander(
            self,
            label: str,
            **kwargs: object,
        ) -> "ListsMergeRecorder":
            del kwargs
            self.expander_labels.append(label)
            self.events.append(("expander", label))
            return self

        def columns(self, spec: object) -> tuple["ListsMergeRecorder", ...]:
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def header(self, value: object) -> None:
            del value

        def subheader(self, value: object) -> None:
            del value

        def write(self, value: object) -> None:
            self.writes.append(str(value))

        def markdown(self, value: object, **kwargs: object) -> None:
            del value, kwargs

        def caption(self, value: object) -> None:
            rendered = str(value)
            self.captions.append(rendered)
            self.events.append(("caption", rendered))

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            self.radio_options.append(tuple(options))
            return str(self.session_state[key])

        def number_input(
            self,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> int:
            del label, kwargs
            return int(self.session_state[key])

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            self.session_state.setdefault(key, False)
            return bool(self.session_state[key])

        def button(self, label: str, **kwargs: object) -> bool:
            del label, kwargs
            return False

        def warning(self, value: object) -> None:
            del value

        def error(self, value: object) -> None:
            del value

    recorder = ListsMergeRecorder()
    app._render_requirement_merge(recorder)

    rendered = "\n".join(recorder.captions)
    assert (
        "Rationale: We think backpacks are more likely to be reused than used "
        "up, so we've preselected one instead of adding both requests together."
        in rendered
    )
    assert (
        "Rationale: Both parts of the list ask for tissues. We expect tissues "
        "to get used up, so we've added the amounts together. Change it if "
        "that's more than you need."
        in rendered
    )
    assert (
        "Rationale: Adding both amounts would come to 84 pencils, which "
        "looked like more than one student would need, so we've preselected "
        "the larger single request of 48 instead."
        in rendered
    )
    assert (
        "Rationale: We believe both lines describe the same thing, just "
        "worded differently."
        in rendered
    )
    identity_rationale_event = (
        "caption",
        "Rationale: We believe both lines describe the same thing, just "
        "worded differently.",
    )
    identity_expander_event = (
        "expander",
        "Change your answer · one product or two?",
    )
    assert identity_rationale_event in recorder.events
    assert identity_expander_event in recorder.events
    assert recorder.events.index(identity_rationale_event) < recorder.events.index(
        identity_expander_event
    )
    assert (
        "More detail · same product or different products"
        not in recorder.expander_labels
    )
    assert (
        "Rationale: 5th Grade asks for cardboard and Highly Capable Class "
        "asks for plastic. Those look like different folders to us, so we've "
        "kept them separate."
        in rendered
    )
    assert all("working limit" not in caption for caption in recorder.captions)
    assert all(
        "This was resolved from the product details" not in caption
        for caption in recorder.captions
    )
    rendered_options = tuple(
        option
        for options in recorder.radio_options
        for option in options
    )
    assert "**1** — Quantity from 5th Grade" in rendered_options
    assert (
        "**1** — Quantity from Highly Capable Class"
        in rendered_options
    )
    assert "5th Grade" in recorder.writes
    assert "Highly Capable Class" in recorder.writes

    folder_decision = next(
        decision
        for decision in item_decisions(result)
        if decision.canonical_item == "folders"
    )
    identity_key = f"{folder_decision.decision_id}:same-or-different"
    recorder.session_state[identity_key] = "The same product"
    recorder.session_state[f"{identity_key}:facts"] = (
        resolve_item_decision_state(folder_decision).state_fingerprint
    )
    recorder.captions.clear()
    recorder.events.clear()
    app._render_requirement_merge(recorder)
    assert (
        "Result: You chose to treat these lines as the same product. The cart "
        "will use the product details from 5th Grade."
        in recorder.captions
    )
    result_event = (
        "caption",
        "Result: You chose to treat these lines as the same product. The cart "
        "will use the product details from 5th Grade.",
    )
    assert result_event in recorder.events
    result_index = recorder.events.index(result_event)
    assert recorder.events[result_index + 1] == identity_expander_event
    assert all(
        "Rationale: 5th Grade asks for cardboard" not in caption
        for caption in recorder.captions
    )

    backpack_decision = next(
        decision
        for decision in item_decisions(result)
        if decision.canonical_item == "backpacks"
    )
    backpack_identity_key = (
        f"{backpack_decision.decision_id}:same-or-different"
    )
    recorder.session_state[backpack_identity_key] = "Different products"
    recorder.session_state[f"{backpack_identity_key}:facts"] = (
        resolve_item_decision_state(backpack_decision).state_fingerprint
    )
    recorder.captions.clear()
    recorder.events.clear()
    app._render_requirement_merge(recorder)
    assert (
        "Result: You chose to treat these lines as different products."
        in recorder.captions
    )
    different_result_event = (
        "caption",
        "Result: You chose to treat these lines as different products.",
    )
    different_result_index = recorder.events.index(different_result_event)
    assert (
        recorder.events[different_result_index + 1]
        == identity_expander_event
    )


def test_lists_merge_screen_names_identical_backpack_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Identical Backpack evidence gets the exact-match rationale."""

    requirements = (
        Requirement(
            req_id="backpack-grade",
            child_id="child-1",
            raw_text="Backpack or book bag",
            canonical_item="backpacks",
            quantity=1,
            source_document="Machiasschoolsupplylist 1.pdf",
            source_section="5th",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="backpack-capable",
            child_id="child-1",
            raw_text="Backpack or book bag",
            canonical_item="backpacks",
            quantity=1,
            source_document="Machiasschoolsupplylist 1.pdf",
            source_section="Highly Capable Class",
            source_page=3,
            extraction_confidence=1.0,
        ),
    )
    envelope = ExtractionEnvelope(requirements=requirements)
    _, result = consolidate_extractions({"child-1": envelope})

    monkeypatch.setattr(
        app,
        "_render_merge_source_rows",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_render_merge_quantity_controls",
        lambda *args, **kwargs: ("source", 1),
    )

    class MergeScreenRecorder:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {
                "requirement_merge_result": result,
                "unmerged_extracted_lists": {"child-1": envelope},
                "intake": {
                    "children": (
                        {"child_id": "child-1", "label": "Jawan"},
                    )
                },
                "list_inputs": (),
            }
            self.writes: list[str] = []
            self.captions: list[str] = []

        def __enter__(self) -> "MergeScreenRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def container(self, **kwargs: object) -> "MergeScreenRecorder":
            del kwargs
            return self

        def expander(
            self,
            label: str,
            **kwargs: object,
        ) -> "MergeScreenRecorder":
            del label, kwargs
            return self

        def header(self, value: object) -> None:
            del value

        def subheader(self, value: object) -> None:
            del value

        def write(self, value: object) -> None:
            self.writes.append(str(value))

        def markdown(self, value: object, **kwargs: object) -> None:
            del value, kwargs

        def caption(self, value: object) -> None:
            self.captions.append(str(value))

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, options, kwargs
            return str(self.session_state[key])

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            self.session_state.setdefault(key, False)
            return bool(self.session_state[key])

        def button(self, label: str, **kwargs: object) -> bool:
            del label, kwargs
            return False

        def error(self, value: object) -> None:
            del value

    recorder = MergeScreenRecorder()
    app._render_requirement_merge(recorder)

    assert "Both parts of the list ask for 1." in recorder.writes
    assert (
        "Rationale: Both lines match exactly, so we've treated them as the "
        "same product."
        in recorder.captions
    )
    assert all(
        "worded differently" not in caption
        for caption in recorder.captions
    )


def test_merge_exclusion_reaches_personalize_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A submitted duplicate exclusion invalidates stale Personalize rows."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="folders-grade",
                child_id="child-1",
                raw_text="2 folders",
                canonical_item="folders",
                quantity=2,
                source_section="5th",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="folders-capable",
                child_id="child-1",
                raw_text="3 folders",
                canonical_item="folders",
                quantity=3,
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )
    _, merge_result = consolidate_extractions({"child-1": envelope})
    decision = item_decisions(merge_result)[0]
    exclude_key = f"{decision.decision_id}:exclude"

    class RerunRequested(Exception):
        pass

    class MergeRecorder:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {
                "requirement_merge_result": merge_result,
                "unmerged_extracted_lists": {"child-1": envelope},
                "intake": {
                    "children": (
                        {
                            "child_id": "child-1",
                            "label": "Jawan",
                            "grade": "Grade 5",
                        },
                    )
                },
                "list_inputs": (),
                "review_items": organize_extractions({"child-1": envelope}),
                "parent_added_review_items": (),
                exclude_key: True,
            }

        def __enter__(self) -> "MergeRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def container(self, **kwargs: object) -> "MergeRecorder":
            del kwargs
            return self

        def expander(self, *args: object, **kwargs: object) -> "MergeRecorder":
            del args, kwargs
            return self

        def columns(self, spec: object) -> tuple["MergeRecorder", ...]:
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def header(self, value: object) -> None:
            del value

        def subheader(self, value: object) -> None:
            del value

        def write(self, value: object) -> None:
            del value

        def markdown(self, value: object, **kwargs: object) -> None:
            del value, kwargs

        def caption(self, value: object) -> None:
            del value

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(self.session_state.get(key, options[0]))

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            return bool(self.session_state.get(key, False))

        def button(self, label: str, **kwargs: object) -> bool:
            del kwargs
            return label == "Continue with these choices"

        def warning(self, value: object) -> None:
            del value

        def error(self, value: object) -> None:
            raise AssertionError(value)

        def rerun(self) -> None:
            raise RerunRequested

    monkeypatch.setattr(
        app,
        "_render_merge_source_rows",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_render_merge_quantity_controls",
        lambda *args, **kwargs: ("total", 5),
    )
    recorder = MergeRecorder()
    assert decision.quantity_interrupt is not None
    quantity_key = f"{decision.quantity_interrupt.interrupt_id}:quantity"
    choice_key = f"{decision.quantity_interrupt.interrupt_id}:choice"
    custom_pending_key = (
        f"{decision.quantity_interrupt.interrupt_id}:custom-pending"
    )
    recorder.session_state[quantity_key] = 5
    app.apply_merge_item_exclusion(
        recorder.session_state,
        exclude_key,
        choice_key,
        (quantity_key,),
        custom_pending_key,
    )
    monkeypatch.setattr(
        app,
        "_render_merge_quantity_controls",
        lambda *args, **kwargs: (
            "custom",
            int(recorder.session_state[quantity_key]),
        ),
    )
    with pytest.raises(RerunRequested):
        app._render_requirement_merge(recorder)

    merged = recorder.session_state["extracted_lists"]
    assert tuple(merged["child-1"].requirements) == ()

    rebuilt = app._refresh_personalize_review_cache(
        recorder.session_state,
        dict(merged),
    )
    assert rebuilt is True
    personalize_rows = tuple(recorder.session_state["review_items"])
    assert personalize_rows == ()
    sections = app.build_personalize_student_sections(
        tuple(recorder.session_state["intake"]["children"]),
        personalize_rows,
        review_flag_groups(personalize_rows),
    )
    assert sections[0].cart_item_ids == ()


def _submit_composition_variant_state(
    monkeypatch: pytest.MonkeyPatch,
    quantities: tuple[int, int],
) -> tuple[SupplyItemReview, ...]:
    """Drive the production merge renderer with its displayed variant values."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="graph",
                child_id="child-1",
                raw_text="1 graph paper composition notebook",
                canonical_item="composition_notebooks",
                quantity=1,
                attributes={"ruling": "graph"},
                source_section="5th",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="lined",
                child_id="child-1",
                raw_text="4 regular composition notebooks",
                canonical_item="composition_notebooks",
                quantity=4,
                attributes={"ruling": "lined"},
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )
    _, merge_result = consolidate_extractions({"child-1": envelope})
    decision = item_decisions(merge_result)[0]

    class RerunRequested(Exception):
        pass

    class MergeRecorder:
        def __init__(self) -> None:
            identity_key = f"{decision.decision_id}:same-or-different"
            self.session_state: dict[str, object] = {
                "requirement_merge_result": merge_result,
                "unmerged_extracted_lists": {"child-1": envelope},
                "intake": {
                    "children": (
                        {
                            "child_id": "child-1",
                            "label": "Jawan",
                            "grade": "Grade 5",
                        },
                    )
                },
                "list_inputs": (),
                "review_items": organize_extractions({"child-1": envelope}),
                "parent_added_review_items": (),
                identity_key: "Different products",
                f"{identity_key}:facts": (
                    resolve_item_decision_state(decision).state_fingerprint
                ),
                f"{decision.decision_id}:exclude": False,
            }
            for variant, quantity in zip(
                decision.variants,
                quantities,
                strict=True,
            ):
                self.session_state[f"{variant.variant_id}:quantity"] = quantity

        def __enter__(self) -> "MergeRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def container(self, **kwargs: object) -> "MergeRecorder":
            del kwargs
            return self

        def expander(self, *args: object, **kwargs: object) -> "MergeRecorder":
            del args, kwargs
            return self

        def columns(self, spec: object) -> tuple["MergeRecorder", ...]:
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def header(self, value: object) -> None:
            del value

        def subheader(self, value: object) -> None:
            del value

        def write(self, value: object) -> None:
            del value

        def markdown(self, value: object, **kwargs: object) -> None:
            del value, kwargs

        def caption(self, value: object) -> None:
            del value

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, options, kwargs
            return str(self.session_state[key])

        def number_input(
            self,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> int:
            del label, kwargs
            return int(self.session_state[key])

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            return bool(self.session_state[key])

        def button(self, label: str, **kwargs: object) -> bool:
            del kwargs
            return label == "Continue with these choices"

        def warning(self, value: object) -> None:
            del value

        def error(self, value: object) -> None:
            raise AssertionError(value)

        def rerun(self) -> None:
            raise RerunRequested

    monkeypatch.setattr(
        app,
        "_render_merge_source_rows",
        lambda *args, **kwargs: None,
    )
    recorder = MergeRecorder()
    with pytest.raises(RerunRequested):
        app._render_requirement_merge(recorder)

    merged = dict(recorder.session_state["extracted_lists"])
    app._refresh_personalize_review_cache(recorder.session_state, merged)
    return tuple(recorder.session_state["review_items"])


def test_merge_variant_names_include_the_product_not_only_the_attribute() -> None:
    """Partial-exclusion copy names the product a parent recognizes."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="graph",
                child_id="child-1",
                raw_text="1 graph paper composition notebook",
                canonical_item="composition_notebooks",
                quantity=1,
                attributes={"ruling": "graph"},
                source_section="5th",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="lined",
                child_id="child-1",
                raw_text="4 regular composition notebooks",
                canonical_item="composition_notebooks",
                quantity=4,
                attributes={"ruling": "lined"},
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )
    _, merge_result = consolidate_extractions({"child-1": envelope})
    decision = item_decisions(merge_result)[0]

    assert tuple(
        app._merge_variant_item_name(decision, variant)
        for variant in decision.variants
    ) == (
        "graph composition notebooks",
        "lined composition notebooks",
    )


def test_merge_checkbox_zeroes_submit_as_a_complete_exclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Displayed zeroes from the exclusion action keep every variant out."""

    assert _submit_composition_variant_state(monkeypatch, (0, 0)) == ()


def test_merge_restoring_one_variant_keeps_the_other_variant_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restoring one displayed quantity cannot revive an untouched zero."""

    rows = _submit_composition_variant_state(monkeypatch, (1, 0))

    assert len(rows) == 1
    assert rows[0].required_quantity == 1
    assert rows[0].source_text == "1 graph paper composition notebook"
    assert (
        SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY
        not in rows[0].system_decisions
    )


def _submit_merge_choices_to_personalize(
    monkeypatch: pytest.MonkeyPatch,
    envelope: ExtractionEnvelope,
    *,
    selected_quantity: int,
    configure_state: object | None = None,
) -> tuple[
    dict[str, object],
    tuple[SupplyItemReview, ...],
]:
    """Drive the production duplicate screen into Personalize rows."""

    _, merge_result = consolidate_extractions({"child-1": envelope})
    decision = item_decisions(merge_result)[0]

    class RerunRequested(Exception):
        pass

    class MergeRecorder:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {
                "requirement_merge_result": merge_result,
                "unmerged_extracted_lists": {"child-1": envelope},
                "intake": {
                    "children": (
                        {
                            "child_id": "child-1",
                            "label": "Jawan",
                            "grade": "Grade 5",
                        },
                    )
                },
                "list_inputs": (),
                "review_items": organize_extractions({"child-1": envelope}),
                "parent_added_review_items": (),
            }
            if decision.quantity_interrupt is not None:
                self.session_state[
                    f"{decision.quantity_interrupt.interrupt_id}:"
                    "parent-confirmed"
                ] = True
            if callable(configure_state):
                configure_state(self.session_state, decision)

        def __enter__(self) -> "MergeRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def container(self, **kwargs: object) -> "MergeRecorder":
            del kwargs
            return self

        def expander(self, *args: object, **kwargs: object) -> "MergeRecorder":
            del args, kwargs
            return self

        def columns(self, spec: object) -> tuple["MergeRecorder", ...]:
            count = spec if isinstance(spec, int) else len(spec)
            return tuple(self for _ in range(count))

        def header(self, value: object) -> None:
            del value

        def subheader(self, value: object) -> None:
            del value

        def write(self, value: object) -> None:
            del value

        def markdown(self, value: object, **kwargs: object) -> None:
            del value, kwargs

        def caption(self, value: object) -> None:
            del value

        def radio(
            self,
            label: str,
            options: tuple[str, ...],
            *,
            key: str,
            **kwargs: object,
        ) -> str:
            del label, kwargs
            return str(self.session_state.get(key, options[0]))

        def checkbox(
            self,
            label: str,
            *,
            key: str,
            **kwargs: object,
        ) -> bool:
            del label, kwargs
            return bool(self.session_state.get(key, False))

        def button(self, label: str, **kwargs: object) -> bool:
            del kwargs
            return label == "Continue with these choices"

        def warning(self, value: object) -> None:
            del value

        def error(self, value: object) -> None:
            raise AssertionError(value)

        def rerun(self) -> None:
            raise RerunRequested

    monkeypatch.setattr(
        app,
        "_render_merge_source_rows",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_render_merge_quantity_controls",
        lambda *args, **kwargs: ("custom", selected_quantity),
    )
    recorder = MergeRecorder()
    with pytest.raises(RerunRequested):
        app._render_requirement_merge(recorder)

    merged = dict(recorder.session_state["extracted_lists"])
    app._refresh_personalize_review_cache(
        recorder.session_state,
        merged,
    )
    personalize_rows = tuple(recorder.session_state["review_items"])
    return recorder.session_state, personalize_rows


def test_merge_quantity_choice_reaches_personalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chosen duplicate quantity replaces stale Personalize quantity."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="pencils-grade",
                child_id="child-1",
                raw_text="12 pencils",
                canonical_item="pencils",
                quantity=12,
                source_section="5th",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="pencils-capable",
                child_id="child-1",
                raw_text="24 pencils",
                canonical_item="pencils",
                quantity=24,
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )

    state, personalize_rows = _submit_merge_choices_to_personalize(
        monkeypatch,
        envelope,
        selected_quantity=17,
    )

    assert tuple(state["review_items"]) == personalize_rows
    assert len(personalize_rows) == 1
    assert personalize_rows[0].required_quantity == 17


def test_merge_product_identity_choice_reaches_personalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A same-product answer replaces stale separate Personalize rows."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="folders-grade",
                child_id="child-1",
                raw_text="2 cardboard folders",
                canonical_item="folders",
                quantity=2,
                attributes={"material": "cardboard"},
                source_section="5th",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="folders-capable",
                child_id="child-1",
                raw_text="3 plastic folders",
                canonical_item="folders",
                quantity=3,
                attributes={"material": "plastic"},
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )

    def choose_same(state: dict[str, object], decision: object) -> None:
        identity_key = f"{decision.decision_id}:same-or-different"
        state[identity_key] = "The same product"
        state[f"{identity_key}:facts"] = (
            resolve_item_decision_state(decision).state_fingerprint
        )

    state, personalize_rows = _submit_merge_choices_to_personalize(
        monkeypatch,
        envelope,
        selected_quantity=4,
        configure_state=choose_same,
    )

    assert tuple(state["review_items"]) == personalize_rows
    assert len(personalize_rows) == 1
    assert personalize_rows[0].required_quantity == 4
    assert personalize_rows[0].material == "cardboard"


def test_grade_change_writer_refreshes_stale_personalize_rows() -> None:
    """A grade-driven re-extraction cannot leave the earlier review rows visible."""

    earlier = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="old-grade",
                child_id="child-1",
                raw_text="12 pencils",
                canonical_item="pencils",
                quantity=12,
                source_section="2nd Grade",
                extraction_confidence=1.0,
            ),
        )
    )
    updated = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="new-grade",
                child_id="child-1",
                raw_text="24 pencils",
                canonical_item="pencils",
                quantity=24,
                source_section="5th Grade",
                extraction_confidence=1.0,
            ),
        )
    )
    state: dict[str, object] = {
        "document_selections": {
            "child-1": DocumentSelection(
                selected_section_ids=("grade-2",),
                selected_section_labels=("2nd Grade",),
            )
        },
        "intake_previous_grade_0": "Grade 2",
        "review_items": organize_extractions({"child-1": earlier}),
        app.PERSONALIZE_REVIEW_SOURCE_FINGERPRINTS_KEY: (
            app._extraction_envelope_fingerprints({"child-1": earlier})
        ),
    }

    notices = app.clear_section_selection_after_grade_change(
        state,
        0,
        "Grade 5",
        "Maya",
    )
    assert notices
    state["extracted_lists"] = {"child-1": updated}

    assert app._refresh_personalize_review_cache(
        state,
        state["extracted_lists"],  # type: ignore[arg-type]
    )
    rows = tuple(state["review_items"])
    assert len(rows) == 1
    assert rows[0].required_quantity == 24
    assert rows[0].source_section == "5th Grade"


def test_automatic_section_writer_refreshes_stale_personalize_rows() -> None:
    """An automatically selected section cannot reuse another section's rows."""

    earlier = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="manual-section",
                child_id="child-1",
                raw_text="1 backpack",
                canonical_item="backpacks",
                quantity=1,
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )
    updated = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="automatic-section",
                child_id="child-1",
                raw_text="2 composition books",
                canonical_item="composition_notebooks",
                quantity=2,
                source_section="5th Grade",
                extraction_confidence=1.0,
            ),
        )
    )
    state: dict[str, object] = {
        "review_items": organize_extractions({"child-1": earlier}),
        "parent_added_review_items": (),
        app.PERSONALIZE_REVIEW_SOURCE_FINGERPRINTS_KEY: (
            app._extraction_envelope_fingerprints({"child-1": earlier})
        ),
    }

    assert app._refresh_personalize_review_cache(
        state,
        {"child-1": updated},
    )
    rows = tuple(state["review_items"])
    assert len(rows) == 1
    assert rows[0].item_name == "composition_notebooks"
    assert rows[0].source_section == "5th Grade"


def test_source_refresh_preserves_parent_added_item() -> None:
    """Independent parent input survives a source-envelope cache rebuild."""

    earlier = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="old-list",
                child_id="child-1",
                raw_text="12 pencils",
                canonical_item="pencils",
                quantity=12,
                extraction_confidence=1.0,
            ),
        )
    )
    updated = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="replacement-list",
                child_id="child-1",
                raw_text="3 folders",
                canonical_item="folders",
                quantity=3,
                extraction_confidence=1.0,
            ),
        )
    )
    parent_item = SupplyItemReview(
        review_id="parent-added",
        req_id="parent-added",
        child_id="child-1",
        item_name="erasers",
        required_quantity=2,
        source_text="Added by parent",
        confidence=1.0,
    )
    state: dict[str, object] = {
        "review_items": organize_extractions({"child-1": earlier}),
        "parent_added_review_items": (parent_item,),
        app.PERSONALIZE_REVIEW_SOURCE_FINGERPRINTS_KEY: (
            app._extraction_envelope_fingerprints({"child-1": earlier})
        ),
    }

    assert app._refresh_personalize_review_cache(
        state,
        {"child-1": updated},
    )
    source_rows = tuple(state["review_items"])
    assert len(source_rows) == 1
    assert source_rows[0].item_name == "folders"
    assert source_rows[0].required_quantity == 3
    assert state["parent_added_review_items"] == (parent_item,)


def test_student_refresh_preserves_another_students_parent_edits() -> None:
    """A changed list cannot erase an unaffected student's review choices."""

    earlier = {
        "child-1": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id="child-1",
                    raw_text="12 pencils",
                    canonical_item="pencils",
                    quantity=12,
                    extraction_confidence=1.0,
                ),
            )
        ),
        "child-2": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="folders",
                    child_id="child-2",
                    raw_text="2 folders",
                    canonical_item="folders",
                    quantity=2,
                    extraction_confidence=1.0,
                ),
            )
        ),
    }
    updated = {
        **earlier,
        "child-2": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="folders-new",
                    child_id="child-2",
                    raw_text="4 folders",
                    canonical_item="folders",
                    quantity=4,
                    extraction_confidence=1.0,
                ),
            )
        ),
    }
    initial_rows = organize_extractions(earlier)
    pencils = next(
        row for row in initial_rows if row.child_id == "child-1"
    )
    edited_pencils = pencils.model_copy(
        update={
            "required_quantity": 8,
            "already_owned": True,
        }
    )
    quantity_key = (
        f"{app.personalize_settled_row_key_prefix(pencils)}:quantity"
    )
    owned_key = f"{app.personalize_settled_row_key_prefix(pencils)}:owned"
    state: dict[str, object] = {
        "review_items": tuple(
            edited_pencils if row.review_id == pencils.review_id else row
            for row in initial_rows
        ),
        "parent_added_review_items": (),
        app.PERSONALIZE_REVIEW_SOURCE_FINGERPRINTS_KEY: (
            app._extraction_envelope_fingerprints(earlier)
        ),
        quantity_key: 8,
        owned_key: True,
    }

    assert app._refresh_personalize_review_cache(state, updated)

    refreshed_pencils = next(
        row
        for row in state["review_items"]  # type: ignore[union-attr]
        if row.child_id == "child-1"
    )
    refreshed_folders = next(
        row
        for row in state["review_items"]  # type: ignore[union-attr]
        if row.child_id == "child-2"
    )
    assert refreshed_pencils.required_quantity == 8
    assert refreshed_pencils.already_owned is True
    assert state[quantity_key] == 8
    assert state[owned_key] is True
    assert refreshed_folders.required_quantity == 4


def test_changed_source_warns_before_discarding_parent_choice() -> None:
    """A source change names the Personalize choice that no longer applies."""

    earlier = {
        "child-1": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id="child-1",
                    raw_text="12 pencils",
                    canonical_item="pencils",
                    quantity=12,
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="folders",
                    child_id="child-1",
                    raw_text="2 folders",
                    canonical_item="folders",
                    quantity=2,
                    extraction_confidence=1.0,
                ),
            )
        )
    }
    initial_rows = organize_extractions(earlier)
    originals = {
        row.review_id: row.model_copy(deep=True)
        for row in initial_rows
    }
    edited_rows = tuple(
        row.model_copy(update={"required_quantity": 8})
        if row.review_id == "child-1:pencils"
        else row.model_copy(update={"required_quantity": 1})
        if row.review_id == "child-1:folders"
        else row
        for row in initial_rows
    )
    state: dict[str, object] = {
        "intake": {
            "children": (
                {
                    "child_id": "child-1",
                    "label": "Maya",
                },
            )
        },
        "review_items": edited_rows,
        "parent_added_review_items": (),
        app.PERSONALIZE_ORIGINAL_ITEMS_KEY: originals,
        app.PERSONALIZE_REVIEW_SOURCE_FINGERPRINTS_KEY: (
            app._extraction_envelope_fingerprints(earlier)
        ),
    }
    updated = {
        "child-1": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id="child-1",
                    raw_text="12 pencils",
                    canonical_item="pencils",
                    quantity=12,
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="folders",
                    child_id="child-1",
                    raw_text="4 folders",
                    canonical_item="folders",
                    quantity=4,
                    extraction_confidence=1.0,
                ),
            )
        )
    }

    assert app._refresh_personalize_review_cache(state, updated)

    refreshed_rows = {
        row.review_id: row for row in state["review_items"]
    }
    assert refreshed_rows["child-1:pencils"].required_quantity == 8
    assert refreshed_rows["child-1:folders"].required_quantity == 4
    assert state[app.PERSONALIZE_SOURCE_CHANGE_NOTICES_KEY] == (
        "The source line for folders on Maya's list changed, so your "
        "earlier choice no longer applies. Please review it again.",
    )


def test_changed_shared_group_is_reconsidered_without_clearing_others() -> None:
    """Only a shared decision touched by a changed student is reset."""

    earlier = {
        "child-1": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="paper-a",
                    child_id="child-1",
                    raw_text="1 pack notebook paper",
                    canonical_item="notebook_paper",
                    quantity=1,
                    unit_type="pack",
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="glue-a",
                    child_id="child-1",
                    raw_text="1 pack glue sticks",
                    canonical_item="glue_sticks",
                    quantity=1,
                    unit_type="pack",
                    extraction_confidence=1.0,
                ),
            )
        ),
        "child-2": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="paper-b",
                    child_id="child-2",
                    raw_text="1 pack notebook paper",
                    canonical_item="notebook_paper",
                    quantity=1,
                    unit_type="pack",
                    extraction_confidence=1.0,
                ),
            )
        ),
    }
    initial_rows = organize_extractions(earlier)
    initial_groups = review_flag_groups(initial_rows)
    shared_group = next(
        group for group in initial_groups if len(group.child_ids) == 2
    )
    unrelated_group = next(
        group for group in initial_groups if len(group.child_ids) == 1
    )
    edited_rows = tuple(
        (
            row.model_copy(update={"required_quantity": 7})
            if row.review_id in unrelated_group.row_ids
            else row.model_copy(update={"required_quantity": 9})
            if row.review_id in shared_group.row_ids
            else row
        )
        for row in initial_rows
    )
    state: dict[str, object] = {
        "review_items": edited_rows,
        "parent_added_review_items": (),
        app.PERSONALIZE_REVIEW_SOURCE_FINGERPRINTS_KEY: (
            app._extraction_envelope_fingerprints(earlier)
        ),
        app.PERSONALIZE_CONFIRMED_GROUP_IDS_KEY: frozenset(
            group.group_id for group in initial_groups
        ),
        app.PERSONALIZE_PARENT_EDITED_GROUP_IDS_KEY: frozenset(
            group.group_id for group in initial_groups
        ),
    }
    updated = {
        **earlier,
        "child-2": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="paper-b-new",
                    child_id="child-2",
                    raw_text="2 packs notebook paper",
                    canonical_item="notebook_paper",
                    quantity=2,
                    unit_type="pack",
                    extraction_confidence=1.0,
                ),
            )
        ),
    }

    assert app._refresh_personalize_review_cache(state, updated)

    refreshed_rows = tuple(state["review_items"])
    refreshed_groups = review_flag_groups(refreshed_rows)
    refreshed_unrelated = next(
        group
        for group in refreshed_groups
        if any(
            row.item_name == "glue_sticks"
            for row in refreshed_rows
            if row.review_id in group.row_ids
        )
    )
    confirmed = frozenset(
        state[app.PERSONALIZE_CONFIRMED_GROUP_IDS_KEY]
    )
    parent_edited = frozenset(
        state[app.PERSONALIZE_PARENT_EDITED_GROUP_IDS_KEY]
    )
    assert refreshed_unrelated.group_id in confirmed
    assert refreshed_unrelated.group_id in parent_edited
    assert next(
        row
        for row in refreshed_rows
        if row.review_id == "child-1:glue-a"
    ).required_quantity == 7
    assert next(
        row
        for row in refreshed_rows
        if row.review_id == "child-1:paper-a"
    ).required_quantity == 1
    assert next(
        row
        for row in refreshed_rows
        if row.review_id == "child-2:paper-b-new"
    ).required_quantity == 2
    reconsidered_group_ids = {
        group.group_id
        for group in refreshed_groups
        if any(
            row.item_name == "notebook_paper"
            for row in refreshed_rows
            if row.review_id in group.row_ids
        )
    }
    assert reconsidered_group_ids.isdisjoint(confirmed)
    assert reconsidered_group_ids.isdisjoint(parent_edited)


def test_custom_quantity_choice_highlights_until_parent_enters_value() -> None:
    """FR-12: the custom quantity field has explicit pending state."""

    state: dict[str, object] = {
        "choice": app.MERGE_CUSTOM_QUANTITY_LABEL,
        "quantity": 4,
    }
    choices = {
        "**4** — Highly Capable Class, page 3 — default": 4,
        app.MERGE_CUSTOM_QUANTITY_LABEL: None,
    }

    app.apply_merge_quick_choice(
        state,
        "choice",
        {"quantity-choice": "quantity"},
        choices,
        "custom-pending",
    )
    assert state["custom-pending"] is True

    app.mark_merge_quantities_custom(
        state,
        "choice",
        app.MERGE_CUSTOM_QUANTITY_LABEL,
        "custom-pending",
    )
    assert state["custom-pending"] is False


def test_failed_concurrent_document_retries_without_repeating_success() -> None:
    """BR-38: only a failed production-shaped extraction retries sequentially."""

    attempts = {"child-1": 0, "child-2": 0}
    progress: list[tuple[str, int, int]] = []

    def extractor(
        source: object,
        *,
        child_id: str,
        mime_type: str | None,
    ) -> ExtractionEnvelope:
        del source, mime_type
        attempts[child_id] += 1
        if child_id == "child-2" and attempts[child_id] == 1:
            raise TimeoutError("first attempt did not finish")
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id=f"{child_id}:pencils",
                    child_id=child_id,
                    raw_text="1 pencil",
                    canonical_item="pencils",
                    quantity=1,
                    extraction_confidence=1.0,
                ),
            )
        )

    extracted, errors = app._extract_list_inputs(
        (
            ListInput("child-1", "first list"),
            ListInput("child-2", "second list"),
        ),
        extractor=extractor,
        progress_callback=lambda stage, done, total, detail: (
            progress.append((stage, done, total))
        ),
    )

    assert tuple(extracted) == ("child-1", "child-2")
    assert errors == {}
    assert attempts == {"child-1": 1, "child-2": 2}
    assert ("extraction_retry", 1, 1) in progress


def test_saved_list_page_count_uses_retained_production_input() -> None:
    """FR-06: saved-list display names the real retained PDF page count."""

    pdf_path = Path("tests/sample_lists/Machiasschoolsupplylist 1.pdf")
    pdf_input = ListInput(
        child_id="child-1",
        source=pdf_path,
        mime_type="application/pdf",
        document_name=pdf_path.name,
    )
    text_input = ListInput(
        child_id="child-2",
        source="2 pencils",
        mime_type="text/plain",
        document_name="pasted-list.txt",
    )

    assert app._saved_list_page_count(pdf_input) == 3
    assert app._saved_list_page_count(text_input) == 1


def test_review_detail_visibility_uses_real_catalog_variation() -> None:
    """BR-28: only source-backed or catalog-discriminating fields appear."""

    item = SupplyItemReview(
        review_id="review-composition",
        req_id="composition",
        child_id="child-1",
        item_name="composition_notebooks",
        required_quantity=2,
        source_text="2 composition notebooks",
        confidence=1.0,
    )

    visibility = app.review_detail_field_visibility(
        item,
        load_catalog(),
    )
    supplied_material = app.review_detail_field_visibility(
        item.model_copy(update={"material": "cardboard"}),
        load_catalog(),
    )

    assert visibility == {
        "size": False,
        "material": False,
        "acceptable_colors": True,
    }
    assert supplied_material["material"] is True


def test_personalize_names_understood_item_with_no_stocked_catalog_category() -> None:
    """FR-12/E-12: catalog gaps are visible before the cart is built."""

    item = SupplyItemReview(
        review_id="pencils",
        req_id="pencils",
        child_id="child-1",
        item_name="pencils",
        required_quantity=24,
        source_text="24 pencils",
        source_page=2,
        confidence=1.0,
    )

    gaps = app.catalog_unstocked_review_items(
        (item,),
        tuple(
            offer for offer in load_catalog() if offer.category != "pencils"
        ),
    )

    assert gaps == (item,)
    assert gaps[0].source_text == "24 pencils"
    assert gaps[0].source_page == 2


def test_source_annotation_is_hidden_only_at_display_edge() -> None:
    """Matrix annotations stay in provenance but not parent-facing copy."""

    exact_line = "Composition book | 5th: 1"
    source = RequirementSource(
        source_req_id="composition",
        document_name="district.pdf",
        section_name="5th Grade",
        page_number=2,
        exact_line=exact_line,
        quantity=1,
    )

    assert app._display_source_line(source.exact_line) == "Composition book"
    assert source.exact_line == exact_line


def test_leading_source_quantity_is_hidden_only_at_display_edge() -> None:
    """BR-42: duplicate quantity is removed without changing exact evidence."""

    exact_line = "4 Regular composition books"
    source = RequirementSource(
        source_req_id="composition",
        document_name="district.pdf",
        section_name="Highly Capable Class",
        page_number=3,
        exact_line=exact_line,
        quantity=4,
    )

    assert app._display_source_line(source.exact_line) == (
        "Regular composition books"
    )
    assert source.exact_line == exact_line


@pytest.mark.parametrize(
    ("exact_line", "expected"),
    (
        ("1 box | Ziploc quart gallon sized", "Ziploc quart gallon sized"),
        (
            "1 set | Colored markers (wide or thin)",
            "Colored markers (wide or thin)",
        ),
    ),
)
def test_source_description_prefers_item_wording_over_container_only_segment(
    exact_line: str,
    expected: str,
) -> None:
    """BR-46: a generic quantity container cannot hide item wording."""

    assert app._display_source_line(exact_line) == expected


def test_source_button_filename_is_bounded_and_keeps_extension() -> None:
    """BR-41: long source names stay within the parent-facing column."""

    label = app._source_document_button_label(
        "very-long-district-school-supply-list-for-every-grade.pdf"
    )

    assert len(label) <= 30
    assert label.endswith(".pdf")
    assert "…" in label
    reference = app.SourceReference(
        document_name=(
            "very-long-district-school-supply-list-for-every-grade.pdf"
        ),
        page_number=3,
        source_line="3 glue sticks",
        rendered_page=None,
        text_page=None,
        mime_type="application/pdf",
    )
    assert app._source_reference_hover_text(reference) == (
        "View source · "
        "very-long-district-school-supply-list-for-every-grade.pdf · page 3"
    )


def test_pasted_list_screen_builds_exact_paginated_viewable_source() -> None:
    """BR-64: the production Lists builder and source control share pages."""

    source_lines = ["  Quantity\tItem\tNotes\r\n"] + [
        f"{index}\tItem {index}\tkeep typoo {index}\r\n"
        for index in range(1, 50)
    ]
    pasted = "".join(source_lines) + "  "
    state: dict[str, object] = {
        "list_mode_0": "Paste text",
        "list_paste_0": pasted,
    }

    class ListsScreenState:
        session_state = state

    (list_input,) = app._build_list_inputs(
        ListsScreenState(),
        (
            {
                "child_id": "child-1",
                "label": "Maya",
                "grade": "Grade 2",
            },
        ),
    )

    assert list_input.source == pasted
    assert "".join(list_input.source_page_texts) == pasted
    assert list_input.resolved_document_name == "Maya's supply list"
    assert list_input.source_page_count == 2
    assert app._saved_list_page_count(list_input) == 2

    source_line = "49\tItem 49\tkeep typoo 49"
    extracted, errors = app._extract_list_inputs(
        (list_input,),
        extractor=lambda source, **kwargs: ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="late-line",
                    child_id=str(kwargs["child_id"]),
                    raw_text=source_line,
                    canonical_item="folders",
                    quantity=49,
                    source_page=1,
                    extraction_confidence=1.0,
                ),
            ),
            catalog_unavailable_items=(
                CatalogUnavailableItem(
                    child_id=str(kwargs["child_id"]),
                    item_name="locker shelf",
                    source_line=source_line,
                    page_number=1,
                ),
            ),
        ),
    )
    assert errors == {}
    requirement = extracted["child-1"].requirements[0]
    unavailable = extracted["child-1"].catalog_unavailable_items[0]
    assert requirement.source_page == 2
    assert requirement.sources[0].page_number == 2
    assert unavailable.page_number == 2

    reference = app.build_source_reference(
        list_input,
        page_number=1,
        source_line=source_line,
    )
    assert reference.page_number == 2
    assert reference.source_line == source_line
    assert reference.rendered_page is None
    assert reference.text_page == list_input.source_page_texts[1]

    class Popover:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            del args

    class SourceControl:
        session_state: dict[str, object] = {}
        popover_labels: list[str] = []
        captions: list[str] = []
        rendered_text_pages: list[tuple[str, bool]] = []

        @classmethod
        def popover(cls, label: str, **kwargs: object) -> Popover:
            del kwargs
            cls.popover_labels.append(label)
            return Popover()

        @classmethod
        def caption(cls, value: str) -> None:
            cls.captions.append(value)

        @classmethod
        def code(
            cls,
            value: str,
            *,
            language: str | None,
            wrap_lines: bool,
        ) -> None:
            assert language is None
            cls.rendered_text_pages.append((value, wrap_lines))

        @staticmethod
        def image(value: bytes, **kwargs: object) -> None:
            del value, kwargs
            raise AssertionError("Pasted text must not be converted to an image")

        @staticmethod
        def info(value: str) -> None:
            raise AssertionError(value)

    app._render_source_reference(
        SourceControl(),
        list_input,
        page_number=1,
        source_line=source_line,
        key="pasted-source",
    )
    district_input = replace(
        list_input,
        document_name="Machiasschoolsupplylist 1.pdf",
    )
    app._render_source_reference(
        SourceControl(),
        district_input,
        page_number=1,
        source_line=source_line,
        key="table-source",
        under_source_header=True,
    )

    assert len(SourceControl.popover_labels) == 2
    source_label = SourceControl.popover_labels[0]
    assert source_label.startswith("View source")
    assert "Maya's supply list" in source_label
    assert source_label.endswith("page 2")
    assert SourceControl.popover_labels[1] == (
        "Machiasschoolsupplylist 1.pdf · page 2"
    )
    assert SourceControl.rendered_text_pages == [
        (list_input.source_page_texts[1], False),
        (list_input.source_page_texts[1], False),
    ]
    assert SourceControl.captions == [
        f"Cited line on this page: {source_line}",
        f"Cited line on this page: {source_line}",
    ]


def test_pasted_source_controls_reach_all_provenance_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BR-64: production surface renderers all open retained pasted text."""

    pasted = (
        "2 pocket folders\n"
        "3 pocket folders\n"
        "2 glue sticks\n"
        "3 glue sticks\n"
        "1 graphing calculator\n"
    )
    state: dict[str, object] = {
        "list_mode_0": "Paste text",
        "list_paste_0": pasted,
    }

    class ListsState:
        session_state = state

    (list_input,) = app._build_list_inputs(
        ListsState(),
        (
            {
                "child_id": "child-1",
                "label": "Kevin",
                "grade": "Grade 2",
            },
        ),
    )

    class Popover:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            del args

    class SurfaceRecorder:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {
                "list_inputs": (list_input,),
                "source_reference_cache": {},
            }
            self.popovers: list[str] = []
            self.text_pages: list[str] = []
            self.writes: list[str] = []
            self.errors: list[str] = []

        def __enter__(self) -> "SurfaceRecorder":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def container(self, **kwargs: object) -> "SurfaceRecorder":
            del kwargs
            return self

        def popover(self, label: str, **kwargs: object) -> Popover:
            del kwargs
            self.popovers.append(label)
            return Popover()

        def code(
            self,
            value: str,
            *,
            language: str | None,
            wrap_lines: bool,
        ) -> None:
            assert language is None
            assert wrap_lines is False
            self.text_pages.append(value)

        def image(self, value: object, **kwargs: object) -> None:
            del value, kwargs
            raise AssertionError("Pasted provenance must remain text-backed")

        def info(self, value: object) -> None:
            raise AssertionError(value)

        def caption(self, value: object) -> None:
            del value

        def write(self, value: object) -> None:
            self.writes.append(str(value))

        def error(self, value: object) -> None:
            self.errors.append(str(value))

        def warning(self, value: object) -> None:
            self.writes.append(str(value))

        def markdown(self, value: object, **kwargs: object) -> None:
            del value, kwargs

        def expander(
            self,
            label: str,
            **kwargs: object,
        ) -> "SurfaceRecorder":
            del label, kwargs
            return self

        def columns(self, spec: object) -> tuple["SurfaceColumn", ...]:
            count = spec if isinstance(spec, int) else len(spec)  # type: ignore[arg-type]
            return tuple(SurfaceColumn(self) for _ in range(count))

    class SurfaceColumn:
        def __init__(self, recorder: SurfaceRecorder) -> None:
            self.recorder = recorder

        @property
        def session_state(self) -> dict[str, object]:
            return self.recorder.session_state

        def __enter__(self) -> "SurfaceColumn":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def markdown(self, value: object) -> None:
            del value

        def write(self, value: object) -> None:
            self.recorder.write(value)

        def caption(self, value: object) -> None:
            self.recorder.caption(value)

        def popover(self, label: str, **kwargs: object) -> Popover:
            return self.recorder.popover(label, **kwargs)

        def code(
            self,
            value: str,
            *,
            language: str | None,
            wrap_lines: bool,
        ) -> None:
            self.recorder.code(
                value,
                language=language,
                wrap_lines=wrap_lines,
            )

        def image(self, value: object, **kwargs: object) -> None:
            self.recorder.image(value, **kwargs)

        def info(self, value: object) -> None:
            self.recorder.info(value)

    recorder = SurfaceRecorder()
    item = SupplyItemReview(
        review_id="review-folders",
        req_id="folders-one",
        child_id="child-1",
        item_name="folders",
        required_quantity=2,
        source_text="2 pocket folders",
        source_document=list_input.resolved_document_name,
        source_page=1,
        package_quantity_state="assumed",
        confidence=1.0,
    )
    monkeypatch.setattr(
        app,
        "_render_review_detail_controls",
        lambda st, item, **kwargs: item,
    )
    app._render_personalize_child_sources(
        recorder,
        "child-1",
        "Kevin",
    )
    student_source_count = len(recorder.popovers)
    before_item = len(recorder.popovers)
    app._render_compact_review_row(
        recorder,
        (item,),
        {"child-1": "Kevin"},
        key_prefix="item",
        offers=(),
    )
    item_surface_count = len(recorder.popovers) - before_item

    conflict = item_decisions(
        consolidate_requirements(
            (
                Requirement(
                    req_id="glue-one",
                    child_id="child-1",
                    raw_text="2 glue sticks",
                    canonical_item="glue_sticks",
                    quantity=2,
                    source_document=list_input.resolved_document_name,
                    source_section="List A",
                    source_page=1,
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="glue-two",
                    child_id="child-1",
                    raw_text="3 glue sticks",
                    canonical_item="glue_sticks",
                    quantity=3,
                    source_document=list_input.resolved_document_name,
                    source_section="List B",
                    source_page=1,
                    extraction_confidence=1.0,
                ),
            )
        )
    )[0]
    app._render_merge_source_rows(recorder, conflict, list_input)
    before_conflict = student_source_count + item_surface_count
    conflict_surface_count = len(recorder.popovers) - before_conflict

    envelope = ExtractionEnvelope(
        catalog_unavailable_items=(
            CatalogUnavailableItem(
                child_id="child-1",
                item_name="graphing_calculator",
                source_line="1 graphing calculator",
                document_name=list_input.resolved_document_name,
                page_number=1,
            ),
        )
    )
    app._personalize_source_summary(
        recorder,
        "child-1",
        envelope,
    )
    before_unavailable = len(recorder.popovers)
    app._render_personalize_unavailable(
        recorder,
        "child-1",
        envelope,
        (),
    )
    unavailable_surface_count = (
        len(recorder.popovers) - before_unavailable
    )

    assert student_source_count == 1
    assert item_surface_count == 0
    assert conflict_surface_count == 2
    assert unavailable_surface_count == 0
    conflict_labels = recorder.popovers[
        before_conflict : before_conflict + conflict_surface_count
    ]
    standalone_labels = tuple(
        label
        for label in recorder.popovers
        if label not in conflict_labels
    )
    assert all(
        not label.startswith("View source")
        and "Kevin's supply list" in label
        for label in conflict_labels
    )
    assert standalone_labels == ("View pasted list",)
    assert recorder.text_pages == [
        pasted
        for _ in recorder.popovers
    ]
    assert recorder.errors == []
    assert "1 graphing calculator" in recorder.writes


def test_review_understanding_pluralizes_composition_notebooks() -> None:
    """Personalize copy uses a grammatically correct quantity label."""

    item = SupplyItemReview(
        review_id="review-composition",
        req_id="composition",
        child_id="child-1",
        item_name="composition_notebooks",
        required_quantity=2,
        source_text="2 composition notebooks",
        confidence=1.0,
    )

    assert app.review_understanding_text(item) == (
        "2 composition notebooks"
    )


def test_system_merge_decisions_are_plainly_visible() -> None:
    """BR-29: consolidation and reconciliation are named at the item."""

    item = SupplyItemReview(
        review_id="review-folder",
        req_id="folder",
        child_id="child-1",
        item_name="folders",
        required_quantity=1,
        sources=(
            RequirementSource(
                source_req_id="folder-1",
                document_name="district.pdf",
                section_name="5th Grade",
                page_number=2,
                exact_line="1 folder",
                quantity=1,
            ),
            RequirementSource(
                source_req_id="folder-2",
                document_name="district.pdf",
                section_name="Highly Capable",
                page_number=3,
                exact_line="1 plastic folder",
                quantity=1,
            ),
        ),
        system_decisions=(
            "consolidated_sources",
            "reconciled_attribute:material",
        ),
        source_text="1 folder",
        confidence=1.0,
    )

    messages = app.review_system_decision_messages(item)

    assert len(messages) == 1
    assert messages[0] == (
        "We believe these 2 source lines describe one item; page 2 asks for "
        "1 and page 3 asks for 1, so 1 is used."
    )


def test_personalize_keeps_resolved_decisions_in_more_detail() -> None:
    """BR-49: completed Lists explanations do not repeat in the main card."""

    item = SupplyItemReview(
        review_id="review-folder",
        req_id="folder",
        child_id="child-1",
        item_name="folders",
        required_quantity=1,
        sources=(
            RequirementSource(
                source_req_id="folder-1",
                document_name="district.pdf",
                section_name="5th Grade",
                page_number=2,
                exact_line="1 folder",
                quantity=1,
            ),
            RequirementSource(
                source_req_id="folder-2",
                document_name="district.pdf",
                section_name="Highly Capable",
                page_number=3,
                exact_line="1 | folder",
                quantity=1,
            ),
        ),
        system_decisions=("consolidated_sources",),
        source_text="1 folder",
        confidence=1.0,
    )

    main_messages, detail_messages = app.review_message_placement((item,))

    assert main_messages == ()
    assert detail_messages == (
        "We believe these 2 source lines describe one item; page 2 asks for "
        "1 and page 3 asks for 1, so 1 is used.",
    )


def test_reconciled_boolean_attribute_uses_product_language() -> None:
    """BR-50: Personalize never exposes raw booleans or schema names."""

    item = SupplyItemReview(
        review_id="review-pencil",
        req_id="pencil",
        child_id="child-1",
        item_name="pencils",
        required_quantity=12,
        required_attributes={"sharpened": True},
        system_decisions=("reconciled_attribute:sharpened",),
        source_text="12 sharpened pencils",
        confidence=1.0,
    )

    messages = app.review_system_decision_messages(item)

    assert messages == (
        "One part of the list specifies sharpening as pre-sharpened; another "
        "appears to leave it open, so pre-sharpened is kept.",
    )
    assert "True" not in messages[0]
    assert "sharpened:" not in messages[0]


def test_grade_preselection_handles_ordinals_and_preserves_parent_changes() -> None:
    """The keyed widget starts at the entered grade but remains changeable."""

    structure = DocumentStructureEnvelope(
        sections=(
            DocumentSection(
                section_id="grade-2",
                label="Second Grade",
                grades=("Second Grade",),
                source_line="Second Grade",
            ),
            DocumentSection(
                section_id="grade-5",
                label="5th Grade",
                grades=("5th Grade",),
                source_line="5th Grade",
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
