"""Deterministically consolidate duplicate same-student requirements."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from agent.aggregate import normalized_requirement_identity
from agent.rules import (
    REQUIREMENT_MERGE_CONFLICT_DEFAULT_ACTION,
    REQUIREMENT_SOURCE_DEDUPLICATION_FIELDS,
)
from agent.schema import ExtractionEnvelope, Requirement, RequirementSource


@dataclass(frozen=True)
class RequirementQuantityInterrupt:
    """One quantity disagreement that needs one parent decision."""

    interrupt_id: str
    child_id: str
    canonical_item: str
    sources: tuple[RequirementSource, ...]
    default_quantity: int
    default_action: str = REQUIREMENT_MERGE_CONFLICT_DEFAULT_ACTION


@dataclass(frozen=True)
class RequirementMergeResult:
    """Consolidated requirements plus unresolved quantity choices."""

    requirements: tuple[Requirement, ...]
    interrupts: tuple[RequirementQuantityInterrupt, ...]


def requirement_source(requirement: Requirement) -> RequirementSource:
    """Build trusted provenance from one production Requirement."""

    return RequirementSource(
        source_req_id=requirement.req_id,
        document_name=requirement.source_document,
        section_name=requirement.source_section,
        page_number=requirement.source_page,
        exact_line=requirement.raw_text,
        quantity=requirement.quantity,
    )


def _distinct_sources(
    requirements: Iterable[Requirement],
) -> tuple[RequirementSource, ...]:
    sources: list[RequirementSource] = []
    seen: set[tuple[object, ...]] = set()
    for requirement in requirements:
        candidates = requirement.sources or (requirement_source(requirement),)
        for source in candidates:
            key = tuple(
                getattr(source, field_name)
                for field_name in REQUIREMENT_SOURCE_DEDUPLICATION_FIELDS
            )
            if key not in seen:
                seen.add(key)
                sources.append(source)
    return tuple(sources)


def _merge_identity(requirement: Requirement) -> tuple[Any, ...]:
    return (
        requirement.child_id,
        requirement.requirement_type,
        requirement.supply_scope,
        normalized_requirement_identity(requirement),
    )


def _interrupt_id(
    child_id: str,
    identity: tuple[Any, ...],
) -> str:
    digest = sha256(repr(identity).encode("utf-8")).hexdigest()[:12]
    return f"quantity-merge:{child_id}:{digest}"


def consolidate_requirements(
    requirements: Iterable[Requirement],
    *,
    quantity_choices: Mapping[str, int] | None = None,
) -> RequirementMergeResult:
    """Merge same-student duplicates and flag quantity conflicts (FR-14)."""

    choices = quantity_choices or {}
    grouped: dict[tuple[Any, ...], list[Requirement]] = {}
    passthrough: list[Requirement] = []
    for requirement in requirements:
        if not requirement.is_purchasable:
            passthrough.append(requirement)
            continue
        grouped.setdefault(_merge_identity(requirement), []).append(requirement)

    merged: list[Requirement] = []
    interrupts: list[RequirementQuantityInterrupt] = []
    for identity, group in grouped.items():
        first = group[0]
        sources = _distinct_sources(group)
        quantities = tuple(requirement.quantity for requirement in group)
        if len(group) == 1:
            merged.append(first.model_copy(update={"sources": sources}))
            continue
        if len(set(quantities)) == 1:
            quantity = quantities[0]
        else:
            interrupt_id = _interrupt_id(first.child_id, identity)
            default_quantity = sum(quantities)
            quantity = choices.get(interrupt_id, default_quantity)
            if quantity < 1:
                raise ValueError("A merged purchasable quantity must be positive")
            interrupts.append(
                RequirementQuantityInterrupt(
                    interrupt_id=interrupt_id,
                    child_id=first.child_id,
                    canonical_item=first.canonical_item,
                    sources=sources,
                    default_quantity=default_quantity,
                )
            )
        merged.append(
            first.model_copy(
                update={
                    "quantity": quantity,
                    "quantity_is_range": False,
                    "quantity_max": None,
                    "sources": sources,
                }
            )
        )

    ordered = tuple(
        sorted(
            (*passthrough, *merged),
            key=lambda requirement: requirement.req_id,
        )
    )
    return RequirementMergeResult(
        requirements=ordered,
        interrupts=tuple(interrupts),
    )


def consolidate_extractions(
    extractions: Mapping[str, ExtractionEnvelope],
    *,
    quantity_choices: Mapping[str, int] | None = None,
) -> tuple[dict[str, ExtractionEnvelope], RequirementMergeResult]:
    """Merge production extraction envelopes without changing their metadata."""

    result = consolidate_requirements(
        (
            requirement
            for envelope in extractions.values()
            for requirement in envelope.requirements
        ),
        quantity_choices=quantity_choices,
    )
    requirements_by_child: dict[str, list[Requirement]] = {
        child_id: [] for child_id in extractions
    }
    for requirement in result.requirements:
        requirements_by_child.setdefault(requirement.child_id, []).append(
            requirement
        )
    return (
        {
            child_id: envelope.model_copy(
                update={
                    "requirements": tuple(
                        requirements_by_child.get(child_id, ())
                    )
                }
            )
            for child_id, envelope in extractions.items()
        },
        result,
    )
