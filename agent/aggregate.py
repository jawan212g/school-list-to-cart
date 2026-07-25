"""Deterministically aggregate extracted requirements into unit needs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

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


def aggregate_requirements(
    requirements: Iterable[Requirement],
) -> tuple[UnitNeed, ...]:
    """Roll up needs and retain child attribution (FR-14, FR-15, FR-16)."""

    grouped: dict[tuple[Any, ...], _NeedAccumulator] = {}

    for requirement in requirements:
        if not requirement.is_purchasable:
            continue
        if requirement.quantity <= 0:
            raise ValueError(
                f"Requirement {requirement.req_id} must have positive quantity"
            )

        normalized_brand = _normalized_brand(requirement.brand_lock)
        requirement_attributes = requirement.attributes.model_dump(
            exclude_none=True
        )
        normalized_exclusions = tuple(
            sorted(exclusion.strip().casefold() for exclusion in requirement.exclusions)
        )
        key = (
            requirement.canonical_item,
            normalized_brand,
            requirement.unit_type,
            normalized_exclusions,
            requirement.is_required,
            _freeze(requirement_attributes),
        )
        accumulator = grouped.get(key)
        if accumulator is None:
            preserved_brand = (
                requirement.brand_lock.strip()
                if requirement.brand_lock is not None
                else None
            )
            accumulator = _NeedAccumulator(
                canonical_item=requirement.canonical_item,
                brand_lock=preserved_brand,
                unit_type=requirement.unit_type,
                exclusions=tuple(requirement.exclusions),
                is_required=requirement.is_required,
                attributes=requirement_attributes,
            )
            grouped[key] = accumulator

        accumulator.quantity += requirement.quantity
        accumulator.allocated_to[requirement.child_id] = (
            accumulator.allocated_to.get(requirement.child_id, 0)
            + requirement.quantity
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
        )
        for accumulator in grouped.values()
    )
