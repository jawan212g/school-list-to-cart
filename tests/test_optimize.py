"""Hand-computed tests for deterministic aggregation and optimization."""

from collections.abc import Mapping

from agent.aggregate import Requirement, UnitNeed, aggregate_requirements
from agent.optimize import (
    OptimizationConfig,
    ShoppingMode,
    optimize_cart,
    select_packages,
)
from data.loader import Offer, Store


def _unit_need(
    canonical_item: str,
    allocated_to: Mapping[str, int],
    brand_lock: str | None = None,
) -> UnitNeed:
    requirements = [
        Requirement(
            req_id=f"{canonical_item}-{index}",
            child_id=child_id,
            raw_text=canonical_item,
            canonical_item=canonical_item,
            quantity=quantity,
            brand_lock=brand_lock,
        )
        for index, (child_id, quantity) in enumerate(allocated_to.items())
    ]
    needs = aggregate_requirements(requirements)
    assert len(needs) == 1
    return needs[0]


def _offer(
    sku: str,
    store_id: str,
    category: str,
    pack_size: int,
    pack_price: int,
    *,
    brand: str = "Generic",
    stock_qty: int = 100,
) -> Offer:
    return Offer(
        sku=sku,
        store_id=store_id,
        brand=brand,
        title=sku,
        category=category,
        pack_size=pack_size,
        unit_price=pack_price // pack_size,
        pack_price=pack_price,
        stock_qty=stock_qty,
        is_returnable=True,
        attributes={},
    )


def _store(
    store_id: str,
    *,
    pickup_fee: int = 0,
    pickup_minimum: int = 0,
    tax_applies: bool = True,
) -> Store:
    return Store(
        store_id=store_id,
        name=store_id,
        distance_miles=1.0,
        pickup_fee=pickup_fee,
        pickup_minimum=pickup_minimum,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=tax_applies,
        pickup_available=True,
    )


def _config(
    *,
    mode: ShoppingMode = "budget",
    budget_cents: int | None = None,
    tax_basis_points: int = 0,
    max_stores: int | None = None,
    allowed_store_ids: frozenset[str] | None = None,
) -> OptimizationConfig:
    return OptimizationConfig(
        shopping_mode=mode,
        budget_cents=budget_cents,
        tax_basis_points=tax_basis_points,
        max_stores=max_stores,
        allowed_store_ids=allowed_store_ids,
        fulfillment_preference="pickup",
    )


def test_aggregation_rolls_up_children_but_separates_brand_locks() -> None:
    """FR-14/15/16: quantities and child attribution remain exact."""

    requirements = [
        Requirement("r1", "child-a", "2 pencils", "pencils", 2),
        Requirement("r2", "child-b", "3 pencils", "pencils", 3),
        Requirement(
            "r3",
            "child-b",
            "4 Ticonderoga pencils",
            "pencils",
            4,
            brand_lock="Ticonderoga",
        ),
    ]

    generic, locked = aggregate_requirements(requirements)

    assert generic.quantity == 5
    assert generic.allocated_to == {"child-a": 2, "child-b": 3}
    assert locked.quantity == 4
    assert locked.brand_lock == "Ticonderoga"
    assert locked.allocated_to == {"child-b": 4}


def test_e13_forty_eight_pack_is_blocked_by_overage_ceiling() -> None:
    """E-13: 5 units cost $5.00; the cheaper $4.80 48-pack is invalid."""

    need = _unit_need("pencils", {"child-a": 5})
    offers = [
        _offer("S-PEN-005", "S", "pencils", 5, 500),
        _offer("S-PEN-048", "S", "pencils", 48, 480),
    ]

    selection = select_packages(need, offers)

    assert selection is not None
    assert selection.item_subtotal == 500
    assert selection.units_purchased == 5
    assert selection.overage_units == 0
    assert selection.lines[0].packs_purchased == 1


def test_e14_twelve_pack_supplies_eight_with_four_overage() -> None:
    """E-14: one $6.00 12-pack allocates $3.00 to each child."""

    need = _unit_need("pencils", {"child-a": 4, "child-b": 4})
    offers = [_offer("S-PEN-012", "S", "pencils", 12, 600)]

    result = optimize_cart(
        [need],
        offers,
        [_store("S")],
        _config(),
    )

    assert result.plan.item_subtotal == 600
    assert result.plan.landed_cost == 600
    assert result.plan.lines[0].units_purchased == 12
    assert result.plan.lines[0].overage_units == 4
    assert result.plan.per_child_item_costs == {
        "child-a": 300,
        "child-b": 300,
    }


def test_e15_mixed_pack_combination_beats_three_twelves() -> None:
    """E-15: 2×$5.00 plus 1×$3.50 is $13.50, below 3×$5.00."""

    need = _unit_need("pencils", {"child-a": 26})
    offers = [
        _offer("S-PEN-006", "S", "pencils", 6, 350),
        _offer("S-PEN-012", "S", "pencils", 12, 500),
    ]

    selection = select_packages(need, offers)

    assert selection is not None
    assert selection.item_subtotal == 1_350
    assert selection.units_purchased == 30
    assert selection.overage_units == 4
    packs_by_sku = {
        line.sku: line.packs_purchased for line in selection.lines
    }
    assert packs_by_sku == {"S-PEN-006": 1, "S-PEN-012": 2}


def test_shared_package_cost_allocates_proportionally_by_units() -> None:
    """BR-09: a $6.00 pack split 8:4 allocates exactly $4.00 and $2.00."""

    need = _unit_need("pencils", {"child-a": 8, "child-b": 4})
    result = optimize_cart(
        [need],
        [_offer("S-PEN-012", "S", "pencils", 12, 600)],
        [_store("S")],
        _config(),
    )

    assert result.plan.per_child_item_costs == {
        "child-a": 400,
        "child-b": 200,
    }
    assert sum(result.plan.per_child_item_costs.values()) == 600


def test_e18_landed_cost_under_budget_is_recommended() -> None:
    """E-18: $137.00 landed against $150.00 leaves $13.00 headroom."""

    result = optimize_cart(
        [_unit_need("backpacks", {"child-a": 1})],
        [_offer("S-BPK", "S", "backpacks", 1, 13_700)],
        [_store("S")],
        _config(budget_cents=15_000),
    )

    assert result.plan.item_subtotal == 13_700
    assert result.plan.tax == 0
    assert result.plan.fulfillment_fees == 0
    assert result.landed_cost == 13_700
    assert result.within_budget is True
    assert result.shortfall_cents == 0


def test_e19_cart_eight_dollars_over_budget_is_preserved() -> None:
    """E-19: $158.00 landed is $8.00 over; the required item remains."""

    result = optimize_cart(
        [_unit_need("backpacks", {"child-a": 1})],
        [_offer("S-BPK", "S", "backpacks", 1, 15_800)],
        [_store("S")],
        _config(budget_cents=15_000),
    )

    assert result.landed_cost == 15_800
    assert result.shortfall_cents == 800
    assert result.within_budget is False
    assert len(result.plan.lines) == 1
    assert result.plan.lines[0].units_needed == 1


def test_e20_minimum_cart_reports_full_shortfall_without_dropping() -> None:
    """E-20: the $135.00 minimum is $35.00 over a $100.00 budget."""

    result = optimize_cart(
        [_unit_need("headphones", {"child-a": 1})],
        [_offer("S-HDP", "S", "headphones", 1, 13_500)],
        [_store("S")],
        _config(budget_cents=10_000),
    )

    assert result.plan.item_subtotal == 13_500
    assert result.landed_cost == 13_500
    assert result.shortfall_cents == 3_500
    assert result.within_budget is False
    assert result.gap_items == ()


def test_e21_fees_and_tax_turn_item_headroom_into_budget_breach() -> None:
    """E-21: $95.00 + $6.65 tax + $5.00 fee = $106.65 landed."""

    result = optimize_cart(
        [_unit_need("backpacks", {"child-a": 1})],
        [_offer("S-BPK", "S", "backpacks", 1, 9_500)],
        [_store("S", pickup_fee=500, pickup_minimum=10_000)],
        _config(budget_cents=10_000, tax_basis_points=700),
    )

    assert result.plan.item_subtotal == 9_500
    assert result.plan.tax == 665
    assert result.plan.fulfillment_fees == 500
    assert result.landed_cost == 10_665
    assert result.shortfall_cents == 665
    assert result.within_budget is False


def test_e24_single_stop_returns_gap_and_minimum_second_trip() -> None:
    """E-24: $1.00 at A plus a $2.00 closing trip at B totals $3.00."""

    needs = [
        _unit_need("pencils", {"child-a": 1}),
        _unit_need("glue_sticks", {"child-a": 1}),
    ]
    offers = [
        _offer("A-PEN", "A", "pencils", 1, 100),
        _offer("B-GLU", "B", "glue_sticks", 1, 200),
    ]

    result = optimize_cart(
        needs,
        offers,
        [_store("A"), _store("B")],
        _config(mode="single_stop"),
    )

    assert result.plan.landed_cost == 100
    assert result.plan.store_orders[0].store_id == "A"
    assert result.gap_items == ("glue_sticks",)
    assert result.minimum_second_trip is not None
    assert result.minimum_second_trip.landed_cost == 200
    assert result.minimum_second_trip.store_orders[0].store_id == "B"
    assert result.landed_cost == 300
    assert result.comparison_cost == 900


def test_e25_four_store_six_dollar_saving_is_rejected() -> None:
    """E-25: $34.00 over four stores loses to $40.00 at one after penalties."""

    categories = ("pencils", "glue_sticks", "scissors", "crayons")
    needs = [
        _unit_need(category, {"child-a": 1})
        for category in categories
    ]
    offers = [
        _offer("A-PEN", "A", "pencils", 1, 850),
        _offer("A-GLU", "A", "glue_sticks", 1, 1_050),
        _offer("A-SCI", "A", "scissors", 1, 1_050),
        _offer("A-CRA", "A", "crayons", 1, 1_050),
        _offer("B-GLU", "B", "glue_sticks", 1, 850),
        _offer("C-SCI", "C", "scissors", 1, 850),
        _offer("D-CRA", "D", "crayons", 1, 850),
    ]

    result = optimize_cart(
        needs,
        offers,
        [_store("A"), _store("B"), _store("C"), _store("D")],
        _config(),
    )

    assert result.plan.item_subtotal == 4_000
    assert result.plan.landed_cost == 4_000
    assert result.plan.comparison_cost == 4_000
    assert len(result.plan.store_orders) == 1
    assert result.plan.store_orders[0].store_id == "A"


def test_e28_pickup_minimum_fee_changes_store_assignment() -> None:
    """E-28: A becomes $25.00 with its fee, so free-pickup B wins at $24.00."""

    need = _unit_need("backpacks", {"child-a": 1})
    stores = [
        _store("A", pickup_fee=500, pickup_minimum=3_000),
        _store("B"),
    ]
    offers = [
        _offer("A-BPK", "A", "backpacks", 1, 2_000),
        _offer("B-BPK", "B", "backpacks", 1, 2_400),
    ]

    result = optimize_cart([need], offers, stores, _config())
    store_a_only = optimize_cart(
        [need],
        [offers[0]],
        [stores[0]],
        _config(),
    )

    assert store_a_only.plan.item_subtotal == 2_000
    assert store_a_only.plan.fulfillment_fees == 500
    assert store_a_only.landed_cost == 2_500
    assert result.landed_cost == 2_400
    assert result.plan.store_orders[0].store_id == "B"


def test_custom_mode_enforces_store_limit_before_comparing_cost() -> None:
    """FR-04: one store costs $20.00; two stores cost $2.00 plus $6 penalty."""

    needs = [
        _unit_need("pencils", {"child-a": 1}),
        _unit_need("glue_sticks", {"child-a": 1}),
    ]
    offers = [
        _offer("A-PEN", "A", "pencils", 1, 1_000),
        _offer("A-GLU", "A", "glue_sticks", 1, 1_000),
        _offer("B-PEN", "B", "pencils", 1, 100),
        _offer("C-GLU", "C", "glue_sticks", 1, 100),
    ]
    stores = [_store("A"), _store("B"), _store("C")]
    allowed = frozenset({"A", "B", "C"})

    one_store = optimize_cart(
        needs,
        offers,
        stores,
        _config(
            mode="custom",
            max_stores=1,
            allowed_store_ids=allowed,
        ),
    )
    two_stores = optimize_cart(
        needs,
        offers,
        stores,
        _config(
            mode="custom",
            max_stores=2,
            allowed_store_ids=allowed,
        ),
    )

    assert one_store.landed_cost == 2_000
    assert one_store.comparison_cost == 2_000
    assert len(one_store.plan.store_orders) == 1
    assert two_stores.landed_cost == 200
    assert two_stores.comparison_cost == 800
    assert len(two_stores.plan.store_orders) == 2
