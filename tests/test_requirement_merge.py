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
