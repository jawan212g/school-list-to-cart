"""Streamlit integration tests for intake widget cleanup and remounting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import app


streamlit = pytest.importorskip(
    "streamlit",
    reason=(
        "Streamlit has no supported local installation on this Windows ARM64 "
        "machine; these lifecycle tests run in the deployed x86 environment."
    ),
)
from streamlit.testing.v1 import AppTest


APP_PATH = Path(app.__file__).resolve()


def _run_app() -> AppTest:
    test_app = AppTest.from_file(str(APP_PATH), default_timeout=15)
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _assert_no_exception(test_app: AppTest) -> None:
    assert not test_app.exception


def _run_working_progress_screen() -> AppTest:
    """Mount the production router with deterministic empty list inspection."""

    test_app = AppTest.from_string(
        """
import streamlit as st
import app
from agent.pipeline import ListInput

def inspect_without_model(*args, **kwargs):
    return {}, {}

app._inspect_list_inputs = inspect_without_model
st.session_state.setdefault(
    "intake",
    {
        "children": (
            {
                "child_id": "child-1",
                "label": "Maya",
                "grade": "Grade 2",
            },
        ),
        "demo_mode": False,
    },
)
st.session_state.setdefault(
    "list_inputs",
    (
        ListInput(
            child_id="child-1",
            source="1 box of pencils",
            mime_type="text/plain",
            document_name="Maya's supply list",
        ),
    ),
)
st.session_state.setdefault("screen", "working")
app.main()
"""
    )
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _run_section_screen() -> AppTest:
    """Mount the production section screen with production Pydantic models."""

    test_app = AppTest.from_string(
        """
import streamlit as st
import app
from agent.pipeline import ListInput
from agent.schema import DocumentSection, DocumentStructureEnvelope

st.session_state.setdefault(
    "intake",
    {
        "children": (
            {
                "child_id": "child-1",
                "label": "Ms. K",
                "grade": "Grade 1",
            },
        )
    },
)
st.session_state.setdefault(
    "document_structures",
    {
        "child-1": DocumentStructureEnvelope(
            document_title="Machias School Supply List",
            languages=("English",),
            primary_language="English",
            sections=(
                DocumentSection(
                    section_id="grade-1",
                    label="1st Grade",
                    grades=("Grade 1",),
                    page_numbers=(1,),
                    language="English",
                    source_line="1st Grade",
                ),
                DocumentSection(
                    section_id="highly-capable",
                    label="Highly Capable Class",
                    page_numbers=(3,),
                    language="English",
                    source_line="Highly Capable Class",
                ),
                DocumentSection(
                    section_id="grade-2",
                    label="2nd Grade",
                    grades=("Grade 2",),
                    page_numbers=(2,),
                    language="English",
                    source_line="2nd Grade",
                ),
            ),
        )
    },
)
st.session_state.setdefault(
    "list_inputs",
    (
        ListInput(
            child_id="child-1",
            source="1st Grade\\nHighly Capable Class",
            mime_type="text/plain",
            document_name="Machias.pdf",
        ),
    ),
)
st.session_state.setdefault("document_selections", {})
st.session_state.setdefault("structure_errors", {})
st.session_state.setdefault("screen", "sections")
st.session_state.setdefault("organized_list_confirmed", False)
st.session_state.setdefault("extraction_cache_ready", False)
if st.session_state.get("screen") == "sections":
    app._render_sections(st)
"""
    )
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def test_working_progress_scroll_is_marked_once_per_episode() -> None:
    """Working-screen reruns keep one scroll marker until a new episode."""

    test_app = _run_working_progress_screen()

    assert (
        test_app.session_state[app.WORK_EPISODE_COUNTER_KEY] == 1
    )
    assert test_app.session_state[app.WORK_EPISODE_ACTIVE_KEY] == 1
    assert test_app.session_state[app.WORK_SCROLL_COMPLETED_KEY] == 1

    test_app.run()
    _assert_no_exception(test_app)
    assert (
        test_app.session_state[app.WORK_EPISODE_COUNTER_KEY] == 1
    )
    assert test_app.session_state[app.WORK_EPISODE_ACTIVE_KEY] == 1
    assert test_app.session_state[app.WORK_SCROLL_COMPLETED_KEY] == 1

    test_app.session_state["screen"] = "intake"
    test_app.run()
    _assert_no_exception(test_app)
    assert (
        test_app.session_state[app.WORK_EPISODE_ACTIVE_KEY] is None
    )
    assert (
        test_app.session_state[app.WORK_SCROLL_COMPLETED_KEY] is None
    )

    test_app.session_state["screen"] = "working"
    test_app.session_state["structure_cache_ready"] = False
    test_app.session_state["extraction_cache_ready"] = False
    test_app.run()
    _assert_no_exception(test_app)
    assert (
        test_app.session_state[app.WORK_EPISODE_COUNTER_KEY] == 2
    )
    assert test_app.session_state[app.WORK_EPISODE_ACTIVE_KEY] == 2
    assert test_app.session_state[app.WORK_SCROLL_COMPLETED_KEY] == 2


def _run_personalize_screen() -> AppTest:
    """Mount the production Personalize screen with two settled items."""

    test_app = AppTest.from_string(
        """
import streamlit as st
import app
from agent.schema import ExtractionEnvelope, SupplyItemReview

st.session_state.setdefault(
    "intake",
    {
        "children": (
            {
                "child_id": "child-1",
                "label": "Maya",
                "grade": "Grade 2",
            },
        )
    },
)
st.session_state.setdefault(
    "extracted_lists",
    {"child-1": ExtractionEnvelope()},
)
st.session_state.setdefault(
    "review_items",
    (
        SupplyItemReview(
            review_id="pencils",
            req_id="pencils",
            child_id="child-1",
            item_name="pencils",
            required_quantity=12,
            source_text="12 pencils",
            confidence=1.0,
        ),
        SupplyItemReview(
            review_id="erasers",
            req_id="erasers",
            child_id="child-1",
            item_name="erasers",
            required_quantity=2,
            source_text="2 erasers",
            confidence=1.0,
        ),
    ),
)
st.session_state.setdefault("parent_added_review_items", ())
st.session_state.setdefault("extraction_errors", {})
st.session_state.setdefault("list_inputs", ())
st.session_state.setdefault(app.PERSONALIZE_SELECTED_VIEW_KEY, "child-1")
app._render_review(st)
"""
    )
    test_app.session_state["settled:pencils:expanded"] = True
    test_app.session_state["settled:erasers:expanded"] = False
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _widget(
    test_app: AppTest,
    widget_type: str,
    durable_key: str,
) -> Any:
    widgets = getattr(test_app, widget_type)
    return widgets(key=app.intake_widget_key(durable_key))


def _set_widget(
    test_app: AppTest,
    widget_type: str,
    durable_key: str,
    value: Any,
) -> AppTest:
    _widget(test_app, widget_type, durable_key).set_value(value).run()
    _assert_no_exception(test_app)
    return test_app


def _click_label(test_app: AppTest, label: str) -> AppTest:
    button = next(
        candidate
        for candidate in test_app.button
        if candidate.label == label
    )
    button.click().run()
    _assert_no_exception(test_app)
    return test_app


def _complete_students(
    test_app: AppTest,
    names: tuple[str, ...],
) -> AppTest:
    _set_widget(
        test_app,
        "number_input",
        "child_count",
        len(names),
    )
    for index, name in enumerate(names):
        _set_widget(
            test_app,
            "radio",
            f"entity_type_{index}",
            "Student",
        )
        _set_widget(
            test_app,
            "text_input",
            f"student_name_{index}",
            name,
        )
        _set_widget(
            test_app,
            "selectbox",
            f"student_grade_{index}",
            f"Grade {index + 2}",
        )
    return _click_label(test_app, "Continue to budget")


def test_empty_type_change_does_not_claim_details_were_cleared() -> None:
    """FR-05: an empty Student/Classroom switch produces no clearing notice."""

    test_app = _run_app()
    _set_widget(test_app, "number_input", "child_count", 2)
    _set_widget(test_app, "radio", "entity_type_1", "Student")
    _set_widget(test_app, "radio", "entity_type_1", "Classroom")
    assert not any(
        "previous entry details were cleared" in str(message.value)
        for message in test_app.info
    )
    _set_widget(test_app, "radio", "entity_type_1", "Student")
    assert not any(
        "previous entry details were cleared" in str(message.value)
        for message in test_app.info
    )


def test_budget_modes_survive_real_widget_unmount_and_remount() -> None:
    """FR-03: combined and per-entry drafts survive conditional rendering."""

    test_app = _complete_students(_run_app(), ("Maya", "Noah"))
    assert _widget(
        test_app,
        "radio",
        "budget_mode_label",
    ).value == "A budget for each student or classroom"
    assert _widget(test_app, "text_input", "budget_0").value == "75.00"
    assert _widget(test_app, "text_input", "budget_1").value == "75.00"

    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "One combined budget",
    )
    assert _widget(
        test_app,
        "text_input",
        "combined_budget_text",
    ).value == "150.00"

    _click_label(test_app, "Back to students")
    _click_label(test_app, "Continue to budget")
    assert _widget(
        test_app,
        "radio",
        "budget_mode_label",
    ).value == "One combined budget"


def test_classroom_budget_default_tracks_count_until_parent_edits() -> None:
    """BR-71: real Budget widgets stop auto-scaling after a parent edit."""

    test_app = _run_app()
    _set_widget(test_app, "radio", "entity_type_0", "Classroom")
    _set_widget(test_app, "text_input", "teacher_name_0", "Ms. Rivera")
    _set_widget(test_app, "selectbox", "classroom_grade_0", "Grade 3")
    _set_widget(test_app, "number_input", "student_count_0", 10)
    _click_label(test_app, "Continue to budget")
    assert _widget(
        test_app,
        "text_input",
        "combined_budget_text",
    ).value == "750.00"

    _click_label(test_app, "Back to students")
    _set_widget(test_app, "number_input", "student_count_0", 12)
    _click_label(test_app, "Continue to budget")
    assert _widget(
        test_app,
        "text_input",
        "combined_budget_text",
    ).value == "900.00"

    _set_widget(
        test_app,
        "text_input",
        "combined_budget_text",
        "800.00",
    )
    _click_label(test_app, "Back to students")
    _set_widget(test_app, "number_input", "student_count_0", 15)
    _click_label(test_app, "Continue to budget")
    assert _widget(
        test_app,
        "text_input",
        "combined_budget_text",
    ).value == "800.00"


def test_preferences_do_not_narrate_unused_budget_state() -> None:
    """FR-03: confirming a budget mode exposes no internal cleanup message."""

    test_app = _complete_students(_run_app(), ("Maya", "Noah"))
    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "A budget for each student or classroom",
    )
    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "One combined budget",
    )
    _click_label(test_app, "Continue to shopping preferences")

    parent_messages = tuple(
        str(message.value).casefold()
        for message in test_app.info
    )
    assert not any(
        "draft" in message or "cleared" in message
        for message in parent_messages
    )


def test_preferences_explain_discarded_entered_individual_budgets() -> None:
    """FR-03: the screen names a real consequence without internal vocabulary."""

    test_app = _complete_students(_run_app(), ("Maya", "Noah"))
    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "A budget for each student or classroom",
    )
    _set_widget(test_app, "text_input", "budget_0", "42.00")
    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "One combined budget",
    )
    _click_label(test_app, "Continue to shopping preferences")

    assert any(
        str(message.value) == (
            "The individual amounts you entered no longer apply because "
            "you chose one combined budget."
        )
        for message in test_app.info
    )


def test_preferences_explain_discarded_entered_combined_budget() -> None:
    """FR-03: the reverse mode change explains only the amount affected."""

    test_app = _complete_students(_run_app(), ("Maya", "Noah"))
    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "One combined budget",
    )
    _set_widget(
        test_app,
        "text_input",
        "combined_budget_text",
        "125.00",
    )
    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "A budget for each student or classroom",
    )
    _click_label(test_app, "Continue to shopping preferences")

    assert any(
        str(message.value) == (
            "The combined amount you entered no longer applies because you "
            "chose a budget for each student or classroom."
        )
        for message in test_app.info
    )


def test_preferences_survive_banner_widget_cleanup_and_remount() -> None:
    """FR-04: advanced settings survive a real section banner round-trip."""

    test_app = _complete_students(_run_app(), ("Maya",))
    _click_label(test_app, "Continue to shopping preferences")
    _set_widget(
        test_app,
        "selectbox",
        "fulfillment_label",
        "Pickup only",
    )
    _set_widget(
        test_app,
        "number_input",
        "store_radius_miles",
        6.5,
    )
    _set_widget(
        test_app,
        "selectbox",
        "sales_tax_state",
        "California",
    )
    _set_widget(
        test_app,
        "text_input",
        "tax_rate_text",
        "8.125",
    )

    test_app.button(key="intake_section_navigation_1").click().run()
    _assert_no_exception(test_app)
    test_app.button(key="intake_section_navigation_3").click().run()
    _assert_no_exception(test_app)

    assert _widget(
        test_app,
        "selectbox",
        "fulfillment_label",
    ).value == "Pickup only"
    assert _widget(
        test_app,
        "number_input",
        "store_radius_miles",
    ).value == 6.5
    assert _widget(
        test_app,
        "selectbox",
        "sales_tax_state",
    ).value == "California"
    assert _widget(
        test_app,
        "text_input",
        "tax_rate_text",
    ).value == "8.125"


def test_untouched_defaults_are_committed_before_continue() -> None:
    """FR-03/FR-04/BR-02: displayed defaults reach the intake plan untouched."""

    test_app = _complete_students(_run_app(), ("Maya",))
    assert _widget(
        test_app,
        "text_input",
        "combined_budget_text",
    ).value == app.DEFAULT_BUDGET_TEXT
    _click_label(test_app, "Continue to shopping preferences")
    assert _widget(
        test_app,
        "number_input",
        "store_radius_miles",
    ).value == app.DEFAULT_RADIUS_MILES
    assert _widget(
        test_app,
        "text_input",
        "tax_rate_text",
    ).value == "7.0"

    _click_label(test_app, "Continue to the lists")
    intake = test_app.session_state["intake"]
    assert intake["budget_total"] == 7_500
    assert intake["store_radius_miles"] == 10.0
    assert intake["tax_basis_points"] == 700


def test_setup_callbacks_keep_captions_destinations_and_validation_aligned() -> None:
    """Setup: real widgets render immediately through every callback transition."""

    test_app = _run_app()
    assert any(
        button.label == "Continue to budget"
        for button in test_app.button
    )
    _click_label(test_app, "Continue to budget")
    assert test_app.session_state["intake_step"] == 1
    assert any(
        "Choose Student or Classroom" in str(error.value)
        for error in test_app.error
    )

    _set_widget(test_app, "radio", "entity_type_0", "Student")
    _set_widget(test_app, "text_input", "student_name_0", "Maya")
    _set_widget(test_app, "selectbox", "student_grade_0", "Grade 2")
    _click_label(test_app, "Continue to budget")
    assert test_app.session_state["intake_step"] == 2
    assert {
        button.label for button in test_app.button
    }.issuperset(
        {"Back to students", "Continue to shopping preferences"}
    )

    _set_widget(
        test_app,
        "text_input",
        "combined_budget_text",
        "0",
    )
    _click_label(test_app, "Continue to shopping preferences")
    assert test_app.session_state["intake_step"] == 2
    assert any(
        "greater than zero" in str(error.value)
        for error in test_app.error
    )
    _set_widget(
        test_app,
        "text_input",
        "combined_budget_text",
        "150.00",
    )
    _click_label(test_app, "Continue to shopping preferences")
    assert test_app.session_state["intake_step"] == 3
    assert {
        button.label for button in test_app.button
    }.issuperset({"Back to budget", "Continue to the lists"})

    _click_label(test_app, "Back to budget")
    assert test_app.session_state["intake_step"] == 2
    assert {
        button.label for button in test_app.button
    }.issuperset(
        {"Back to students", "Continue to shopping preferences"}
    )
    _click_label(test_app, "Back to students")
    assert test_app.session_state["intake_step"] == 1
    assert any(
        button.label == "Continue to budget"
        for button in test_app.button
    )

    _click_label(test_app, "Continue to budget")
    _click_label(test_app, "Continue to shopping preferences")
    _set_widget(
        test_app,
        "text_input",
        "tax_rate_text",
        "not a rate",
    )
    _click_label(test_app, "Continue to the lists")
    assert test_app.session_state["screen"] == "intake"
    assert test_app.session_state["intake_step"] == 3
    assert any(
        "Enter a tax rate" in str(error.value)
        for error in test_app.error
    )
    _set_widget(test_app, "text_input", "tax_rate_text", "7.0")
    _click_label(test_app, "Continue to the lists")
    assert test_app.session_state["screen"] == "lists"


def test_section_statement_and_submitted_scope_use_same_live_state() -> None:
    """A5: the section explanation cannot diverge from the submitted IDs."""

    test_app = _run_section_screen()
    scope_text = " ".join(str(item.value) for item in test_app.markdown)
    assert "We will extract items from 1st Grade" in scope_text
    assert "Highly Capable Class" not in scope_text

    question = next(
        checkbox
        for checkbox in test_app.checkbox
        if checkbox.label == "Also use Highly Capable Class for Ms. K?"
    )
    assert question.value is False
    assert question.disabled is False
    question.set_value(True).run()
    _assert_no_exception(test_app)
    scope_text = " ".join(str(item.value) for item in test_app.markdown)
    assert (
        "We will extract items from 1st Grade and Highly Capable Class"
        in scope_text
    )
    override_selector = next(
        item
        for item in test_app.multiselect
        if item.label == "Sections for Ms. K"
    )
    assert override_selector.value == [
        "grade-1",
        "highly-capable",
    ]

    _click_label(test_app, "Continue with these sections")
    selection = test_app.session_state["document_selections"]["child-1"]
    assert selection.selected_section_ids == (
        "grade-1",
        "highly-capable",
    )
    assert selection.selected_section_labels == (
        "1st Grade",
        "Highly Capable Class",
    )


def test_section_override_recomputes_excluded_section_count() -> None:
    """Part A-2: live override state changes the not-read count."""

    test_app = _run_section_screen()
    captions = " ".join(str(item.value) for item in test_app.caption)
    assert "1 section was for another grade" in captions

    override = next(
        checkbox
        for checkbox in test_app.checkbox
        if checkbox.label == "Use a different section selection"
    )
    override.set_value(True).run()
    _assert_no_exception(test_app)
    selector = next(
        item
        for item in test_app.multiselect
        if item.label == "Sections for Ms. K"
    )
    selector.set_value(["grade-1", "grade-2"]).run()
    _assert_no_exception(test_app)

    captions = " ".join(str(item.value) for item in test_app.caption)
    assert "section was for another grade" not in captions


def test_personalize_item_expanders_and_controls_keep_independent_state() -> None:
    """FR-12: real keyed item disclosures survive their control reruns."""

    test_app = _run_personalize_screen()
    assert test_app.session_state["settled:pencils:expanded"] is True
    assert test_app.session_state["settled:erasers:expanded"] is False

    test_app.number_input(
        key="settled:pencils:quantity"
    ).set_value(24).run()
    _assert_no_exception(test_app)
    assert test_app.session_state["settled:pencils:expanded"] is True
    assert test_app.session_state["settled:erasers:expanded"] is False
    assert test_app.number_input(
        key="settled:pencils:quantity"
    ).value == 24

    test_app.toggle(
        key="settled:pencils:more-options"
    ).set_value(True).run()
    _assert_no_exception(test_app)
    test_app.text_input(
        key="settled:pencils:brand"
    ).set_value("Ticonderoga").run()
    _assert_no_exception(test_app)
    assert test_app.session_state["settled:pencils:expanded"] is True
    assert test_app.session_state["settled:erasers:expanded"] is False
    assert test_app.number_input(
        key="settled:pencils:quantity"
    ).value == 24
    assert test_app.text_input(
        key="settled:pencils:brand"
    ).value == "Ticonderoga"
