"""Deterministic BR-05 optional and donation add-on proposals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agent.aggregate import UnitNeed, aggregate_requirements
from agent.consolidate import consolidate_selected_skus
from agent.match import MatchResult, NeedMatches, match_offers
from agent.normalize import NormalizationResult
from agent.optimize import (
    OptimizationConfig,
    OptimizationResult,
    optimize_cart,
)
from agent.rules import OPTIONAL_ITEM_HEADROOM_PERCENT, PERCENT_DENOMINATOR
from data.loader import Offer, Store


@dataclass(frozen=True)
class AddOnItem:
    """One optional or donation requirement offered under BR-05."""

    requirement_id: str
    child_id: str
    raw_text: str
    requirement_type: str
    canonical_item: str
    quantity: int


@dataclass(frozen=True)
class AddOnProposal:
    """A separately priced add-on that never mutates the base cart."""

    eligible: bool
    reason: str
    items: tuple[AddOnItem, ...]
    optimization: OptimizationResult | None = None
    purchase_needs: tuple[UnitNeed, ...] = ()
    matches: MatchResult | None = None
    resulting_landed_cost_cents: int | None = None
    incremental_landed_cost_cents: int | None = None
    review_requirement_ids: tuple[str, ...] = ()
    gap_items: tuple[str, ...] = ()


def _optional_items(
    normalization: NormalizationResult,
) -> tuple[AddOnItem, ...]:
    return tuple(
        AddOnItem(
            requirement_id=requirement.source.req_id,
            child_id=requirement.source.child_id,
            raw_text=requirement.source.raw_text,
            requirement_type=requirement.source.requirement_type,
            canonical_item=requirement.canonical_item,
            quantity=requirement.quantity,
        )
        for requirement in normalization.cart_requirements
        if not requirement.is_budget_eligible
    )


def propose_addons(
    normalization: NormalizationResult,
    base_optimization: OptimizationResult,
    base_purchase_needs: Sequence[UnitNeed],
    base_matches: MatchResult,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
    *,
    student_counts_by_child: Mapping[str, int] | None = None,
) -> AddOnProposal:
    """Price optional lines only when BR-05 headroom exists (FR-09)."""

    items = _optional_items(normalization)
    if not items:
        return AddOnProposal(
            eligible=False,
            reason="No optional or donation items were found.",
            items=(),
        )
    if base_optimization.budget_cents is None:
        return AddOnProposal(
            eligible=False,
            reason="A budget is required before add-ons can be offered.",
            items=items,
        )
    within_headroom = (
        base_optimization.landed_cost * PERCENT_DENOMINATOR
        <= base_optimization.budget_cents * OPTIONAL_ITEM_HEADROOM_PERCENT
    )
    if not within_headroom:
        return AddOnProposal(
            eligible=False,
            reason=(
                "The required-item cart is above the BR-05 headroom threshold."
            ),
            items=items,
        )

    optional_ids = frozenset(item.requirement_id for item in items)
    optional_requirements = tuple(
        requirement
        for requirement in normalization.cart_requirements
        if requirement.source.req_id in optional_ids
    )
    optional_needs = aggregate_requirements(
        optional_requirements,
        student_counts_by_child=student_counts_by_child,
    )
    optional_matches = match_offers(
        optional_needs,
        offers,
        stores,
        allowed_store_ids=config.allowed_store_ids,
        store_radius_miles=config.store_radius_miles,
    )
    combined_needs = tuple(base_purchase_needs) + optional_needs
    combined_matches = MatchResult(
        needs=(
            base_matches.needs
            + optional_matches.needs
        )
    )
    preliminary = optimize_cart(
        combined_needs,
        offers,
        stores,
        config,
        candidate_skus_by_need=combined_matches.candidate_skus_by_need,
    )
    consolidation = consolidate_selected_skus(
        combined_needs,
        combined_matches,
        preliminary,
    )
    optimization = (
        optimize_cart(
            consolidation.unit_needs,
            offers,
            stores,
            config,
            candidate_skus_by_need=(
                consolidation.matches.candidate_skus_by_need
            ),
        )
        if consolidation.changed
        else preliminary
    )
    review_ids = tuple(
        requirement.source.req_id
        for requirement in normalization.review_requirements_for(
            optional_ids
        )
        if requirement.source.req_id in optional_ids
    )
    return AddOnProposal(
        eligible=True,
        reason="The base cart is at or below 90% of the budget.",
        items=items,
        optimization=optimization,
        purchase_needs=consolidation.unit_needs,
        matches=consolidation.matches,
        resulting_landed_cost_cents=optimization.landed_cost,
        incremental_landed_cost_cents=(
            optimization.landed_cost - base_optimization.landed_cost
        ),
        review_requirement_ids=review_ids,
        gap_items=optimization.gap_items,
    )
