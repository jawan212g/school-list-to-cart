"""Hand-computed tests for deterministic whole-budget strategies."""

from agent.aggregate import UnitNeed
from agent.budget_plans import (
    apply_budget_actions,
    build_budget_analysis,
    preview_budget_actions,
)
from agent.match import match_offers
from agent.optimize import OptimizationConfig, optimize_cart
from data.loader import Offer, Store


def _store() -> Store:
    return Store(
        store_id="STORE",
        name="Test Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )


def _need(
    category: str,
    req_id: str,
    child_id: str,
    *,
    attributes: dict[str, object] | None = None,
) -> UnitNeed:
    return UnitNeed(
        canonical_item=category,
        quantity=1,
        brand_lock=None,
        unit_type="each",
        exclusions=(),
        is_required=True,
        attributes=attributes or {},
        allocated_to={child_id: 1},
        source_requirement_ids=(req_id,),
    )


def _offer(
    sku: str,
    category: str,
    price: int,
    *,
    attributes: dict[str, object] | None = None,
) -> Offer:
    return Offer(
        sku=sku,
        store_id="STORE",
        brand="Test",
        title=sku,
        category=category,
        pack_size=1,
        unit_price=price,
        pack_price=price,
        stock_qty=10,
        is_returnable=True,
        attributes=attributes or {},
    )


def _analysis(
    needs: tuple[UnitNeed, ...],
    offers: tuple[Offer, ...],
    budget: int,
):
    stores = (_store(),)
    matches = match_offers(needs, offers, stores)
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=budget,
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    optimization = optimize_cart(
        needs,
        offers,
        stores,
        config,
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    analysis = build_budget_analysis(
        optimization,
        matches,
        needs,
        offers,
        stores,
        config,
    )
    assert analysis is not None
    return stores, matches, config, optimization, analysis


def test_recommended_plan_reaches_budget_with_fewest_items_unmet() -> None:
    """BR-04: $13.00 becomes $7.00 by omitting one $6.00 line."""

    needs = (
        _need("headphones", "headphones", "grade2"),
        _need("pens", "pens", "grade5"),
        _need("pencils", "pencils", "grade5"),
    )
    offers = (
        _offer("HEADPHONES", "headphones", 600),
        _offer("PENS", "pens", 400),
        _offer("PENCILS", "pencils", 300),
    )
    _, _, _, _, analysis = _analysis(needs, offers, 700)

    assert analysis.baseline_landed_cost_cents == 1_300
    assert analysis.recommended_plan is not None
    assert analysis.recommended_plan.resulting_landed_cost_cents == 700
    assert len(analysis.recommended_plan.unmet_action_ids) == 1
    assert len(analysis.alternative_plans) == 1
    assert analysis.alternative_plans[0].resulting_landed_cost_cents == 600
    assert len(analysis.alternative_plans[0].unmet_action_ids) == 2


def test_no_required_item_drop_plan_when_substitution_alone_reaches() -> None:
    """BR-04: a $2.00 cheaper pen makes the $7.50 budget reachable."""

    needs = (
        _need(
            "pens",
            "pens",
            "grade5",
            attributes={"acceptable_colors": ("blue",)},
        ),
        _need("pencils", "pencils", "grade5"),
    )
    offers = (
        _offer(
            "BLUE-PENS",
            "pens",
            500,
            attributes={"ink_color": "blue"},
        ),
        _offer(
            "RED-PENS",
            "pens",
            300,
            attributes={"ink_color": "red"},
        ),
        _offer("PENCILS", "pencils", 400),
    )
    _, _, _, _, analysis = _analysis(needs, offers, 750)

    assert analysis.baseline_landed_cost_cents == 900
    assert analysis.substitution_only_landed_cost_cents == 700
    assert analysis.substitutions_reach_budget is True
    assert analysis.recommended_plan is None
    assert analysis.alternative_plans == ()


def test_multiselect_preview_equals_submitted_plan() -> None:
    """Two precomputed deltas predict and produce the exact $6.00 cart."""

    needs = (
        _need(
            "pens",
            "pens",
            "grade5",
            attributes={"acceptable_colors": ("blue",)},
        ),
        _need("headphones", "headphones", "grade2"),
        _need("pencils", "pencils", "grade5"),
    )
    offers = (
        _offer(
            "BLUE-PENS",
            "pens",
            500,
            attributes={"ink_color": "blue"},
        ),
        _offer(
            "RED-PENS",
            "pens",
            300,
            attributes={"ink_color": "red"},
        ),
        _offer("HEADPHONES", "headphones", 400),
        _offer("PENCILS", "pencils", 300),
    )
    stores, matches, config, optimization, analysis = _analysis(
        needs,
        offers,
        650,
    )
    headphone_omission = next(
        action.action_id
        for action in analysis.omission_actions
        if action.canonical_item == "headphones"
    )
    selected = (
        analysis.preferred_substitution_action_ids
        + (headphone_omission,)
    )

    preview = preview_budget_actions(analysis, selected)
    submitted = apply_budget_actions(
        analysis,
        selected,
        optimization,
        matches,
        needs,
        offers,
        stores,
        config,
    )

    assert preview.predicted_landed_cost_cents == 600
    assert preview.unmet_item_count == 1
    assert submitted.landed_cost == 600
