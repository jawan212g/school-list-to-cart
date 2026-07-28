"""Deterministically consolidate duplicate same-student requirements."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from agent.rules import (
    REQUIREMENT_MERGE_CONFLICT_DEFAULT_ACTION,
    REQUIREMENT_CONSTRAINT_CONFLICT_ACTION,
    REQUIREMENT_ITEM_IDENTITY_FIELDS,
    REQUIREMENT_SOURCE_DEDUPLICATION_FIELDS,
)
from agent.schema import (
    ExtractionEnvelope,
    Requirement,
    RequirementAttributes,
    RequirementSource,
)


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
class RequirementConstraintOption:
    """One source-backed value for a conflicting requirement constraint."""

    value: object
    sources: tuple[RequirementSource, ...]


@dataclass(frozen=True)
class RequirementConstraintInterrupt:
    """One incompatible same-item constraint needing a parent choice."""

    interrupt_id: str
    child_id: str
    canonical_item: str
    field_name: str
    options: tuple[RequirementConstraintOption, ...]
    action: str = REQUIREMENT_CONSTRAINT_CONFLICT_ACTION


@dataclass(frozen=True)
class RequirementMergeResult:
    """Consolidated requirements plus unresolved quantity choices."""

    requirements: tuple[Requirement, ...]
    interrupts: tuple[RequirementQuantityInterrupt, ...]
    constraint_interrupts: tuple[RequirementConstraintInterrupt, ...] = ()


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
    return tuple(
        getattr(requirement, field_name)
        for field_name in REQUIREMENT_ITEM_IDENTITY_FIELDS
    )


def _interrupt_id(
    child_id: str,
    identity: tuple[Any, ...],
) -> str:
    digest = sha256(repr(identity).encode("utf-8")).hexdigest()[:12]
    return f"quantity-merge:{child_id}:{digest}"


def _constraint_interrupt_id(
    child_id: str,
    identity: tuple[Any, ...],
    field_name: str,
) -> str:
    digest = sha256(
        repr((identity, field_name)).encode("utf-8")
    ).hexdigest()[:12]
    return f"constraint-merge:{child_id}:{digest}"


def _source_for_requirement(
    requirement: Requirement,
) -> tuple[RequirementSource, ...]:
    return requirement.sources or (requirement_source(requirement),)


def _constraint_options(
    group: list[Requirement],
    values: list[object],
) -> tuple[RequirementConstraintOption, ...]:
    grouped: list[tuple[object, list[RequirementSource]]] = []
    for requirement, value in zip(group, values, strict=True):
        if value in (None, (), ""):
            continue
        existing = next(
            (
                sources
                for prior, sources in grouped
                if prior == value
            ),
            None,
        )
        if existing is None:
            grouped.append((value, list(_source_for_requirement(requirement))))
        else:
            existing.extend(_source_for_requirement(requirement))
    return tuple(
        RequirementConstraintOption(
            value=value,
            sources=tuple(dict.fromkeys(sources)),
        )
        for value, sources in grouped
    )


def _reconcile_constraints(
    identity: tuple[Any, ...],
    group: list[Requirement],
    choices: Mapping[str, object],
) -> tuple[
    str | None,
    tuple[str, ...],
    RequirementAttributes,
    tuple[RequirementConstraintInterrupt, ...],
]:
    conflicts: list[RequirementConstraintInterrupt] = []
    brands = [requirement.brand_lock for requirement in group]
    brand_options = _constraint_options(group, brands)
    brand_lock = (
        str(brand_options[0].value) if brand_options else None
    )
    if len(brand_options) > 1:
        interrupt_id = _constraint_interrupt_id(
            group[0].child_id,
            identity,
            "brand",
        )
        conflicts.append(
            RequirementConstraintInterrupt(
                interrupt_id=interrupt_id,
                child_id=group[0].child_id,
                canonical_item=group[0].canonical_item,
                field_name="brand",
                options=brand_options,
            )
        )
        if interrupt_id in choices:
            brand_lock = str(choices[interrupt_id])

    merged_attributes: dict[str, object] = {}
    attribute_rows = [
        requirement.attributes.model_dump(exclude_none=True)
        for requirement in group
    ]
    for field_name in RequirementAttributes.model_fields:
        values = [
            attributes.get(field_name)
            for attributes in attribute_rows
        ]
        options = _constraint_options(group, values)
        if not options:
            continue
        if field_name == "acceptable_colors":
            sets = [
                set(option.value)
                for option in options
                if isinstance(option.value, (tuple, list, set))
            ]
            common = set.intersection(*sets) if sets else set()
            if common:
                merged_attributes[field_name] = tuple(sorted(common))
                continue
        if len(options) == 1:
            merged_attributes[field_name] = options[0].value
            continue
        interrupt_id = _constraint_interrupt_id(
            group[0].child_id,
            identity,
            field_name,
        )
        conflicts.append(
            RequirementConstraintInterrupt(
                interrupt_id=interrupt_id,
                child_id=group[0].child_id,
                canonical_item=group[0].canonical_item,
                field_name=field_name,
                options=options,
            )
        )
        merged_attributes[field_name] = choices.get(
            interrupt_id,
            options[0].value,
        )

    exclusions = tuple(
        dict.fromkeys(
            exclusion
            for requirement in group
            for exclusion in requirement.exclusions
        )
    )
    return (
        brand_lock,
        exclusions,
        RequirementAttributes.model_validate(merged_attributes),
        tuple(conflicts),
    )


def consolidate_requirements(
    requirements: Iterable[Requirement],
    *,
    quantity_choices: Mapping[str, int] | None = None,
    constraint_choices: Mapping[str, object] | None = None,
) -> RequirementMergeResult:
    """Merge same-student duplicates and flag quantity conflicts (FR-14)."""

    choices = quantity_choices or {}
    active_constraint_choices = constraint_choices or {}
    grouped: dict[tuple[Any, ...], list[Requirement]] = {}
    passthrough: list[Requirement] = []
    for requirement in requirements:
        if not requirement.is_purchasable:
            passthrough.append(requirement)
            continue
        grouped.setdefault(_merge_identity(requirement), []).append(requirement)

    merged: list[Requirement] = []
    interrupts: list[RequirementQuantityInterrupt] = []
    constraint_interrupts: list[RequirementConstraintInterrupt] = []
    for identity, group in grouped.items():
        first = group[0]
        sources = _distinct_sources(group)
        quantities = tuple(requirement.quantity for requirement in group)
        if len(group) == 1:
            merged.append(first.model_copy(update={"sources": sources}))
            continue
        (
            brand_lock,
            exclusions,
            attributes,
            group_constraint_interrupts,
        ) = _reconcile_constraints(
            identity,
            group,
            active_constraint_choices,
        )
        constraint_interrupts.extend(group_constraint_interrupts)
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
                    "brand_lock": brand_lock,
                    "exclusions": exclusions,
                    "attributes": attributes,
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
        constraint_interrupts=tuple(constraint_interrupts),
    )


def consolidate_extractions(
    extractions: Mapping[str, ExtractionEnvelope],
    *,
    quantity_choices: Mapping[str, int] | None = None,
    constraint_choices: Mapping[str, object] | None = None,
) -> tuple[dict[str, ExtractionEnvelope], RequirementMergeResult]:
    """Merge production extraction envelopes without changing their metadata."""

    result = consolidate_requirements(
        (
            requirement
            for envelope in extractions.values()
            for requirement in envelope.requirements
        ),
        quantity_choices=quantity_choices,
        constraint_choices=constraint_choices,
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
