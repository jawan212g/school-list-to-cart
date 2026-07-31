"""Deterministic, batched approval gate for the five active FR-26 conditions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from agent.aggregate import UnitNeed
from agent.decisions import DecisionLog
from agent.match import CandidateMatch, MatchResult
from agent.normalize import NormalizationResult
from agent.optimize import (
    CartLine,
    CartPlan,
    OptimizationConfig,
    OptimizationResult,
    calculate_tax,
    optimize_cart,
    per_entry_budget_overages,
)
from agent.rules import (
    DEFAULT_TAX_BASIS_POINTS,
    INTERRUPT_DESIGN_FAILURE_COUNT,
    INTERRUPT_TARGET_COUNT,
    PREFERENCE_DEPENDENT_ATTRIBUTES,
    REQUIRED_ITEM_AUTO_DROP_ALLOWED,
    SUBSTITUTION_MAJOR,
)
from agent.schema import ExtractionEnvelope
from data.loader import Offer, Store


InterruptKind = Literal[
    "budget_exceeded",
    "major_substitution",
    "brand_lock_break",
    "attribute_choice",
    "low_confidence",
]

BRAND_LOCK_REASON = "brand_lock_break"
ATTRIBUTE_REASON_PREFIX = "attribute_change:"


@dataclass(frozen=True)
class ApprovalAlternative:
    """One concrete parent choice and its exact cart-cost delta (FR-28)."""

    alternative_id: str
    label: str
    cost_delta_cents: int


@dataclass(frozen=True)
class ApprovalInterrupt:
    """One approval decision displayed in the session's single batch."""

    interrupt_id: str
    kind: InterruptKind
    message: str
    recommendation: str
    alternatives: tuple[ApprovalAlternative, ...]
    cost_impact_cents: int
    affected_lines: tuple[str, ...] = ()
    source_requirement_ids: tuple[str, ...] = ()
    sku: str | None = None
    grouped_interrupts: tuple[ApprovalInterrupt, ...] = ()


@dataclass(frozen=True)
class ApprovalBatch:
    """All current interrupts returned for one approval screen (FR-27)."""

    interrupts: tuple[ApprovalInterrupt, ...]
    target_count: int = INTERRUPT_TARGET_COUNT
    grouped_by_type: bool = False
    raw_interrupt_count: int = 0


@dataclass(frozen=True)
class GateContext:
    """Deterministic evidence required for the five active FR-26 conditions."""

    optimization: OptimizationResult
    matches: MatchResult
    normalization: NormalizationResult
    extractions: Mapping[str, ExtractionEnvelope]
    offers: Sequence[Offer]
    stores: Sequence[Store] = ()
    tax_basis_points: int = DEFAULT_TAX_BASIS_POINTS
    unit_needs: Sequence[UnitNeed] = ()
    optimization_config: OptimizationConfig | None = None
    budget_mode: Literal["combined", "per_child", "none"] = "combined"
    budget_allocations: Mapping[str, int] = field(default_factory=dict)


def _selected_lines(
    optimization: OptimizationResult,
) -> tuple[CartLine, ...]:
    if optimization.minimum_second_trip is None:
        return optimization.plan.lines
    return (
        optimization.plan.lines
        + optimization.minimum_second_trip.lines
    )


def _plans(
    optimization: OptimizationResult,
) -> tuple[CartPlan, ...]:
    return (optimization.plan,) + (
        ()
        if optimization.minimum_second_trip is None
        else (optimization.minimum_second_trip,)
    )


def _removal_cost_delta(
    context: GateContext,
    line: CartLine,
) -> int | None:
    stores_by_id = {store.store_id: store for store in context.stores}
    store = stores_by_id.get(line.store_id)
    if store is None:
        return None
    for plan in _plans(context.optimization):
        order = next(
            (
                candidate_order
                for candidate_order in plan.store_orders
                if any(
                    candidate_line.line_id == line.line_id
                    for candidate_line in candidate_order.lines
                )
            ),
            None,
        )
        if order is None:
            continue
        remaining_lines = tuple(
            candidate_line
            for candidate_line in order.lines
            if candidate_line.line_id != line.line_id
        )
        if not remaining_lines:
            return -order.landed_cost
        new_subtotal = order.item_subtotal - line.line_cost
        new_tax = (
            calculate_tax(new_subtotal, context.tax_basis_points)
            if store.tax_applies
            else 0
        )
        if order.fulfillment_method == "pickup":
            new_fee = (
                store.pickup_fee
                if new_subtotal < store.pickup_minimum
                else 0
            )
        else:
            new_fee = (
                store.delivery_fee
                if new_subtotal < store.delivery_minimum
                else 0
            )
        new_landed_cost = new_subtotal + new_tax + new_fee
        return new_landed_cost - order.landed_cost
    return None


def _decision_alternatives(
    context: GateContext,
    interrupt_id: str,
    line: CartLine,
) -> tuple[ApprovalAlternative, ...]:
    removal_delta = _removal_cost_delta(context, line)
    if removal_delta is None:
        second = ApprovalAlternative(
            alternative_id=f"{interrupt_id}-pending",
            label="Leave this line pending and do not proceed",
            cost_delta_cents=0,
        )
    else:
        second = ApprovalAlternative(
            alternative_id=f"{interrupt_id}-omit",
            label=(
                f"Parent chooses not to buy {line.canonical_item}"
            ),
            cost_delta_cents=removal_delta,
        )
    return (
        ApprovalAlternative(
            alternative_id=f"{interrupt_id}-approve",
            label="Approve the recommended product",
            cost_delta_cents=0,
        ),
        second,
    )


def _cheaper_substitution_alternative(
    context: GateContext,
    interrupt_id: str,
) -> ApprovalAlternative | None:
    if (
        context.optimization_config is None
        or not context.unit_needs
        or not context.stores
    ):
        return None
    all_candidate_skus = {
        need_matches.unit_need.source_requirement_ids: frozenset(
            candidate.offer.sku
            for candidate in need_matches.candidates
        )
        for need_matches in context.matches.needs
    }
    alternative = optimize_cart(
        context.unit_needs,
        context.offers,
        context.stores,
        context.optimization_config,
        candidate_skus_by_need=all_candidate_skus,
    )
    if (
        not alternative.is_complete
        or alternative.landed_cost >= context.optimization.landed_cost
    ):
        return None
    return ApprovalAlternative(
        alternative_id=f"{interrupt_id}-substitute",
        label="Use the lowest-cost available substitutions",
        cost_delta_cents=(
            alternative.landed_cost - context.optimization.landed_cost
        ),
    )


def _budget_interrupt(
    context: GateContext,
) -> ApprovalInterrupt | None:
    optimization = context.optimization
    entry_overages = (
        per_entry_budget_overages(
            optimization,
            context.budget_allocations,
        )
        if context.budget_mode == "per_child"
        else {}
    )
    if entry_overages:
        affected_entry_ids = frozenset(entry_overages)
        affected_lines = tuple(
            line
            for line in _selected_lines(optimization)
            if affected_entry_ids.intersection(line.allocated_to)
        )
        total_overage = sum(entry_overages.values())
        interrupt_id = "approval-budget-per-entry"
        return ApprovalInterrupt(
            interrupt_id=interrupt_id,
            kind="budget_exceeded",
            message=(
                "One or more individual budgets are exceeded by "
                f"{total_overage} cents in total."
            ),
            recommendation=(
                "Raise only the affected individual budgets to cover the "
                "current required-item plan."
            ),
            alternatives=(
                ApprovalAlternative(
                    alternative_id=f"{interrupt_id}-raise",
                    label="Raise the affected individual budgets",
                    cost_delta_cents=0,
                ),
            ),
            cost_impact_cents=total_overage,
            affected_lines=tuple(line.line_id for line in affected_lines),
            source_requirement_ids=tuple(
                dict.fromkeys(
                    source_id
                    for line in affected_lines
                    for source_id in line.source_requirement_ids
                )
            ),
        )
    if optimization.within_budget is not False:
        return None
    interrupt_id = "approval-budget"
    alternatives: list[ApprovalAlternative] = [
        ApprovalAlternative(
            alternative_id=f"{interrupt_id}-raise",
            label=(
                "Raise the budget by "
                f"{optimization.shortfall_cents} cents"
            ),
            cost_delta_cents=0,
        )
    ]
    cheaper_substitution = _cheaper_substitution_alternative(
        context,
        interrupt_id,
    )
    if cheaper_substitution is not None:
        alternatives.append(cheaper_substitution)
    removable_lines = _selected_lines(optimization)
    removal_options = tuple(
        (line, _removal_cost_delta(context, line))
        for line in removable_lines
    )
    known_removals = tuple(
        (line, delta)
        for line, delta in removal_options
        if delta is not None
    )
    if known_removals:
        line, delta = min(
            known_removals,
            key=lambda option: option[1],
        )
        alternatives.append(
            ApprovalAlternative(
                alternative_id=f"{interrupt_id}-parent-remove",
                label=(
                    f"Parent chooses to remove {line.canonical_item}"
                ),
                cost_delta_cents=delta,
            )
        )
    else:
        alternatives.append(
            ApprovalAlternative(
                alternative_id=f"{interrupt_id}-pending",
                label="Leave the complete cart pending",
                cost_delta_cents=0,
            )
        )
    return ApprovalInterrupt(
        interrupt_id=interrupt_id,
        kind="budget_exceeded",
        message=(
            "The minimum valid cart exceeds the budget by "
            f"{optimization.shortfall_cents} cents."
        ),
        recommendation=(
            "Raise the budget to the minimum total cost so every required "
            "item remains covered."
        ),
        alternatives=tuple(alternatives),
        cost_impact_cents=optimization.shortfall_cents,
    )


def _line_candidate(
    line: CartLine,
    matches: MatchResult,
) -> CandidateMatch | None:
    return matches.candidate(line.source_requirement_ids, line.sku)


def _line_interrupts(
    context: GateContext,
) -> list[ApprovalInterrupt]:
    interrupts: list[ApprovalInterrupt] = []
    for line in _selected_lines(context.optimization):
        candidate = _line_candidate(line, context.matches)
        if candidate is not None:
            reasons = candidate.substitution_reasons
            has_brand_break = BRAND_LOCK_REASON in reasons
            attribute_reasons = tuple(
                reason
                for reason in reasons
                if (
                    reason.startswith(ATTRIBUTE_REASON_PREFIX)
                    and reason.removeprefix(ATTRIBUTE_REASON_PREFIX)
                    in PREFERENCE_DEPENDENT_ATTRIBUTES
                )
            )
            if has_brand_break:
                interrupt_id = f"approval-brand-{line.sku}"
                interrupts.append(
                    ApprovalInterrupt(
                        interrupt_id=interrupt_id,
                        kind="brand_lock_break",
                        message=(
                            f"{line.sku} appears to break the required brand "
                            "lock."
                        ),
                        recommendation=(
                            "Keep this pending unless the parent explicitly "
                            "allows the different brand."
                        ),
                        alternatives=_decision_alternatives(
                            context,
                            interrupt_id,
                            line,
                        ),
                        cost_impact_cents=line.line_cost,
                        affected_lines=(line.line_id,),
                        source_requirement_ids=line.source_requirement_ids,
                        sku=line.sku,
                    )
                )
            elif attribute_reasons:
                attributes = ", ".join(
                    reason.removeprefix(ATTRIBUTE_REASON_PREFIX)
                    for reason in attribute_reasons
                )
                interrupt_id = f"approval-attribute-{line.sku}"
                interrupts.append(
                    ApprovalInterrupt(
                        interrupt_id=interrupt_id,
                        kind="attribute_choice",
                        message=(
                            f"{line.sku} appears to change a specified "
                            "preference: "
                            f"{attributes}."
                        ),
                        recommendation=(
                            "Use the exact requested attribute when available; "
                            "otherwise let the parent choose."
                        ),
                        alternatives=_decision_alternatives(
                            context,
                            interrupt_id,
                            line,
                        ),
                        cost_impact_cents=line.line_cost,
                        affected_lines=(line.line_id,),
                        source_requirement_ids=line.source_requirement_ids,
                        sku=line.sku,
                    )
                )
            elif candidate.substitution_type == SUBSTITUTION_MAJOR:
                interrupt_id = f"approval-substitution-{line.sku}"
                interrupts.append(
                    ApprovalInterrupt(
                        interrupt_id=interrupt_id,
                        kind="major_substitution",
                        message=(
                            f"{line.sku} looks like a major substitution: "
                            f"{', '.join(reasons)}."
                        ),
                        recommendation=(
                            "Approve only if the listed product differences "
                            "are acceptable."
                        ),
                        alternatives=_decision_alternatives(
                            context,
                            interrupt_id,
                            line,
                        ),
                        cost_impact_cents=line.line_cost,
                        affected_lines=(line.line_id,),
                        source_requirement_ids=line.source_requirement_ids,
                        sku=line.sku,
                    )
                )

    return interrupts


def _need_interrupts(
    context: GateContext,
) -> list[ApprovalInterrupt]:
    interrupts: list[ApprovalInterrupt] = []
    for need_matches in context.matches.needs:
        need = need_matches.unit_need
        if need_matches.requires_confidence_review:
            interrupt_id = (
                "approval-low-confidence-match-"
                + "-".join(need.source_requirement_ids)
            )
            interrupts.append(
                ApprovalInterrupt(
                    interrupt_id=interrupt_id,
                    kind="low_confidence",
                    message=(
                        f"All catalog matches for {need.label} are below "
                        "the confidence floor."
                    ),
                    recommendation=(
                        "Review the candidate match before purchasing it."
                    ),
                    alternatives=(
                        ApprovalAlternative(
                            alternative_id=f"{interrupt_id}-review",
                            label="Review the blocked catalog match",
                            cost_delta_cents=0,
                        ),
                        ApprovalAlternative(
                            alternative_id=f"{interrupt_id}-correct",
                            label="Correct the requirement and rematch",
                            cost_delta_cents=0,
                        ),
                    ),
                    cost_impact_cents=0,
                    source_requirement_ids=need.source_requirement_ids,
                )
            )
            continue
    return interrupts


def _deduplicate(
    interrupts: Sequence[ApprovalInterrupt],
) -> list[ApprovalInterrupt]:
    unique: dict[
        tuple[InterruptKind, str | None, str],
        ApprovalInterrupt,
    ] = {}
    for interrupt in interrupts:
        key = (interrupt.kind, interrupt.sku, interrupt.message)
        existing = unique.get(key)
        if existing is None:
            unique[key] = interrupt
            continue
        unique[key] = replace(
            existing,
            affected_lines=tuple(
                dict.fromkeys(
                    existing.affected_lines + interrupt.affected_lines
                )
            ),
            source_requirement_ids=tuple(
                dict.fromkeys(
                    existing.source_requirement_ids
                    + interrupt.source_requirement_ids
                )
            ),
            cost_impact_cents=max(
                existing.cost_impact_cents,
                interrupt.cost_impact_cents,
            ),
        )
    return list(unique.values())


def _group_by_type(
    interrupts: Sequence[ApprovalInterrupt],
) -> list[ApprovalInterrupt]:
    by_kind: dict[InterruptKind, list[ApprovalInterrupt]] = defaultdict(list)
    for interrupt in interrupts:
        by_kind[interrupt.kind].append(interrupt)
    grouped: list[ApprovalInterrupt] = []
    for kind, same_type in by_kind.items():
        if len(same_type) == 1:
            grouped.append(same_type[0])
            continue
        highest = max(
            same_type,
            key=lambda interrupt: interrupt.cost_impact_cents,
        )
        grouped.append(
            replace(
                highest,
                interrupt_id=f"approval-group-{kind}",
                message=(
                    f"{len(same_type)} {kind.replace('_', ' ')} decisions "
                    "need review."
                ),
                recommendation=(
                    "Review the highest-cost decisions in this group first."
                ),
                alternatives=(
                    ApprovalAlternative(
                        alternative_id=f"approval-group-{kind}-review",
                        label="Review every decision in this group",
                        cost_delta_cents=0,
                    ),
                    ApprovalAlternative(
                        alternative_id=f"approval-group-{kind}-pending",
                        label="Leave every decision in this group pending",
                        cost_delta_cents=0,
                    ),
                ),
                affected_lines=tuple(
                    dict.fromkeys(
                        line_id
                        for interrupt in same_type
                        for line_id in interrupt.affected_lines
                    )
                ),
                source_requirement_ids=tuple(
                    dict.fromkeys(
                        requirement_id
                        for interrupt in same_type
                        for requirement_id
                        in interrupt.source_requirement_ids
                    )
                ),
                sku=None,
                cost_impact_cents=sum(
                    interrupt.cost_impact_cents
                    for interrupt in same_type
                ),
                grouped_interrupts=tuple(
                    sorted(
                        same_type,
                        key=lambda interrupt: (
                            -interrupt.cost_impact_cents,
                            interrupt.interrupt_id,
                        ),
                    )
                ),
            )
        )
    return grouped


def evaluate_gate(
    context: GateContext,
    *,
    decision_log: DecisionLog | None = None,
) -> ApprovalBatch:
    """Return all five active FR-26 conditions in one batch (FR-27–FR-29)."""

    if REQUIRED_ITEM_AUTO_DROP_ALLOWED:
        raise RuntimeError("BR-04 must prohibit automatic required-item removal")

    raw: list[ApprovalInterrupt] = []
    budget = _budget_interrupt(context)
    if budget is not None:
        raw.append(budget)
    raw.extend(_line_interrupts(context))
    raw.extend(_need_interrupts(context))
    raw = _deduplicate(raw)
    raw_count = len(raw)
    grouped_by_type = raw_count > INTERRUPT_DESIGN_FAILURE_COUNT
    if grouped_by_type:
        raw = _group_by_type(raw)
    ordered = tuple(
        sorted(
            raw,
            key=lambda interrupt: (
                interrupt.kind != "budget_exceeded",
                -interrupt.cost_impact_cents,
                interrupt.kind,
                interrupt.interrupt_id,
            ),
        )
    )
    if decision_log is not None:
        for interrupt in ordered:
            decision_log.record(
                "approval_request",
                (
                    f"{interrupt.message} Recommendation: "
                    f"{interrupt.recommendation}"
                ),
                actor="agent",
                affected_lines=interrupt.affected_lines,
            )
    return ApprovalBatch(
        interrupts=ordered,
        grouped_by_type=grouped_by_type,
        raw_interrupt_count=raw_count,
    )
