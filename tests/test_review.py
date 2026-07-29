"""Deterministic tests for the mandatory organized-list review boundary."""

import pytest

from agent.review import (
    apply_conditional_answers,
    apply_review_confirmations,
    ConditionalReviewOption,
    ConditionalReviewQuestion,
    conditional_review_questions,
    conditional_answers_for_selection,
    confidence_band,
    confirmed_requirements,
    deduplicate_conditional_questions,
    organize_extractions,
    review_flag_groups,
    review_issue_explanations,
    reviewed_envelopes,
    teacher_note_groups,
    unhandled_review_flag_groups,
    unresolved_required_items,
)
from agent.schema import ExtractionEnvelope, Requirement, SupplyItemReview


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


def test_unnamed_no_substitutes_routes_to_production_review() -> None:
    """BR-69: a strict generic line asks the parent instead of inventing a brand."""

    requirement = Requirement(
        req_id="tissues",
        child_id="child-1",
        raw_text="Tissues, no substitutes",
        canonical_item="tissues",
        quantity=1,
        extraction_confidence=1.0,
    )

    (row,) = organize_extractions(
        {"child-1": ExtractionEnvelope(requirements=(requirement,))}
    )
    (group,) = review_flag_groups((row,))

    assert row.brand is None
    assert row.brand_required is False
    assert row.issue_codes == ("brand_requirement_without_named_brand",)
    assert group.messages == (
        "The list says not to substitute, but it does not name a brand. "
        "Check what must stay exact.",
    )


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


def test_package_assumption_populates_editable_production_field() -> None:
    """BR-35/E-02: an inferred pack count is data, not prose only."""

    requirement = Requirement(
        req_id="erasers",
        child_id="child-1",
        raw_text="1 pack erasers",
        canonical_item="erasers",
        quantity=1,
        unit_type="pack",
        extraction_confidence=1.0,
    )

    row = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=(requirement,),
            )
        }
    )[0]
    confirmed = confirmed_requirements(
        (row.model_copy(update={"review_status": "confirmed"}),)
    )[0]

    assert row.package_size == 3
    assert row.package_quantity_state == "assumed"
    assert row.item_fulfillment_preference == "minimum_cost_at_least"
    assert confirmed.attributes.count == 3
    assert confirmed.package_quantity_state == "assumed"


def test_pack_quantity_any_is_distinct_from_unspecified() -> None:
    """BR-35: parent acceptance of any pack size remains explicit data."""

    row = SupplyItemReview(
        review_id="review",
        req_id="erasers",
        child_id="child-1",
        item_name="erasers",
        required_quantity=1,
        unit="pack",
        package_size=3,
        package_quantity_state="any",
        source_page=1,
        source_text="1 pack erasers",
        confidence=1.0,
        review_status="confirmed",
    )

    requirement = confirmed_requirements((row,))[0]

    assert requirement.package_quantity_state == "any"
    assert requirement.attributes.count == 3


def test_marked_items_and_summary_count_share_one_source() -> None:
    """FR-12: unhandled decision count equals the marked production rows."""

    rows = (
        SupplyItemReview(
            review_id="one",
            req_id="one",
            child_id="child-1",
            item_name="erasers",
            required_quantity=1,
            source_text="1 pack erasers",
            confidence=0.6,
            issue_codes=("low_confidence",),
        ),
        SupplyItemReview(
            review_id="two",
            req_id="two",
            child_id="child-1",
            item_name="tissues",
            required_quantity=2,
            source_text="2-3 tissues",
            confidence=1.0,
            issue_codes=("quantity_range",),
        ),
    )
    groups = review_flag_groups(rows)

    unhandled = unhandled_review_flag_groups(
        rows,
        groups,
        acknowledged_group_ids=(groups[0].group_id,),
    )
    marked_row_ids = {
        row_id for group in unhandled for row_id in group.row_ids
    }

    assert len(unhandled) == 1
    assert len(marked_row_ids) == 1


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


def test_confidence_is_presented_as_plain_bands() -> None:
    """Raw model confidence remains internal to BR-11."""

    assert confidence_band(0.95) == "clear"
    assert confidence_band(0.75) == "worth checking"
    assert confidence_band(0.69) == "uncertain"


def test_review_flags_explain_range_and_package_assumptions_plainly() -> None:
    """Review copy explains the choice instead of exposing issue codes."""

    ranged = SupplyItemReview(
        review_id="child-1:tissues",
        req_id="tissues",
        child_id="child-1",
        item_name="tissues",
        required_quantity=2,
        quantity_is_range=True,
        quantity_max=3,
        unit="box",
        source_text="2-3 boxes of tissues",
        confidence=0.9,
        issue_codes=("quantity_range",),
    )
    paper = SupplyItemReview(
        review_id="child-1:paper",
        req_id="paper",
        child_id="child-1",
        item_name="notebook_paper",
        required_quantity=1,
        unit="pack",
        source_text="1 pack notebook paper",
        confidence=0.9,
        issue_codes=("ambiguous_package_size",),
    )

    assert review_issue_explanations(ranged) == (
        "The list gave a range of 2–3 boxes. We chose 2.",
    )
    assert review_issue_explanations(paper) == (
        "The list did not say how many sheets were in the package. "
        "We assumed 150.",
    )


def test_quantity_range_survives_the_editable_review_boundary() -> None:
    """Secondary editing does not erase the source range used by FR-11."""

    requirement = Requirement(
        req_id="tissues",
        child_id="child-1",
        raw_text="2-3 boxes of tissues",
        canonical_item="tissues",
        quantity=2,
        quantity_is_range=True,
        quantity_max=3,
        unit_type="box",
        extraction_confidence=1.0,
    )
    row = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=(requirement,)
            )
        }
    )[0].model_copy(update={"review_status": "confirmed"})

    reviewed = confirmed_requirements((row,))

    assert reviewed[0].quantity == 2
    assert reviewed[0].quantity_is_range is True
    assert reviewed[0].quantity_max == 3


def test_identical_flags_confirm_once_across_children() -> None:
    """One shared confirmation resolves the same ambiguity on both lists."""

    rows = tuple(
        SupplyItemReview(
            review_id=f"{child_id}:paper",
            req_id=f"{child_id}-paper",
            child_id=child_id,
            item_name="notebook_paper",
            required_quantity=1,
            unit="pack",
            source_text="1 pack notebook paper",
            confidence=0.9,
            issue_codes=("ambiguous_package_size",),
        )
        for child_id in ("child-1", "child-2")
    )

    groups = review_flag_groups(rows)

    assert len(groups) == 1
    assert groups[0].child_ids == ("child-1", "child-2")
    assert groups[0].row_ids == (
        "child-1:paper",
        "child-2:paper",
    )
    confirmed = apply_review_confirmations(
        rows,
        groups,
        (groups[0].group_id,),
    )
    assert all(row.review_status == "confirmed" for row in confirmed)


def test_clear_items_are_accepted_without_individual_confirmation() -> None:
    """The one submit action accepts clear rows while flags stay pending."""

    clear = SupplyItemReview(
        review_id="child-1:pencils",
        req_id="pencils",
        child_id="child-1",
        item_name="pencils",
        required_quantity=24,
        source_text="24 pencils",
        confidence=1.0,
    )
    flagged = SupplyItemReview(
        review_id="child-1:paper",
        req_id="paper",
        child_id="child-1",
        item_name="notebook_paper",
        required_quantity=1,
        unit="pack",
        source_text="1 pack paper",
        confidence=0.9,
        issue_codes=("ambiguous_package_size",),
    )
    groups = review_flag_groups((clear, flagged))

    reviewed = apply_review_confirmations(
        (clear, flagged),
        groups,
        (),
    )

    assert reviewed[0].review_status == "confirmed"
    assert reviewed[1].review_status == "pending"


def test_teacher_notes_are_deduplicated_and_never_require_confirmation() -> None:
    """Repeated non-purchase directions appear once with both child labels."""

    rows = tuple(
        SupplyItemReview(
            review_id=f"{child_id}:note",
            req_id=f"{child_id}-note",
            child_id=child_id,
            item_name="non_purchasable",
            required_quantity=1,
            is_purchasable=False,
            optional=True,
            source_text="Please label all supplies with your child's name.",
            confidence=1.0,
        )
        for child_id in ("child-1", "child-2")
    )

    notes = teacher_note_groups(rows)

    assert len(notes) == 1
    assert notes[0].child_ids == ("child-1", "child-2")
    assert notes[0].source_text.startswith("Please label")
    assert review_flag_groups(rows) == ()


def test_identical_conditional_questions_are_asked_once() -> None:
    """One last-name choice expands back to both children's branch groups."""

    questions = (
        ConditionalReviewQuestion(
            question_id="bags-child-1",
            child_id="child-1",
            prompt="Which bag assignment applies?",
            options=(
                ConditionalReviewOption("c1-a", "Gallon — A-G"),
                ConditionalReviewOption("c1-b", "Quart — H-P"),
            ),
            selected_value=None,
        ),
        ConditionalReviewQuestion(
            question_id="bags-child-2",
            child_id="child-2",
            prompt="Which bag assignment applies?",
            options=(
                ConditionalReviewOption("c2-a", "Gallon — A-G"),
                ConditionalReviewOption("c2-b", "Quart — H-P"),
            ),
            selected_value=None,
        ),
    )

    groups = deduplicate_conditional_questions(questions)
    answers = conditional_answers_for_selection(
        groups[0],
        "Quart — H-P",
    )

    assert len(groups) == 1
    assert groups[0].child_ids == ("child-1", "child-2")
    assert answers == {
        "bags-child-1": "c1-b",
        "bags-child-2": "c2-b",
    }
