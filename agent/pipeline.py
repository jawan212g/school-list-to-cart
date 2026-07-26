"""End-to-end proposal pipeline without an approval user interface."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from openai import OpenAI

from agent.addons import AddOnProposal, propose_addons
from agent.aggregate import UnitNeed, aggregate_requirements
from agent.budget_plans import BudgetAnalysis, build_budget_analysis
from agent.consolidate import consolidate_selected_skus
from agent.decisions import Decision, DecisionLog
from agent.extract import (
    apply_extraction_security_filters,
    extract_document,
)
from agent.gate import (
    ApprovalBatch,
    GateContext,
    InterruptKind,
    evaluate_gate,
)
from agent.match import (
    CandidateMatch,
    MatchResult,
    OpenAISuitabilityJudge,
    SuitabilityJudge,
    match_offers,
)
from agent.normalize import NormalizationResult, normalize_requirements
from agent.optimize import (
    CartLine,
    CartPlan,
    FulfillmentPreference,
    OptimizationConfig,
    OptimizationResult,
    ShoppingMode,
    optimize_cart,
)
from agent.rules import (
    DEFAULT_TAX_BASIS_POINTS,
    MODEL_MAX_CONCURRENCY,
    SUBSTITUTION_MAJOR,
    SUBSTITUTION_MINOR,
    SUBSTITUTION_NONE,
)
from agent.schema import ExtractionEnvelope
from data.loader import Offer, Store, load_catalog, load_stores


BudgetMode = Literal["combined", "per_child"]
ApprovalKind = Literal[
    "budget",
    "major_substitution",
    "attribute_choice",
    "non_returnable",
    "low_confidence",
    "required_unavailable",
]


@dataclass(frozen=True)
class PipelineSession:
    """Session controls matching the BRD Section 8 session entity."""

    session_id: str
    children: tuple[str, ...]
    budget_total: int | None
    budget_mode: BudgetMode = "combined"
    shopping_mode: ShoppingMode = "budget"
    store_radius_miles: float | None = None
    allowed_stores: frozenset[str] | None = None
    fulfillment_pref: FulfillmentPreference = "either"
    tax_basis_points: int = DEFAULT_TAX_BASIS_POINTS
    created_at: datetime | None = None
    max_stores: int | None = None
    student_counts: Mapping[str, int] = field(default_factory=dict)
    budget_allocations: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ListInput:
    """One child or classroom list supplied to the pipeline."""

    child_id: str
    source: str | Path | bytes
    mime_type: str | None = None


@dataclass(frozen=True)
class ApprovalFlag:
    """One batched condition for the future approval gate (FR-26, FR-27)."""

    kind: ApprovalKind
    message: str
    source_requirement_ids: tuple[str, ...] = ()
    sku: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    """Every stage of a proposed cart plus unresolved approval conditions."""

    session: PipelineSession
    extractions: Mapping[str, ExtractionEnvelope]
    normalization: NormalizationResult
    unit_needs: tuple[UnitNeed, ...]
    purchase_needs: tuple[UnitNeed, ...]
    matches: MatchResult
    proposed_cart: OptimizationResult
    approval_batch: ApprovalBatch
    approval_flags: tuple[ApprovalFlag, ...]
    decisions: tuple[Decision, ...]
    extraction_failures: Mapping[str, str]
    addon_proposal: AddOnProposal
    budget_analysis: BudgetAnalysis | None = None


Extractor = Callable[..., ExtractionEnvelope]
ProgressCallback = Callable[[str, int, int, str], None]


def _stronger_substitution(
    current: str,
    candidate: str,
) -> str:
    if SUBSTITUTION_MAJOR in {current, candidate}:
        return SUBSTITUTION_MAJOR
    if SUBSTITUTION_MINOR in {current, candidate}:
        return SUBSTITUTION_MINOR
    return current


def _decorate_line(line: CartLine, matches: MatchResult) -> CartLine:
    candidate = matches.candidate(line.source_requirement_ids, line.sku)
    if candidate is None:
        return line
    substitution_type = _stronger_substitution(
        line.substitution_type,
        candidate.substitution_type,
    )
    approval_status = (
        "pending"
        if line.approval_status == "pending" or candidate.requires_approval
        else "not_required"
    )
    return replace(
        line,
        substitution_type=substitution_type,
        approval_status=approval_status,
        match_confidence=candidate.match_confidence,
        notes=candidate.line_notes,
    )


def _decorate_plan(plan: CartPlan, matches: MatchResult) -> CartPlan:
    decorated_lines = tuple(
        _decorate_line(line, matches) for line in plan.lines
    )
    lines_by_id = {line.line_id: line for line in decorated_lines}
    decorated_orders = tuple(
        replace(
            order,
            lines=tuple(lines_by_id[line.line_id] for line in order.lines),
        )
        for order in plan.store_orders
    )
    return replace(
        plan,
        lines=decorated_lines,
        store_orders=decorated_orders,
    )


def _decorate_optimization(
    result: OptimizationResult,
    matches: MatchResult,
) -> OptimizationResult:
    second_trip = (
        None
        if result.minimum_second_trip is None
        else _decorate_plan(result.minimum_second_trip, matches)
    )
    return replace(
        result,
        plan=_decorate_plan(result.plan, matches),
        minimum_second_trip=second_trip,
    )


def _selected_lines(result: OptimizationResult) -> tuple[CartLine, ...]:
    if result.minimum_second_trip is None:
        return result.plan.lines
    return result.plan.lines + result.minimum_second_trip.lines


def _candidate_for_line(
    line: CartLine,
    matches: MatchResult,
) -> CandidateMatch | None:
    return matches.candidate(line.source_requirement_ids, line.sku)


def _legacy_approval_kind(kind: InterruptKind) -> ApprovalKind:
    return {
        "budget_exceeded": "budget",
        "major_substitution": "major_substitution",
        "brand_lock_break": "major_substitution",
        "attribute_choice": "attribute_choice",
        "non_returnable_threshold": "non_returnable",
        "low_confidence": "low_confidence",
        "required_unavailable": "required_unavailable",
    }[kind]  # type: ignore[return-value]


def _approval_flags(
    batch: ApprovalBatch,
) -> tuple[ApprovalFlag, ...]:
    return tuple(
        ApprovalFlag(
            kind=_legacy_approval_kind(interrupt.kind),
            message=interrupt.message,
            source_requirement_ids=interrupt.source_requirement_ids,
            sku=interrupt.sku,
        )
        for interrupt in batch.interrupts
    )


def _record_cart_decisions(
    log: DecisionLog,
    matches: MatchResult,
    optimization: OptimizationResult,
) -> None:
    """Record selected matches and all deterministic cart actions."""

    for line in _selected_lines(optimization):
        candidate = _candidate_for_line(line, matches)
        confidence_text = (
            "catalog rules"
            if candidate is None
            else f"match confidence {candidate.match_confidence:.2f}"
        )
        log.record(
            "match",
            (
                f"Selected {line.sku} for {line.canonical_item} using "
                f"{confidence_text}."
            ),
            actor="agent",
            affected_lines=(line.line_id,),
        )
        if line.substitution_type != SUBSTITUTION_NONE:
            reasons = (
                ()
                if candidate is None
                else candidate.substitution_reasons
            )
            reason_text = ", ".join(reasons) or "package overage"
            log.record(
                "substitution",
                (
                    f"Classified {line.sku} as "
                    f"{line.substitution_type}: {reason_text}."
                ),
                actor="agent",
                affected_lines=(line.line_id,),
            )

    plans = (optimization.plan,) + (
        ()
        if optimization.minimum_second_trip is None
        else (optimization.minimum_second_trip,)
    )
    for plan in plans:
        for order in plan.store_orders:
            log.record(
                "store_assignment",
                (
                    f"Assigned {len(order.lines)} cart line(s) to "
                    f"{order.store_id} by {order.fulfillment_method}; "
                    f"landed cost is {order.landed_cost} cents."
                ),
                actor="agent",
                affected_lines=tuple(
                    line.line_id for line in order.lines
                ),
            )

    if optimization.budget_cents is None:
        rationale = (
            f"No budget ceiling was set; minimum landed cost is "
            f"{optimization.landed_cost} cents."
        )
    elif optimization.within_budget:
        rationale = (
            f"The cart is within budget at "
            f"{optimization.landed_cost} cents landed."
        )
    else:
        rationale = (
            f"The minimum landed cost exceeds budget by "
            f"{optimization.shortfall_cents} cents; no required item was "
            "removed."
        )
    log.record(
        "budget_action",
        rationale,
        actor="agent",
        affected_lines=tuple(
            line.line_id for line in _selected_lines(optimization)
        ),
    )


def run_pipeline(
    session: PipelineSession,
    lists: Sequence[ListInput],
    *,
    stores: Sequence[Store] | None = None,
    offers: Sequence[Offer] | None = None,
    model_client: OpenAI | None = None,
    suitability_judge: SuitabilityJudge | None = None,
    extractor: Extractor = extract_document,
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Build a proposed cart, approval batch, and log (FR-06–FR-30)."""

    active_stores = tuple(stores) if stores is not None else tuple(load_stores())
    active_offers = tuple(offers) if offers is not None else tuple(load_catalog())

    child_ids = tuple(list_input.child_id for list_input in lists)
    for child_id in child_ids:
        if child_id not in session.children:
            raise ValueError(f"List child_id is not in the session: {child_id}")
    if len(set(child_ids)) != len(child_ids):
        raise ValueError("Only one list per child_id is supported")

    extractions: dict[str, ExtractionEnvelope] = {}
    extraction_failures: dict[str, str] = {}
    extracted_requirements = []
    completed_envelopes: dict[str, ExtractionEnvelope] = {}

    def extract_one(list_input: ListInput) -> ExtractionEnvelope:
        return extractor(
            list_input.source,
            child_id=list_input.child_id,
            mime_type=list_input.mime_type,
            client=model_client,
        )

    futures = {}
    with ThreadPoolExecutor(
        max_workers=min(max(len(lists), 1), MODEL_MAX_CONCURRENCY)
    ) as executor:
        futures = {
            executor.submit(extract_one, list_input): list_input
            for list_input in lists
        }
        completed_extractions = 0
        for future in as_completed(futures):
            list_input = futures[future]
            completed_extractions += 1
            if progress_callback is not None:
                progress_callback(
                    "extraction",
                    completed_extractions,
                    len(lists),
                    f"Read {completed_extractions} of {len(lists)} lists",
                )
            try:
                completed_envelopes[list_input.child_id] = future.result()
            except Exception as error:
                extraction_failures[list_input.child_id] = (
                    f"{type(error).__name__}: {error}"
                )
    for list_input in lists:
        extraction = completed_envelopes.get(list_input.child_id)
        if extraction is None:
            continue
        extraction = apply_extraction_security_filters(
                extraction,
                list_input.child_id,
            )
        extraction = extraction.model_copy(
            update={
                "requirements": tuple(
                    requirement.model_copy(
                        update={
                            "req_id": (
                                f"{list_input.child_id}:{requirement.req_id}"
                            )
                        }
                    )
                    for requirement in extraction.requirements
                )
            }
        )
        extractions[list_input.child_id] = extraction
        extracted_requirements.extend(extraction.requirements)

    if progress_callback is not None:
        progress_callback(
            "normalization",
            0,
            len(extracted_requirements),
            "Normalizing quantities and combining shared needs",
        )

    normalization = normalize_requirements(extracted_requirements)
    unit_needs = aggregate_requirements(
        normalization.budget_requirements,
        student_counts_by_child=session.student_counts,
    )
    if progress_callback is not None:
        progress_callback(
            "matching",
            0,
            len(unit_needs),
            f"Matching 0 of {len(unit_needs)} item types",
        )
    matches = match_offers(
        unit_needs,
        active_offers,
        active_stores,
        allowed_store_ids=session.allowed_stores,
        store_radius_miles=session.store_radius_miles,
        fulfillment_preference=session.fulfillment_pref,
        judge=(
            suitability_judge
            or OpenAISuitabilityJudge(
                model_client,
                progress_callback=progress_callback,
            )
        ),
    )
    if progress_callback is not None:
        progress_callback(
            "optimization",
            0,
            len(unit_needs),
            "Optimizing packages, stores, tax, and fulfillment",
        )
    optimization_config = OptimizationConfig(
        shopping_mode=session.shopping_mode,
        budget_cents=session.budget_total,
        allowed_store_ids=session.allowed_stores,
        max_stores=session.max_stores,
        store_radius_miles=session.store_radius_miles,
        fulfillment_preference=session.fulfillment_pref,
        tax_basis_points=session.tax_basis_points,
    )
    preliminary_optimization = optimize_cart(
        unit_needs,
        active_offers,
        active_stores,
        optimization_config,
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    consolidation = consolidate_selected_skus(
        unit_needs,
        matches,
        preliminary_optimization,
    )
    final_matches = consolidation.matches
    if consolidation.changed:
        optimization = optimize_cart(
            consolidation.unit_needs,
            active_offers,
            active_stores,
            optimization_config,
            candidate_skus_by_need=(
                final_matches.candidate_skus_by_need
            ),
        )
    else:
        optimization = preliminary_optimization
    proposed_cart = _decorate_optimization(optimization, final_matches)
    if progress_callback is not None:
        progress_callback(
            "optimization",
            len(consolidation.unit_needs),
            len(consolidation.unit_needs),
            "Package and store optimization complete",
        )

    decision_log = DecisionLog(session.session_id)
    _record_cart_decisions(
        decision_log,
        final_matches,
        proposed_cart,
    )
    approval_batch = evaluate_gate(
        GateContext(
            optimization=proposed_cart,
            matches=final_matches,
            normalization=normalization,
            extractions=extractions,
            offers=active_offers,
            stores=active_stores,
            tax_basis_points=session.tax_basis_points,
            unit_needs=consolidation.unit_needs,
            optimization_config=optimization_config,
        ),
        decision_log=decision_log,
    )
    addon_proposal = propose_addons(
        normalization,
        proposed_cart,
        consolidation.unit_needs,
        final_matches,
        active_offers,
        active_stores,
        optimization_config,
        student_counts_by_child=session.student_counts,
    )
    budget_analysis = build_budget_analysis(
        proposed_cart,
        final_matches,
        consolidation.unit_needs,
        active_offers,
        active_stores,
        optimization_config,
    )
    if progress_callback is not None:
        progress_callback(
            "approval",
            len(approval_batch.interrupts),
            len(approval_batch.interrupts),
            "Approval choices and optional add-ons are ready",
        )
    approval_flags = _approval_flags(approval_batch)
    return PipelineResult(
        session=session,
        extractions=extractions,
        normalization=normalization,
        unit_needs=unit_needs,
        purchase_needs=consolidation.unit_needs,
        matches=final_matches,
        proposed_cart=proposed_cart,
        approval_batch=approval_batch,
        approval_flags=approval_flags,
        decisions=decision_log.entries,
        extraction_failures=extraction_failures,
        addon_proposal=addon_proposal,
        budget_analysis=budget_analysis,
    )
