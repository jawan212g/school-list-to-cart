"""Production-shape tests for deterministic same-student requirement merge."""

from __future__ import annotations

import pytest

from agent.match import StructuredSuitabilityJudge
from agent.pipeline import PipelineSession, run_pipeline_from_confirmed_extractions
from agent.requirement_merge import (
    consolidate_extractions,
    consolidate_requirements,
    item_decisions,
    resolve_item_decision_state,
    same_product_override_notice,
)
from agent.rules import (
    AMBIGUOUS_PRODUCT_DESCRIPTORS,
    LOW_CONFIDENCE_IDENTITY_ISSUE,
    LOW_CONFIDENCE_QUANTITY_ISSUE,
    PLAUSIBLE_ANNUAL_MAXIMUM_BY_ITEM,
    SINGLE_INSTANCE_REQUIREMENT_ITEMS,
    SYSTEM_DECISION_PARENT_CONFIRMED_PRODUCT_IDENTITY,
    SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY,
    SYSTEM_DECISION_PARENT_REMOVED_MERGED_ITEM,
)
from agent.aggregate import aggregate_requirements
from agent.optimize import OptimizationConfig, optimize_cart
from agent.review import (
    confirmed_requirements,
    organize_extractions,
    review_flag_groups,
)
from agent.schema import ExtractionEnvelope, Requirement
from data.loader import Offer, Store


def _requirement(
    req_id: str,
    quantity: int,
    section: str,
    page: int,
) -> Requirement:
    return Requirement(
        req_id=req_id,
        child_id="child-1",
        raw_text=f"{quantity} backpacks",
        canonical_item="backpacks",
        quantity=quantity,
        source_document="district.pdf",
        source_section=section,
        source_page=page,
        extraction_confidence=1.0,
    )


def test_equal_durable_quantities_merge_once_with_parent_total_option() -> None:
    """BR-20/BR-47: one backpack is default while two remains available."""

    result = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 1, "Highly Capable Class", 3),
        )
    )

    assert len(result.requirements) == 1
    assert result.requirements[0].quantity == 1
    assert len(result.interrupts) == 1
    assert result.interrupts[0].default_action == "largest"
    assert result.interrupts[0].default_quantity == 1
    assert result.interrupts[0].combined_quantity == 2


def test_different_quantities_produce_exactly_one_interrupt() -> None:
    """BR-21: one normalized item disagreement produces one choice."""

    result = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 2, "Highly Capable Class", 3),
        )
    )

    assert len(result.requirements) == 1
    assert result.requirements[0].quantity == 2
    assert len(result.interrupts) == 1
    assert result.interrupts[0].default_action == "largest"
    assert result.interrupts[0].default_quantity == 2
    assert result.interrupts[0].combined_quantity == 3
    assert result.interrupts[0].plausible_annual_maximum == 2


def test_machias_folder_wording_produces_one_product_identity_decision() -> None:
    """BR-13/BR-31: source wording preserves the two folder styles."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="folders-grade-5",
                child_id="child-1",
                raw_text="Pocket folder (bottom pockets) | 5th: 3",
                canonical_item="folders",
                quantity=3,
                source_document="Machiasschoolsupplylist 1.pdf",
                source_section="5th Grade",
                source_page=2,
                attributes={},
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="folders-highly-capable",
                child_id="child-1",
                raw_text="2 Pocket folder w/ fasteners",
                canonical_item="folders",
                quantity=2,
                source_document="Machiasschoolsupplylist 1.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                attributes={},
                extraction_confidence=1.0,
            ),
        )
    )

    _, result = consolidate_extractions({"child-1": envelope})
    folder_decisions = tuple(
        decision
        for decision in item_decisions(result)
        if decision.canonical_item == "folders"
    )

    assert tuple(
        requirement.attributes.style
        for requirement in envelope.requirements
    ) == ("bottom pockets", "with fasteners")
    assert len(folder_decisions) == 1
    assert folder_decisions[0].conflict_type == "different_products"
    assert tuple(source.page_number for source in folder_decisions[0].sources) == (
        2,
        3,
    )


def test_quantity_total_remains_an_explicit_parent_choice() -> None:
    """BR-30: summing cross-section quantities is available but not default."""

    initial = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 2, "Highly Capable Class", 3),
        )
    )
    interrupt_id = initial.interrupts[0].interrupt_id

    resolved = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 2, "Highly Capable Class", 3),
        ),
        quantity_choices={interrupt_id: 3},
    )

    assert resolved.requirements[0].quantity == 3


def test_parent_selected_quantity_confirms_only_quantity_reading() -> None:
    """BR-44: a selected quantity does not suppress identity uncertainty."""

    requirements = (
        _requirement("grade-5", 1, "5th Grade", 2).model_copy(
            update={"extraction_confidence": 0.5}
        ),
        _requirement("hc", 2, "Highly Capable Class", 3).model_copy(
            update={"extraction_confidence": 0.5}
        ),
    )
    initial = consolidate_requirements(requirements)
    interrupt_id = initial.interrupts[0].interrupt_id

    resolved = consolidate_requirements(
        requirements,
        quantity_choices={interrupt_id: 3},
    )
    requirement = resolved.requirements[0]
    row = organize_extractions(
        {"child-1": ExtractionEnvelope(requirements=(requirement,))}
    )[0]

    assert SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY in (
        requirement.system_decisions
    )
    assert SYSTEM_DECISION_PARENT_CONFIRMED_PRODUCT_IDENTITY not in (
        requirement.system_decisions
    )
    assert row.issue_codes == (LOW_CONFIDENCE_IDENTITY_ISSUE,)


def test_different_products_answer_keeps_unread_quantity_uncertainty() -> None:
    """BR-44: an identity answer never confirms untouched variant quantities."""

    requirements = (
        Requirement(
            req_id="graph",
            child_id="child-1",
            raw_text="1 graph paper composition notebook",
            canonical_item="composition_notebooks",
            quantity=1,
            attributes={"ruling": "graph"},
            source_document="district.pdf",
            source_section="5th Grade",
            source_page=2,
            extraction_confidence=0.5,
        ),
        Requirement(
            req_id="regular",
            child_id="child-1",
            raw_text="4 regular composition notebooks",
            canonical_item="composition_notebooks",
            quantity=4,
            attributes={"ruling": "wide"},
            source_document="district.pdf",
            source_section="Highly Capable Class",
            source_page=3,
            extraction_confidence=0.5,
        ),
    )
    initial = consolidate_requirements(requirements)
    decision = item_decisions(initial)[0]

    resolved = consolidate_requirements(
        requirements,
        product_identity_choices={decision.decision_id: "different"},
    )
    rows = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=resolved.requirements
            )
        }
    )

    assert len(rows) == 2
    assert all(
        SYSTEM_DECISION_PARENT_CONFIRMED_PRODUCT_IDENTITY
        in row.system_decisions
        for row in rows
    )
    assert all(
        SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY
        not in row.system_decisions
        for row in rows
    )
    assert all(
        row.issue_codes == (LOW_CONFIDENCE_QUANTITY_ISSUE,)
        for row in rows
    )


@pytest.mark.parametrize(
    (
        "canonical_item",
        "quantities",
        "expected_action",
        "expected_quantity",
        "expected_maximum",
    ),
    (
        ("pencils", (48, 36), "largest", 48, 48),
        ("glue_sticks", (4, 3), "total", 7, 12),
        ("tissues", (4, 1), "total", 5, 6),
        ("folders", (6, 2), "total", 8, 10),
        ("composition_notebooks", (1, 4), "total", 5, 10),
        ("backpacks", (1, 1), "largest", 1, 2),
        ("scissors", (1, 1), "largest", 1, 2),
    ),
)
def test_plausible_annual_maximum_selects_named_item_default(
    canonical_item: str,
    quantities: tuple[int, int],
    expected_action: str,
    expected_quantity: int,
    expected_maximum: int,
) -> None:
    """BR-40: named merge defaults are deterministic per canonical item."""

    requirements = tuple(
        Requirement(
            req_id=f"source-{index}",
            child_id="child-1",
            raw_text=f"{quantity} {canonical_item}",
            canonical_item=canonical_item,
            quantity=quantity,
            source_document="district.pdf",
            source_section=section,
            source_page=index + 2,
            extraction_confidence=1.0,
        )
        for index, (quantity, section) in enumerate(
            zip(
                quantities,
                ("5th Grade", "Highly Capable Class"),
                strict=True,
            )
        )
    )

    result = consolidate_requirements(requirements)
    interrupt = result.interrupts[0]

    assert interrupt.default_action == expected_action
    assert interrupt.default_quantity == expected_quantity
    assert interrupt.combined_quantity == sum(quantities)
    assert interrupt.plausible_annual_maximum == expected_maximum


def test_quantity_classification_covers_the_full_plausible_maximum_table() -> None:
    """BR-47: every single-instance category is an explicit table entry."""

    assert SINGLE_INSTANCE_REQUIREMENT_ITEMS == {
        "backpacks",
        "headphones",
        "pencil_boxes",
        "pencil_pouches",
        "pencil_sharpeners",
        "rulers",
        "scissors",
        "water_bottles",
    }
    assert SINGLE_INSTANCE_REQUIREMENT_ITEMS <= (
        PLAUSIBLE_ANNUAL_MAXIMUM_BY_ITEM.keys()
    )


def test_parent_can_exclude_an_entire_conflicted_item() -> None:
    """A8: exclusion remains visible for review but cannot reach the cart."""

    requirements = (
        _requirement("grade-5", 1, "5th Grade", 2),
        _requirement("hc", 2, "Highly Capable Class", 3),
    )
    initial = consolidate_requirements(requirements)
    decision_id = item_decisions(initial)[0].decision_id

    resolved = consolidate_requirements(
        requirements,
        excluded_decision_ids=(decision_id,),
    )

    assert len(resolved.requirements) == 1
    removed = resolved.requirements[0]
    assert SYSTEM_DECISION_PARENT_REMOVED_MERGED_ITEM in (
        removed.system_decisions
    )
    assert tuple(source.exact_line for source in removed.sources) == (
        "1 backpacks",
        "2 backpacks",
    )
    review_rows = organize_extractions(
        {"child-1": ExtractionEnvelope(requirements=(removed,))}
    )
    assert len(review_rows) == 1
    assert review_rows[0].review_status == "deleted"
    assert confirmed_requirements(review_rows) == ()
    assert resolved.interrupts == ()
    assert resolved.constraint_interrupts == ()


def test_consolidated_requirement_retains_every_source_reference() -> None:
    """BR-22: merge retains exact lines, sections, pages, and quantities."""

    result = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 1, "Highly Capable Class", 3),
        )
    )

    sources = result.requirements[0].sources
    assert tuple(source.section_name for source in sources) == (
        "5th Grade",
        "Highly Capable Class",
    )
    assert tuple(source.page_number for source in sources) == (2, 3)
    assert tuple(source.exact_line for source in sources) == (
        "1 backpacks",
        "1 backpacks",
    )


def test_scissors_preferences_merge_without_inventing_brand_lock() -> None:
    """BR-24/BR-25: brand mentions and preferences do not split scissors."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="adult-scissors",
                child_id="child-1",
                raw_text="1 Scissors (adult sized Fiskar)",
                canonical_item="scissors",
                quantity=1,
                brand_lock="Fiskar",
                attributes={"size": "adult"},
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="pointed-scissors",
                child_id="child-1",
                raw_text="Scissors - pointed tip (Fiskars are best)",
                canonical_item="scissors",
                quantity=1,
                brand_lock="Fiskars",
                attributes={"tip_style": "pointed"},
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
        )
    )

    assert len(result.requirements) == 1
    assert result.requirements[0].brand_lock is None
    assert result.requirements[0].attributes.size == "adult"
    assert result.requirements[0].attributes.tip_style == "pointed"
    assert len(result.requirements[0].sources) == 2
    assert len(result.interrupts) == 1
    assert result.interrupts[0].default_action == "largest"
    assert result.interrupts[0].default_quantity == 1
    assert result.interrupts[0].combined_quantity == 2
    assert result.constraint_interrupts == ()


def test_graph_and_regular_composition_books_are_different_products() -> None:
    """BR-31/BR-43: regular is lined and differs from graph paper."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="graph",
                child_id="child-1",
                raw_text="1 composition book - graph paper",
                canonical_item="composition_notebooks",
                quantity=1,
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="regular",
                child_id="child-1",
                raw_text="4 Regular composition books",
                canonical_item="composition_notebooks",
                quantity=4,
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )

    decision = item_decisions(result)[0]
    assert decision.conflict_type == "different_products"
    assert decision.default_identity == "different"
    assert tuple(source.page_number for source in decision.sources) == (2, 3)
    assert decision.variants[0].attributes.ruling == "graph"
    assert decision.variants[1].attributes.ruling == "lined"
    assert tuple(
        variant.default_quantity for variant in decision.variants
    ) == (1, 4)
    resolved = resolve_item_decision_state(decision)
    assert resolved.quantity_control == "variants"
    assert resolved.rationale == (
        "Highly Capable Class asks for graph and 5th Grade asks for lined. "
        "Those look like different composition notebooks to us, so we've "
        "kept them separate."
    )


def test_model_populated_graph_paper_ruling_stays_separate_from_lined() -> None:
    """BR-13/BR-31: live model phrasing cannot hide a ruling conflict."""

    requirements = (
        Requirement(
            req_id="graph-model-value",
            child_id="child-1",
            raw_text="Composition book (sewn binding) - graph paper | 5th: 1",
            canonical_item="composition_notebooks",
            quantity=1,
            attributes={"ruling": "graph paper"},
            source_document="Machiasschoolsupplylist 1.pdf",
            source_section="5th",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="lined-model-value",
            child_id="child-1",
            raw_text="4 Regular composition books",
            canonical_item="composition_notebooks",
            quantity=4,
            attributes={"ruling": "lined"},
            source_document="Machiasschoolsupplylist 1.pdf",
            source_section="Highly Capable Class",
            source_page=3,
            extraction_confidence=1.0,
        ),
    )

    assert requirements[0].attributes.ruling == "graph"
    result = consolidate_requirements(requirements)
    decision = item_decisions(result)[0]
    assert decision.conflict_type == "different_products"
    assert decision.default_identity == "different"
    assert tuple(
        variant.attributes.ruling for variant in decision.variants
    ) == ("graph", "lined")


def test_reviewed_composition_identity_keeps_quantity_review_open() -> None:
    """BR-44: product identity does not confirm unread variant quantities."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="graph",
                child_id="child-1",
                raw_text="Composition book (sewn binding) - graph paper",
                canonical_item="composition_notebooks",
                quantity=1,
                attributes={"ruling": "graph"},
                source_document="Machiasschoolsupplylist 1.pdf",
                source_section="5th",
                source_page=2,
                extraction_confidence=0.6,
            ),
            Requirement(
                req_id="regular",
                child_id="child-1",
                raw_text="Regular composition books",
                canonical_item="composition_notebooks",
                quantity=4,
                attributes={"ruling": "lined"},
                source_document="Machiasschoolsupplylist 1.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=0.6,
            ),
        )
    )
    initial = consolidate_requirements(envelope.requirements)
    decision = item_decisions(initial)[0]

    merged, _ = consolidate_extractions(
        {"child-1": envelope},
        product_identity_choices={decision.decision_id: "different"},
    )
    rows = organize_extractions(merged)

    assert len(rows) == 2
    assert tuple(row.required_quantity for row in rows) == (1, 4)
    groups = review_flag_groups(rows)
    assert len(groups) == 2
    assert all(
        group.messages
        == (
            "The quantity may be unclear. Compare it with the source shown "
            "here.",
        )
        for group in groups
    )
    assert AMBIGUOUS_PRODUCT_DESCRIPTORS == frozenset()


def test_identical_descriptions_never_ask_product_identity() -> None:
    """BR-43: identical parent-facing wording is quantity-only."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="one",
                child_id="child-1",
                raw_text="1 Box of facial tissues",
                canonical_item="tissues",
                quantity=1,
                source_document="district.pdf",
                source_section="Grade 5",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="two",
                child_id="child-1",
                raw_text="2 Box of facial tissues",
                canonical_item="tissues",
                quantity=2,
                source_document="district.pdf",
                source_section="Highly Capable",
                extraction_confidence=1.0,
            ),
        )
    )

    decision = item_decisions(result)[0]
    assert decision.conflict_type == "quantity_only"
    assert not resolve_item_decision_state(decision).show_identity_on_main


def test_word_order_and_resolved_details_never_ask_product_identity() -> None:
    """BR-43: word order and one stated compatible detail do not interrupt."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="one",
                child_id="child-1",
                raw_text="12 Ticonderoga sharpened pencils - #2",
                canonical_item="pencils",
                quantity=12,
                brand_lock="Ticonderoga",
                attributes={"sharpened": True},
                source_document="district.pdf",
                source_section="Grade 5",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="two",
                child_id="child-1",
                raw_text="24 Ticonderoga #2 pencils",
                canonical_item="pencils",
                quantity=24,
                brand_lock="Ticonderoga",
                source_document="district.pdf",
                source_section="Highly Capable",
                extraction_confidence=1.0,
            ),
        )
    )

    decision = item_decisions(result)[0]
    assert decision.conflict_type == "quantity_only"
    assert not resolve_item_decision_state(decision).show_identity_on_main


@pytest.mark.parametrize(
    (
        "canonical_item",
        "first_line",
        "first_quantity",
        "second_line",
        "second_quantity",
    ),
    (
        ("glue_sticks", "4 Glue sticks", 4, "3 | Glue sticks", 3),
        (
            "tissues",
            "4 Boxes of facial tissues",
            4,
            "1 | Box of facial tissues",
            1,
        ),
        ("backpacks", "1 Backpack", 1, "1 | Backpack or book bag", 1),
        (
            "scissors",
            "1 Fiskars blunt-tip scissors",
            1,
            "1 | Blunt tip Fiskars scissors",
            1,
        ),
    ),
)
def test_equivalent_reversed_matrix_wording_never_asks_identity(
    canonical_item: str,
    first_line: str,
    first_quantity: int,
    second_line: str,
    second_quantity: int,
) -> None:
    """BR-43/BR-46: screen evidence order cannot create a question."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="first",
                child_id="child-1",
                raw_text=first_line,
                canonical_item=canonical_item,
                quantity=first_quantity,
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="second",
                child_id="child-1",
                raw_text=second_line,
                canonical_item=canonical_item,
                quantity=second_quantity,
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )

    decision = item_decisions(result)[0]
    assert decision.conflict_type == "quantity_only"
    assert not resolve_item_decision_state(decision).show_identity_on_main


def test_different_non_null_rulings_are_different_products() -> None:
    """BR-31: graph and lined are Type B product variants."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="graph",
                child_id="child-1",
                raw_text="1 graph paper composition notebook",
                canonical_item="composition_notebooks",
                quantity=1,
                source_document="district.pdf",
                source_section="Section A",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="lined",
                child_id="child-1",
                raw_text="4 lined composition notebooks",
                canonical_item="composition_notebooks",
                quantity=4,
                source_document="district.pdf",
                source_section="Section B",
                extraction_confidence=1.0,
            ),
        )
    )

    decision = item_decisions(result)[0]
    assert len(result.requirements) == 2
    assert decision.conflict_type == "different_products"
    assert decision.default_identity == "different"
    assert sorted(
        variant.attributes.ruling for variant in decision.variants
    ) == ["graph", "lined"]


def test_boolean_product_difference_uses_parent_language() -> None:
    """BR-48/BR-50: rule rationale never exposes True or schema names."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="sharpened",
                child_id="child-1",
                raw_text="12 pre-sharpened pencils",
                canonical_item="pencils",
                quantity=12,
                attributes={"sharpened": True},
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="unsharpened",
                child_id="child-1",
                raw_text="12 unsharpened pencils",
                canonical_item="pencils",
                quantity=12,
                attributes={"sharpened": False},
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )

    rationale = resolve_item_decision_state(item_decisions(result)[0]).rationale

    assert rationale == (
        "5th Grade asks for pre-sharpened and Highly Capable Class asks for "
        "unsharpened. Those look like different pencils to us, so we've kept "
        "them separate."
    )
    assert "True" not in rationale
    assert "False" not in rationale


def test_color_differences_do_not_split_product_identity() -> None:
    """BR-31: color is incidental to deterministic requirement merge."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="red-folder",
                child_id="child-1",
                raw_text="1 red folder",
                canonical_item="folders",
                quantity=1,
                attributes={"acceptable_colors": ("red",)},
                source_document="district.pdf",
                source_section="5th Grade",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="blue-folder",
                child_id="child-1",
                raw_text="1 blue folder",
                canonical_item="folders",
                quantity=1,
                attributes={"acceptable_colors": ("blue",)},
                source_document="district.pdf",
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )

    assert len(result.requirements) == 1
    assert result.constraint_interrupts == ()
    assert result.requirements[0].attributes.acceptable_colors == (
        "blue",
        "red",
    )


def test_binding_and_packaging_differences_are_incidental() -> None:
    """BR-31: manufacturing binding and package count do not split an item."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="sewn",
                child_id="child-1",
                raw_text="1 sewn binding composition notebook, 2 count",
                canonical_item="composition_notebooks",
                quantity=1,
                attributes={"binding": "sewn", "count": 2},
                source_document="district.pdf",
                source_section="Section A",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="spiral",
                child_id="child-1",
                raw_text="1 spiral binding composition notebook, 4 count",
                canonical_item="composition_notebooks",
                quantity=1,
                attributes={"binding": "spiral", "count": 4},
                source_document="district.pdf",
                source_section="Section B",
                extraction_confidence=1.0,
            ),
        )
    )

    assert len(result.requirements) == 1
    assert result.constraint_interrupts == ()
    assert result.requirements[0].attributes.binding is None
    assert result.requirements[0].attributes.count is None


def test_one_product_definition_and_one_silent_source_keep_definition() -> None:
    """BR-31: one specified ruling plus silence remains one specified item."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="graph",
                child_id="child-1",
                raw_text="1 graph paper composition notebook",
                canonical_item="composition_notebooks",
                quantity=1,
                source_document="district.pdf",
                source_section="Section A",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="silent",
                child_id="child-1",
                raw_text="1 composition notebook",
                canonical_item="composition_notebooks",
                quantity=1,
                source_document="district.pdf",
                source_section="Section B",
                extraction_confidence=1.0,
            ),
        )
    )

    assert len(result.requirements) == 1
    assert result.requirements[0].attributes.ruling == "graph"
    assert result.constraint_interrupts == ()


def test_quantity_conflict_accepts_custom_and_named_source_values() -> None:
    """BR-21: the parent's selected quantity changes the merged requirement."""

    requirements = (
        _requirement("grade-5", 1, "5th Grade", 2),
        _requirement("hc", 2, "Highly Capable Class", 3),
    )
    initial = consolidate_requirements(requirements)
    interrupt_id = initial.interrupts[0].interrupt_id

    custom = consolidate_requirements(
        requirements,
        quantity_choices={interrupt_id: 7},
    )
    named_source = consolidate_requirements(
        requirements,
        quantity_choices={interrupt_id: 2},
    )

    assert custom.requirements[0].quantity == 7
    assert named_source.requirements[0].quantity == 2


def test_same_section_permanent_marker_variants_remain_additive() -> None:
    """BR-27: two deliberately enumerated same-section rows stay separate."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="fine",
                child_id="child-1",
                raw_text="1 Fine tip black sharpie",
                canonical_item="permanent_markers",
                quantity=1,
                attributes={
                    "tip_style": "fine",
                    "acceptable_colors": ("black",),
                },
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="ultra-fine",
                child_id="child-1",
                raw_text="1 Ultra fine tip black sharpie",
                canonical_item="permanent_markers",
                quantity=1,
                attributes={
                    "tip_style": "ultra fine",
                    "acceptable_colors": ("black",),
                },
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )

    assert len(result.requirements) == 2
    assert sum(item.quantity for item in result.requirements) == 2
    assert result.interrupts == ()
    assert result.constraint_interrupts == ()


def test_quantity_and_color_difference_is_type_a_only() -> None:
    """BR-31: incidental color does not turn a quantity choice into variants."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="red",
                child_id="child-1",
                raw_text="2 red folders",
                canonical_item="folders",
                quantity=2,
                attributes={"acceptable_colors": ("red",)},
                source_document="district.pdf",
                source_section="5th Grade",
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="blue",
                child_id="child-1",
                raw_text="1 blue folder",
                canonical_item="folders",
                quantity=1,
                attributes={"acceptable_colors": ("blue",)},
                source_document="district.pdf",
                source_section="Highly Capable Class",
                extraction_confidence=1.0,
            ),
        )
    )

    decisions = item_decisions(result)

    assert len(decisions) == 1
    assert decisions[0].quantity_interrupt is not None
    assert decisions[0].constraint_interrupts == ()
    assert len(decisions[0].variants) == 2
    assert decisions[0].conflict_type == "quantity_only"
    assert decisions[0].default_identity == "same"


def test_parent_can_split_quantity_across_conflicting_variants() -> None:
    """BR-26: per-variant quantities become separate cart requirements."""

    requirements = (
        Requirement(
            req_id="fine",
            child_id="child-1",
            raw_text="2 fine tip permanent markers",
            canonical_item="permanent_markers",
            quantity=2,
            attributes={"tip_style": "fine"},
            source_document="district.pdf",
            source_section="5th Grade",
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="ultra",
            child_id="child-1",
            raw_text="1 ultra fine tip permanent marker",
            canonical_item="permanent_markers",
            quantity=1,
            attributes={"tip_style": "ultra fine"},
            source_document="district.pdf",
            source_section="Highly Capable Class",
            extraction_confidence=1.0,
        ),
    )
    initial = consolidate_requirements(requirements)
    decision = item_decisions(initial)[0]
    quantities = {
        variant.variant_id: variant.default_quantity
        for variant in decision.variants
    }

    split = consolidate_requirements(
        requirements,
        variant_quantity_choices={
            decision.decision_id: quantities,
        },
    )
    one_variant = consolidate_requirements(
        requirements,
        variant_quantity_choices={
            decision.decision_id: {
                decision.variants[0].variant_id: 3,
                decision.variants[1].variant_id: 0,
            },
        },
    )

    assert sorted(item.quantity for item in split.requirements) == [1, 2]
    assert all(len(item.sources) == 2 for item in split.requirements)
    assert all(len(item.variant_sources) == 1 for item in split.requirements)
    assert len(one_variant.requirements) == 1
    assert one_variant.requirements[0].quantity == 3


def test_variant_allocations_survive_as_two_cart_lines() -> None:
    """BR-31: production pipeline keeps a parent-selected two-product split."""

    requirements = (
        Requirement(
            req_id="sewn",
            child_id="child-1",
            raw_text="1 graph paper composition notebook",
            canonical_item="composition_notebooks",
            quantity=1,
            attributes={"ruling": "graph"},
            source_document="district.pdf",
            source_section="Highly Capable",
            source_page=3,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="regular",
            child_id="child-1",
            raw_text="4 Regular composition notebooks",
            canonical_item="composition_notebooks",
            quantity=4,
            source_document="district.pdf",
            source_section="5th Grade",
            source_page=2,
            extraction_confidence=1.0,
        ),
    )
    initial = consolidate_requirements(requirements)
    decision = item_decisions(initial)[0]
    selected = {
        variant.variant_id: variant.default_quantity
        for variant in decision.variants
    }
    merged = consolidate_requirements(
        requirements,
        variant_quantity_choices={decision.decision_id: selected},
        product_identity_choices={decision.decision_id: "different"},
    )
    store = Store(
        store_id="store",
        name="Fixture Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offers = (
        Offer(
            sku="sewn-sku",
            store_id="store",
            brand="Fixture",
            title="Graph composition notebook",
            category="composition_notebooks",
            pack_size=1,
            unit_price=100,
            pack_price=100,
            stock_qty=10,
            is_returnable=True,
            attributes={"ruling": "graph"},
        ),
        Offer(
            sku="regular-sku",
            store_id="store",
            brand="Fixture",
            title="Wide-ruled composition notebook",
            category="composition_notebooks",
            pack_size=1,
            unit_price=80,
            pack_price=80,
            stock_qty=10,
            is_returnable=True,
            attributes={"ruling": "wide"},
        ),
    )
    result = run_pipeline_from_confirmed_extractions(
        PipelineSession(
            session_id="variant-cart",
            children=("child-1",),
            budget_total=1_000,
            shopping_mode="budget",
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        {
            "child-1": ExtractionEnvelope(
                requirements=merged.requirements,
            )
        },
        stores=(store,),
        offers=offers,
        suitability_judge=StructuredSuitabilityJudge(),
    )

    assert tuple(
        sorted(line.units_needed for line in result.proposed_cart.plan.lines)
    ) == (
        1,
        4,
    )
    assert len(result.proposed_cart.plan.lines) == 2


def test_parent_can_override_type_b_to_one_product() -> None:
    """BR-37: a rules-classified product difference remains parent-overridable."""

    requirements = (
        Requirement(
            req_id="paper",
            child_id="child-1",
            raw_text="2 cardboard pocket folders",
            canonical_item="folders",
            quantity=2,
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
    assert decision.conflict_type == "different_products"
    assert decision.default_identity == "different"
    assert decision.quantity_interrupt is not None

    merged = consolidate_requirements(
        requirements,
        quantity_choices={
            decision.quantity_interrupt.interrupt_id: 2,
        },
        product_identity_choices={decision.decision_id: "same"},
    )

    assert len(merged.requirements) == 1
    assert merged.requirements[0].quantity == 2
    assert len(merged.requirements[0].sources) == 2
    assert merged.requirements[0].attributes.material == "cardboard"
    assert merged.requirements[0].attributes.connector is None
    assert same_product_override_notice(decision) == (
        "You chose to treat these lines as the same product. The cart will "
        "use the product details from 5th Grade."
    )


def test_parent_can_override_type_a_to_two_products() -> None:
    """BR-37: a quantity-only card can retain two parent-declared kinds."""

    requirements = (
        Requirement(
            req_id="grade-five",
            child_id="child-1",
            raw_text="1 composition notebook",
            canonical_item="composition_notebooks",
            quantity=1,
            source_document="district.pdf",
            source_section="5th Grade",
            source_page=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="capable",
            child_id="child-1",
            raw_text="4 composition notebooks",
            canonical_item="composition_notebooks",
            quantity=4,
            source_document="district.pdf",
            source_section="Highly Capable Class",
            source_page=3,
            extraction_confidence=1.0,
        ),
    )
    initial = consolidate_requirements(requirements)
    decision = item_decisions(initial)[0]
    selected = {
        variant.variant_id: variant.default_quantity
        for variant in decision.variants
    }

    split = consolidate_requirements(
        requirements,
        variant_quantity_choices={decision.decision_id: selected},
        product_identity_choices={decision.decision_id: "different"},
    )

    assert sorted(item.quantity for item in split.requirements) == [1, 4]
    assert all(item.product_variant_id for item in split.requirements)


@pytest.mark.parametrize(
    ("canonical_item", "source_line"),
    (
        ("backpacks", "1 backpack"),
        ("tissues", "2 tissues"),
        ("glue_sticks", "4 glue sticks"),
    ),
)
def test_listed_cross_section_restatements_merge_once(
    canonical_item: str,
    source_line: str,
) -> None:
    """BR-27: the listed cross-section restatements consolidate."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id=f"{canonical_item}-grade-5",
                child_id="child-1",
                raw_text=source_line,
                canonical_item=canonical_item,
                quantity=int(source_line.split()[0]),
                source_document="district.pdf",
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id=f"{canonical_item}-hc",
                child_id="child-1",
                raw_text=source_line,
                canonical_item=canonical_item,
                quantity=int(source_line.split()[0]),
                source_document="district.pdf",
                source_section="Highly Capable Class",
                source_page=3,
                extraction_confidence=1.0,
            ),
        )
    )

    assert len(result.requirements) == 1
    assert len(result.requirements[0].sources) == 2


def test_merge_decision_metadata_reaches_production_review_rows() -> None:
    """BR-29: deterministic merge notes survive into Personalize objects."""

    merged = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 1, "Highly Capable Class", 3),
        )
    )
    rows = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=merged.requirements,
            )
        }
    )

    assert rows[0].system_decisions == (
        "consolidated_sources",
        "merged_quantity:1",
    )
    assert len(rows[0].sources) == 2
