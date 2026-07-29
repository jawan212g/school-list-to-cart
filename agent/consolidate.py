"""Consolidate selected shared SKUs before final package optimization."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agent.aggregate import UnitNeed
from agent.match import CandidateMatch, MatchResult, NeedMatches
from agent.optimize import CartLine, OptimizationResult
from agent.rules import (
    PRODUCT_DEFINING_ATTRIBUTE_FIELDS,
    SUBSTITUTION_MAJOR,
    SUBSTITUTION_MINOR,
    SUBSTITUTION_NONE,
)


@dataclass(frozen=True)
class ConsolidationResult:
    """Purchase needs and matches after shared-SKU consolidation."""

    unit_needs: tuple[UnitNeed, ...]
    matches: MatchResult
    changed: bool


def _selected_lines(
    optimization: OptimizationResult,
) -> tuple[CartLine, ...]:
    if optimization.minimum_second_trip is None:
        return optimization.plan.lines
    return (
        optimization.plan.lines
        + optimization.minimum_second_trip.lines
    )


def _strongest_substitution(
    candidates: Sequence[CandidateMatch],
) -> str:
    types = {candidate.substitution_type for candidate in candidates}
    if SUBSTITUTION_MAJOR in types:
        return SUBSTITUTION_MAJOR
    if SUBSTITUTION_MINOR in types:
        return SUBSTITUTION_MINOR
    return SUBSTITUTION_NONE


def _combined_attribute_status(
    candidates: Sequence[CandidateMatch],
) -> str:
    statuses = {candidate.attribute_status for candidate in candidates}
    if "different" in statuses:
        return "different"
    if "unknown" in statuses:
        return "unknown"
    return "exact"


def _merge_attributes(needs: Sequence[UnitNeed]) -> Mapping[str, object]:
    first = dict(needs[0].attributes)
    if all(dict(need.attributes) == first for need in needs):
        return first
    return {
        "component_attributes": tuple(
            tuple(sorted(dict(need.attributes).items()))
            for need in needs
        )
    }


def _product_definitions_are_compatible(
    needs: Sequence[UnitNeed],
) -> bool:
    """Keep BR-31 product variants separate even when one SKU was proposed."""

    variant_ids = {
        need.product_variant_id
        for need in needs
        if need.product_variant_id is not None
    }
    if len(variant_ids) > 1:
        return False
    for field_name in PRODUCT_DEFINING_ATTRIBUTE_FIELDS:
        values = {
            repr(need.attributes.get(field_name)).casefold()
            for need in needs
            if need.attributes.get(field_name) not in (None, "", (), [], {})
        }
        if len(values) > 1:
            return False
    return True


def _merge_needs(
    needs: Sequence[UnitNeed],
    selected_candidate: CandidateMatch,
) -> UnitNeed:
    brand_locks = {
        need.brand_lock
        for need in needs
        if need.brand_lock is not None
    }
    brand_lock = (
        next(iter(brand_locks))
        if len(brand_locks) == 1
        else selected_candidate.offer.brand
        if brand_locks
        else None
    )
    allocated_to: dict[str, int] = defaultdict(int)
    for need in needs:
        for child_id, quantity in need.allocated_to.items():
            allocated_to[child_id] += quantity
    return UnitNeed(
        canonical_item=needs[0].canonical_item,
        quantity=sum(need.quantity for need in needs),
        brand_lock=brand_lock,
        unit_type=needs[0].unit_type,
        exclusions=tuple(
            dict.fromkeys(
                exclusion
                for need in needs
                for exclusion in need.exclusions
            )
        ),
        is_required=any(need.is_required for need in needs),
        attributes=_merge_attributes(needs),
        allocated_to=dict(allocated_to),
        source_requirement_ids=tuple(
            requirement_id
            for need in needs
            for requirement_id in need.source_requirement_ids
        ),
        product_variant_id=(
            needs[0].product_variant_id
            if all(
                need.product_variant_id == needs[0].product_variant_id
                for need in needs
            )
            else None
        ),
    )


def _merge_candidates(
    merged_need: UnitNeed,
    candidates: Sequence[CandidateMatch],
) -> CandidateMatch:
    first = candidates[0]
    substitution_type = _strongest_substitution(candidates)
    return CandidateMatch(
        need_key="|".join(merged_need.source_requirement_ids),
        offer=first.offer,
        match_confidence=min(
            candidate.match_confidence for candidate in candidates
        ),
        suitability_reason=(
            "Shared SKU selected for multiple compatible requirements."
        ),
        substitution_type=substitution_type,  # type: ignore[arg-type]
        substitution_reasons=tuple(
            dict.fromkeys(
                reason
                for candidate in candidates
                for reason in candidate.substitution_reasons
            )
        ),
        attribute_status=_combined_attribute_status(  # type: ignore[arg-type]
            candidates
        ),
        line_notes=tuple(
            dict.fromkeys(
                note
                for candidate in candidates
                for note in candidate.line_notes
            )
        ),
        approval_reasons=tuple(
            dict.fromkeys(
                reason
                for candidate in candidates
                for reason in candidate.approval_reasons
            )
        ),
        requires_approval=any(
            candidate.requires_approval for candidate in candidates
        ),
    )


def consolidate_selected_skus(
    unit_needs: Sequence[UnitNeed],
    matches: MatchResult,
    preliminary: OptimizationResult,
) -> ConsolidationResult:
    """Merge shared-SKU needs with allocation and provenance (FR-14, FR-16)."""

    selected_skus_by_need: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for line in _selected_lines(preliminary):
        selected_skus_by_need[line.source_requirement_ids].add(line.sku)

    groups_by_sku: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for source_ids, skus in selected_skus_by_need.items():
        if len(skus) == 1:
            groups_by_sku[next(iter(skus))].append(source_ids)

    needs_by_ids = {
        need.source_requirement_ids: need for need in unit_needs
    }
    matches_by_ids = {
        need_matches.unit_need.source_requirement_ids: need_matches
        for need_matches in matches.needs
    }
    group_for_ids: dict[tuple[str, ...], tuple[str, ...]] = {}
    valid_groups: dict[
        tuple[str, ...],
        tuple[str, tuple[UnitNeed, ...], tuple[CandidateMatch, ...]],
    ] = {}

    for sku, source_groups in groups_by_sku.items():
        if len(source_groups) < 2:
            continue
        grouped_needs = tuple(needs_by_ids[source_ids] for source_ids in source_groups)
        if len({need.canonical_item for need in grouped_needs}) != 1:
            continue
        if len({need.unit_type for need in grouped_needs}) != 1:
            continue
        if not _product_definitions_are_compatible(grouped_needs):
            continue
        grouped_candidates = tuple(
            matches.candidate(source_ids, sku)
            for source_ids in source_groups
        )
        if any(candidate is None for candidate in grouped_candidates):
            continue
        group_key = source_groups[0]
        typed_candidates = tuple(
            candidate
            for candidate in grouped_candidates
            if candidate is not None
        )
        valid_groups[group_key] = (
            sku,
            grouped_needs,
            typed_candidates,
        )
        for source_ids in source_groups:
            group_for_ids[source_ids] = group_key

    if not valid_groups:
        return ConsolidationResult(
            unit_needs=tuple(unit_needs),
            matches=matches,
            changed=False,
        )

    consolidated_needs: list[UnitNeed] = []
    consolidated_matches: list[NeedMatches] = []
    emitted_groups: set[tuple[str, ...]] = set()
    for need in unit_needs:
        group_key = group_for_ids.get(need.source_requirement_ids)
        if group_key is None:
            consolidated_needs.append(need)
            consolidated_matches.append(
                matches_by_ids[need.source_requirement_ids]
            )
            continue
        if group_key in emitted_groups:
            continue
        _, grouped_needs, grouped_candidates = valid_groups[group_key]
        merged_need = _merge_needs(grouped_needs, grouped_candidates[0])
        merged_candidate = _merge_candidates(
            merged_need,
            grouped_candidates,
        )
        consolidated_needs.append(merged_need)
        consolidated_matches.append(
            NeedMatches(
                unit_need=merged_need,
                candidates=(merged_candidate,),
                review_blocked_candidates=(),
            )
        )
        emitted_groups.add(group_key)

    return ConsolidationResult(
        unit_needs=tuple(consolidated_needs),
        matches=MatchResult(needs=tuple(consolidated_matches)),
        changed=True,
    )
