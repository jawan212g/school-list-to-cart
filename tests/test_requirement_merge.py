"""Production-shape tests for deterministic same-student requirement merge."""

from __future__ import annotations

from agent.requirement_merge import consolidate_requirements
from agent.schema import Requirement


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


def test_equal_quantities_merge_once_without_interrupt() -> None:
    """BR-20: agreeing duplicates become one same-student requirement."""

    result = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 1, "Highly Capable Class", 3),
        )
    )

    assert len(result.requirements) == 1
    assert result.requirements[0].quantity == 1
    assert result.interrupts == ()


def test_different_quantities_produce_exactly_one_interrupt() -> None:
    """BR-21: one normalized item disagreement produces one choice."""

    result = consolidate_requirements(
        (
            _requirement("grade-5", 1, "5th Grade", 2),
            _requirement("hc", 2, "Highly Capable Class", 3),
        )
    )

    assert len(result.requirements) == 1
    assert result.requirements[0].quantity == 3
    assert len(result.interrupts) == 1
    assert result.interrupts[0].default_action == "total"
    assert result.interrupts[0].default_quantity == 3


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
    assert result.interrupts == ()
    assert result.constraint_interrupts == ()


def test_genuine_attribute_conflict_becomes_one_parent_decision() -> None:
    """BR-26: incompatible constraints merge once and produce one interrupt."""

    result = consolidate_requirements(
        (
            Requirement(
                req_id="red-folder",
                child_id="child-1",
                raw_text="1 red folder",
                canonical_item="folders",
                quantity=1,
                attributes={"acceptable_colors": ("red",)},
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="blue-folder",
                child_id="child-1",
                raw_text="1 blue folder",
                canonical_item="folders",
                quantity=1,
                attributes={"acceptable_colors": ("blue",)},
                extraction_confidence=1.0,
            ),
        )
    )

    assert len(result.requirements) == 1
    assert len(result.constraint_interrupts) == 1
    assert result.constraint_interrupts[0].field_name == (
        "acceptable_colors"
    )


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
