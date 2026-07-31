"""Deterministically aggregate extracted requirements into unit needs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent.normalize import NormalizedRequirement
from agent.rules import (
    CATEGORY_IMPLIED_ATTRIBUTE_TERMS,
    CATEGORY_IMPLIED_EXCLUSION_TERMS,
    CLASSROOM_INDIVIDUAL_SCOPE,
    CLASSROOM_SHARED_SCOPE,
)
from agent.schema import Requirement


@dataclass(frozen=True)
class UnitNeed:
    """An aggregated purchasable need with child-level unit attribution."""

    canonical_item: str
    quantity: int
    brand_lock: str | None
    unit_type: str
    exclusions: tuple[str, ...]
    is_required: bool
    attributes: Mapping[str, Any]
    allocated_to: Mapping[str, int]
    source_requirement_ids: tuple[str, ...]
    product_variant_id: str | None = None

    @property
    def label(self) -> str:
        """Return a stable human-readable identifier for gaps and decisions."""

        if self.brand_lock is None:
            return self.canonical_item
        return f"{self.canonical_item} ({self.brand_lock})"


@dataclass
class _NeedAccumulator:
    canonical_item: str
    brand_lock: str | None
    unit_type: str
    exclusions: tuple[str, ...]
    is_required: bool
    attributes: Mapping[str, Any]
    quantity: int = 0
    allocated_to: dict[str, int] = field(default_factory=dict)
    source_requirement_ids: list[str] = field(default_factory=list)
    product_variant_id: str | None = None


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            sorted((str(key), _freeze(item)) for key, item in value.items())
        )
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _normalized_brand(brand_lock: str | None) -> str | None:
    if brand_lock is None:
        return None
    normalized = brand_lock.strip()
    return normalized.casefold() if normalized else None


def _normalized_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _effective_exclusions(
    canonical_item: str,
    exclusions: Iterable[str],
) -> tuple[str, ...]:
    implied_terms = CATEGORY_IMPLIED_EXCLUSION_TERMS.get(
        canonical_item,
        frozenset(),
    )
    normalized = []
    for exclusion in exclusions:
        text = _normalized_text(exclusion)
        if any(term in text for term in implied_terms):
            continue
        normalized.append(text)
    return tuple(sorted(normalized))


def _effective_attributes(
    canonical_item: str,
    attributes: Mapping[str, Any],
) -> dict[str, Any]:
    effective = dict(attributes)
    effective.pop("binding", None)
    implied_terms = CATEGORY_IMPLIED_ATTRIBUTE_TERMS.get(
        canonical_item,
        frozenset(),
    )
    for field_name in ("style", "other_details"):
        value = effective.get(field_name)
        if value is None:
            continue
        text = _normalized_text(value)
        if any(term in text for term in implied_terms):
            effective.pop(field_name)
    return effective


def normalized_requirement_identity(
    item: Requirement | NormalizedRequirement,
) -> tuple[Any, ...]:
    """Return the same normalized identity used for aggregation (FR-14)."""

    if isinstance(item, NormalizedRequirement):
        requirement = item.source
        canonical_item = item.canonical_item
        unit_type = item.unit_type
        requirement_attributes = _effective_attributes(
            canonical_item,
            item.attributes,
        )
    else:
        requirement = item
        canonical_item = requirement.canonical_item
        unit_type = requirement.unit_type
        requirement_attributes = _effective_attributes(
            canonical_item,
            requirement.attributes.model_dump(exclude_none=True),
        )
    return (
        canonical_item,
        _normalized_brand(requirement.brand_lock),
        unit_type,
        _effective_exclusions(canonical_item, requirement.exclusions),
        requirement.is_required,
        _freeze(requirement_attributes),
        requirement.product_variant_id,
    )


def aggregate_requirements(
    requirements: Iterable[Requirement | NormalizedRequirement],
    *,
    student_counts_by_child: Mapping[str, int] | None = None,
) -> tuple[UnitNeed, ...]:
    """Roll up needs and retain child attribution (FR-14, FR-15, FR-16)."""

    grouped: dict[tuple[Any, ...], _NeedAccumulator] = {}
    student_counts = student_counts_by_child or {}

    for item in requirements:
        if isinstance(item, NormalizedRequirement):
            requirement = item.source
            is_purchasable = item.is_cart_eligible
            canonical_item = item.canonical_item
            quantity = item.quantity
            unit_type = item.unit_type
            requirement_attributes = _effective_attributes(
                canonical_item,
                item.attributes,
            )
        else:
            requirement = item
            is_purchasable = requirement.is_purchasable
            canonical_item = requirement.canonical_item
            quantity = requirement.quantity
            unit_type = requirement.unit_type
            requirement_attributes = _effective_attributes(
                canonical_item,
                requirement.attributes.model_dump(exclude_none=True),
            )

        if not is_purchasable:
            continue
        if quantity <= 0:
            raise ValueError(
                f"Requirement {requirement.req_id} must have positive quantity"
            )
        student_count = student_counts.get(requirement.child_id, 1)
        if student_count <= 0:
            raise ValueError("Classroom student counts must be positive")
        if (
            student_count > 1
            and requirement.supply_scope
            not in {
                CLASSROOM_INDIVIDUAL_SCOPE,
                CLASSROOM_SHARED_SCOPE,
            }
        ):
            raise ValueError(
                "Choose whether classroom quantities apply to each student "
                "or to the whole class before building the cart."
            )
        if requirement.supply_scope != CLASSROOM_SHARED_SCOPE:
            quantity *= student_count

        key = normalized_requirement_identity(item)
        normalized_brand = key[1]
        normalized_exclusions = key[3]
        accumulator = grouped.get(key)
        if accumulator is None:
            preserved_brand = (
                requirement.brand_lock.strip()
                if requirement.brand_lock is not None
                else None
            )
            accumulator = _NeedAccumulator(
                canonical_item=canonical_item,
                brand_lock=preserved_brand,
                unit_type=unit_type,
                exclusions=normalized_exclusions,
                is_required=requirement.is_required,
                attributes=requirement_attributes,
                product_variant_id=requirement.product_variant_id,
            )
            grouped[key] = accumulator

        accumulator.quantity += quantity
        accumulator.allocated_to[requirement.child_id] = (
            accumulator.allocated_to.get(requirement.child_id, 0)
            + quantity
        )
        accumulator.source_requirement_ids.append(requirement.req_id)

    return tuple(
        UnitNeed(
            canonical_item=accumulator.canonical_item,
            quantity=accumulator.quantity,
            brand_lock=accumulator.brand_lock,
            unit_type=accumulator.unit_type,
            exclusions=accumulator.exclusions,
            is_required=accumulator.is_required,
            attributes=accumulator.attributes,
            allocated_to=dict(accumulator.allocated_to),
            source_requirement_ids=tuple(accumulator.source_requirement_ids),
            product_variant_id=accumulator.product_variant_id,
        )
        for accumulator in grouped.values()
    )
