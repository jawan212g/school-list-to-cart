"""Deterministic whole-plan choices for an over-budget required cart."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import combinations

from agent.aggregate import UnitNeed
from agent.approval_options import (
    build_catalog_approval_choices,
    build_required_item_removal_choices,
)
from agent.gate import ApprovalInterrupt
from agent.match import MatchResult
from agent.optimize import (
    CartLine,
    OptimizationConfig,
    OptimizationResult,
    optimize_cart,
)
from agent.rules import (
    BUDGET_ALTERNATIVE_PLAN_COUNT,
    BUDGET_PLAN_CANDIDATE_LIMIT,
)
from data.loader import Offer, Store


@dataclass(frozen=True)
class BudgetAction:
    """One pre-priced substitution or parent-authorized omission (BR-04)."""

    action_id: str
    kind: str
    canonical_item: str
    source_requirement_ids: tuple[str, ...]
    affected_line_ids: tuple[str, ...]
    allocated_to: Mapping[str, int]
    landed_delta_cents: int
    item_subtotal_delta_cents: int
    tax_delta_cents: int
    fulfillment_fee_delta_cents: int
    replacement_sku: str | None = None

    @property
    def landed_saving_cents(self) -> int:
        """Return this action's positive, precomputed landed saving."""

        return max(-self.landed_delta_cents, 0)


@dataclass(frozen=True)
class BudgetPlan:
    """One whole strategy whose exact result has been validated."""

    plan_id: str
    label: str
    description: str
    action_ids: tuple[str, ...]
    resulting_landed_cost_cents: int
    unmet_action_ids: tuple[str, ...]
    preserves: str


@dataclass(frozen=True)
class BudgetSelectionEvaluation:
    """Exact deterministic cart and budget status for checkbox choices."""

    selected_action_ids: tuple[str, ...]
    optimization: OptimizationResult
    budget_variance_cents: int
    unmet_item_count: int
    reaches_budget: bool

    @property
    def landed_cost_cents(self) -> int:
        """Return the exact figure rendered by the approval screen."""

        return self.optimization.landed_cost


@dataclass(frozen=True)
class BudgetAnalysis:
    """All deterministic evidence needed by the two-tier budget interrupt."""

    baseline_landed_cost_cents: int
    budget_cents: int
    original_shortfall_cents: int
    substitution_actions: tuple[BudgetAction, ...]
    omission_actions: tuple[BudgetAction, ...]
    preferred_substitution_action_ids: tuple[str, ...]
    substitution_only_landed_cost_cents: int
    substitutions_reach_budget: bool
    recommended_plan: BudgetPlan | None
    alternative_plans: tuple[BudgetPlan, ...]

    @property
    def actions(self) -> tuple[BudgetAction, ...]:
        """Return every checkbox action in stable display order."""

        return self.substitution_actions + self.omission_actions

    @property
    def actions_by_id(self) -> Mapping[str, BudgetAction]:
        """Index precomputed actions by their stable IDs."""

        return {action.action_id: action for action in self.actions}


def _selected_lines(
    optimization: OptimizationResult,
) -> tuple[CartLine, ...]:
    second = (
        ()
        if optimization.minimum_second_trip is None
        else optimization.minimum_second_trip.lines
    )
    return optimization.plan.lines + second


def _action_key(prefix: str, source_ids: tuple[str, ...], suffix: str) -> str:
    encoded_source = "--".join(source_ids)
    return f"budget-{prefix}-{encoded_source}-{suffix}"


def apply_budget_actions(
    analysis: BudgetAnalysis | None,
    selected_action_ids: Sequence[str],
    optimization: OptimizationResult,
    matches: MatchResult,
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> OptimizationResult:
    """Apply a parent's multi-select budget choices exactly once (BR-04)."""

    if analysis is None or not selected_action_ids:
        return optimization
    actions_by_id = analysis.actions_by_id
    actions = tuple(
        actions_by_id[action_id]
        for action_id in dict.fromkeys(selected_action_ids)
        if action_id in actions_by_id
    )
    omitted_sources = {
        action.source_requirement_ids
        for action in actions
        if action.kind == "omit"
    }
    forced_skus: dict[tuple[str, ...], frozenset[str]] = {}
    for action in actions:
        if action.kind != "substitute" or action.replacement_sku is None:
            continue
        if action.source_requirement_ids in forced_skus:
            raise ValueError(
                "Select only one cheaper substitution for each required line"
            )
        forced_skus[action.source_requirement_ids] = frozenset(
            {action.replacement_sku}
        )

    remaining_needs = tuple(
        need
        for need in unit_needs
        if need.source_requirement_ids not in omitted_sources
    )
    candidate_skus = dict(matches.candidate_skus_by_need)
    candidate_skus.update(forced_skus)
    return optimize_cart(
        remaining_needs,
        offers,
        stores,
        config,
        candidate_skus_by_need=candidate_skus,
    )


def evaluate_budget_actions(
    analysis: BudgetAnalysis,
    selected_action_ids: Sequence[str],
    optimization: OptimizationResult,
    matches: MatchResult,
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> BudgetSelectionEvaluation:
    """Re-optimize cached candidates for an exact live checkbox total."""

    actions_by_id = analysis.actions_by_id
    selected = tuple(
        action_id
        for action_id in dict.fromkeys(selected_action_ids)
        if action_id in actions_by_id
    )
    selected_actions = tuple(actions_by_id[action_id] for action_id in selected)
    exact = apply_budget_actions(
        analysis,
        selected,
        optimization,
        matches,
        unit_needs,
        offers,
        stores,
        config,
    )
    variance = analysis.budget_cents - exact.landed_cost
    return BudgetSelectionEvaluation(
        selected_action_ids=selected,
        optimization=exact,
        budget_variance_cents=variance,
        unmet_item_count=sum(
            action.kind == "omit" for action in selected_actions
        ),
        reaches_budget=variance >= 0,
    )


def _plan_from_actions(
    *,
    plan_id: str,
    label: str,
    description: str,
    preserves: str,
    action_ids: tuple[str, ...],
    analysis_stub: BudgetAnalysis,
    optimization: OptimizationResult,
    matches: MatchResult,
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> BudgetPlan | None:
    exact = apply_budget_actions(
        analysis_stub,
        action_ids,
        optimization,
        matches,
        unit_needs,
        offers,
        stores,
        config,
    )
    if exact.budget_cents is not None and exact.landed_cost > exact.budget_cents:
        return None
    actions_by_id = analysis_stub.actions_by_id
    unmet = tuple(
        action_id
        for action_id in action_ids
        if actions_by_id[action_id].kind == "omit"
    )
    return BudgetPlan(
        plan_id=plan_id,
        label=label,
        description=description,
        action_ids=action_ids,
        resulting_landed_cost_cents=exact.landed_cost,
        unmet_action_ids=unmet,
        preserves=preserves,
    )


def _omission_rank(action: BudgetAction) -> tuple[object, ...]:
    """Prefer lower-impact items after minimizing the number left unmet."""

    return (
        len(action.allocated_to),
        sum(action.allocated_to.values()),
        action.canonical_item,
        action.source_requirement_ids,
    )


def build_budget_analysis(
    optimization: OptimizationResult,
    matches: MatchResult,
    unit_needs: Sequence[UnitNeed],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
) -> BudgetAnalysis | None:
    """Build whole strategies and checkbox deltas deterministically (BR-04)."""

    budget_cents = optimization.budget_cents
    if budget_cents is None or optimization.landed_cost <= budget_cents:
        return None

    lines_by_source: dict[tuple[str, ...], list[CartLine]] = {}
    for line in _selected_lines(optimization):
        lines_by_source.setdefault(line.source_requirement_ids, []).append(line)

    removal_choices = build_required_item_removal_choices(
        optimization,
        matches,
        unit_needs,
        offers,
        stores,
        config,
    )
    omission_actions = tuple(
        BudgetAction(
            action_id=_action_key(
                "omit",
                choice.source_requirement_ids,
                choice.canonical_item,
            ),
            kind="omit",
            canonical_item=choice.canonical_item,
            source_requirement_ids=choice.source_requirement_ids,
            affected_line_ids=choice.affected_line_ids,
            allocated_to=choice.allocated_to,
            landed_delta_cents=choice.cost_delta_cents,
            item_subtotal_delta_cents=choice.item_subtotal_delta_cents,
            tax_delta_cents=choice.tax_delta_cents,
            fulfillment_fee_delta_cents=choice.fulfillment_fee_delta_cents,
        )
        for choice in removal_choices
        if choice.cost_delta_cents < 0
    )

    substitution_actions_list: list[BudgetAction] = []
    for need in unit_needs:
        lines = tuple(lines_by_source.get(need.source_requirement_ids, ()))
        if not lines:
            continue
        interrupt = ApprovalInterrupt(
            interrupt_id="budget-catalog-evidence",
            kind="budget_exceeded",
            message="Budget catalog evidence",
            recommendation="Use a cheaper stocked equivalent when available.",
            alternatives=(),
            cost_impact_cents=optimization.shortfall_cents,
            affected_lines=tuple(line.line_id for line in lines),
            source_requirement_ids=need.source_requirement_ids,
            sku=lines[0].sku,
        )
        for choice in build_catalog_approval_choices(
            interrupt,
            optimization,
            matches,
            unit_needs,
            offers,
            stores,
            config,
        ):
            if choice.is_current or choice.cost_delta_cents >= 0:
                continue
            substitution_actions_list.append(
                BudgetAction(
                    action_id=_action_key(
                        "substitute",
                        need.source_requirement_ids,
                        choice.sku,
                    ),
                    kind="substitute",
                    canonical_item=need.canonical_item,
                    source_requirement_ids=need.source_requirement_ids,
                    affected_line_ids=tuple(
                        line.line_id for line in lines
                    ),
                    allocated_to=need.allocated_to,
                    landed_delta_cents=choice.cost_delta_cents,
                    item_subtotal_delta_cents=(
                        choice.item_subtotal_delta_cents
                    ),
                    tax_delta_cents=choice.tax_delta_cents,
                    fulfillment_fee_delta_cents=(
                        choice.fulfillment_fee_delta_cents
                    ),
                    replacement_sku=choice.sku,
                )
            )
    substitution_actions = tuple(
        sorted(
            substitution_actions_list,
            key=lambda action: (
                action.source_requirement_ids,
                action.landed_delta_cents,
                action.replacement_sku or "",
            ),
        )
    )
    preferred_substitutions = tuple(
        min(
            actions,
            key=lambda action: (
                action.landed_delta_cents,
                action.replacement_sku or "",
            ),
        ).action_id
        for source_ids in dict.fromkeys(
            action.source_requirement_ids
            for action in substitution_actions
        )
        for actions in [
            tuple(
                action
                for action in substitution_actions
                if action.source_requirement_ids == source_ids
            )
        ]
    )

    stub = BudgetAnalysis(
        baseline_landed_cost_cents=optimization.landed_cost,
        budget_cents=budget_cents,
        original_shortfall_cents=optimization.shortfall_cents,
        substitution_actions=substitution_actions,
        omission_actions=omission_actions,
        preferred_substitution_action_ids=preferred_substitutions,
        substitution_only_landed_cost_cents=optimization.landed_cost,
        substitutions_reach_budget=False,
        recommended_plan=None,
        alternative_plans=(),
    )
    substitution_result = apply_budget_actions(
        stub,
        preferred_substitutions,
        optimization,
        matches,
        unit_needs,
        offers,
        stores,
        config,
    )
    substitutions_reach = substitution_result.landed_cost <= budget_cents
    if substitutions_reach:
        return replace(
            stub,
            substitution_only_landed_cost_cents=(
                substitution_result.landed_cost
            ),
            substitutions_reach_budget=True,
        )

    feasible: list[BudgetPlan] = []
    ranked_omissions = tuple(sorted(omission_actions, key=_omission_rank))
    for omission_count in range(1, len(ranked_omissions) + 1):
        candidates = sorted(
            combinations(ranked_omissions, omission_count),
            key=lambda bundle: (
                -sum(action.landed_saving_cents for action in bundle),
                tuple(_omission_rank(action) for action in bundle),
            ),
        )[:BUDGET_PLAN_CANDIDATE_LIMIT]
        for bundle in candidates:
            action_ids = preferred_substitutions + tuple(
                action.action_id for action in bundle
            )
            plan = _plan_from_actions(
                plan_id=f"budget-plan-{len(feasible) + 1}",
                label="Meet the entered budget",
                description=(
                    "Apply every cheaper substitution, then source the fewest "
                    "required items separately."
                ),
                preserves="the greatest number of required lines",
                action_ids=action_ids,
                analysis_stub=stub,
                optimization=optimization,
                matches=matches,
                unit_needs=unit_needs,
                offers=offers,
                stores=stores,
                config=config,
            )
            if plan is not None:
                feasible.append(plan)
        if feasible:
            break

    if not feasible:
        return replace(
            stub,
            substitution_only_landed_cost_cents=(
                substitution_result.landed_cost
            ),
        )

    actions_by_id = stub.actions_by_id
    feasible.sort(
        key=lambda plan: (
            len(plan.unmet_action_ids),
            sum(
                len(actions_by_id[action_id].allocated_to)
                for action_id in plan.unmet_action_ids
            ),
            budget_cents - plan.resulting_landed_cost_cents,
            plan.unmet_action_ids,
        )
    )
    recommended = feasible[0]
    alternatives = list(feasible[1 : 1 + BUDGET_ALTERNATIVE_PLAN_COUNT])

    if len(alternatives) < BUDGET_ALTERNATIVE_PLAN_COUNT:
        recommended_omissions = frozenset(recommended.unmet_action_ids)
        protected = max(
            (
                actions_by_id[action_id]
                for action_id in recommended.unmet_action_ids
            ),
            key=lambda action: (
                action.landed_saving_cents,
                action.action_id,
            ),
        )
        running = list(preferred_substitutions)
        for action in sorted(
            (
                candidate
                for candidate in omission_actions
                if candidate.action_id not in recommended_omissions
                and candidate.action_id != protected.action_id
            ),
            key=lambda candidate: (
                -candidate.landed_saving_cents,
                _omission_rank(candidate),
            ),
        ):
            running.append(action.action_id)
            alternate = _plan_from_actions(
                plan_id="budget-plan-preserve-largest",
                label=f"Keep {protected.canonical_item.replace('_', ' ')}",
                description=(
                    "Preserve the largest item from the recommended plan "
                    "and source several smaller required items separately."
                ),
                preserves=protected.canonical_item.replace("_", " "),
                action_ids=tuple(running),
                analysis_stub=stub,
                optimization=optimization,
                matches=matches,
                unit_needs=unit_needs,
                offers=offers,
                stores=stores,
                config=config,
            )
            if alternate is not None:
                alternatives.append(alternate)
                break

    return replace(
        stub,
        substitution_only_landed_cost_cents=(
            substitution_result.landed_cost
        ),
        recommended_plan=recommended,
        alternative_plans=tuple(
            alternatives[:BUDGET_ALTERNATIVE_PLAN_COUNT]
        ),
    )
