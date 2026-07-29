"""Production-shape tests for deterministic same-student requirement merge."""

from __future__ import annotations

import pytest

from agent.requirement_merge import (
    consolidate_requirements,
    item_decisions,
)
from agent.aggregate import aggregate_requirements
from agent.optimize import OptimizationConfig, optimize_cart
from agent.review import confirmed_requirements, organize_extractions
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
    assert result.requirements[0].quantity == 2
    assert len(result.interrupts) == 1
    assert result.interrupts[0].default_action == "largest"
    assert result.interrupts[0].default_quantity == 2


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


def test_quantity_and_detail_conflicts_share_one_item_decision() -> None:
    """BR-26: one item card contains its quantity and variant questions."""

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
    assert len(decisions[0].constraint_interrupts) == 1
    assert len(decisions[0].variants) == 2


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
    """BR-26: source-backed variants remain distinct through optimization."""

    requirements = (
        Requirement(
            req_id="sewn",
            child_id="child-1",
            raw_text="1 sewn composition notebook",
            canonical_item="composition_notebooks",
            quantity=1,
            attributes={"style": "sewn"},
            source_document="district.pdf",
            source_section="Highly Capable",
            source_page=3,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="regular",
            child_id="child-1",
            raw_text="4 composition notebooks",
            canonical_item="composition_notebooks",
            quantity=4,
            attributes={"style": "regular"},
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
    )
    rows = tuple(
        row.model_copy(update={"review_status": "confirmed"})
        for row in organize_extractions(
            {
                "child-1": ExtractionEnvelope(
                    requirements=merged.requirements,
                )
            }
        )
    )
    needs = aggregate_requirements(confirmed_requirements(rows))
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
            title="Sewn composition notebook",
            category="composition_notebooks",
            pack_size=1,
            unit_price=100,
            pack_price=100,
            stock_qty=10,
            is_returnable=True,
            attributes={"style": "sewn"},
        ),
        Offer(
            sku="regular-sku",
            store_id="store",
            brand="Fixture",
            title="Regular composition notebook",
            category="composition_notebooks",
            pack_size=1,
            unit_price=80,
            pack_price=80,
            stock_qty=10,
            is_returnable=True,
            attributes={"style": "regular"},
        ),
    )
    candidates = {
        need.source_requirement_ids: frozenset(
            ("sewn-sku",)
            if need.attributes.get("style") == "sewn"
            else ("regular-sku",)
        )
        for need in needs
    }

    result = optimize_cart(
        needs,
        offers,
        (store,),
        OptimizationConfig(
            fulfillment_preference="pickup",
            tax_basis_points=0,
        ),
        candidate_skus_by_need=candidates,
    )

    assert tuple(sorted(line.units_needed for line in result.plan.lines)) == (
        1,
        4,
    )
    assert tuple(sorted(line.sku for line in result.plan.lines)) == (
        "regular-sku",
        "sewn-sku",
    )


@pytest.mark.parametrize(
    ("canonical_item", "source_line"),
    (
        ("backpacks", "1 backpack"),
        ("composition_notebooks", "2 composition notebooks"),
        ("folders", "4 folders"),
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

    assert rows[0].system_decisions == ("consolidated_sources",)
    assert len(rows[0].sources) == 2
