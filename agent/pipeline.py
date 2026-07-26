"""End-to-end proposal pipeline without an approval user interface."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from openai import OpenAI

from agent.aggregate import UnitNeed, aggregate_requirements
from agent.extract import extract_document
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
    NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS,
    SUBSTITUTION_MAJOR,
    SUBSTITUTION_MINOR,
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
    "package_overage",
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
    matches: MatchResult
    proposed_cart: OptimizationResult
    approval_flags: tuple[ApprovalFlag, ...]


Extractor = Callable[..., ExtractionEnvelope]


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


def _approval_flags(
    extractions: Mapping[str, ExtractionEnvelope],
    normalization: NormalizationResult,
    matches: MatchResult,
    optimization: OptimizationResult,
    offers: Sequence[Offer],
) -> tuple[ApprovalFlag, ...]:
    flags: list[ApprovalFlag] = []

    for extraction in extractions.values():
        flags.extend(
            ApprovalFlag(kind="low_confidence", message=reason)
            for reason in extraction.review_reasons
        )

    extraction_reason_text = frozenset(
        reason
        for extraction in extractions.values()
        for reason in extraction.review_reasons
    )
    for requirement in normalization.manual_review_requirements:
        message = (
            "Required extraction needs review: "
            f"{requirement.source.raw_text}"
        )
        if any(
            requirement.source.raw_text in reason
            for reason in extraction_reason_text
        ):
            continue
        flags.append(
            ApprovalFlag(
                kind="low_confidence",
                message=message,
                source_requirement_ids=(requirement.source.req_id,),
            )
        )

    for need_matches in matches.needs:
        need = need_matches.unit_need
        if need_matches.requires_confidence_review:
            flags.append(
                ApprovalFlag(
                    kind="low_confidence",
                    message=(
                        f"Only below-confidence matches remain for {need.label}."
                    ),
                    source_requirement_ids=need.source_requirement_ids,
                )
            )
        elif need_matches.unfulfillable:
            flags.append(
                ApprovalFlag(
                    kind="required_unavailable",
                    message=(
                        f"No catalog equivalent is available for {need.label}."
                    ),
                    source_requirement_ids=need.source_requirement_ids,
                )
            )

    offers_by_sku = {offer.sku: offer for offer in offers}
    for line in _selected_lines(optimization):
        candidate = _candidate_for_line(line, matches)
        offer = offers_by_sku[line.sku]
        non_returnable_above_threshold = (
            not offer.is_returnable
            and line.line_cost
            > NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS
        )
        if (
            candidate is not None
            and candidate.substitution_type == SUBSTITUTION_MAJOR
        ):
            attribute_change = any(
                reason.startswith("attribute_change:")
                for reason in candidate.substitution_reasons
            )
            flags.append(
                ApprovalFlag(
                    kind=(
                        "attribute_choice"
                        if attribute_change
                        else "major_substitution"
                    ),
                    message=(
                        f"{line.sku} is a major substitution for "
                        f"{line.canonical_item}: "
                        f"{', '.join(candidate.substitution_reasons)}."
                    ),
                    source_requirement_ids=line.source_requirement_ids,
                    sku=line.sku,
                )
            )
        elif (
            line.approval_status == "pending"
            and not non_returnable_above_threshold
        ):
            flags.append(
                ApprovalFlag(
                    kind="package_overage",
                    message=(
                        f"{line.sku} exceeds the normal package overage ceiling."
                    ),
                    source_requirement_ids=line.source_requirement_ids,
                    sku=line.sku,
                )
            )

        if non_returnable_above_threshold:
            flags.append(
                ApprovalFlag(
                    kind="non_returnable",
                    message=(
                        f"{line.sku} is non-returnable and costs more than "
                        "the BR-08 threshold."
                    ),
                    source_requirement_ids=line.source_requirement_ids,
                    sku=line.sku,
                )
            )

    if optimization.within_budget is False:
        flags.append(
            ApprovalFlag(
                kind="budget",
                message=(
                    f"The minimum landed cost exceeds the budget by "
                    f"{optimization.shortfall_cents} cents."
                ),
            )
        )

    unique: dict[
        tuple[ApprovalKind, str | None, str],
        ApprovalFlag,
    ] = {}
    for flag in flags:
        key = (
            flag.kind,
            flag.sku,
            flag.message,
        )
        existing = unique.get(key)
        if existing is None:
            unique[key] = flag
            continue
        combined_requirement_ids = tuple(
            dict.fromkeys(
                existing.source_requirement_ids
                + flag.source_requirement_ids
            )
        )
        unique[key] = replace(
            existing,
            source_requirement_ids=combined_requirement_ids,
        )
    return tuple(unique.values())


def run_pipeline(
    session: PipelineSession,
    lists: Sequence[ListInput],
    *,
    stores: Sequence[Store] | None = None,
    offers: Sequence[Offer] | None = None,
    model_client: OpenAI | None = None,
    suitability_judge: SuitabilityJudge | None = None,
    extractor: Extractor = extract_document,
) -> PipelineResult:
    """Build a proposed cart and approval flags (FR-06–FR-25)."""

    active_stores = tuple(stores) if stores is not None else tuple(load_stores())
    active_offers = tuple(offers) if offers is not None else tuple(load_catalog())

    extractions: dict[str, ExtractionEnvelope] = {}
    extracted_requirements = []
    for list_input in lists:
        if list_input.child_id not in session.children:
            raise ValueError(
                f"List child_id is not in the session: {list_input.child_id}"
            )
        if list_input.child_id in extractions:
            raise ValueError(
                f"Only one list per child_id is supported: {list_input.child_id}"
            )
        extraction = extractor(
            list_input.source,
            child_id=list_input.child_id,
            mime_type=list_input.mime_type,
            client=model_client,
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

    normalization = normalize_requirements(extracted_requirements)
    unit_needs = aggregate_requirements(normalization.budget_requirements)
    matches = match_offers(
        unit_needs,
        active_offers,
        active_stores,
        allowed_store_ids=session.allowed_stores,
        store_radius_miles=session.store_radius_miles,
        judge=(
            suitability_judge
            or OpenAISuitabilityJudge(model_client)
        ),
    )
    optimization = optimize_cart(
        unit_needs,
        active_offers,
        active_stores,
        OptimizationConfig(
            shopping_mode=session.shopping_mode,
            budget_cents=session.budget_total,
            allowed_store_ids=session.allowed_stores,
            max_stores=session.max_stores,
            store_radius_miles=session.store_radius_miles,
            fulfillment_preference=session.fulfillment_pref,
            tax_basis_points=session.tax_basis_points,
        ),
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    proposed_cart = _decorate_optimization(optimization, matches)
    approval_flags = _approval_flags(
        extractions,
        normalization,
        matches,
        proposed_cart,
        active_offers,
    )
    return PipelineResult(
        session=session,
        extractions=extractions,
        normalization=normalization,
        unit_needs=unit_needs,
        matches=matches,
        proposed_cart=proposed_cart,
        approval_flags=approval_flags,
    )
