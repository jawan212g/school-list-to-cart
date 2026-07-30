"""Pure catalog-choice support for the approval presentation layer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agent.aggregate import UnitNeed
from agent.gate import ApprovalInterrupt
from agent.match import MatchResult
from agent.optimize import (
    CartLine,
    CartPlan,
    OptimizationConfig,
    OptimizationResult,
    optimize_cart,
)
from agent.rules import (
    OVERAGE_ABSOLUTE_UNITS,
    OVERAGE_PERCENT,
    PERCENT_DENOMINATOR,
)
from data.loader import Offer, Store


@dataclass(frozen=True)
class CatalogApprovalChoice:
    """One stocked catalog choice with an exact total-cost comparison."""

    sku: str
    store_id: str
    cost_delta_cents: int
    is_current: bool
    item_subtotal_delta_cents: int
    tax_delta_cents: int
    fulfillment_fee_delta_cents: int


@dataclass(frozen=True)
class RemovalCostContext:
    """Facts explaining why required-item savings differ from its line cost."""

    line_cost_cents: int
    store_id: str
    fulfillment_method: str
    tax_changes: bool
    fee_returns_cents: int
    fee_threshold_cents: int | None


@dataclass(frozen=True)
class RequiredItemRemovalChoice:
    """One parent-authorized required-item omission priced as a full cart."""

    canonical_item: str
    source_requirement_ids: tuple[str, ...]
    affected_line_ids: tuple[str, ...]
    allocated_to: Mapping[str, int]
    cost_delta_cents: int
    item_subtotal_delta_cents: int
    tax_delta_cents: int
    fulfillment_fee_delta_cents: int


def _plans(
    optimization: OptimizationResult,
) -> tuple[CartPlan, ...]:
    return (optimization.plan,) + (
        ()
        if optimization.minimum_second_trip is None
        else (optimization.minimum_second_trip,)
    )


def _selected_lines(
    optimization: OptimizationResult,
) -> tuple[CartLine, ...]:
    return tuple(
        line
        for plan in _plans(optimization)
        for line in plan.lines
    )


def _cost_components(
    optimization: OptimizationResult,
) -> tuple[int, int, int]:
    plans = _plans(optimization)
    return (
        sum(
            plan.item_subtotal for plan in plans
        ),
        sum(plan.tax for plan in plans),
        sum(
            plan.fulfillment_fees for plan in plans
        ),
    )


def _line_for_interrupt(
    interrupt: ApprovalInterrupt,
    optimization: OptimizationResult,
) -> CartLine | None:
    affected = frozenset(interrupt.affected_lines)
    return next(
        (
            line
            for line in _selected_lines(optimization)
            if line.line_id in affected
        ),
        None,
    )


def _offer_within_overage_ceiling(
    unit_need: UnitNeed,
    offer: Offer,
) -> bool:
    """Apply BR-06 to one forced-SKU approval alternative."""

    packs = (
        unit_need.quantity + offer.pack_size - 1
    ) // offer.pack_size
    purchased_units = packs * offer.pack_size
    relative_allowance = (
        unit_need.quantity * OVERAGE_PERCENT // PERCENT_DENOMINATOR
    )
    allowed_overage = max(
        relative_allowance,
        OVERAGE_ABSOLUTE_UNITS,
    )
    return purchased_units <= unit_need.quantity + allowed_overage


def build_catalog_approval_choices(
    interrupt: ApprovalInterrupt,
    optimization: OptimizationResult,
    matches: MatchResult,
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> tuple[CatalogApprovalChoice, ...]:
    """Price every stocked matched product for one line decision (FR-28)."""

    line = _line_for_interrupt(interrupt, optimization)
    if line is None:
        return ()
    need_matches = next(
        (
            item
            for item in matches.needs
            if item.unit_need.source_requirement_ids
            == line.source_requirement_ids
        ),
        None,
    )
    if need_matches is None:
        return ()
    compliant_skus = frozenset(
        candidate.offer.sku
        for candidate in need_matches.candidates
        if _offer_within_overage_ceiling(
            need_matches.unit_need,
            candidate.offer,
        )
    )

    baseline_item, baseline_tax, baseline_fees = _cost_components(
        optimization
    )
    baseline_candidates: Mapping[
        tuple[str, ...],
        frozenset[str],
    ] = matches.candidate_skus_by_need
    choices: list[CatalogApprovalChoice] = []
    for candidate in need_matches.candidates:
        offer = candidate.offer
        if compliant_skus and offer.sku not in compliant_skus:
            continue
        is_current = offer.sku == line.sku
        if is_current:
            alternative = optimization
        else:
            forced_candidates = dict(baseline_candidates)
            forced_candidates[line.source_requirement_ids] = frozenset(
                {offer.sku}
            )
            alternative = optimize_cart(
                unit_needs,
                offers,
                stores,
                config,
                candidate_skus_by_need=forced_candidates,
            )
            if not alternative.is_complete:
                continue
        item_subtotal, tax, fees = _cost_components(alternative)
        choices.append(
            CatalogApprovalChoice(
                sku=offer.sku,
                store_id=offer.store_id,
                cost_delta_cents=(
                    alternative.landed_cost - optimization.landed_cost
                ),
                is_current=is_current,
                item_subtotal_delta_cents=(
                    item_subtotal - baseline_item
                ),
                tax_delta_cents=tax - baseline_tax,
                fulfillment_fee_delta_cents=fees - baseline_fees,
            )
        )
    return tuple(
        sorted(
            choices,
            key=lambda choice: (
                not choice.is_current,
                choice.cost_delta_cents,
                choice.sku,
            ),
        )
    )


def build_required_item_removal_choices(
    optimization: OptimizationResult,
    matches: MatchResult,
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> tuple[RequiredItemRemovalChoice, ...]:
    """Price each parent-authorized required-item omission (BR-04, FR-28)."""

    baseline_item, baseline_tax, baseline_fees = _cost_components(
        optimization
    )
    lines_by_need: dict[tuple[str, ...], list[CartLine]] = {}
    for line in _selected_lines(optimization):
        lines_by_need.setdefault(
            line.source_requirement_ids,
            [],
        ).append(line)

    choices: list[RequiredItemRemovalChoice] = []
    for need in unit_needs:
        affected_lines = tuple(
            lines_by_need.get(need.source_requirement_ids, ())
        )
        if not affected_lines:
            continue
        remaining_needs = tuple(
            candidate
            for candidate in unit_needs
            if (
                candidate.source_requirement_ids
                != need.source_requirement_ids
            )
        )
        alternative = optimize_cart(
            remaining_needs,
            offers,
            stores,
            config,
            candidate_skus_by_need=matches.candidate_skus_by_need,
        )
        item_subtotal, tax, fees = _cost_components(alternative)
        choices.append(
            RequiredItemRemovalChoice(
                canonical_item=need.canonical_item,
                source_requirement_ids=need.source_requirement_ids,
                affected_line_ids=tuple(
                    line.line_id for line in affected_lines
                ),
                allocated_to=need.allocated_to,
                cost_delta_cents=(
                    alternative.landed_cost - optimization.landed_cost
                ),
                item_subtotal_delta_cents=(
                    item_subtotal - baseline_item
                ),
                tax_delta_cents=tax - baseline_tax,
                fulfillment_fee_delta_cents=fees - baseline_fees,
            )
        )
    return tuple(
        sorted(
            choices,
            key=lambda choice: (
                choice.cost_delta_cents,
                choice.canonical_item,
                choice.source_requirement_ids,
            ),
        )
    )


def removal_cost_context(
    interrupt: ApprovalInterrupt,
    optimization: OptimizationResult,
    stores: Sequence[Store],
) -> RemovalCostContext | None:
    """Describe tax and threshold effects for a gate-provided removal delta."""

    line = _line_for_interrupt(interrupt, optimization)
    if line is None:
        return None
    stores_by_id = {store.store_id: store for store in stores}
    store = stores_by_id.get(line.store_id)
    if store is None:
        return None
    order = next(
        (
            order
            for plan in _plans(optimization)
            for order in plan.store_orders
            if any(
                candidate.line_id == line.line_id
                for candidate in order.lines
            )
        ),
        None,
    )
    if order is None:
        return None

    remaining_lines = tuple(
        candidate
        for candidate in order.lines
        if candidate.line_id != line.line_id
    )
    fee = (
        store.pickup_fee
        if order.fulfillment_method == "pickup"
        else store.delivery_fee
    )
    threshold = (
        store.pickup_minimum
        if order.fulfillment_method == "pickup"
        else store.delivery_minimum
    )
    remaining_subtotal = order.item_subtotal - line.line_cost
    fee_returns = (
        fee
        if (
            remaining_lines
            and order.fulfillment_fee == 0
            and fee > 0
            and remaining_subtotal < threshold
        )
        else 0
    )
    return RemovalCostContext(
        line_cost_cents=line.line_cost,
        store_id=line.store_id,
        fulfillment_method=order.fulfillment_method,
        tax_changes=store.tax_applies,
        fee_returns_cents=fee_returns,
        fee_threshold_cents=threshold if fee_returns else None,
    )
