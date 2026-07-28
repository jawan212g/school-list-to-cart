"""Deterministic BR-05 optional and donation add-on proposals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agent.aggregate import UnitNeed, aggregate_requirements
from agent.match import MatchResult, match_offers
from agent.normalize import NormalizationResult
from agent.optimize import (
    OptimizationConfig,
    OptimizationResult,
    optimize_cart,
)
from agent.rules import (
    OPTIONAL_ITEM_HEADROOM_BYPASSED_WITHOUT_BUDGET,
    OPTIONAL_ITEM_HEADROOM_PERCENT,
    PERCENT_DENOMINATOR,
)
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
    optional_needs: tuple[UnitNeed, ...] = ()
    optional_matches: MatchResult | None = None
    resulting_landed_cost_cents: int | None = None
    incremental_landed_cost_cents: int | None = None
    review_requirement_ids: tuple[str, ...] = ()
    gap_items: tuple[str, ...] = ()


@dataclass(frozen=True)
class AddOnSelectionEvaluation:
    """Exact result for the currently selected BR-05 add-on requirements."""

    selected_requirement_ids: tuple[str, ...]
    optimization: OptimizationResult
    purchase_needs: tuple[UnitNeed, ...]
    matches: MatchResult
    resulting_landed_cost_cents: int
    incremental_landed_cost_cents: int
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


def _separate_optional_needs(
    normalization: NormalizationResult,
    optional_ids: frozenset[str],
    student_counts_by_child: Mapping[str, int] | None,
) -> tuple[UnitNeed, ...]:
    """Keep each classroom's donation need separate from every other list."""

    needs: list[UnitNeed] = []
    for requirement in normalization.cart_requirements:
        if requirement.source.req_id not in optional_ids:
            continue
        needs.extend(
            aggregate_requirements(
                (requirement,),
                student_counts_by_child=student_counts_by_child,
            )
        )
    return tuple(needs)


def evaluate_addon_selection(
    proposal: AddOnProposal,
    selected_requirement_ids: Sequence[str],
    base_optimization: OptimizationResult,
    base_purchase_needs: Sequence[UnitNeed],
    base_matches: MatchResult,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
    *,
    base_candidate_skus_by_need: (
        Mapping[tuple[str, ...], frozenset[str]] | None
    ) = None,
) -> AddOnSelectionEvaluation:
    """Re-optimize selected add-ons from cached needs and matches (BR-05)."""

    valid_ids = frozenset(item.requirement_id for item in proposal.items)
    selected = tuple(
        requirement_id
        for requirement_id in dict.fromkeys(selected_requirement_ids)
        if requirement_id in valid_ids
    )
    selected_set = frozenset(selected)
    optional_needs = tuple(
        need
        for need in proposal.optional_needs
        if selected_set.intersection(need.source_requirement_ids)
    )
    optional_matches_source = proposal.optional_matches or MatchResult(needs=())
    optional_need_keys = frozenset(
        need.source_requirement_ids for need in optional_needs
    )
    selected_optional_matches = tuple(
        need_matches
        for need_matches in optional_matches_source.needs
        if need_matches.unit_need.source_requirement_ids in optional_need_keys
    )
    combined_needs = tuple(base_purchase_needs) + optional_needs
    combined_matches = MatchResult(
        needs=base_matches.needs + selected_optional_matches
    )
    candidate_skus = dict(
        base_candidate_skus_by_need
        or base_matches.candidate_skus_by_need
    )
    candidate_skus.update(
        MatchResult(
            needs=selected_optional_matches
        ).candidate_skus_by_need
    )
    optimization = (
        base_optimization
        if not optional_needs
        else optimize_cart(
            combined_needs,
            offers,
            stores,
            config,
            candidate_skus_by_need=candidate_skus,
        )
    )
    review_ids = tuple(
        requirement_id
        for requirement_id in proposal.review_requirement_ids
        if requirement_id in selected_set
    )
    return AddOnSelectionEvaluation(
        selected_requirement_ids=selected,
        optimization=optimization,
        purchase_needs=combined_needs,
        matches=combined_matches,
        resulting_landed_cost_cents=optimization.landed_cost,
        incremental_landed_cost_cents=(
            optimization.landed_cost - base_optimization.landed_cost
        ),
        review_requirement_ids=review_ids,
        gap_items=optimization.gap_items,
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
    """Price optional lines under the applicable BR-05 rule (FR-09)."""

    items = _optional_items(normalization)
    if not items:
        return AddOnProposal(
            eligible=False,
            reason="No optional or donation items were found.",
            items=(),
        )
    if not base_optimization.is_complete:
        return AddOnProposal(
            eligible=False,
            reason=(
                "Optional items stay hidden until every required item is "
                "covered."
            ),
            items=items,
        )
    if base_optimization.budget_cents is None:
        if not OPTIONAL_ITEM_HEADROOM_BYPASSED_WITHOUT_BUDGET:
            raise RuntimeError(
                "BR-05 must define add-on behavior without a budget"
            )
        eligibility_reason = (
            "No budget constraint was set, so the BR-05 headroom threshold "
            "does not apply."
        )
    else:
        within_headroom = (
            base_optimization.landed_cost * PERCENT_DENOMINATOR
            <= (
                base_optimization.budget_cents
                * OPTIONAL_ITEM_HEADROOM_PERCENT
            )
        )
        if not within_headroom:
            return AddOnProposal(
                eligible=False,
                reason=(
                    "The required-item cart is above the BR-05 headroom "
                    "threshold."
                ),
                items=items,
            )
        eligibility_reason = "The base cart is at or below 90% of the budget."

    optional_ids = frozenset(item.requirement_id for item in items)
    optional_needs = _separate_optional_needs(
        normalization,
        optional_ids,
        student_counts_by_child,
    )
    optional_matches = match_offers(
        optional_needs,
        offers,
        stores,
        allowed_store_ids=config.allowed_store_ids,
        store_radius_miles=config.store_radius_miles,
        fulfillment_preference=config.fulfillment_preference,
    )
    combined_needs = tuple(base_purchase_needs) + optional_needs
    combined_matches = MatchResult(
        needs=(
            base_matches.needs
            + optional_matches.needs
        )
    )
    optimization = optimize_cart(
        combined_needs,
        offers,
        stores,
        config,
        candidate_skus_by_need=combined_matches.candidate_skus_by_need,
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
        reason=eligibility_reason,
        items=items,
        optimization=optimization,
        purchase_needs=combined_needs,
        matches=combined_matches,
        optional_needs=optional_needs,
        optional_matches=optional_matches,
        resulting_landed_cost_cents=optimization.landed_cost,
        incremental_landed_cost_cents=(
            optimization.landed_cost - base_optimization.landed_cost
        ),
        review_requirement_ids=review_ids,
        gap_items=optimization.gap_items,
    )
