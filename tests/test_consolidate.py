"""Tests for post-match shared-SKU purchase consolidation."""

from agent.aggregate import UnitNeed
from agent.consolidate import consolidate_selected_skus
from agent.match import CandidateMatch, MatchResult, NeedMatches
from agent.optimize import OptimizationConfig, optimize_cart
from data.loader import Offer, Store


def _need(
    req_id: str,
    child_id: str,
    attributes: dict[str, object],
) -> UnitNeed:
    return UnitNeed(
        canonical_item="glue_sticks",
        quantity=4,
        brand_lock=None,
        unit_type="each",
        exclusions=(),
        is_required=True,
        attributes=attributes,
        allocated_to={child_id: 4},
        source_requirement_ids=(req_id,),
    )


def _candidate(need: UnitNeed, offer: Offer) -> CandidateMatch:
    return CandidateMatch(
        need_key="|".join(need.source_requirement_ids),
        offer=offer,
        match_confidence=0.96,
        suitability_reason="Fixed suitable offer.",
        substitution_type="minor",
        substitution_reasons=("different_unlocked_brand",),
        attribute_status="exact",
        line_notes=(),
        approval_reasons=(),
        requires_approval=False,
    )


def test_two_needs_selecting_one_sku_are_cheaper_after_consolidation() -> None:
    """FR-14/BR-13: optimize one shared SKU across both source needs."""

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="GLUE-8",
        store_id="S",
        brand="Value",
        title="Eight glue sticks",
        category="glue_sticks",
        pack_size=8,
        unit_price=62,
        pack_price=500,
        stock_qty=2,
        is_returnable=True,
        attributes={"size_label": "large"},
    )
    grade_two = _need("grade2-glue", "grade2", {"size": "large"})
    grade_five = _need("grade5-glue", "grade5", {})
    matches = MatchResult(
        needs=(
            NeedMatches(
                unit_need=grade_two,
                candidates=(_candidate(grade_two, offer),),
                review_blocked_candidates=(),
            ),
            NeedMatches(
                unit_need=grade_five,
                candidates=(_candidate(grade_five, offer),),
                review_blocked_candidates=(),
            ),
        )
    )
    config = OptimizationConfig(
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )

    split = optimize_cart(
        [grade_two, grade_five],
        [offer],
        [store],
        config,
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    consolidated = consolidate_selected_skus(
        [grade_two, grade_five],
        matches,
        split,
    )
    merged = optimize_cart(
        consolidated.unit_needs,
        [offer],
        [store],
        config,
        candidate_skus_by_need=(
            consolidated.matches.candidate_skus_by_need
        ),
    )

    assert split.plan.item_subtotal == 1_000
    assert consolidated.changed is True
    assert len(consolidated.unit_needs) == 1
    assert consolidated.unit_needs[0].quantity == 8
    assert consolidated.unit_needs[0].allocated_to == {
        "grade2": 4,
        "grade5": 4,
    }
    assert consolidated.unit_needs[0].source_requirement_ids == (
        "grade2-glue",
        "grade5-glue",
    )
    assert merged.plan.item_subtotal == 500
    assert len(merged.plan.lines) == 1
    assert merged.plan.lines[0].allocated_to == {
        "grade2": 4,
        "grade5": 4,
    }
    assert merged.plan.lines[0].source_requirement_ids == (
        "grade2-glue",
        "grade5-glue",
    )
