"""End-to-end proposal pipeline without an approval user interface."""

from __future__ import annotations

from collections import Counter
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
    require_extracted_requirements,
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
    FAILED_DOCUMENT_SEQUENTIAL_FALLBACK,
    MODEL_MAX_CONCURRENCY,
    NONPAGINATED_SOURCE_PAGE,
    SUBSTITUTION_MAJOR,
    SUBSTITUTION_MINOR,
    SUBSTITUTION_NONE,
    non_returnable_offer_requires_approval,
)
from agent.requirement_merge import (
    RequirementConstraintInterrupt,
    RequirementQuantityInterrupt,
    consolidate_requirements,
    requirement_source,
)
from agent.schema import ExtractionEnvelope, Requirement
from data.loader import Offer, Store, load_catalog, load_stores


BudgetMode = Literal["combined", "per_child", "none"]
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
    document_name: str | None = None
    source_page_texts: tuple[str, ...] = ()
    rendered_source_pages: tuple[bytes, ...] = ()

    @property
    def resolved_document_name(self) -> str:
        """Return trusted source provenance without using model output."""

        if self.document_name:
            return self.document_name
        if isinstance(self.source, Path):
            return self.source.name
        if isinstance(self.source, str):
            candidate = Path(self.source)
            try:
                if candidate.is_file():
                    return candidate.name
            except OSError:
                pass
            return "Pasted supply list"
        return "Uploaded supply list"

    @property
    def source_page_count(self) -> int:
        """Return the deterministic page count for retained source evidence."""

        return max(
            len(self.source_page_texts),
            len(self.rendered_source_pages),
            1,
        )

    def resolved_source_page(
        self,
        source_line: str,
        fallback_page: int | None,
    ) -> int | None:
        """Locate an exact pasted source line without a downstream type branch."""

        if self.source_page_texts and source_line:
            for page_number, page_text in enumerate(
                self.source_page_texts,
                start=1,
            ):
                if source_line in page_text:
                    return page_number
        return fallback_page


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
    source_matches: MatchResult | None = None
    requirement_merge_interrupts: tuple[
        RequirementQuantityInterrupt | RequirementConstraintInterrupt, ...
    ] = ()


CatalogChangeKind = Literal["stockout", "price_change"]
CatalogStalenessKind = Literal["stock", "price"]


@dataclass(frozen=True)
class ReplanTransition:
    """One FR-32 catalog-change transition and its approval effects."""

    result: PipelineResult
    preserved_approval_outcomes: Mapping[str, str]
    preserved_budget_action_ids: tuple[str, ...]
    invalidated_approval_ids: tuple[str, ...]
    new_interrupt_ids: tuple[str, ...]
    change_kind: CatalogChangeKind
    changed_sku: str


@dataclass(frozen=True)
class CatalogStaleness:
    """One BR-12 difference between a built cart and active catalog."""

    kind: CatalogStalenessKind
    sku: str
    prior_line_cost_cents: int
    active_line_cost_cents: int | None


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
    extractions: dict[str, ExtractionEnvelope] = {}
    extraction_failures: dict[str, str] = {}
    extracted_requirements = []
    merge_interrupts: list[
        RequirementQuantityInterrupt | RequirementConstraintInterrupt
    ] = []
    completed_envelopes: dict[int, ExtractionEnvelope] = {}

    def extract_one(list_input: ListInput) -> ExtractionEnvelope:
        return require_extracted_requirements(
            extractor(
                list_input.source,
                child_id=list_input.child_id,
                mime_type=list_input.mime_type,
                client=model_client,
            )
        )

    futures = {}
    with ThreadPoolExecutor(
        max_workers=min(max(len(lists), 1), MODEL_MAX_CONCURRENCY)
    ) as executor:
        futures = {
            executor.submit(extract_one, list_input): (index, list_input)
            for index, list_input in enumerate(lists)
        }
        completed_extractions = 0
        for future in as_completed(futures):
            list_index, list_input = futures[future]
            completed_extractions += 1
            if progress_callback is not None:
                progress_callback(
                    "extraction",
                    completed_extractions,
                    len(lists),
                    f"Read {completed_extractions} of {len(lists)} lists",
                )
            try:
                completed_envelopes[list_index] = future.result()
            except Exception as error:
                extraction_failures[list_input.child_id] = (
                    f"{type(error).__name__}: {error}"
                )
    if FAILED_DOCUMENT_SEQUENTIAL_FALLBACK and extraction_failures:
        failed_lists = tuple(
            (list_index, list_input)
            for list_index, list_input in enumerate(lists)
            if list_input.child_id in extraction_failures
        )
        for retry_index, (list_index, list_input) in enumerate(
            failed_lists,
            start=1,
        ):
            if progress_callback is not None:
                progress_callback(
                    "extraction_retry",
                    retry_index,
                    len(failed_lists),
                    (
                        "Retrying the list that did not finish "
                        f"({retry_index} of {len(failed_lists)})"
                    ),
                )
            try:
                completed_envelopes[list_index] = extract_one(list_input)
                extraction_failures.pop(list_input.child_id, None)
            except Exception as error:
                extraction_failures[list_input.child_id] = (
                    f"{type(error).__name__}: {error}"
                )
    requirements_by_child: dict[str, list[Requirement]] = {}
    envelopes_by_child: dict[str, list[ExtractionEnvelope]] = {}
    child_list_counts = Counter(child_ids)
    child_list_indexes: Counter[str] = Counter()
    for list_index, list_input in enumerate(lists):
        extraction = completed_envelopes.get(list_index)
        if extraction is None:
            continue
        child_list_indexes[list_input.child_id] += 1
        extraction = apply_extraction_security_filters(
            extraction,
            list_input.child_id,
        )
        extraction = extraction.model_copy(
            update={
                "catalog_unavailable_items": tuple(
                    item.model_copy(
                        update={
                            "document_name": (
                                list_input.resolved_document_name
                            ),
                            "page_number": (
                                list_input.resolved_source_page(
                                    item.source_line,
                                    item.page_number,
                                )
                                or NONPAGINATED_SOURCE_PAGE
                            ),
                        }
                    )
                    for item in extraction.catalog_unavailable_items
                )
            }
        )
        stamped_requirements = tuple(
            requirement.model_copy(
                update={
                    "req_id": (
                        f"{list_input.child_id}:"
                        + (
                            f"list-{child_list_indexes[list_input.child_id]}:"
                            if child_list_counts[list_input.child_id] > 1
                            else ""
                        )
                        + requirement.req_id
                    ),
                    "source_document": (
                        requirement.source_document
                        or list_input.resolved_document_name
                    ),
                    "source_page": list_input.resolved_source_page(
                        requirement.raw_text,
                        requirement.source_page,
                    ),
                }
            )
            for requirement in extraction.requirements
        )
        stamped_requirements = tuple(
            requirement.model_copy(
                update={
                    "sources": (
                        requirement.sources
                        or (requirement_source(requirement),)
                    )
                }
            )
            for requirement in stamped_requirements
        )
        requirements_by_child.setdefault(list_input.child_id, []).extend(
            stamped_requirements
        )
        envelopes_by_child.setdefault(list_input.child_id, []).append(
            extraction
        )

    for child_id, child_envelopes in envelopes_by_child.items():
        merge_result = consolidate_requirements(
            requirements_by_child[child_id]
        )
        first = child_envelopes[0]
        combined = first.model_copy(
            update={
                "stated_grades": tuple(
                    dict.fromkeys(
                        grade
                        for envelope in child_envelopes
                        for grade in envelope.stated_grades
                    )
                ),
                "stated_teachers": tuple(
                    dict.fromkeys(
                        teacher
                        for envelope in child_envelopes
                        for teacher in envelope.stated_teachers
                    )
                ),
                "requirements": merge_result.requirements,
                "manual_review_required": any(
                    envelope.manual_review_required
                    for envelope in child_envelopes
                ),
                "review_reasons": tuple(
                    dict.fromkeys(
                        reason
                        for envelope in child_envelopes
                        for reason in envelope.review_reasons
                    )
                ),
                "deferred_review_reasons": tuple(
                    dict.fromkeys(
                        reason
                        for envelope in child_envelopes
                        for reason in envelope.deferred_review_reasons
                    )
                ),
                "document_selection": (
                    first.document_selection
                    if all(
                        envelope.document_selection
                        == first.document_selection
                        for envelope in child_envelopes
                    )
                    else None
                ),
                "uninterpreted_lines": tuple(
                    line
                    for envelope in child_envelopes
                    for line in envelope.uninterpreted_lines
                ),
                "skipped_lines": tuple(
                    line
                    for envelope in child_envelopes
                    for line in envelope.skipped_lines
                ),
                "catalog_unavailable_items": tuple(
                    item
                    for envelope in child_envelopes
                    for item in envelope.catalog_unavailable_items
                ),
            }
        )
        extractions[child_id] = combined
        extracted_requirements.extend(combined.requirements)
        merge_interrupts.extend(merge_result.interrupts)
        merge_interrupts.extend(merge_result.constraint_interrupts)

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
        source_matches=matches,
        requirement_merge_interrupts=tuple(merge_interrupts),
    )


def run_pipeline_from_confirmed_extractions(
    session: PipelineSession,
    extractions: Mapping[str, ExtractionEnvelope],
    *,
    extraction_errors: Mapping[str, Exception] | None = None,
    stores: Sequence[Store] | None = None,
    offers: Sequence[Offer] | None = None,
    suitability_judge: SuitabilityJudge | None = None,
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Build a plan only from user-confirmed extraction envelopes (FR-12)."""

    errors = extraction_errors or {}
    lists = tuple(
        ListInput(
            child_id=child_id,
            source="[user-confirmed organized list]",
            mime_type="text/plain",
        )
        for child_id in session.children
    )

    def confirmed_extractor(
        source: str | Path | bytes,
        *,
        child_id: str,
        mime_type: str | None,
        client: OpenAI | None,
    ) -> ExtractionEnvelope:
        del source, mime_type, client
        error = errors.get(child_id)
        if error is not None:
            raise error
        return extractions[child_id]

    return run_pipeline(
        session,
        lists,
        stores=stores,
        offers=offers,
        extractor=confirmed_extractor,
        suitability_judge=suitability_judge,
        progress_callback=progress_callback,
    )


def _refresh_candidate(
    candidate: CandidateMatch,
    active_offer: Offer,
) -> CandidateMatch:
    """Refresh price and stock without repeating model suitability judgment."""

    non_returnable_approval = non_returnable_offer_requires_approval(
        active_offer.is_returnable,
        active_offer.pack_price,
    )
    approval_reasons = tuple(
        reason
        for reason in candidate.approval_reasons
        if reason != "non_returnable_threshold"
    ) + (
        ("non_returnable_threshold",)
        if non_returnable_approval
        else ()
    )
    return replace(
        candidate,
        offer=active_offer,
        approval_reasons=approval_reasons,
        requires_approval=(
            candidate.substitution_type == SUBSTITUTION_MAJOR
            or non_returnable_approval
        ),
    )


def _refresh_matches_for_catalog(
    matches: MatchResult,
    offers: Sequence[Offer],
) -> MatchResult:
    """Apply current catalog price and stock to already-judged candidates."""

    offers_by_sku = {offer.sku: offer for offer in offers}

    def active_candidates(
        candidates: Sequence[CandidateMatch],
    ) -> tuple[CandidateMatch, ...]:
        refreshed = []
        for candidate in candidates:
            active_offer = offers_by_sku.get(candidate.offer.sku)
            if active_offer is None or active_offer.stock_qty <= 0:
                continue
            refreshed.append(_refresh_candidate(candidate, active_offer))
        return tuple(refreshed)

    return MatchResult(
        needs=tuple(
            replace(
                need_matches,
                candidates=active_candidates(need_matches.candidates),
                review_blocked_candidates=active_candidates(
                    need_matches.review_blocked_candidates
                ),
            )
            for need_matches in matches.needs
        )
    )


def _ungrouped_interrupt_ids(batch: ApprovalBatch) -> tuple[str, ...]:
    """Return stable condition IDs even when BR-10 groups their display."""

    return tuple(
        child.interrupt_id
        for interrupt in batch.interrupts
        for child in (
            interrupt.grouped_interrupts
            if interrupt.grouped_interrupts
            else (interrupt,)
        )
    )


def replan_after_catalog_change(
    prior: PipelineResult,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    *,
    change_kind: CatalogChangeKind,
    changed_sku: str,
    approval_outcomes: Mapping[str, str] | None = None,
    budget_action_ids: Sequence[str] = (),
) -> ReplanTransition:
    """Replan from cached matches after an FR-32 stock or price change."""

    active_offers = tuple(offers)
    active_stores = tuple(stores)
    active_by_sku = {offer.sku: offer for offer in active_offers}
    if changed_sku not in active_by_sku:
        raise ValueError(f"Changed SKU is not in the catalog: {changed_sku}")
    if change_kind == "stockout":
        if active_by_sku[changed_sku].stock_qty > 0:
            raise ValueError("A stockout change must set stock_qty to zero")
    elif change_kind != "price_change":
        raise ValueError(f"Unsupported catalog change: {change_kind}")

    source_matches = prior.source_matches or prior.matches
    refreshed_source_matches = _refresh_matches_for_catalog(
        source_matches,
        active_offers,
    )
    config = OptimizationConfig(
        shopping_mode=prior.session.shopping_mode,
        budget_cents=prior.session.budget_total,
        allowed_store_ids=prior.session.allowed_stores,
        max_stores=prior.session.max_stores,
        store_radius_miles=prior.session.store_radius_miles,
        fulfillment_preference=prior.session.fulfillment_pref,
        tax_basis_points=prior.session.tax_basis_points,
    )
    preliminary = optimize_cart(
        prior.unit_needs,
        active_offers,
        active_stores,
        config,
        candidate_skus_by_need=(
            refreshed_source_matches.candidate_skus_by_need
        ),
    )
    consolidation = consolidate_selected_skus(
        prior.unit_needs,
        refreshed_source_matches,
        preliminary,
    )
    final_matches = consolidation.matches
    if consolidation.changed:
        optimization = optimize_cart(
            consolidation.unit_needs,
            active_offers,
            active_stores,
            config,
            candidate_skus_by_need=final_matches.candidate_skus_by_need,
        )
    else:
        optimization = preliminary
    proposed_cart = _decorate_optimization(optimization, final_matches)

    decision_log = DecisionLog(
        f"{prior.session.session_id}-replan-{len(prior.decisions) + 1}"
    )
    affected_lines = tuple(
        line.line_id
        for line in _selected_lines(prior.proposed_cart)
        if line.sku == changed_sku
    )
    decision_log.record(
        "match",
        (
            f"Replanned after a {change_kind.replace('_', ' ')} for "
            f"{changed_sku}; cached extraction and suitability judgments "
            "were retained."
        ),
        actor="agent",
        affected_lines=affected_lines,
    )
    _record_cart_decisions(
        decision_log,
        final_matches,
        proposed_cart,
    )
    approval_batch = evaluate_gate(
        GateContext(
            optimization=proposed_cart,
            matches=final_matches,
            normalization=prior.normalization,
            extractions=prior.extractions,
            offers=active_offers,
            stores=active_stores,
            tax_basis_points=prior.session.tax_basis_points,
            unit_needs=consolidation.unit_needs,
            optimization_config=config,
        ),
        decision_log=decision_log,
    )
    addon_proposal = propose_addons(
        prior.normalization,
        proposed_cart,
        consolidation.unit_needs,
        final_matches,
        active_offers,
        active_stores,
        config,
        student_counts_by_child=prior.session.student_counts,
    )
    budget_analysis = build_budget_analysis(
        proposed_cart,
        final_matches,
        consolidation.unit_needs,
        active_offers,
        active_stores,
        config,
    )
    result = PipelineResult(
        session=prior.session,
        extractions=prior.extractions,
        normalization=prior.normalization,
        unit_needs=prior.unit_needs,
        purchase_needs=consolidation.unit_needs,
        matches=final_matches,
        proposed_cart=proposed_cart,
        approval_batch=approval_batch,
        approval_flags=_approval_flags(approval_batch),
        decisions=prior.decisions + decision_log.entries,
        extraction_failures=prior.extraction_failures,
        addon_proposal=addon_proposal,
        budget_analysis=budget_analysis,
        source_matches=refreshed_source_matches,
        requirement_merge_interrupts=prior.requirement_merge_interrupts,
    )

    previous_ids = frozenset(
        _ungrouped_interrupt_ids(prior.approval_batch)
    )
    current_ids = frozenset(_ungrouped_interrupt_ids(approval_batch))
    previous_outcomes = approval_outcomes or {}
    preserved_outcomes = {
        interrupt_id: outcome
        for interrupt_id, outcome in previous_outcomes.items()
        if interrupt_id in current_ids
    }
    actions_by_id = (
        {}
        if budget_analysis is None
        else budget_analysis.actions_by_id
    )
    preserved_budget_actions = tuple(
        action_id
        for action_id in dict.fromkeys(budget_action_ids)
        if action_id in actions_by_id
    )
    return ReplanTransition(
        result=result,
        preserved_approval_outcomes=preserved_outcomes,
        preserved_budget_action_ids=preserved_budget_actions,
        invalidated_approval_ids=tuple(
            sorted(set(previous_outcomes).difference(preserved_outcomes))
        ),
        new_interrupt_ids=tuple(sorted(current_ids.difference(previous_ids))),
        change_kind=change_kind,
        changed_sku=changed_sku,
    )


def detect_cart_staleness(
    optimization: OptimizationResult,
    offers: Sequence[Offer],
) -> tuple[CatalogStaleness, ...]:
    """Revalidate selected price and stock before simulated checkout (BR-12)."""

    offers_by_sku = {offer.sku: offer for offer in offers}
    stale: list[CatalogStaleness] = []
    for line in _selected_lines(optimization):
        offer = offers_by_sku.get(line.sku)
        if offer is None or offer.stock_qty < line.packs_purchased:
            stale.append(
                CatalogStaleness(
                    kind="stock",
                    sku=line.sku,
                    prior_line_cost_cents=line.line_cost,
                    active_line_cost_cents=None,
                )
            )
            continue
        active_line_cost = offer.pack_price * line.packs_purchased
        if active_line_cost != line.line_cost:
            stale.append(
                CatalogStaleness(
                    kind="price",
                    sku=line.sku,
                    prior_line_cost_cents=line.line_cost,
                    active_line_cost_cents=active_line_cost,
                )
            )
    return tuple(stale)
