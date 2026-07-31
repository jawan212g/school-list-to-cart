"""Streamlit integration tests for intake widget cleanup and remounting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import app
from agent.review import confirmed_requirements
from agent.rules import SYSTEM_DECISION_PARENT_CHOSE_SCHOOL_PROVIDED_ITEM


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


def _session_value(
    test_app: AppTest,
    key: str,
    default: Any = None,
) -> Any:
    """Read AppTest's keyed state without assuming Mapping.get support."""

    try:
        return test_app.session_state[key]
    except KeyError:
        return default


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
from agent.review import organize_extractions
from agent.schema import ExtractionEnvelope, Requirement

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
    {
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
                    req_id="erasers",
                    child_id="child-1",
                    raw_text="2 erasers",
                    canonical_item="erasers",
                    quantity=2,
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="tissues",
                    child_id="child-1",
                    raw_text="1 box of tissues, optional",
                    canonical_item="tissues",
                    quantity=1,
                    unit_type="box",
                    is_required=False,
                    requirement_type="optional",
                    extraction_confidence=1.0,
                ),
                Requirement(
                    req_id="school-crayons",
                    child_id="child-1",
                    raw_text="District will provide 24 crayons",
                    canonical_item="crayons",
                    quantity=24,
                    unit_type="each",
                    is_required=False,
                    is_purchasable=False,
                    requirement_type="optional",
                    provided_by_school=True,
                    source_document="Maya district list.pdf",
                    source_section="District will provide",
                    source_page=2,
                    extraction_confidence=1.0,
                ),
            )
        )
    },
)
st.session_state.setdefault(
    "review_items",
    organize_extractions(dict(st.session_state["extracted_lists"])),
)
st.session_state.setdefault("parent_added_review_items", ())
st.session_state.setdefault("extraction_errors", {})
st.session_state.setdefault("list_inputs", ())
st.session_state.setdefault(app.PERSONALIZE_SELECTED_VIEW_KEY, "child-1")
app._render_review(st)
"""
    )
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _run_personalize_decision_screen() -> AppTest:
    """Mount the production Personalize screen with one flagged source item."""

    test_app = AppTest.from_string(
        """
import streamlit as st
import app
from agent.review import organize_extractions
from agent.schema import ExtractionEnvelope, Requirement

st.session_state.setdefault(
    "intake",
    {
        "children": (
            {
                "child_id": "child-1",
                "label": "Jawan",
                "grade": "Grade 5",
            },
        )
    },
)
st.session_state.setdefault(
    "extracted_lists",
    {
        "child-1": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="composition",
                    child_id="child-1",
                    raw_text="1 composition notebook",
                    canonical_item="composition_notebooks",
                    quantity=1,
                    extraction_confidence=0.6,
                ),
            )
        )
    },
)
st.session_state.setdefault(
    "review_items",
    organize_extractions(dict(st.session_state["extracted_lists"])),
)
st.session_state.setdefault("parent_added_review_items", ())
st.session_state.setdefault("extraction_errors", {})
st.session_state.setdefault("list_inputs", ())
st.session_state.setdefault(app.PERSONALIZE_SELECTED_VIEW_KEY, "summary")
app._render_review(st)
"""
    )
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _run_personalize_two_decision_screen() -> AppTest:
    """Mount production Personalize with two independently flagged items."""

    test_app = AppTest.from_string(
        """
import streamlit as st
import app
from agent.review import organize_extractions
from agent.schema import ExtractionEnvelope, Requirement

st.session_state.setdefault(
    "intake",
    {
        "children": (
            {
                "child_id": "child-1",
                "label": "Mr. G",
                "grade": "Grade 5",
            },
        )
    },
)
st.session_state.setdefault(
    "extracted_lists",
    {
        "child-1": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id="child-1",
                    raw_text="24 pencils",
                    canonical_item="pencils",
                    quantity=24,
                    extraction_confidence=0.6,
                ),
                Requirement(
                    req_id="sticky-notes",
                    child_id="child-1",
                    raw_text="2 packs of sticky notes",
                    canonical_item="sticky_notes",
                    quantity=2,
                    unit_type="pack",
                    package_quantity_state="specified",
                    extraction_confidence=0.6,
                ),
            )
        )
    },
)
st.session_state.setdefault(
    "review_items",
    organize_extractions(dict(st.session_state["extracted_lists"])),
)
st.session_state.setdefault("parent_added_review_items", ())
st.session_state.setdefault("extraction_errors", {})
st.session_state.setdefault("list_inputs", ())
st.session_state.setdefault(app.PERSONALIZE_SELECTED_VIEW_KEY, "summary")
app._render_review(st)
"""
    )
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _run_personalize_package_decision_screen() -> AppTest:
    """Mount the production Personalize path with one missing pack count."""

    test_app = AppTest.from_string(
        """
import streamlit as st
import app
from agent.review import organize_extractions
from agent.schema import ExtractionEnvelope, Requirement

st.session_state.setdefault(
    "intake",
    {
        "children": (
            {
                "child_id": "child-1",
                "label": "Kevin",
                "grade": "Grade 6",
            },
        )
    },
)
st.session_state.setdefault(
    "extracted_lists",
    {
        "child-1": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="red-pens",
                    child_id="child-1",
                    raw_text="1 Pack of Red Pens",
                    canonical_item="pens",
                    quantity=1,
                    unit_type="pack",
                    extraction_confidence=1.0,
                ),
            )
        )
    },
)
st.session_state.setdefault(
    "review_items",
    organize_extractions(dict(st.session_state["extracted_lists"])),
)
st.session_state.setdefault("parent_added_review_items", ())
st.session_state.setdefault("extraction_errors", {})
st.session_state.setdefault("list_inputs", ())
st.session_state.setdefault(app.PERSONALIZE_SELECTED_VIEW_KEY, "child-1")
app._render_review(st)
"""
    )
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _run_composition_merge_screen() -> AppTest:
    """Mount the production duplicate-resolution screen with two variants."""

    test_app = AppTest.from_string(
        """
import streamlit as st
import app
from agent.requirement_merge import consolidate_extractions
from agent.schema import ExtractionEnvelope, Requirement

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
st.session_state.setdefault("requirement_merge_result", merge_result)
st.session_state.setdefault("unmerged_extracted_lists", {"child-1": envelope})
st.session_state.setdefault(
    "intake",
    {
        "children": (
            {
                "child_id": "child-1",
                "label": "Jawan",
                "grade": "Grade 5",
            },
        )
    },
)
st.session_state.setdefault("list_inputs", ())
st.session_state.setdefault("review_items", ())
st.session_state.setdefault("parent_added_review_items", ())
st.session_state.setdefault("screen", "requirement_merge")
if st.session_state["screen"] == "requirement_merge":
    app._render_requirement_merge(st)
else:
    app._refresh_personalize_review_cache(
        st.session_state,
        dict(st.session_state["extracted_lists"]),
    )
"""
    )
    test_app.run()
    _assert_no_exception(test_app)
    return test_app


def _composition_review_rows(test_app: AppTest) -> tuple[Any, ...]:
    return tuple(_session_value(test_app, "review_items", ()))


def test_merge_exclusion_checkbox_keeps_every_variant_out() -> None:
    """The production checkbox alone excludes both displayed variants."""

    test_app = _run_composition_merge_screen()
    checkbox = next(
        item
        for item in test_app.checkbox
        if item.label == "Do not add this item to the cart"
    )
    checkbox.check().run()
    _assert_no_exception(test_app)
    _click_label(test_app, "Continue with these choices")

    assert _composition_review_rows(test_app) == ()


def test_merge_restoring_one_variant_does_not_restore_its_sibling() -> None:
    """One restored quantity unchecks exclusion without reviving another zero."""

    test_app = _run_composition_merge_screen()
    checkbox = next(
        item
        for item in test_app.checkbox
        if item.label == "Do not add this item to the cart"
    )
    checkbox.check().run()
    _assert_no_exception(test_app)
    test_app.number_input[0].set_value(1).run()
    _assert_no_exception(test_app)
    checkbox = next(
        item
        for item in test_app.checkbox
        if item.label == "Do not add this item to the cart"
    )
    assert checkbox.value is False
    _click_label(test_app, "Continue with these choices")

    rows = _composition_review_rows(test_app)
    assert len(rows) == 1
    assert rows[0].required_quantity == 1
    assert rows[0].source_text == "1 graph paper composition notebook"


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
    assert (
        _session_value(test_app, app.NEXT_TASK_SCROLL_COMPLETED_KEY)
        is None
    )
    assert any(
        button.label == "Continue to budget"
        for button in test_app.button
    )
    _click_label(test_app, "Continue to budget")
    assert test_app.session_state["intake_step"] == 1
    assert (
        _session_value(test_app, app.NEXT_TASK_SCROLL_COMPLETED_KEY)
        is None
    )
    assert any(
        "Choose Student or Classroom" in str(error.value)
        for error in test_app.error
    )

    _set_widget(test_app, "radio", "entity_type_0", "Student")
    _set_widget(test_app, "text_input", "student_name_0", "Maya")
    _set_widget(test_app, "selectbox", "student_grade_0", "Grade 2")
    _click_label(test_app, "Continue to budget")
    assert test_app.session_state["intake_step"] == 2
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 1
    assert (
        _session_value(test_app, app.NEXT_TASK_SCROLL_PENDING_KEY)
        is None
    )
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
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 1
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
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 2
    assert {
        button.label for button in test_app.button
    }.issuperset({"Back to budget", "Continue to the lists"})

    _click_label(test_app, "Back to budget")
    assert test_app.session_state["intake_step"] == 2
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 2
    assert {
        button.label for button in test_app.button
    }.issuperset(
        {"Back to students", "Continue to shopping preferences"}
    )
    _click_label(test_app, "Back to students")
    assert test_app.session_state["intake_step"] == 1
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 2
    assert any(
        button.label == "Continue to budget"
        for button in test_app.button
    )

    _click_label(test_app, "Continue to budget")
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 3
    _click_label(test_app, "Continue to shopping preferences")
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 4
    _set_widget(
        test_app,
        "text_input",
        "tax_rate_text",
        "not a rate",
    )
    _click_label(test_app, "Continue to the lists")
    assert test_app.session_state["screen"] == "intake"
    assert test_app.session_state["intake_step"] == 3
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 4
    assert any(
        "Enter a tax rate" in str(error.value)
        for error in test_app.error
    )
    _set_widget(test_app, "text_input", "tax_rate_text", "7.0")
    _click_label(test_app, "Continue to the lists")
    assert test_app.session_state["screen"] == "lists"
    assert test_app.session_state[app.NEXT_TASK_SCROLL_COMPLETED_KEY] == 5
    assert (
        _session_value(test_app, app.NEXT_TASK_SCROLL_PENDING_KEY)
        is None
    )


def test_section_statement_and_submitted_scope_use_same_live_state() -> None:
    """A5: the section explanation cannot diverge from the submitted IDs."""

    test_app = _run_section_screen()
    scope_text = " ".join(str(item.value) for item in test_app.markdown)
    assert "We will read items from 1st Grade" in scope_text
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
        "We will read items from 1st Grade and Highly Capable Class"
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
    review_items = tuple(test_app.session_state["review_items"])
    pencils = next(item for item in review_items if item.item_name == "pencils")
    erasers = next(item for item in review_items if item.item_name == "erasers")
    pencils_expander_key = app.personalize_settled_expander_key(pencils)
    erasers_expander_key = app.personalize_settled_expander_key(erasers)

    pencils_expander = next(
        expander
        for expander in test_app.expander
        if expander.label == app.review_understanding_text(pencils)
    )
    erasers_expander = next(
        expander
        for expander in test_app.expander
        if expander.label == app.review_understanding_text(erasers)
    )
    pencils_quantity = next(
        widget
        for widget in pencils_expander.number_input
        if widget.label == "Quantity"
    )
    erasers_quantity = next(
        widget
        for widget in erasers_expander.number_input
        if widget.label == "Quantity"
    )

    test_app.session_state[pencils_expander_key] = True
    test_app.run()
    _assert_no_exception(test_app)
    pencils_expander = next(
        expander
        for expander in test_app.expander
        if any(
            widget.key == pencils_quantity.key
            for widget in expander.number_input
        )
    )
    assert pencils_expander.proto.expanded is True

    test_app.number_input(key=pencils_quantity.key).set_value(24).run()
    _assert_no_exception(test_app)
    test_app.session_state[erasers_expander_key] = True
    test_app.run()
    _assert_no_exception(test_app)
    pencils_expander = next(
        expander
        for expander in test_app.expander
        if any(
            widget.key == pencils_quantity.key
            for widget in expander.number_input
        )
    )
    erasers_expander = next(
        expander
        for expander in test_app.expander
        if any(
            widget.key == erasers_quantity.key
            for widget in expander.number_input
        )
    )
    assert pencils_expander.proto.expanded is True
    assert erasers_expander.proto.expanded is True
    assert test_app.number_input(key=pencils_quantity.key).value == 24

    test_app.number_input(key=erasers_quantity.key).set_value(5).run()
    _assert_no_exception(test_app)
    pencils_expander = next(
        expander
        for expander in test_app.expander
        if any(
            widget.key == pencils_quantity.key
            for widget in expander.number_input
        )
    )
    erasers_expander = next(
        expander
        for expander in test_app.expander
        if any(
            widget.key == erasers_quantity.key
            for widget in expander.number_input
        )
    )
    assert pencils_expander.proto.expanded is True
    assert erasers_expander.proto.expanded is True
    assert test_app.number_input(key=pencils_quantity.key).value == 24
    assert test_app.number_input(key=erasers_quantity.key).value == 5


def test_personalize_optional_item_can_return_to_cart() -> None:
    """FR-12: an optional item is left out by default but is not a one-way door."""

    test_app = _run_personalize_screen()
    optional_item = next(
        item
        for item in test_app.session_state["review_items"]
        if item.item_name == "tissues"
    )
    assert optional_item.optional is True
    expander_key = app.personalize_row_expander_key(
        f"optional:{optional_item.review_id}"
    )
    test_app.session_state[expander_key] = True
    test_app.run()
    _assert_no_exception(test_app)
    optional_expander = next(
        expander
        for expander in test_app.expander
        if expander.label == app.review_understanding_text(optional_item)
    )
    optional_checkbox = next(
        checkbox
        for checkbox in optional_expander.checkbox
        if checkbox.label == "This item is optional"
    )
    optional_checkbox.set_value(False).run()
    _assert_no_exception(test_app)

    updated = next(
        item
        for item in test_app.session_state["review_items"]
        if item.review_id == optional_item.review_id
    )
    assert updated.optional is False
    assert any(
        "In your cart (3)" in markdown.value
        for markdown in test_app.markdown
    )


def test_personalize_school_provided_item_can_be_added_with_provenance() -> None:
    """FR-12: a parent can override a school-provided line without losing evidence."""

    test_app = _run_personalize_screen()
    original = next(
        item
        for item in test_app.session_state["review_items"]
        if item.req_id == "school-crayons"
    )
    original_sources = original.sources
    button = next(
        candidate
        for candidate in test_app.button
        if candidate.label == "Add this to my cart instead"
    )

    button.click().run()
    _assert_no_exception(test_app)

    updated = next(
        item
        for item in test_app.session_state["review_items"]
        if item.review_id == original.review_id
    )
    assert updated.provided_by_school is False
    assert updated.is_purchasable is True
    assert updated.optional is False
    assert updated.review_status == "confirmed"
    assert updated.source_text == original.source_text
    assert updated.source_document == original.source_document
    assert updated.source_section == original.source_section
    assert updated.source_page == original.source_page
    assert updated.sources == original_sources
    assert (
        SYSTEM_DECISION_PARENT_CHOSE_SCHOOL_PROVIDED_ITEM
        in updated.system_decisions
    )
    assert any(
        "In your cart (3)" in markdown.value
        for markdown in test_app.markdown
    )

    parent_decisions = tuple(test_app.session_state["parent_decisions"])
    assert len(parent_decisions) == 1
    assert parent_decisions[0].actor == "parent"
    assert parent_decisions[0].affected_lines == ("school-crayons",)
    assert "the school will provide it" in parent_decisions[0].rationale

    requirement = confirmed_requirements((updated,))[0]
    assert requirement.is_purchasable is True
    assert requirement.is_required is True
    assert requirement.provided_by_school is False
    assert requirement.raw_text == original.source_text
    assert requirement.source_document == original.source_document
    assert requirement.source_section == original.source_section
    assert requirement.source_page == original.source_page
    assert requirement.sources == original_sources
    assert (
        SYSTEM_DECISION_PARENT_CHOSE_SCHOOL_PROVIDED_ITEM
        in requirement.system_decisions
    )


def test_personalize_edit_survives_summary_round_trip_without_button_crash() -> None:
    """A flagged student view can be edited, left, and reopened safely."""

    test_app = _run_personalize_decision_screen()
    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("child-1").run()
    _assert_no_exception(test_app)
    assert (
        test_app.session_state[app.PERSONALIZE_SELECTED_VIEW_KEY]
        == "child-1"
    )
    first_bulk_key = next(
        button.key
        for button in test_app.button
        if button.label == "Approve all AI recommendations"
    )

    _click_label(test_app, "Change item or quantity")
    assert (
        test_app.session_state[app.PERSONALIZE_SELECTED_VIEW_KEY]
        == "child-1"
    )

    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("summary").run()
    _assert_no_exception(test_app)
    assert (
        test_app.session_state[app.PERSONALIZE_SELECTED_VIEW_KEY]
        == "summary"
    )

    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("child-1").run()
    _assert_no_exception(test_app)
    assert (
        test_app.session_state[app.PERSONALIZE_SELECTED_VIEW_KEY]
        == "child-1"
    )
    reopened_bulk_key = next(
        button.key
        for button in test_app.button
        if button.label == "Approve all AI recommendations"
    )
    assert reopened_bulk_key != first_bulk_key


def test_unresolved_open_student_button_survives_a_view_round_trip() -> None:
    """Every Personalize button remounts under a new visit identity."""

    test_app = _run_personalize_two_decision_screen()
    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("child-1").run()
    _assert_no_exception(test_app)

    _click_label(test_app, "Change item or quantity")
    _click_label(test_app, "Send selection to cart")

    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("summary").run()
    _assert_no_exception(test_app)
    _click_label(test_app, "Use these choices and build my shopping plan")

    unresolved_open = next(
        button
        for button in test_app.button
        if (
            button.label == "Open Mr. G"
            and "unresolved-student" in str(button.key)
        )
    )
    first_unresolved_key = unresolved_open.key
    unresolved_open.click().run()
    _assert_no_exception(test_app)

    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("summary").run()
    _assert_no_exception(test_app)
    _click_label(test_app, "Use these choices and build my shopping plan")
    _assert_no_exception(test_app)
    reopened_unresolved = next(
        button
        for button in test_app.button
        if (
            button.label == "Open Mr. G"
            and "unresolved-student" in str(button.key)
        )
    )
    assert reopened_unresolved.key != first_unresolved_key


def test_partial_personalize_actions_leave_the_same_decision_visible_to_gate() -> None:
    """BR-52: Summary and submission consume one pending-decision truth."""

    test_app = _run_personalize_two_decision_screen()
    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("child-1").run()
    _assert_no_exception(test_app)

    _click_label(test_app, "Remove item from cart")

    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("summary").run()
    _assert_no_exception(test_app)

    assert any(
        markdown.value == "**1**  \nNeeds a decision"
        for markdown in test_app.markdown
    )
    assert any(
        expander.label == "Review 1 decision"
        for expander in test_app.expander
    )
    assert any(
        "sticky notes" in str(markdown.value).casefold()
        for markdown in test_app.markdown
    )

    _click_label(test_app, "Use these choices and build my shopping plan")
    rendered_lines = tuple(
        str(item.value).strip()
        for item in test_app.markdown
    )
    assert "Mr. G: Sticky notes" in rendered_lines
    assert "Mr. G: Pencils" not in rendered_lines
    assert "Mr. G: Pencils and Sticky notes" not in rendered_lines
    assert any(
        button.label == "Open Mr. G"
        and "unresolved-student" in str(button.key)
        for button in test_app.button
    )


def test_parent_edit_and_gate_share_the_same_resolved_decision_set() -> None:
    """BR-52: a submitted parent edit is not reclassified as pending."""

    test_app = _run_personalize_two_decision_screen()
    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("child-1").run()
    _assert_no_exception(test_app)

    _click_label(test_app, "Change item or quantity")
    _click_label(test_app, "Send selection to cart")

    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("summary").run()
    _assert_no_exception(test_app)
    assert any(
        markdown.value == "**1**  \nNeeds a decision"
        for markdown in test_app.markdown
    )

    _click_label(test_app, "Use these choices and build my shopping plan")
    warning_text = " ".join(
        str(item.value)
        for item in (*test_app.warning, *test_app.markdown)
    ).casefold()
    assert "sticky notes" in warning_text
    assert "pencils" not in warning_text


def test_personalize_remove_action_uses_distinct_removed_group() -> None:
    """FR-12: removal is explicit and remains distinct from already-owned."""

    test_app = _run_personalize_decision_screen()
    navigation = next(
        radio
        for radio in test_app.radio
        if radio.label == "Choose a student or Summary"
    )
    navigation.set_value("child-1").run()
    _assert_no_exception(test_app)

    _click_label(test_app, "Remove item from cart")
    _assert_no_exception(test_app)

    item = test_app.session_state["review_items"][0]
    assert item.required_quantity == 0
    assert item.review_status == "deleted"
    assert item.already_owned is False
    assert any(
        markdown.value == "**Removed from cart (1)**"
        for markdown in test_app.markdown
    )
    assert not any(
        markdown.value.startswith("**Already owned")
        for markdown in test_app.markdown
    )


def test_package_count_decision_edits_items_per_package_not_order_quantity() -> None:
    """E-02: the production decision card edits the uncertainty it names."""

    test_app = _run_personalize_package_decision_screen()
    _click_label(test_app, "Change package quantity")

    package_input = next(
        widget
        for widget in test_app.number_input
        if widget.label == "Items per package"
    )
    assert package_input.value == 12
    package_input.set_value(24).run()
    _assert_no_exception(test_app)
    _click_label(test_app, "Send selection to cart")

    item = test_app.session_state["review_items"][0]
    assert item.package_size == 24
    assert item.required_quantity == 1
    assert item.unit == "pack"
