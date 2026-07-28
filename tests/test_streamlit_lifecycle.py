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
        "text_input",
        "combined_budget_text",
    ).value == "150.00"

    _set_widget(
        test_app,
        "radio",
        "budget_mode_label",
        "A budget for each student or classroom",
    )
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
    assert intake["budget_total"] == 15_000
    assert intake["store_radius_miles"] == 10.0
    assert intake["tax_basis_points"] == 700
