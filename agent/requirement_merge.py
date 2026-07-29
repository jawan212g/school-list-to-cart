"""Deterministically consolidate duplicate same-student requirements."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any

from agent.rules import (
    REQUIREMENT_MERGE_CONFLICT_DEFAULT_ACTION,
    REQUIREMENT_CONSTRAINT_CONFLICT_ACTION,
    REQUIREMENT_ITEM_IDENTITY_FIELDS,
    REQUIREMENT_MERGE_ORIGIN_FIELDS,
    REQUIREMENT_SOURCE_DEDUPLICATION_FIELDS,
    SYSTEM_DECISION_CONSOLIDATED_SOURCES,
    SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX,
    SYSTEM_DECISION_RECONCILED_BRAND,
    SYSTEM_DECISION_RECONCILED_EXCLUSIONS,
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
    decision_id: str
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
class RequirementVariant:
    """One complete source-backed variant and its requested quantity."""

    variant_id: str
    details: tuple[tuple[str, object], ...]
    default_quantity: int
    sources: tuple[RequirementSource, ...]
    brand_lock: str | None
    exclusions: tuple[str, ...]
    attributes: RequirementAttributes


@dataclass(frozen=True)
class RequirementConstraintInterrupt:
    """One incompatible same-item constraint needing a parent choice."""

    interrupt_id: str
    decision_id: str
    child_id: str
    canonical_item: str
    field_name: str
    options: tuple[RequirementConstraintOption, ...]
    variants: tuple[RequirementVariant, ...] = ()
    action: str = REQUIREMENT_CONSTRAINT_CONFLICT_ACTION


@dataclass(frozen=True)
class RequirementMergeResult:
    """Consolidated requirements plus unresolved quantity choices."""

    requirements: tuple[Requirement, ...]
    interrupts: tuple[RequirementQuantityInterrupt, ...]
    constraint_interrupts: tuple[RequirementConstraintInterrupt, ...] = ()


@dataclass(frozen=True)
class RequirementItemDecision:
    """Every open quantity and detail question for one merged item."""

    decision_id: str
    child_id: str
    canonical_item: str
    sources: tuple[RequirementSource, ...]
    quantity_interrupt: RequirementQuantityInterrupt | None
    constraint_interrupts: tuple[RequirementConstraintInterrupt, ...]
    variants: tuple[RequirementVariant, ...]


def item_decisions(
    result: RequirementMergeResult,
) -> tuple[RequirementItemDecision, ...]:
    """Group all open questions into one card per item (FR-12)."""

    decision_ids = tuple(
        dict.fromkeys(
            (
                *(
                    interrupt.decision_id
                    for interrupt in result.interrupts
                ),
                *(
                    interrupt.decision_id
                    for interrupt in result.constraint_interrupts
                ),
            )
        )
    )
    decisions: list[RequirementItemDecision] = []
    for decision_id in decision_ids:
        quantity = next(
            (
                interrupt
                for interrupt in result.interrupts
                if interrupt.decision_id == decision_id
            ),
            None,
        )
        constraints = tuple(
            interrupt
            for interrupt in result.constraint_interrupts
            if interrupt.decision_id == decision_id
        )
        representative = quantity or constraints[0]
        sources = (
            quantity.sources
            if quantity is not None
            else _distinct_option_sources(constraints)
        )
        decisions.append(
            RequirementItemDecision(
                decision_id=decision_id,
                child_id=representative.child_id,
                canonical_item=representative.canonical_item,
                sources=sources,
                quantity_interrupt=quantity,
                constraint_interrupts=constraints,
                variants=constraints[0].variants if constraints else (),
            )
        )
    return tuple(decisions)


def _distinct_option_sources(
    constraints: tuple[RequirementConstraintInterrupt, ...],
) -> tuple[RequirementSource, ...]:
    sources: list[RequirementSource] = []
    for constraint in constraints:
        for option in constraint.options:
            for source in option.sources:
                if source not in sources:
                    sources.append(source)
    return tuple(sources)


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


def _requirement_origins(
    requirement: Requirement,
) -> frozenset[tuple[str | None, str | None]]:
    """Return the BR-27 document-section origins represented by one row."""

    sources = requirement.sources or (requirement_source(requirement),)
    return frozenset(
        tuple(
            getattr(source, field_name)
            for field_name in REQUIREMENT_MERGE_ORIGIN_FIELDS
        )
        for source in sources
    )


def _section_scoped_groups(
    requirements: list[Requirement],
) -> tuple[list[Requirement], ...]:
    """Keep repeated rows from one section additive under BR-27."""

    groups: list[list[Requirement]] = []
    origins_by_group: list[set[tuple[str | None, str | None]]] = []
    for requirement in requirements:
        origins = set(_requirement_origins(requirement))
        destination = next(
            (
                index
                for index, prior_origins in enumerate(origins_by_group)
                if origins.isdisjoint(prior_origins)
            ),
            None,
        )
        if destination is None:
            groups.append([requirement])
            origins_by_group.append(origins)
        else:
            groups[destination].append(requirement)
            origins_by_group[destination].update(origins)
    return tuple(groups)


def _decision_id(
    child_id: str,
    identity: tuple[Any, ...],
) -> str:
    digest = sha256(repr(identity).encode("utf-8")).hexdigest()[:12]
    return f"requirement-merge:{child_id}:{digest}"


def _interrupt_id(
    child_id: str,
    identity: tuple[Any, ...],
) -> str:
    return _decision_id(child_id, identity).replace(
        "requirement-merge",
        "quantity-merge",
        1,
    )


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
    tuple[str, ...],
]:
    conflicts: list[RequirementConstraintInterrupt] = []
    system_decisions: list[str] = []
    brands = [requirement.brand_lock for requirement in group]
    brand_options = _constraint_options(group, brands)
    brand_lock = (
        str(brand_options[0].value) if brand_options else None
    )
    if len(brand_options) == 1 and len(set(brands)) > 1:
        system_decisions.append(SYSTEM_DECISION_RECONCILED_BRAND)
    if len(brand_options) > 1:
        interrupt_id = _constraint_interrupt_id(
            group[0].child_id,
            identity,
            "brand",
        )
        conflicts.append(
            RequirementConstraintInterrupt(
                interrupt_id=interrupt_id,
                decision_id=_decision_id(group[0].child_id, identity),
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
                if len(options) > 1:
                    system_decisions.append(
                        SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX + field_name
                    )
                continue
        if len(options) == 1:
            merged_attributes[field_name] = options[0].value
            if len(set(map(repr, values))) > 1:
                system_decisions.append(
                    SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX + field_name
                )
            continue
        interrupt_id = _constraint_interrupt_id(
            group[0].child_id,
            identity,
            field_name,
        )
        conflicts.append(
            RequirementConstraintInterrupt(
                interrupt_id=interrupt_id,
                decision_id=_decision_id(group[0].child_id, identity),
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
    if len({requirement.exclusions for requirement in group}) > 1:
        system_decisions.append(SYSTEM_DECISION_RECONCILED_EXCLUSIONS)
    return (
        brand_lock,
        exclusions,
        RequirementAttributes.model_validate(merged_attributes),
        tuple(conflicts),
        tuple(dict.fromkeys(system_decisions)),
    )


def _variant_value(
    requirement: Requirement,
    field_name: str,
) -> object:
    if field_name == "brand":
        return requirement.brand_lock
    return getattr(requirement.attributes, field_name)


def _build_variants(
    decision_id: str,
    group: list[Requirement],
    conflicts: tuple[RequirementConstraintInterrupt, ...],
) -> tuple[RequirementVariant, ...]:
    """Build complete variants so the parent can allocate quantities."""

    field_names = tuple(
        dict.fromkeys(conflict.field_name for conflict in conflicts)
    )
    grouped: dict[
        tuple[tuple[str, object], ...],
        list[Requirement],
    ] = {}
    for requirement in group:
        details = tuple(
            (field_name, _variant_value(requirement, field_name))
            for field_name in field_names
        )
        grouped.setdefault(details, []).append(requirement)

    variants: list[RequirementVariant] = []
    for index, (details, members) in enumerate(grouped.items(), start=1):
        quantities = tuple(member.quantity for member in members)
        default_quantity = (
            quantities[0]
            if len(set(quantities)) == 1
            else sum(quantities)
        )
        representative = members[0]
        variants.append(
            RequirementVariant(
                variant_id=f"{decision_id}:variant-{index}",
                details=details,
                default_quantity=default_quantity,
                sources=_distinct_sources(members),
                brand_lock=representative.brand_lock,
                exclusions=tuple(
                    dict.fromkeys(
                        exclusion
                        for member in members
                        for exclusion in member.exclusions
                    )
                ),
                attributes=representative.attributes,
            )
        )
    return tuple(variants)


def _resolved_variant_requirements(
    first: Requirement,
    variants: tuple[RequirementVariant, ...],
    quantities: Mapping[str, int],
    compatible_attributes: RequirementAttributes,
    compatible_brand: str | None,
    compatible_exclusions: tuple[str, ...],
    system_decisions: tuple[str, ...],
) -> tuple[Requirement, ...]:
    """Apply parent-entered variant quantities to production requirements."""

    resolved: list[Requirement] = []
    for index, variant in enumerate(variants, start=1):
        quantity = int(
            quantities.get(variant.variant_id, variant.default_quantity)
        )
        if quantity < 0:
            raise ValueError("A variant quantity cannot be negative")
        if quantity == 0:
            continue
        attributes = compatible_attributes.model_dump()
        brand_lock = compatible_brand
        for field_name, value in variant.details:
            if field_name == "brand":
                brand_lock = (
                    str(value) if value not in (None, "") else None
                )
            else:
                attributes[field_name] = value
        resolved.append(
            first.model_copy(
                update={
                    "req_id": f"{first.req_id}:variant-{index}",
                    "quantity": quantity,
                    "quantity_is_range": False,
                    "quantity_max": None,
                    "sources": variant.sources,
                    "brand_lock": brand_lock,
                    "exclusions": tuple(
                        dict.fromkeys(
                            (*compatible_exclusions, *variant.exclusions)
                        )
                    ),
                    "attributes": RequirementAttributes.model_validate(
                        attributes
                    ),
                    "system_decisions": system_decisions,
                }
            )
        )
    if not resolved:
        raise ValueError("At least one variant must have a quantity")
    return tuple(resolved)


def consolidate_requirements(
    requirements: Iterable[Requirement],
    *,
    quantity_choices: Mapping[str, int] | None = None,
    constraint_choices: Mapping[str, object] | None = None,
    variant_quantity_choices: Mapping[
        str,
        Mapping[str, int],
    ] | None = None,
) -> RequirementMergeResult:
    """Merge same-student duplicates and flag quantity conflicts (FR-14)."""

    choices = quantity_choices or {}
    active_constraint_choices = constraint_choices or {}
    active_variant_choices = variant_quantity_choices or {}
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
    scoped_groups = tuple(
        (
            (*identity, "section-occurrence", occurrence),
            group,
        )
        for identity, requirements_for_item in grouped.items()
        for occurrence, group in enumerate(
            _section_scoped_groups(requirements_for_item),
            start=1,
        )
    )
    for identity, group in scoped_groups:
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
            reconciliation_decisions,
        ) = _reconcile_constraints(
            identity,
            group,
            active_constraint_choices,
        )
        decision_id = _decision_id(first.child_id, identity)
        variants = (
            _build_variants(
                decision_id,
                group,
                group_constraint_interrupts,
            )
            if group_constraint_interrupts
            else ()
        )
        group_constraint_interrupts = tuple(
            replace(interrupt, variants=variants)
            for interrupt in group_constraint_interrupts
        )
        constraint_interrupts.extend(group_constraint_interrupts)
        system_decisions = tuple(
            dict.fromkeys(
                (
                    *first.system_decisions,
                    SYSTEM_DECISION_CONSOLIDATED_SOURCES,
                    *reconciliation_decisions,
                )
            )
        )
        if variants and decision_id in active_variant_choices:
            merged.extend(
                _resolved_variant_requirements(
                    first,
                    variants,
                    active_variant_choices[decision_id],
                    attributes,
                    brand_lock,
                    exclusions,
                    system_decisions,
                )
            )
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
                    decision_id=decision_id,
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
                    "system_decisions": system_decisions,
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
    variant_quantity_choices: Mapping[
        str,
        Mapping[str, int],
    ] | None = None,
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
        variant_quantity_choices=variant_quantity_choices,
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
