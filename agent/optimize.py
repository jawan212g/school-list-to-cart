"""Deterministic package and store optimization with integer-cent arithmetic."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
import logging
from time import perf_counter
from typing import Literal

from agent.aggregate import UnitNeed
from agent.rules import (
    ADDITIONAL_STORE_PENALTY_CENTS,
    BASIS_POINTS_DENOMINATOR,
    DEFAULT_TAX_BASIS_POINTS,
    OVERAGE_ABSOLUTE_UNITS,
    OVERAGE_PERCENT,
    PERCENT_DENOMINATOR,
    TAX_ROUNDING_OFFSET,
)
from agent.store_scope import (
    FulfillmentPreference,
    pickup_trip_is_within_radius,
    store_supports_fulfillment,
)
from data.loader import Offer, Store


LOGGER = logging.getLogger(__name__)
OPTIMIZER_STATE_CACHE_MAX_ENTRIES = 25_000
# Operational memory guard, not a cart rule: eviction only causes exact-search
# recomputation and cannot change candidates, costs, pruning, or the result.


ShoppingMode = Literal["budget", "single_stop", "custom"]
FulfillmentMethod = Literal["pickup", "delivery"]


@dataclass(frozen=True)
class OptimizationConfig:
    """Session-level controls used by FR-04 and FR-24."""

    shopping_mode: ShoppingMode = "budget"
    budget_cents: int | None = None
    allowed_store_ids: frozenset[str] | None = None
    max_stores: int | None = None
    store_radius_miles: float | None = None
    fulfillment_preference: FulfillmentPreference = "either"
    tax_basis_points: int = DEFAULT_TAX_BASIS_POINTS


@dataclass(frozen=True)
class SelectedPack:
    """One SKU and pack count within a package-size solution."""

    sku: str
    store_id: str
    brand: str
    pack_size: int
    pack_price: int
    packs_purchased: int

    @property
    def units_purchased(self) -> int:
        """Return individual units supplied by this selected SKU."""

        return self.pack_size * self.packs_purchased

    @property
    def line_cost(self) -> int:
        """Return this selected SKU's extended price in integer cents."""

        return self.pack_price * self.packs_purchased


@dataclass(frozen=True)
class PackageSelection:
    """Lowest-cost valid combination of packs for one need at one store."""

    store_id: str
    lines: tuple[SelectedPack, ...]
    units_needed: int
    units_purchased: int
    overage_units: int
    item_subtotal: int
    overage_exception: bool


@dataclass(frozen=True)
class CartLine:
    """A deterministic BRD Section 8 cart line."""

    line_id: str
    canonical_item: str
    sku: str
    store_id: str
    packs_purchased: int
    units_purchased: int
    units_needed: int
    overage_units: int
    allocated_to: Mapping[str, int]
    line_cost: int
    substitution_type: str
    approval_status: str
    source_requirement_ids: tuple[str, ...] = ()
    match_confidence: float = 1.0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoreOrder:
    """One pickup or delivery order and its complete landed cost."""

    store_id: str
    fulfillment_method: FulfillmentMethod
    lines: tuple[CartLine, ...]
    item_subtotal: int
    tax: int
    fulfillment_fee: int
    landed_cost: int


@dataclass(frozen=True)
class CartPlan:
    """A complete deterministic cart with actual and comparison costs."""

    lines: tuple[CartLine, ...]
    store_orders: tuple[StoreOrder, ...]
    item_subtotal: int
    tax: int
    fulfillment_fees: int
    landed_cost: int
    comparison_cost: int
    per_child_item_costs: Mapping[str, int] = field(default_factory=dict)
    per_child_landed_costs: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class FulfillmentTradeoff:
    """A store excluded because it cannot honor the requested fulfillment."""

    store_id: str
    requested_preference: FulfillmentPreference
    required_method: FulfillmentMethod
    affected_items: tuple[str, ...]
    alternative_landed_cost: int | None


@dataclass(frozen=True)
class OptimizationResult:
    """Recommended cart plus budget and single-stop fallback information."""

    plan: CartPlan
    gap_items: tuple[str, ...]
    minimum_second_trip: CartPlan | None
    landed_cost: int
    comparison_cost: int
    budget_cents: int | None
    within_budget: bool | None
    shortfall_cents: int
    fulfillment_tradeoffs: tuple[FulfillmentTradeoff, ...] = ()

    @property
    def is_complete(self) -> bool:
        """Return whether the primary plan or its second trip closes all gaps."""

        return not self.unfulfilled_gap_items

    @property
    def unfulfilled_gap_items(self) -> tuple[str, ...]:
        """Return only gaps not supplied by the completed second-trip plan."""

        if self.minimum_second_trip is not None:
            return ()
        return self.gap_items


def per_entry_landed_costs(
    optimization: OptimizationResult,
) -> dict[str, int]:
    """Return each entry's full allocated cost across every store plan."""

    totals: dict[str, int] = {}
    plans = (optimization.plan,) + (
        ()
        if optimization.minimum_second_trip is None
        else (optimization.minimum_second_trip,)
    )
    for plan in plans:
        for entry_id, amount in plan.per_child_landed_costs.items():
            totals[entry_id] = totals.get(entry_id, 0) + amount
    return totals


def per_entry_budget_overages(
    optimization: OptimizationResult,
    allocations: Mapping[str, int],
) -> dict[str, int]:
    """Return positive E-22 overages without pooling independent budgets."""

    costs = per_entry_landed_costs(optimization)
    return {
        entry_id: costs.get(entry_id, 0) - budget
        for entry_id, budget in allocations.items()
        if costs.get(entry_id, 0) > budget
    }


@dataclass(frozen=True)
class _PackageState:
    cost: int
    pack_count: int
    counts: tuple[int, ...]


def _matching_offers(
    unit_need: UnitNeed,
    offers: Sequence[Offer],
) -> tuple[Offer, ...]:
    matching = []
    for offer in offers:
        if offer.stock_qty <= 0 or offer.category != unit_need.canonical_item:
            continue
        if (
            unit_need.brand_lock is not None
            and offer.brand.casefold() != unit_need.brand_lock.casefold()
        ):
            continue
        matching.append(offer)
    return tuple(sorted(matching, key=lambda offer: offer.sku))


def _better_package_state(
    candidate: _PackageState,
    current: _PackageState | None,
) -> bool:
    if current is None:
        return True
    return (
        candidate.cost,
        candidate.pack_count,
        candidate.counts,
    ) < (
        current.cost,
        current.pack_count,
        current.counts,
    )


def _package_states(
    offers: Sequence[Offer],
    maximum_units: int,
) -> dict[int, _PackageState]:
    states: dict[int, _PackageState] = {
        0: _PackageState(cost=0, pack_count=0, counts=())
    }

    for offer in offers:
        next_states: dict[int, _PackageState] = {}
        maximum_packs = min(
            offer.stock_qty,
            maximum_units // offer.pack_size,
        )
        for units, state in states.items():
            for packs in range(maximum_packs + 1):
                new_units = units + packs * offer.pack_size
                if new_units > maximum_units:
                    break
                candidate = _PackageState(
                    cost=state.cost + packs * offer.pack_price,
                    pack_count=state.pack_count + packs,
                    counts=state.counts + (packs,),
                )
                if _better_package_state(candidate, next_states.get(new_units)):
                    next_states[new_units] = candidate
        states = next_states

    return states


def _best_qualifying_state(
    states: Mapping[int, _PackageState],
    units_needed: int,
) -> tuple[int, _PackageState] | None:
    qualifying = [
        (units, state)
        for units, state in states.items()
        if units >= units_needed
    ]
    if not qualifying:
        return None
    return min(
        qualifying,
        key=lambda item: (
            item[1].cost,
            item[0] - units_needed,
            item[1].pack_count,
            item[1].counts,
        ),
    )


def select_packages(
    unit_need: UnitNeed,
    offers: Sequence[Offer],
) -> PackageSelection | None:
    """Select a valid pack combination at one store (FR-21, BR-06)."""

    if unit_need.quantity <= 0:
        raise ValueError("Unit need quantity must be positive")

    matching = _matching_offers(unit_need, offers)
    if not matching:
        return None
    store_ids = {offer.store_id for offer in matching}
    if len(store_ids) != 1:
        raise ValueError("select_packages requires offers from exactly one store")
    if any(offer.pack_size <= 0 or offer.pack_price < 0 for offer in matching):
        raise ValueError("Offer pack sizes must be positive and prices nonnegative")

    relative_allowance = (
        unit_need.quantity * OVERAGE_PERCENT // PERCENT_DENOMINATOR
    )
    allowed_overage = max(relative_allowance, OVERAGE_ABSOLUTE_UNITS)
    maximum_units = unit_need.quantity + allowed_overage
    best = _best_qualifying_state(
        _package_states(matching, maximum_units),
        unit_need.quantity,
    )
    overage_exception = False

    if best is None:
        largest_pack = max(offer.pack_size for offer in matching)
        fallback_maximum = unit_need.quantity + largest_pack - 1
        best = _best_qualifying_state(
            _package_states(matching, fallback_maximum),
            unit_need.quantity,
        )
        overage_exception = best is not None

    if best is None:
        return None

    units_purchased, state = best
    selected_lines = tuple(
        SelectedPack(
            sku=offer.sku,
            store_id=offer.store_id,
            brand=offer.brand,
            pack_size=offer.pack_size,
            pack_price=offer.pack_price,
            packs_purchased=packs,
        )
        for offer, packs in zip(matching, state.counts, strict=True)
        if packs > 0
    )
    return PackageSelection(
        store_id=next(iter(store_ids)),
        lines=selected_lines,
        units_needed=unit_need.quantity,
        units_purchased=units_purchased,
        overage_units=units_purchased - unit_need.quantity,
        item_subtotal=state.cost,
        overage_exception=overage_exception,
    )


def calculate_tax(subtotal_cents: int, tax_basis_points: int) -> int:
    """Calculate item tax with integer half-up rounding (FR-24, BR-02)."""

    if subtotal_cents < 0 or tax_basis_points < 0:
        raise ValueError("Subtotal and tax rate must be nonnegative")
    return (
        subtotal_cents * tax_basis_points + TAX_ROUNDING_OFFSET
    ) // BASIS_POINTS_DENOMINATOR


def _fee_for_minimum(
    item_subtotal: int,
    fee: int,
    waiver_minimum: int,
) -> int:
    return fee if item_subtotal < waiver_minimum else 0


def _choose_fulfillment(
    store: Store,
    item_subtotal: int,
    preference: FulfillmentPreference,
    store_radius_miles: float | None,
) -> tuple[FulfillmentMethod, int] | None:
    choices: list[tuple[FulfillmentMethod, int]] = []
    if (
        preference in {"pickup", "either"}
        and pickup_trip_is_within_radius(store, store_radius_miles)
    ):
        choices.append(
            (
                "pickup",
                _fee_for_minimum(
                    item_subtotal,
                    store.pickup_fee,
                    store.pickup_minimum,
                ),
            )
        )
    if preference in {"delivery", "either"}:
        choices.append(
            (
                "delivery",
                _fee_for_minimum(
                    item_subtotal,
                    store.delivery_fee,
                    store.delivery_minimum,
                ),
            )
        )
    if not choices:
        return None
    return min(
        choices,
        key=lambda choice: (
            choice[1],
            choice[0] != "pickup",
        ),
    )


def _allocate_cents(
    total_cents: int,
    unit_weights: Mapping[str, int],
) -> dict[str, int]:
    if total_cents < 0:
        raise ValueError("Allocated cost must be nonnegative")
    positive_weights = {
        child_id: units
        for child_id, units in unit_weights.items()
        if units > 0
    }
    if not positive_weights:
        return {}

    total_units = sum(positive_weights.values())
    allocations = {
        child_id: total_cents * units // total_units
        for child_id, units in positive_weights.items()
    }
    remainders = sorted(
        (
            (total_cents * units % total_units, child_id)
            for child_id, units in positive_weights.items()
        ),
        key=lambda item: (-item[0], item[1]),
    )
    undistributed = total_cents - sum(allocations.values())
    for _, child_id in remainders[:undistributed]:
        allocations[child_id] += 1
    return allocations


def _line_unit_allocations(
    unit_need: UnitNeed,
    selection: PackageSelection,
) -> tuple[Mapping[str, int], ...]:
    remaining = dict(unit_need.allocated_to)
    allocations: list[Mapping[str, int]] = []

    for selected_pack in selection.lines:
        line_capacity = selected_pack.units_purchased
        line_allocation: dict[str, int] = {}
        for child_id in sorted(remaining):
            units = min(remaining[child_id], line_capacity)
            if units > 0:
                line_allocation[child_id] = units
                remaining[child_id] -= units
                line_capacity -= units
            if line_capacity == 0:
                break
        allocations.append(line_allocation)

    return tuple(allocations)


def _empty_plan() -> CartPlan:
    return CartPlan(
        lines=(),
        store_orders=(),
        item_subtotal=0,
        tax=0,
        fulfillment_fees=0,
        landed_cost=0,
        comparison_cost=0,
        per_child_item_costs={},
        per_child_landed_costs={},
    )


def _build_plan(
    assignments: Sequence[tuple[UnitNeed, PackageSelection]],
    stores_by_id: Mapping[str, Store],
    config: OptimizationConfig,
) -> CartPlan:
    if not assignments:
        return _empty_plan()

    cart_lines: list[CartLine] = []
    lines_by_store: dict[str, list[CartLine]] = defaultdict(list)
    item_costs_by_store_child: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    per_child_item_costs: dict[str, int] = defaultdict(int)

    for assignment_index, (unit_need, selection) in enumerate(assignments):
        child_costs = _allocate_cents(
            selection.item_subtotal,
            unit_need.allocated_to,
        )
        for child_id, cost in child_costs.items():
            per_child_item_costs[child_id] += cost
            item_costs_by_store_child[selection.store_id][child_id] += cost

        line_allocations = _line_unit_allocations(unit_need, selection)
        for line_index, (selected_pack, allocated_to) in enumerate(
            zip(selection.lines, line_allocations, strict=True)
        ):
            units_needed = sum(allocated_to.values())
            overage_units = selected_pack.units_purchased - units_needed
            substitution_type = (
                "minor" if selection.overage_units > 0 else "none"
            )
            approval_status = (
                "pending" if selection.overage_exception else "not_required"
            )
            line = CartLine(
                line_id=f"line-{assignment_index + 1}-{line_index + 1}",
                canonical_item=unit_need.canonical_item,
                sku=selected_pack.sku,
                store_id=selected_pack.store_id,
                packs_purchased=selected_pack.packs_purchased,
                units_purchased=selected_pack.units_purchased,
                units_needed=units_needed,
                overage_units=overage_units,
                allocated_to=allocated_to,
                line_cost=selected_pack.line_cost,
                substitution_type=substitution_type,
                approval_status=approval_status,
                source_requirement_ids=unit_need.source_requirement_ids,
            )
            cart_lines.append(line)
            lines_by_store[line.store_id].append(line)

    store_orders: list[StoreOrder] = []
    per_child_landed_costs = dict(per_child_item_costs)
    for store_id in sorted(lines_by_store):
        store = stores_by_id[store_id]
        store_lines = tuple(lines_by_store[store_id])
        item_subtotal = sum(line.line_cost for line in store_lines)
        fulfillment = _choose_fulfillment(
            store,
            item_subtotal,
            config.fulfillment_preference,
            config.store_radius_miles,
        )
        if fulfillment is None:
            raise ValueError(
                f"Store {store_id} cannot satisfy the fulfillment preference"
            )
        fulfillment_method, fulfillment_fee = fulfillment
        tax = (
            calculate_tax(item_subtotal, config.tax_basis_points)
            if store.tax_applies
            else 0
        )
        landed_cost = item_subtotal + tax + fulfillment_fee
        store_orders.append(
            StoreOrder(
                store_id=store_id,
                fulfillment_method=fulfillment_method,
                lines=store_lines,
                item_subtotal=item_subtotal,
                tax=tax,
                fulfillment_fee=fulfillment_fee,
                landed_cost=landed_cost,
            )
        )

        child_weights = item_costs_by_store_child[store_id]
        child_tax = _allocate_cents(tax, child_weights)
        child_fee = _allocate_cents(fulfillment_fee, child_weights)
        for child_id in child_weights:
            per_child_landed_costs[child_id] = (
                per_child_landed_costs.get(child_id, 0)
                + child_tax.get(child_id, 0)
                + child_fee.get(child_id, 0)
            )

    item_subtotal = sum(order.item_subtotal for order in store_orders)
    tax = sum(order.tax for order in store_orders)
    fulfillment_fees = sum(
        order.fulfillment_fee for order in store_orders
    )
    landed_cost = item_subtotal + tax + fulfillment_fees
    additional_stores = max(len(store_orders) - 1, 0)
    comparison_cost = (
        landed_cost
        + additional_stores * ADDITIONAL_STORE_PENALTY_CENTS
    )
    return CartPlan(
        lines=tuple(cart_lines),
        store_orders=tuple(store_orders),
        item_subtotal=item_subtotal,
        tax=tax,
        fulfillment_fees=fulfillment_fees,
        landed_cost=landed_cost,
        comparison_cost=comparison_cost,
        per_child_item_costs=dict(per_child_item_costs),
        per_child_landed_costs=per_child_landed_costs,
    )


def _stores_in_scope(
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> tuple[Store, ...]:
    in_scope = []
    for store in stores:
        if (
            config.allowed_store_ids is not None
            and store.store_id not in config.allowed_store_ids
        ):
            continue
        in_scope.append(store)
    return tuple(sorted(in_scope, key=lambda store: store.store_id))


def _eligible_stores(
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> tuple[Store, ...]:
    eligible = []
    for store in _stores_in_scope(stores, config):
        if not store_supports_fulfillment(
            store,
            config.store_radius_miles,
            config.fulfillment_preference,
        ):
            continue
        eligible.append(store)
    return tuple(sorted(eligible, key=lambda store: store.store_id))


def _candidate_selections(
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    eligible_stores: Sequence[Store],
    candidate_skus_by_need: (
        Mapping[tuple[str, ...], frozenset[str]] | None
    ) = None,
) -> tuple[Mapping[str, PackageSelection], ...]:
    offers_by_store: dict[str, list[Offer]] = defaultdict(list)
    eligible_ids = {store.store_id for store in eligible_stores}
    for offer in offers:
        if offer.store_id in eligible_ids:
            offers_by_store[offer.store_id].append(offer)

    candidates: list[Mapping[str, PackageSelection]] = []
    for unit_need in unit_needs:
        need_candidates: dict[str, PackageSelection] = {}
        allowed_skus = (
            None
            if candidate_skus_by_need is None
            else candidate_skus_by_need.get(
                unit_need.source_requirement_ids,
                frozenset(),
            )
        )
        for store in eligible_stores:
            store_offers = offers_by_store.get(store.store_id, ())
            if allowed_skus is not None:
                store_offers = tuple(
                    offer
                    for offer in store_offers
                    if offer.sku in allowed_skus
                )
            selection = select_packages(
                unit_need,
                store_offers,
            )
            if selection is not None:
                need_candidates[store.store_id] = selection
        candidates.append(need_candidates)
    return tuple(candidates)


def _plan_sort_key(plan: CartPlan) -> tuple[object, ...]:
    return (
        plan.comparison_cost,
        plan.landed_cost,
        len(plan.store_orders),
        tuple(order.store_id for order in plan.store_orders),
        tuple(line.sku for line in plan.lines),
    )


def _best_multi_store_plan(
    unit_needs: Sequence[UnitNeed],
    candidates: Sequence[Mapping[str, PackageSelection]],
    stores_by_id: Mapping[str, Store],
    config: OptimizationConfig,
) -> CartPlan:
    if not unit_needs:
        return _empty_plan()

    ordered = sorted(
        zip(unit_needs, candidates, strict=True),
        key=lambda item: (len(item[1]), item[0].label),
    )
    minimum_remaining_cost = [0] * (len(ordered) + 1)
    for index in range(len(ordered) - 1, -1, -1):
        cheapest = min(
            selection.item_subtotal
            for selection in ordered[index][1].values()
        )
        minimum_remaining_cost[index] = (
            minimum_remaining_cost[index + 1] + cheapest
        )

    store_limit = (
        config.max_stores if config.shopping_mode == "custom" else None
    )
    if store_limit is not None and store_limit <= 0:
        raise ValueError("Custom max_stores must be positive")

    best_plan: CartPlan | None = None
    best_prefix_by_state: OrderedDict[
        tuple[int, tuple[tuple[str, int], ...]],
        tuple[str, ...],
    ] = OrderedDict()
    visited_states = 0
    memoized_prunes = 0
    cache_evictions = 0
    peak_cache_entries = 0
    search_started_at = perf_counter()

    def unavoidable_tax(
        item_subtotals_by_store: Mapping[str, int],
    ) -> int:
        return sum(
            calculate_tax(subtotal, config.tax_basis_points)
            for store_id, subtotal in item_subtotals_by_store.items()
            if stores_by_id[store_id].tax_applies
        )

    def final_comparison_cost(
        item_subtotals_by_store: Mapping[str, int],
    ) -> int:
        landed_cost = 0
        for store_id, subtotal in item_subtotals_by_store.items():
            store = stores_by_id[store_id]
            fulfillment = _choose_fulfillment(
                store,
                subtotal,
                config.fulfillment_preference,
                config.store_radius_miles,
            )
            if fulfillment is None:
                raise ValueError(
                    f"Store {store_id} cannot satisfy the fulfillment preference"
                )
            _, fulfillment_fee = fulfillment
            tax = (
                calculate_tax(subtotal, config.tax_basis_points)
                if store.tax_applies
                else 0
            )
            landed_cost += subtotal + tax + fulfillment_fee
        return (
            landed_cost
            + max(len(item_subtotals_by_store) - 1, 0)
            * ADDITIONAL_STORE_PENALTY_CENTS
        )

    def search(
        index: int,
        chosen: list[tuple[UnitNeed, PackageSelection]],
        used_stores: frozenset[str],
        current_item_cost: int,
        item_subtotals_by_store: dict[str, int],
    ) -> None:
        nonlocal best_plan
        nonlocal cache_evictions
        nonlocal memoized_prunes
        nonlocal peak_cache_entries
        nonlocal visited_states

        visited_states += 1

        state_key = (
            index,
            tuple(sorted(item_subtotals_by_store.items())),
        )
        prefix_key = tuple(
            line.sku
            for _, selection in chosen
            for line in selection.lines
        )
        prior_prefix = best_prefix_by_state.get(state_key)
        if prior_prefix is not None and prior_prefix <= prefix_key:
            memoized_prunes += 1
            best_prefix_by_state.move_to_end(state_key)
            return
        best_prefix_by_state[state_key] = prefix_key
        best_prefix_by_state.move_to_end(state_key)
        if len(best_prefix_by_state) > OPTIMIZER_STATE_CACHE_MAX_ENTRIES:
            best_prefix_by_state.popitem(last=False)
            cache_evictions += 1
            if cache_evictions == 1:
                LOGGER.warning(
                    "OPTIMIZER_STATE_CACHE reached capacity=%d; "
                    "continuing exact search with oldest-state eviction",
                    OPTIMIZER_STATE_CACHE_MAX_ENTRIES,
                )
        peak_cache_entries = max(
            peak_cache_entries,
            len(best_prefix_by_state),
        )

        lower_bound = (
            current_item_cost
            + minimum_remaining_cost[index]
            + unavoidable_tax(item_subtotals_by_store)
            + max(len(used_stores) - 1, 0)
            * ADDITIONAL_STORE_PENALTY_CENTS
        )
        if best_plan is not None and lower_bound > best_plan.comparison_cost:
            return

        if index == len(ordered):
            comparison_cost = final_comparison_cost(
                item_subtotals_by_store
            )
            if (
                best_plan is not None
                and comparison_cost > best_plan.comparison_cost
            ):
                return
            plan = _build_plan(chosen, stores_by_id, config)
            if best_plan is None or _plan_sort_key(plan) < _plan_sort_key(best_plan):
                best_plan = plan
            return

        unit_need, need_candidates = ordered[index]
        for store_id, selection in sorted(
            need_candidates.items(),
            key=lambda item: (
                item[1].item_subtotal,
                item[0],
            ),
        ):
            next_stores = used_stores | {store_id}
            if store_limit is not None and len(next_stores) > store_limit:
                continue
            chosen.append((unit_need, selection))
            item_subtotals_by_store[store_id] = (
                item_subtotals_by_store.get(store_id, 0)
                + selection.item_subtotal
            )
            search(
                index + 1,
                chosen,
                next_stores,
                current_item_cost + selection.item_subtotal,
                item_subtotals_by_store,
            )
            remaining_subtotal = (
                item_subtotals_by_store[store_id]
                - selection.item_subtotal
            )
            if remaining_subtotal:
                item_subtotals_by_store[store_id] = remaining_subtotal
            else:
                del item_subtotals_by_store[store_id]
            chosen.pop()

    search(0, [], frozenset(), 0, {})
    elapsed_seconds = perf_counter() - search_started_at
    if cache_evictions or visited_states >= 10_000 or elapsed_seconds >= 1.0:
        LOGGER.warning(
            "OPTIMIZER_SEARCH completed elapsed_seconds=%.3f needs=%d "
            "visited_states=%d memoized_prunes=%d peak_cache_entries=%d "
            "cache_evictions=%d cache_capacity=%d",
            elapsed_seconds,
            len(ordered),
            visited_states,
            memoized_prunes,
            peak_cache_entries,
            cache_evictions,
            OPTIMIZER_STATE_CACHE_MAX_ENTRIES,
        )
    if best_plan is None:
        raise ValueError("No cart satisfies the active store constraints")
    return best_plan


def _best_custom_constrained_result(
    unit_needs: Sequence[UnitNeed],
    candidates: Sequence[Mapping[str, PackageSelection]],
    eligible_stores: Sequence[Store],
    stores_by_id: Mapping[str, Store],
    config: OptimizationConfig,
) -> tuple[CartPlan, tuple[str, ...]]:
    """Return the best feasible partial or complete custom-store plan (FR-04)."""

    store_limit = config.max_stores
    if store_limit is None:
        return (
            _best_multi_store_plan(
                unit_needs,
                candidates,
                stores_by_id,
                config,
            ),
            (),
        )
    if store_limit <= 0:
        raise ValueError("Custom max_stores must be positive")

    try:
        return (
            _best_multi_store_plan(
                unit_needs,
                candidates,
                stores_by_id,
                config,
            ),
            (),
        )
    except ValueError:
        pass

    store_ids = tuple(store.store_id for store in eligible_stores)
    candidates_by_scope: list[tuple[CartPlan, tuple[str, ...]]] = []
    for scope_size in range(1, min(store_limit, len(store_ids)) + 1):
        for scoped_ids in combinations(store_ids, scope_size):
            scoped_id_set = frozenset(scoped_ids)
            scoped_needs: list[UnitNeed] = []
            scoped_candidates: list[Mapping[str, PackageSelection]] = []
            gaps: list[str] = []
            for unit_need, need_candidates in zip(
                unit_needs,
                candidates,
                strict=True,
            ):
                available = {
                    store_id: selection
                    for store_id, selection in need_candidates.items()
                    if store_id in scoped_id_set
                }
                if available:
                    scoped_needs.append(unit_need)
                    scoped_candidates.append(available)
                else:
                    gaps.append(unit_need.label)
            scoped_stores = {
                store_id: stores_by_id[store_id]
                for store_id in scoped_ids
            }
            scoped_config = replace(config, max_stores=scope_size)
            plan = _best_multi_store_plan(
                scoped_needs,
                scoped_candidates,
                scoped_stores,
                scoped_config,
            )
            candidates_by_scope.append((plan, tuple(gaps)))

    if not candidates_by_scope:
        return _empty_plan(), tuple(need.label for need in unit_needs)
    return min(
        candidates_by_scope,
        key=lambda candidate: (
            bool(candidate[1]),
            len(candidate[1]),
            _plan_sort_key(candidate[0]),
        ),
    )


def _single_store_plan(
    unit_needs: Sequence[UnitNeed],
    candidates: Sequence[Mapping[str, PackageSelection]],
    store_id: str,
    stores_by_id: Mapping[str, Store],
    config: OptimizationConfig,
) -> CartPlan | None:
    assignments: list[tuple[UnitNeed, PackageSelection]] = []
    for unit_need, need_candidates in zip(unit_needs, candidates, strict=True):
        selection = need_candidates.get(store_id)
        if selection is None:
            return None
        assignments.append((unit_need, selection))
    return _build_plan(assignments, stores_by_id, config)


def _fulfillment_tradeoffs(
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
    candidate_skus_by_need: (
        Mapping[tuple[str, ...], frozenset[str]] | None
    ) = None,
) -> tuple[FulfillmentTradeoff, ...]:
    if config.fulfillment_preference != "pickup":
        return ()

    delivery_config = replace(config, fulfillment_preference="delivery")
    tradeoffs: list[FulfillmentTradeoff] = []
    for store in stores:
        if pickup_trip_is_within_radius(
            store,
            config.store_radius_miles,
        ):
            continue
        store_candidates = _candidate_selections(
            unit_needs,
            offers,
            (store,),
            candidate_skus_by_need,
        )
        affected_items = tuple(
            unit_need.label
            for unit_need, candidates in zip(
                unit_needs,
                store_candidates,
                strict=True,
            )
            if candidates
        )
        if not affected_items:
            continue
        alternative_plan = _single_store_plan(
            unit_needs,
            store_candidates,
            store.store_id,
            {store.store_id: store},
            delivery_config,
        )
        tradeoffs.append(
            FulfillmentTradeoff(
                store_id=store.store_id,
                requested_preference="pickup",
                required_method="delivery",
                affected_items=affected_items,
                alternative_landed_cost=(
                    alternative_plan.landed_cost
                    if alternative_plan is not None
                    else None
                ),
            )
        )
    return tuple(tradeoffs)


def _minimum_second_trip(
    gap_needs: Sequence[UnitNeed],
    gap_candidates: Sequence[Mapping[str, PackageSelection]],
    eligible_stores: Sequence[Store],
    stores_by_id: Mapping[str, Store],
    config: OptimizationConfig,
) -> CartPlan | None:
    if not gap_needs:
        return None

    plans: list[CartPlan] = []
    for store in eligible_stores:
        plan = _single_store_plan(
            gap_needs,
            gap_candidates,
            store.store_id,
            stores_by_id,
            config,
        )
        if plan is not None:
            plans.append(plan)
    if not plans:
        return None
    return min(
        plans,
        key=lambda plan: (
            plan.landed_cost,
            tuple(order.store_id for order in plan.store_orders),
        ),
    )


def _best_single_stop_result(
    unit_needs: Sequence[UnitNeed],
    candidates: Sequence[Mapping[str, PackageSelection]],
    eligible_stores: Sequence[Store],
    stores_by_id: Mapping[str, Store],
    config: OptimizationConfig,
) -> tuple[CartPlan, tuple[str, ...], CartPlan | None]:
    candidates_by_primary: list[
        tuple[CartPlan, tuple[str, ...], CartPlan | None]
    ] = []

    for store in eligible_stores:
        assignments: list[tuple[UnitNeed, PackageSelection]] = []
        gap_needs: list[UnitNeed] = []
        gap_candidate_maps: list[Mapping[str, PackageSelection]] = []
        for unit_need, need_candidates in zip(
            unit_needs,
            candidates,
            strict=True,
        ):
            selection = need_candidates.get(store.store_id)
            if selection is None:
                gap_needs.append(unit_need)
                gap_candidate_maps.append(need_candidates)
            else:
                assignments.append((unit_need, selection))

        if not assignments:
            continue
        primary_plan = _build_plan(assignments, stores_by_id, config)
        second_trip = _minimum_second_trip(
            gap_needs,
            gap_candidate_maps,
            eligible_stores,
            stores_by_id,
            config,
        )
        candidates_by_primary.append(
            (
                primary_plan,
                tuple(need.label for need in gap_needs),
                second_trip,
            )
        )

    if not candidates_by_primary:
        return (
            _empty_plan(),
            tuple(need.label for need in unit_needs),
            None,
        )

    return min(
        candidates_by_primary,
        key=lambda candidate: (
            bool(candidate[1]),
            bool(candidate[1]) and candidate[2] is None,
            len(candidate[1]),
            candidate[0].landed_cost
            + (
                candidate[2].landed_cost
                if candidate[2] is not None
                else 0
            ),
            candidate[0].landed_cost,
            tuple(
                order.store_id
                for order in candidate[0].store_orders
            ),
        ),
    )


def _make_result(
    plan: CartPlan,
    gap_items: tuple[str, ...],
    minimum_second_trip: CartPlan | None,
    budget_cents: int | None,
    fulfillment_tradeoffs: tuple[FulfillmentTradeoff, ...] = (),
) -> OptimizationResult:
    landed_cost = plan.landed_cost
    comparison_cost = plan.comparison_cost
    if minimum_second_trip is not None:
        landed_cost += minimum_second_trip.landed_cost
        comparison_cost = (
            landed_cost + ADDITIONAL_STORE_PENALTY_CENTS
        )

    within_budget = (
        None if budget_cents is None else landed_cost <= budget_cents
    )
    shortfall_cents = (
        0
        if budget_cents is None
        else max(landed_cost - budget_cents, 0)
    )
    return OptimizationResult(
        plan=plan,
        gap_items=gap_items,
        minimum_second_trip=minimum_second_trip,
        landed_cost=landed_cost,
        comparison_cost=comparison_cost,
        budget_cents=budget_cents,
        within_budget=within_budget,
        shortfall_cents=shortfall_cents,
        fulfillment_tradeoffs=fulfillment_tradeoffs,
    )


def optimize_cart(
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig | None = None,
    candidate_skus_by_need: (
        Mapping[tuple[str, ...], frozenset[str]] | None
    ) = None,
) -> OptimizationResult:
    """Optimize all shopping modes and landed costs (FR-04, FR-21–FR-25)."""

    active_config = config or OptimizationConfig()
    if active_config.shopping_mode not in {"budget", "single_stop", "custom"}:
        raise ValueError(
            f"Unsupported shopping mode: {active_config.shopping_mode}"
        )
    if active_config.budget_cents is not None and active_config.budget_cents < 0:
        raise ValueError("Budget must be nonnegative")

    stores_in_scope = _stores_in_scope(stores, active_config)
    fulfillment_tradeoffs = _fulfillment_tradeoffs(
        unit_needs,
        offers,
        stores_in_scope,
        active_config,
        candidate_skus_by_need,
    )
    eligible_stores = _eligible_stores(stores_in_scope, active_config)
    stores_by_id = {store.store_id: store for store in eligible_stores}
    if len(stores_by_id) != len(eligible_stores):
        raise ValueError("Store IDs must be unique")

    candidates = _candidate_selections(
        unit_needs,
        offers,
        eligible_stores,
        candidate_skus_by_need,
    )
    if active_config.shopping_mode == "single_stop":
        plan, gap_items, second_trip = _best_single_stop_result(
            unit_needs,
            candidates,
            eligible_stores,
            stores_by_id,
            active_config,
        )
        return _make_result(
            plan,
            gap_items,
            second_trip,
            active_config.budget_cents,
            fulfillment_tradeoffs,
        )

    if (
        active_config.shopping_mode == "custom"
        and active_config.max_stores is not None
    ):
        plan, gap_items = _best_custom_constrained_result(
            unit_needs,
            candidates,
            eligible_stores,
            stores_by_id,
            active_config,
        )
        return _make_result(
            plan,
            gap_items,
            None,
            active_config.budget_cents,
            fulfillment_tradeoffs,
        )

    available_needs: list[UnitNeed] = []
    available_candidates: list[Mapping[str, PackageSelection]] = []
    gap_items: list[str] = []
    for unit_need, need_candidates in zip(
        unit_needs,
        candidates,
        strict=True,
    ):
        if need_candidates:
            available_needs.append(unit_need)
            available_candidates.append(need_candidates)
        else:
            gap_items.append(unit_need.label)

    plan = _best_multi_store_plan(
        available_needs,
        available_candidates,
        stores_by_id,
        active_config,
    )
    return _make_result(
        plan,
        tuple(gap_items),
        None,
        active_config.budget_cents,
        fulfillment_tradeoffs,
    )
