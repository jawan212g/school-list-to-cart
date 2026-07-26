"""Hand-computed tests for deterministic aggregation and optimization."""

from collections.abc import Mapping

from agent.aggregate import Requirement, UnitNeed, aggregate_requirements
from agent.optimize import (
    FulfillmentPreference,
    OptimizationConfig,
    ShoppingMode,
    optimize_cart,
    select_packages,
)
from agent.rules import TAX_ROUNDING_METHOD
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
            extraction_confidence=1.0,
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
    unit_price: int | None = None,
) -> Offer:
    return Offer(
        sku=sku,
        store_id=store_id,
        brand=brand,
        title=sku,
        category=category,
        pack_size=pack_size,
        unit_price=(
            pack_price // pack_size
            if unit_price is None
            else unit_price
        ),
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
    delivery_fee: int = 0,
    delivery_minimum: int = 0,
    tax_applies: bool = True,
    pickup_available: bool = True,
) -> Store:
    return Store(
        store_id=store_id,
        name=store_id,
        distance_miles=1.0,
        pickup_fee=pickup_fee,
        pickup_minimum=pickup_minimum,
        delivery_fee=delivery_fee,
        delivery_minimum=delivery_minimum,
        tax_applies=tax_applies,
        pickup_available=pickup_available,
    )


def _config(
    *,
    mode: ShoppingMode = "budget",
    budget_cents: int | None = None,
    tax_basis_points: int = 0,
    max_stores: int | None = None,
    allowed_store_ids: frozenset[str] | None = None,
    fulfillment_preference: FulfillmentPreference = "pickup",
) -> OptimizationConfig:
    return OptimizationConfig(
        shopping_mode=mode,
        budget_cents=budget_cents,
        tax_basis_points=tax_basis_points,
        max_stores=max_stores,
        allowed_store_ids=allowed_store_ids,
        fulfillment_preference=fulfillment_preference,
    )


def test_aggregation_rolls_up_children_but_separates_brand_locks() -> None:
    """FR-14/15/16: quantities and child attribution remain exact."""

    requirements = [
        Requirement(
            req_id="r1",
            child_id="child-a",
            raw_text="2 pencils",
            canonical_item="pencils",
            quantity=2,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="r2",
            child_id="child-b",
            raw_text="3 pencils",
            canonical_item="pencils",
            quantity=3,
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="r3",
            child_id="child-b",
            raw_text="4 Ticonderoga pencils",
            canonical_item="pencils",
            quantity=4,
            brand_lock="Ticonderoga",
            extraction_confidence=1.0,
        ),
    ]

    generic, locked = aggregate_requirements(requirements)

    assert generic.quantity == 5
    assert generic.allocated_to == {"child-a": 2, "child-b": 3}
    assert locked.quantity == 4
    assert locked.brand_lock == "Ticonderoga"
    assert locked.allocated_to == {"child-b": 4}


def test_br13_redundant_spiral_exclusion_does_not_split_composition_need() -> None:
    """FR-14/BR-13: composition notebooks aggregate to one six-unit need."""

    requirements = [
        Requirement(
            req_id="grade2",
            child_id="grade2",
            raw_text="2 composition notebooks, not spiral bound",
            canonical_item="composition_notebooks",
            quantity=2,
            exclusions=("not spiral bound",),
            attributes={"ruling": "wide"},
            extraction_confidence=1.0,
        ),
        Requirement(
            req_id="grade5",
            child_id="grade5",
            raw_text="4 composition notebooks",
            canonical_item="composition_notebooks",
            quantity=4,
            attributes={"ruling": "wide"},
            extraction_confidence=1.0,
        ),
    ]

    needs = aggregate_requirements(requirements)

    assert len(needs) == 1
    assert needs[0].quantity == 6
    assert needs[0].allocated_to == {"grade2": 2, "grade5": 4}
    assert needs[0].exclusions == ()


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


def test_all_money_uses_pack_price_not_lossy_unit_price() -> None:
    """A deliberately false 1-cent unit price cannot change the $1.00 pack."""

    need = _unit_need("pencils", {"child-a": 3})
    offer = _offer(
        "S-PEN-003",
        "S",
        "pencils",
        3,
        100,
        unit_price=1,
    )

    result = optimize_cart(
        [need],
        [offer],
        [_store("S")],
        _config(),
    )

    assert offer.unit_price == 1
    assert result.plan.lines[0].line_cost == 100
    assert result.plan.item_subtotal == 100
    assert result.landed_cost == 100


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


def test_br09_rounding_allocates_every_cent_across_three_children() -> None:
    """BR-09: $1.00 split by 1:2:3 units becomes 17, 33, and 50 cents."""

    need = _unit_need(
        "pencils",
        {"child-a": 1, "child-b": 2, "child-c": 3},
    )
    result = optimize_cart(
        [need],
        [_offer("S-PEN-006", "S", "pencils", 6, 100)],
        [_store("S")],
        _config(),
    )

    assert result.plan.per_child_item_costs == {
        "child-a": 17,
        "child-b": 33,
        "child-c": 50,
    }
    assert sum(result.plan.per_child_item_costs.values()) == 100
    assert sum(result.plan.per_child_item_costs.values()) == (
        result.plan.lines[0].line_cost
    )


def test_partial_stock_cannot_satisfy_a_unit_need_alone() -> None:
    """Two 4-packs in stock supply only 8 units, so the 10-pack store wins."""

    need = _unit_need("pencils", {"child-a": 10})
    partial_offer = _offer(
        "A-PEN-004",
        "A",
        "pencils",
        4,
        100,
        stock_qty=2,
    )
    complete_offer = _offer(
        "B-PEN-010",
        "B",
        "pencils",
        10,
        500,
        stock_qty=1,
    )

    partial_selection = select_packages(need, [partial_offer])
    result = optimize_cart(
        [need],
        [partial_offer, complete_offer],
        [_store("A"), _store("B")],
        _config(),
    )

    assert partial_offer.stock_qty * partial_offer.pack_size == 8
    assert partial_selection is None
    assert result.plan.lines[0].units_purchased == 10
    assert result.plan.item_subtotal == 500
    assert result.plan.store_orders[0].store_id == "B"


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


def test_br02_tax_rounds_fractional_cents_half_up() -> None:
    """BR-02: 7% of $1.50 is 10.5 cents and rounds half-up to 11 cents."""

    result = optimize_cart(
        [_unit_need("pencils", {"child-a": 1})],
        [_offer("S-PEN", "S", "pencils", 1, 150)],
        [_store("S")],
        _config(tax_basis_points=700),
    )

    assert TAX_ROUNDING_METHOD == "half_up_to_nearest_cent"
    assert result.plan.item_subtotal == 150
    assert result.plan.tax == 11
    assert result.landed_cost == 161


def test_delivery_fee_is_charged_below_and_waived_above_minimum() -> None:
    """FR-25: $7 delivery applies below $50 and is waived at $60."""

    store = _store(
        "D",
        delivery_fee=700,
        delivery_minimum=5_000,
    )
    offer = _offer("D-PEN", "D", "pencils", 1, 3_000)

    below_minimum = optimize_cart(
        [_unit_need("pencils", {"child-a": 1})],
        [offer],
        [store],
        _config(fulfillment_preference="delivery"),
    )
    above_minimum = optimize_cart(
        [_unit_need("pencils", {"child-a": 2})],
        [offer],
        [store],
        _config(fulfillment_preference="delivery"),
    )

    assert below_minimum.plan.item_subtotal == 3_000
    assert below_minimum.plan.fulfillment_fees == 700
    assert below_minimum.landed_cost == 3_700
    assert below_minimum.plan.store_orders[0].fulfillment_method == "delivery"
    assert above_minimum.plan.item_subtotal == 6_000
    assert above_minimum.plan.fulfillment_fees == 0
    assert above_minimum.landed_cost == 6_000
    assert above_minimum.plan.store_orders[0].fulfillment_method == "delivery"


def test_delivery_only_store_ignores_pickup_trip_radius() -> None:
    """FR-04/25: 100-mile online store ships despite a 1-mile trip radius."""

    store = Store(
        store_id="SHIP",
        name="Distant online store",
        distance_miles=100.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=250,
        delivery_minimum=2_000,
        tax_applies=False,
        pickup_available=False,
    )
    offer = _offer("SHIP-PENCILS", "SHIP", "pencils", 8, 1_000)
    config = OptimizationConfig(
        shopping_mode="budget",
        fulfillment_preference="either",
        store_radius_miles=1.0,
        tax_basis_points=0,
    )

    result = optimize_cart(
        [_unit_need("pencils", {"child-a": 8})],
        [offer],
        [store],
        config,
    )

    assert result.gap_items == ()
    assert result.plan.item_subtotal == 1_000
    assert result.plan.fulfillment_fees == 250
    assert result.landed_cost == 1_250
    assert result.plan.store_orders[0].fulfillment_method == "delivery"


def test_e27_pickup_preference_surfaces_cheaper_delivery_only_tradeoff() -> None:
    """E-27: pickup selects $10 at P and reports the excluded $5 delivery cart."""

    need = _unit_need("pencils", {"child-a": 1})
    stores = [
        _store("P"),
        _store("D", pickup_available=False),
    ]
    offers = [
        _offer("P-PEN", "P", "pencils", 1, 1_000),
        _offer("D-PEN", "D", "pencils", 1, 500),
    ]

    pickup_result = optimize_cart(
        [need],
        offers,
        stores,
        _config(fulfillment_preference="pickup"),
    )
    delivery_result = optimize_cart(
        [need],
        offers,
        stores,
        _config(fulfillment_preference="delivery"),
    )

    assert pickup_result.landed_cost == 1_000
    assert pickup_result.plan.store_orders[0].store_id == "P"
    assert pickup_result.plan.store_orders[0].fulfillment_method == "pickup"
    assert len(pickup_result.fulfillment_tradeoffs) == 1
    tradeoff = pickup_result.fulfillment_tradeoffs[0]
    assert tradeoff.store_id == "D"
    assert tradeoff.required_method == "delivery"
    assert tradeoff.affected_items == ("pencils",)
    assert tradeoff.alternative_landed_cost == 500
    assert delivery_result.landed_cost == 500
    assert delivery_result.plan.store_orders[0].store_id == "D"
    assert delivery_result.plan.store_orders[0].fulfillment_method == "delivery"


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
