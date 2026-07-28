"""Deterministic tests for the mandatory organized-list review boundary."""

import pytest

from agent.review import (
    apply_conditional_answers,
    conditional_review_questions,
    confirmed_requirements,
    organize_extractions,
    reviewed_envelopes,
    unresolved_required_items,
)
from agent.schema import ExtractionEnvelope, Requirement


def _requirement(
    req_id: str,
    item: str,
    *,
    confidence: float = 1.0,
) -> Requirement:
    return Requirement(
        req_id=req_id,
        child_id="child-1",
        raw_text=f"2 {item}",
        canonical_item=item,
        quantity=2,
        extraction_confidence=confidence,
    )


def test_organize_extractions_sorts_and_preserves_source_text() -> None:
    extraction = ExtractionEnvelope(
        requirements=(
            _requirement("z", "tissues"),
            _requirement("a", "pencils", confidence=0.6),
        )
    )

    rows = organize_extractions({"child-1": extraction})

    assert [row.item_name for row in rows] == ["pencils", "tissues"]
    assert rows[0].source_text == "2 pencils"
    assert rows[0].issue_codes == ("low_confidence",)
    assert all(row.review_status == "pending" for row in rows)


def test_required_rows_must_be_confirmed_before_planning() -> None:
    rows = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=(_requirement("a", "pencils"),)
            )
        }
    )

    assert unresolved_required_items(rows) == rows
    with pytest.raises(ValueError, match="Required items remain unresolved"):
        confirmed_requirements(rows)
    assert len(
        confirmed_requirements(rows, allow_unresolved=True)
    ) == 1


def test_only_confirmed_active_rows_reach_cart_contract() -> None:
    rows = list(
        organize_extractions(
            {
                "child-1": ExtractionEnvelope(
                    requirements=(
                        _requirement("a", "pencils"),
                        _requirement("b", "tissues"),
                    )
                )
            }
        )
    )
    rows[0] = rows[0].model_copy(
        update={"review_status": "confirmed"}
    )
    rows[1] = rows[1].model_copy(
        update={
            "review_status": "confirmed",
            "already_owned": True,
        }
    )

    requirements = confirmed_requirements(rows)

    assert [item.canonical_item for item in requirements] == ["pencils"]


def test_reviewed_envelopes_preserve_document_metadata() -> None:
    original = {
        "child-1": ExtractionEnvelope(
            stated_grades=("2",),
            stated_teachers=("Ms. Rivera",),
            requirements=(_requirement("a", "pencils"),),
            uninterpreted_lines=("Unreadable footer",),
            skipped_lines=("Repeated translation",),
        )
    }
    rows = [
        row.model_copy(update={"review_status": "confirmed"})
        for row in organize_extractions(original)
    ]

    reviewed = reviewed_envelopes(original, rows)

    assert reviewed["child-1"].stated_grades == ("2",)
    assert reviewed["child-1"].stated_teachers == ("Ms. Rivera",)
    assert reviewed["child-1"].uninterpreted_lines == ("Unreadable footer",)
    assert reviewed["child-1"].skipped_lines == ("Repeated translation",)
    assert len(reviewed["child-1"].requirements) == 1


def test_school_provided_item_stays_visible_but_never_enters_cart() -> None:
    """District-supplied items survive review as display-only evidence."""

    requirement = Requirement(
        req_id="provided",
        child_id="child-1",
        raw_text="District will be supplying: 1 box of crayons",
        canonical_item="crayons",
        quantity=1,
        unit_type="box",
        is_required=False,
        is_purchasable=False,
        requirement_type="optional",
        provided_by_school=True,
        supply_scope="shared",
        source_section="District will be supplying",
        source_page=2,
        extraction_confidence=1.0,
    )
    rows = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=(requirement,)
            )
        }
    )

    confirmed = confirmed_requirements(rows)

    assert len(confirmed) == 1
    assert confirmed[0].provided_by_school is True
    assert confirmed[0].is_purchasable is False
    assert confirmed[0].supply_scope == "shared"
    assert confirmed[0].raw_text == requirement.raw_text


def test_conditional_item_requires_parent_answer_and_preserves_scope() -> None:
    """A last-name condition must be answered before the required cart builds."""

    requirement = Requirement(
        req_id="conditional",
        child_id="child-1",
        raw_text="Ziploc bags — Last Name A-G",
        canonical_item="zip_top_bags",
        quantity=1,
        condition="Last Name A-G",
        condition_applies=None,
        supply_scope="shared",
        extraction_confidence=1.0,
    )
    row = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=(requirement,)
            )
        }
    )[0]

    assert row.issue_codes == ("conditional_item",)
    assert unresolved_required_items((row,))

    excluded = row.model_copy(
        update={
            "review_status": "confirmed",
            "condition_applies": False,
        }
    )
    confirmed = confirmed_requirements((excluded,))

    assert confirmed[0].condition == "Last Name A-G"
    assert confirmed[0].condition_applies is False
    assert confirmed[0].is_purchasable is False
    assert confirmed[0].supply_scope == "shared"


def test_mutually_exclusive_branches_are_one_question_and_one_purchase() -> None:
    """Exactly one selected last-name branch may enter the cart."""

    group_id = "last-name:child-1:2:grade-4:zip_top_bags"
    branches = tuple(
        Requirement(
            req_id=req_id,
            child_id="child-1",
            raw_text=source,
            canonical_item="zip_top_bags",
            quantity=1,
            condition=condition,
            condition_group_id=group_id,
            condition_question=(
                "This list assigns bags by last name. Which applies?"
            ),
            condition_option=label,
            source_page=2,
            extraction_confidence=1.0,
        )
        for req_id, source, condition, label in (
            (
                "gallon",
                "Gallon bags | 4th: Last Name A-G",
                "Last Name A-G",
                "Gallon bags — Last Name A-G",
            ),
            (
                "quart",
                "Quart bags | 4th: Last Name H-P",
                "Last Name H-P",
                "Quart bags — Last Name H-P",
            ),
            (
                "sandwich",
                "Sandwich bags | 4th: Last Name Q-Z",
                "Last Name Q-Z",
                "Sandwich bags — Last Name Q-Z",
            ),
        )
    )
    rows = organize_extractions(
        {"child-1": ExtractionEnvelope(requirements=branches)}
    )

    questions = conditional_review_questions(rows)

    assert len(questions) == 1
    assert questions[0].prompt == (
        "This list assigns bags by last name. Which applies?"
    )
    assert [option.label for option in questions[0].options] == [
        "Gallon bags — Last Name A-G",
        "Quart bags — Last Name H-P",
        "Sandwich bags — Last Name Q-Z",
    ]

    answered = apply_conditional_answers(
        rows,
        {group_id: "child-1:quart"},
    )
    answered = tuple(
        row.model_copy(update={"review_status": "confirmed"})
        for row in answered
    )
    confirmed = confirmed_requirements(answered)

    purchased = [
        requirement
        for requirement in confirmed
        if requirement.is_purchasable
    ]
    assert [requirement.req_id for requirement in purchased] == ["quart"]
    assert sum(
        requirement.condition_applies is True
        for requirement in confirmed
    ) == 1
    assert sum(
        requirement.condition_applies is False
        for requirement in confirmed
    ) == 2


def test_mutually_exclusive_branches_cannot_bypass_parent_choice() -> None:
    """The unresolved-item override cannot purchase multiple branches."""

    group_id = "last-name:child-1:2:grade-4:zip_top_bags"
    rows = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=tuple(
                    Requirement(
                        req_id=req_id,
                        child_id="child-1",
                        raw_text=source,
                        canonical_item="zip_top_bags",
                        quantity=1,
                        condition=condition,
                        condition_group_id=group_id,
                        condition_question=(
                            "This list assigns bags by last name. Which applies?"
                        ),
                        condition_option=source,
                        extraction_confidence=1.0,
                    )
                    for req_id, source, condition in (
                        ("gallon", "Gallon A-G", "Last Name A-G"),
                        ("quart", "Quart H-P", "Last Name H-P"),
                    )
                )
            )
        }
    )

    with pytest.raises(
        ValueError,
        match="This list assigns bags by last name",
    ):
        confirmed_requirements(rows, allow_unresolved=True)
