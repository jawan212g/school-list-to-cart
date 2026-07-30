"""Deterministically consolidate duplicate same-student requirements."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
import re
from typing import Any, Literal

from agent.rules import (
    AMBIGUOUS_DESCRIPTOR_DEFAULT,
    CANONICAL_ITEM_ALIASES,
    CONFLICT_IDENTITY_DEFAULTS,
    CONFLICT_IDENTITY_DIFFERENT,
    CONFLICT_IDENTITY_SAME,
    INCIDENTAL_REQUIREMENT_ATTRIBUTE_FIELDS,
    PRODUCT_DEFINING_ATTRIBUTE_FIELDS,
    REQUIREMENT_ATTRIBUTE_EVIDENCE_WORDS,
    REQUIREMENT_DESCRIPTION_IGNORED_WORDS,
    REQUIREMENT_MERGE_CONFLICT_DEFAULT_ACTION,
    REQUIREMENT_CONSTRAINT_CONFLICT_ACTION,
    REQUIREMENT_ITEM_IDENTITY_FIELDS,
    REQUIREMENT_MERGE_ORIGIN_FIELDS,
    REQUIREMENT_SOURCE_DEDUPLICATION_FIELDS,
    SINGLE_INSTANCE_REQUIREMENT_ITEMS,
    SYSTEM_DECISION_CONSOLIDATED_SOURCES,
    SYSTEM_DECISION_MERGED_QUANTITY_PREFIX,
    SYSTEM_DECISION_PARENT_REVIEWED_DUPLICATE_SOURCES,
    SYSTEM_DECISION_AMBIGUOUS_DESCRIPTOR_PREFIX,
    SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX,
    SYSTEM_DECISION_RECONCILED_BRAND,
    SYSTEM_DECISION_RECONCILED_EXCLUSIONS,
    SAME_PRODUCT_OVERRIDE_SOURCE_PREFIX,
    parent_attribute_value,
    product_identity_rationale,
    requirement_quantity_default,
    same_product_override_rationale,
    source_item_description,
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
    combined_quantity: int
    plausible_annual_maximum: int
    variants: tuple[RequirementVariant, ...] = ()
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
    conflict_type: Literal[
        "quantity_only",
        "different_products",
        "ambiguous",
    ]
    default_identity: Literal["same", "different"]


@dataclass(frozen=True)
class ResolvedRequirementItemDecision:
    """One identity state consumed by rationale, radio, and quantities."""

    selected_identity: Literal["same", "different"]
    default_identity: Literal["same", "different"]
    is_preselected: bool
    show_identity_on_main: bool
    quantity_control: Literal["combined", "variants"]
    rationale: str | None
    state_fingerprint: str


def _description_tokens(requirement: Requirement) -> tuple[str, ...]:
    """Remove BR-43's non-identifying words from one source description."""

    tokens = set(
        re.findall(
            r"[a-z0-9]+",
            source_item_description(requirement.raw_text).casefold(),
        )
    )
    ignored = set(REQUIREMENT_DESCRIPTION_IGNORED_WORDS)
    ignored.update(
        token
        for token in requirement.canonical_item.casefold().split("_")
    )
    ignored.update(
        token.removesuffix("s")
        for token in tuple(ignored)
        if token.endswith("s")
    )
    for alias, canonical_item in CANONICAL_ITEM_ALIASES.items():
        if canonical_item != requirement.canonical_item:
            continue
        ignored.update(re.findall(r"[a-z0-9]+", alias.casefold()))
    ignored.update(REQUIREMENT_ATTRIBUTE_EVIDENCE_WORDS)
    for value in (
        requirement.brand_lock,
        requirement.brand_hint,
        *requirement.exclusions,
        *requirement.attributes.model_dump(exclude_none=True).values(),
    ):
        if isinstance(value, (tuple, list, set)):
            values = value
        else:
            values = (value,)
        for item in values:
            if item is None:
                continue
            ignored.update(re.findall(r"[a-z0-9]+", str(item).casefold()))
    return tuple(
        sorted(
            token
            for token in tokens
            if token not in ignored and not token.isdigit()
        )
    )


def _descriptions_need_identity_question(
    group: Sequence[Requirement],
) -> bool:
    """Apply BR-43 after product-defining constraints are reconciled."""

    descriptions = tuple(_description_tokens(requirement) for requirement in group)
    return len(set(descriptions)) > 1


def _decision_source_values(
    decision: RequirementItemDecision,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Return two source/value pairs for deterministic parent rationale."""

    for constraint in decision.constraint_interrupts:
        options = tuple(
            option
            for option in constraint.options
            if option.value not in (None, "", (), [])
        )
        if (
            constraint.field_name == "ambiguous_descriptor"
            or len(options) < 2
        ):
            continue
        pairs: list[tuple[str, str]] = []
        for index, option in enumerate(options[:2], start=1):
            source = option.sources[0] if option.sources else None
            source_name = (
                source.section_name
                if source is not None and source.section_name
                else source.document_name
                if source is not None and source.document_name
                else f"Source {index}"
            )
            pairs.append(
                (
                    source_name,
                    parent_attribute_value(
                        constraint.field_name,
                        option.value,
                    ),
                )
            )
        return pairs[0], pairs[1]
    return (
        ("Source 1", "one version"),
        ("Source 2", "another version"),
    )


def item_decision_state_fingerprint(
    decision: RequirementItemDecision,
) -> str:
    """Fingerprint the facts that determine BR-44's default state."""

    facts = (
        decision.decision_id,
        decision.conflict_type,
        decision.default_identity,
        tuple(
            (
                constraint.field_name,
                tuple(repr(option.value) for option in constraint.options),
            )
            for constraint in decision.constraint_interrupts
        ),
    )
    return sha256(repr(facts).encode("utf-8")).hexdigest()[:16]


def resolve_item_decision_state(
    decision: RequirementItemDecision,
    selected_identity: Literal["same", "different"] | None = None,
) -> ResolvedRequirementItemDecision:
    """Resolve every BR-44 consumer from one selected identity (FR-12)."""

    selected = selected_identity or decision.default_identity
    if selected not in {CONFLICT_IDENTITY_SAME, CONFLICT_IDENTITY_DIFFERENT}:
        raise ValueError("Unknown product identity")
    is_preselected = selected == decision.default_identity
    return ResolvedRequirementItemDecision(
        selected_identity=selected,
        default_identity=decision.default_identity,
        is_preselected=is_preselected,
        show_identity_on_main=(decision.conflict_type == "ambiguous"),
        quantity_control=(
            "variants"
            if selected == CONFLICT_IDENTITY_DIFFERENT
            else "combined"
        ),
        rationale=(
            product_identity_rationale(
                decision.conflict_type,
                decision.canonical_item.replace("_", " "),
                _decision_source_values(decision),
                tuple(
                    source_item_description(source.exact_line)
                    for source in decision.sources
                ),
            )
            if is_preselected
            else None
        ),
        state_fingerprint=item_decision_state_fingerprint(decision),
    )


def same_product_override_notice(
    decision: RequirementItemDecision,
) -> str | None:
    """Name BR-44's retained complete variant after a parent override."""

    if (
        decision.default_identity != CONFLICT_IDENTITY_DIFFERENT
        or not decision.variants
    ):
        return None
    retained = decision.variants[0]
    source = retained.sources[0] if retained.sources else None
    source_name = (
        source.section_name
        if source is not None and source.section_name
        else source.document_name
        if source is not None and source.document_name
        else "the first list section"
    )
    return same_product_override_rationale(source_name)


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
        conflict_type: Literal[
            "quantity_only",
            "different_products",
            "ambiguous",
        ] = (
            "ambiguous"
            if any(
                constraint.field_name == "ambiguous_descriptor"
                for constraint in constraints
            )
            else "different_products"
            if constraints
            else "quantity_only"
        )
        decisions.append(
            RequirementItemDecision(
                decision_id=decision_id,
                child_id=representative.child_id,
                canonical_item=representative.canonical_item,
                sources=sources,
                quantity_interrupt=quantity,
                constraint_interrupts=constraints,
                variants=(
                    constraints[0].variants
                    if constraints
                    else quantity.variants
                    if quantity is not None
                    else ()
                ),
                conflict_type=conflict_type,
                default_identity=CONFLICT_IDENTITY_DEFAULTS[conflict_type],
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
        str(brand_options[0].value)
        if len(brand_options) == 1
        else None
    )
    if len(set(brands)) > 1:
        system_decisions.append(SYSTEM_DECISION_RECONCILED_BRAND)

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
            colors = {
                str(color)
                for option in options
                if isinstance(option.value, (tuple, list, set))
                for color in option.value
            }
            if colors:
                merged_attributes[field_name] = tuple(sorted(colors))
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
        if field_name not in PRODUCT_DEFINING_ATTRIBUTE_FIELDS:
            if field_name not in INCIDENTAL_REQUIREMENT_ATTRIBUTE_FIELDS:
                # Unclassified details remain visible in provenance but do not
                # silently become a product identity rule.
                pass
            if field_name not in {"count", "binding"}:
                merged_attributes[field_name] = options[0].value
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

    ambiguous_values = tuple(
        dict.fromkeys(
            descriptor
            for requirement in group
            for descriptor in requirement.ambiguous_descriptors
        )
    )
    if ambiguous_values and any(
        not requirement.ambiguous_descriptors for requirement in group
    ):
        interrupt_id = _constraint_interrupt_id(
            group[0].child_id,
            identity,
            "ambiguous_descriptor",
        )
        conflicts.append(
            RequirementConstraintInterrupt(
                interrupt_id=interrupt_id,
                decision_id=_decision_id(group[0].child_id, identity),
                child_id=group[0].child_id,
                canonical_item=group[0].canonical_item,
                field_name="ambiguous_descriptor",
                options=tuple(
                    RequirementConstraintOption(
                        value=value,
                        sources=tuple(
                            source
                            for requirement in group
                            if (
                                requirement.ambiguous_descriptors[0]
                                if requirement.ambiguous_descriptors
                                else None
                            )
                            == value
                            for source in _source_for_requirement(requirement)
                        ),
                    )
                    for value in (
                        *ambiguous_values,
                        None,
                    )
                ),
            )
        )
        system_decisions.append(
            SYSTEM_DECISION_AMBIGUOUS_DESCRIPTOR_PREFIX
            + AMBIGUOUS_DESCRIPTOR_DEFAULT
        )
    if not conflicts and _descriptions_need_identity_question(group):
        descriptor_values = [
            " ".join(_description_tokens(requirement))
            or "general product wording"
            for requirement in group
        ]
        interrupt_id = _constraint_interrupt_id(
            group[0].child_id,
            identity,
            "ambiguous_descriptor",
        )
        conflicts.append(
            RequirementConstraintInterrupt(
                interrupt_id=interrupt_id,
                decision_id=_decision_id(group[0].child_id, identity),
                child_id=group[0].child_id,
                canonical_item=group[0].canonical_item,
                field_name="ambiguous_descriptor",
                options=_constraint_options(group, descriptor_values),
            )
        )
        system_decisions.append(
            SYSTEM_DECISION_AMBIGUOUS_DESCRIPTOR_PREFIX
            + AMBIGUOUS_DESCRIPTOR_DEFAULT
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
    if field_name == "ambiguous_descriptor":
        return (
            requirement.ambiguous_descriptors[0]
            if requirement.ambiguous_descriptors
            else " ".join(_description_tokens(requirement))
            or "general product wording"
        )
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
            else max(quantities)
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


def _build_source_variants(
    decision_id: str,
    group: list[Requirement],
) -> tuple[RequirementVariant, ...]:
    """Keep each source-backed row available when a parent chooses two kinds."""

    return tuple(
        RequirementVariant(
            variant_id=f"{decision_id}:variant-{index}",
            details=(),
            default_quantity=requirement.quantity,
            sources=_distinct_sources((requirement,)),
            brand_lock=requirement.brand_lock,
            exclusions=requirement.exclusions,
            attributes=requirement.attributes,
        )
        for index, requirement in enumerate(group, start=1)
    )


def _resolved_variant_requirements(
    first: Requirement,
    variants: tuple[RequirementVariant, ...],
    quantities: Mapping[str, int],
    all_sources: tuple[RequirementSource, ...],
    compatible_attributes: RequirementAttributes,
    compatible_brand: str | None,
    compatible_brand_hint: str | None,
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
        attributes = (
            variant.attributes.model_dump()
            if any(
                field_name == "ambiguous_descriptor"
                for field_name, _ in variant.details
            )
            else compatible_attributes.model_dump()
        )
        brand_lock = compatible_brand
        for field_name, value in variant.details:
            if field_name == "brand":
                brand_lock = (
                    str(value) if value not in (None, "") else None
                )
            elif field_name != "ambiguous_descriptor":
                attributes[field_name] = value
        resolved.append(
            first.model_copy(
                update={
                    "req_id": f"{first.req_id}:variant-{index}",
                    "quantity": quantity,
                    "quantity_is_range": False,
                    "quantity_max": None,
                    "sources": all_sources,
                    "variant_sources": variant.sources,
                    "product_variant_id": variant.variant_id,
                    "brand_lock": brand_lock,
                    "brand_hint": compatible_brand_hint,
                    "exclusions": tuple(
                        dict.fromkeys(
                            (*compatible_exclusions, *variant.exclusions)
                        )
                    ),
                    "attributes": RequirementAttributes.model_validate(
                        attributes
                    ),
                    "ambiguous_descriptors": (
                        (str(value),)
                        if (
                            value := next(
                                (
                                    detail_value
                                    for detail_name, detail_value in variant.details
                                    if detail_name == "ambiguous_descriptor"
                                ),
                                None,
                            )
                        )
                        not in (None, "")
                        else ()
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
    product_identity_choices: Mapping[
        str,
        Literal["same", "different"],
    ] | None = None,
    excluded_decision_ids: Iterable[str] = (),
) -> RequirementMergeResult:
    """Merge same-student duplicates and flag quantity conflicts (FR-14)."""

    choices = quantity_choices or {}
    active_constraint_choices = constraint_choices or {}
    active_variant_choices = variant_quantity_choices or {}
    active_identity_choices = product_identity_choices or {}
    excluded_ids = frozenset(excluded_decision_ids)
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
        brand_hint = next(
            (
                requirement.brand_hint
                for requirement in group
                if requirement.brand_hint
            ),
            None,
        )
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
        conflict_type = (
            "ambiguous"
            if any(
                interrupt.field_name == "ambiguous_descriptor"
                for interrupt in group_constraint_interrupts
            )
            else "different_products"
            if group_constraint_interrupts
            else "quantity_only"
        )
        default_identity = CONFLICT_IDENTITY_DEFAULTS[conflict_type]
        if decision_id in excluded_ids:
            continue
        selected_identity = active_identity_choices.get(
            decision_id,
            default_identity,
        )
        if selected_identity not in {
            CONFLICT_IDENTITY_SAME,
            CONFLICT_IDENTITY_DIFFERENT,
        }:
            raise ValueError("Unknown product-identity choice")
        if not variants:
            variants = _build_source_variants(decision_id, group)
        if (
            len(set(quantities)) == 1
            and not group_constraint_interrupts
            and first.canonical_item
            not in SINGLE_INSTANCE_REQUIREMENT_ITEMS
        ):
            quantity = quantities[0]
            quantity_interrupt = None
        else:
            interrupt_id = _interrupt_id(first.child_id, identity)
            quantity_default = requirement_quantity_default(
                first.canonical_item,
                quantities,
            )
            default_quantity = quantity_default.selected_quantity
            quantity = choices.get(interrupt_id, default_quantity)
            if quantity < 1:
                raise ValueError(
                    "A merged purchasable quantity must be positive"
                )
            quantity_interrupt = RequirementQuantityInterrupt(
                interrupt_id=interrupt_id,
                decision_id=decision_id,
                child_id=first.child_id,
                canonical_item=first.canonical_item,
                sources=sources,
                default_quantity=default_quantity,
                variants=variants,
                default_action=quantity_default.selected_action,
                combined_quantity=quantity_default.combined_quantity,
                plausible_annual_maximum=(
                    quantity_default.plausible_annual_maximum
                ),
            )
            interrupts.append(quantity_interrupt)
        system_decisions = tuple(
            dict.fromkeys(
                (
                    *first.system_decisions,
                    SYSTEM_DECISION_CONSOLIDATED_SOURCES,
                    *reconciliation_decisions,
                )
            )
        )
        if decision_id in active_identity_choices:
            system_decisions = tuple(
                dict.fromkeys(
                    (
                        *system_decisions,
                        SYSTEM_DECISION_PARENT_REVIEWED_DUPLICATE_SOURCES,
                    )
                )
            )
        if selected_identity != default_identity:
            system_decisions = tuple(
                decision
                for decision in system_decisions
                if not decision.startswith(
                    SYSTEM_DECISION_AMBIGUOUS_DESCRIPTOR_PREFIX
                )
            )
        if (
            selected_identity == CONFLICT_IDENTITY_DIFFERENT
            and decision_id in active_variant_choices
        ):
            merged.extend(
                _resolved_variant_requirements(
                    first,
                    variants,
                    active_variant_choices[decision_id],
                    sources,
                    attributes,
                    brand_lock,
                    brand_hint,
                    exclusions,
                    system_decisions,
                )
            )
            continue
        if selected_identity == CONFLICT_IDENTITY_DIFFERENT:
            merged.extend(
                _resolved_variant_requirements(
                    first,
                    variants,
                    {
                        variant.variant_id: variant.default_quantity
                        for variant in variants
                    },
                    sources,
                    attributes,
                    brand_lock,
                    brand_hint,
                    exclusions,
                    system_decisions,
                )
            )
            continue
        if (
            default_identity == CONFLICT_IDENTITY_DIFFERENT
            and selected_identity == CONFLICT_IDENTITY_SAME
        ):
            retained_variant = variants[0]
            brand_lock = retained_variant.brand_lock
            exclusions = retained_variant.exclusions
            attributes = retained_variant.attributes
            retained_source_id = (
                retained_variant.sources[0].source_req_id
                if retained_variant.sources
                else retained_variant.variant_id
            )
            system_decisions = tuple(
                dict.fromkeys(
                    (
                        *system_decisions,
                        SAME_PRODUCT_OVERRIDE_SOURCE_PREFIX
                        + retained_source_id,
                    )
                )
            )
        if quantity_interrupt is not None:
            system_decisions = tuple(
                dict.fromkeys(
                    (
                        *system_decisions,
                        f"{SYSTEM_DECISION_MERGED_QUANTITY_PREFIX}{quantity}",
                    )
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
                    "brand_hint": brand_hint,
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
    product_identity_choices: Mapping[
        str,
        Literal["same", "different"],
    ] | None = None,
    excluded_decision_ids: Iterable[str] = (),
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
        product_identity_choices=product_identity_choices,
        excluded_decision_ids=excluded_decision_ids,
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
