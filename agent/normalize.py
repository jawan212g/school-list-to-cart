"""Deterministic canonicalization, unit conversion, and cart scoping."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from agent.rules import (
    ALLOWED_CATEGORIES,
    CANONICAL_ITEM_ALIASES,
    CONFIDENCE_FLOOR,
    COUNT_BASED_CATEGORIES,
    NON_PURCHASABLE_CATEGORY,
    PAPER_CATEGORIES,
    REAM_SHEET_COUNT,
    STANDARD_CONTAINER_CONTENT_COUNTS,
    STANDARD_PACK_COUNTS,
)
from agent.schema import AttributeValue, Requirement, UnitType


@dataclass(frozen=True)
class NormalizedRequirement:
    """A deterministic cart-ready or display-only requirement."""

    source: Requirement
    canonical_item: str
    quantity: int
    quantity_is_range: bool
    quantity_max: int | None
    unit_type: UnitType
    attributes: Mapping[str, AttributeValue]
    assumption_flags: tuple[str, ...]
    is_cart_eligible: bool
    is_budget_eligible: bool
    is_display_only: bool
    manual_review_required: bool
    review_deferred: bool


@dataclass(frozen=True)
class NormalizationResult:
    """All normalized lines partitioned without losing display-only content."""

    requirements: tuple[NormalizedRequirement, ...]

    @property
    def cart_requirements(self) -> tuple[NormalizedRequirement, ...]:
        """Return every purchasable line that may enter a cart."""

        return tuple(
            requirement
            for requirement in self.requirements
            if requirement.is_cart_eligible
        )

    @property
    def budget_requirements(self) -> tuple[NormalizedRequirement, ...]:
        """Return required purchasable lines included in the base budget."""

        return tuple(
            requirement
            for requirement in self.requirements
            if requirement.is_budget_eligible
        )

    @property
    def display_only_requirements(self) -> tuple[NormalizedRequirement, ...]:
        """Return lines preserved for display but excluded from cart scope."""

        return tuple(
            requirement
            for requirement in self.requirements
            if requirement.is_display_only
        )

    @property
    def manual_review_requirements(self) -> tuple[NormalizedRequirement, ...]:
        """Return lines that interrupt the required-item cart now (BR-10)."""

        return tuple(
            requirement
            for requirement in self.requirements
            if requirement.manual_review_required
        )

    @property
    def deferred_review_requirements(self) -> tuple[NormalizedRequirement, ...]:
        """Return optional/donation reviews held until add-on selection (BR-10)."""

        return tuple(
            requirement
            for requirement in self.requirements
            if requirement.review_deferred
        )

    def review_requirements_for(
        self,
        selected_add_on_ids: Iterable[str] = (),
    ) -> tuple[NormalizedRequirement, ...]:
        """Activate deferred reviews only for selected add-ons (FR-09, BR-10)."""

        selected = frozenset(selected_add_on_ids)
        return tuple(
            requirement
            for requirement in self.requirements
            if requirement.manual_review_required
            or (
                requirement.review_deferred
                and requirement.source.req_id in selected
            )
        )


def canonicalize_item_name(item_name: str) -> str | None:
    """Map a model-extracted item name to the category allowlist."""

    token = re.sub(
        r"[^a-z0-9#]+",
        "_",
        item_name.casefold().strip(),
    ).strip("_")
    canonical = CANONICAL_ITEM_ALIASES.get(token, token)
    return canonical if canonical in ALLOWED_CATEGORIES else None


def _explicit_count(attributes: Mapping[str, AttributeValue]) -> int | None:
    for key in ("count", "pack_count", "box_count", "items_per_pack"):
        value = attributes.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            parsed = int(value)
            if parsed > 0:
                return parsed
    return None


def normalize_requirement(requirement: Requirement) -> NormalizedRequirement:
    """Normalize one line while preserving review evidence (FR-10, FR-11)."""

    flags: list[str] = []
    attributes = requirement.attributes.model_dump(exclude_none=True)
    canonical_item = (
        NON_PURCHASABLE_CATEGORY
        if not requirement.is_purchasable
        else canonicalize_item_name(requirement.canonical_item)
    )
    low_confidence = (
        Decimal(str(requirement.extraction_confidence)) < CONFIDENCE_FLOOR
    )
    manual_review_required = (
        low_confidence
        and requirement.is_purchasable
        and requirement.is_required
    )
    review_deferred = (
        low_confidence
        and requirement.is_purchasable
        and not requirement.is_required
    )

    if requirement.is_purchasable and canonical_item is None:
        canonical_item = requirement.canonical_item
        flags.append("category_not_allowed")
        if requirement.is_required:
            manual_review_required = True
        else:
            review_deferred = True

    quantity = requirement.quantity
    quantity_max = requirement.quantity_max
    normalized_unit = requirement.unit_type

    if requirement.quantity_is_range:
        flags.append("quantity_range_minimum_selected")

    if normalized_unit in {"pack", "box"}:
        if canonical_item in COUNT_BASED_CATEGORIES:
            count = _explicit_count(attributes)
            if count is None:
                count = STANDARD_PACK_COUNTS.get(canonical_item)
                if count is not None:
                    flags.append(f"standard_pack_count_assumed:{count}")
            if count is None:
                flags.append("ambiguous_container_count")
                if requirement.is_required:
                    manual_review_required = True
                else:
                    review_deferred = True
            else:
                quantity *= count
                if quantity_max is not None:
                    quantity_max *= count
                attributes["count"] = count
                attributes["source_unit_type"] = normalized_unit
                normalized_unit = "each"
        else:
            assumed_content_count = STANDARD_CONTAINER_CONTENT_COUNTS.get(
                canonical_item
            )
            if (
                assumed_content_count is not None
                and _explicit_count(attributes) is None
            ):
                attributes["count"] = assumed_content_count
                flags.append(
                    f"standard_pack_count_assumed:{assumed_content_count}"
                )
            attributes["normalized_container_unit"] = normalized_unit
            normalized_unit = "each"
    elif normalized_unit == "ream":
        if canonical_item in PAPER_CATEGORIES:
            quantity *= REAM_SHEET_COUNT
            if quantity_max is not None:
                quantity_max *= REAM_SHEET_COUNT
            attributes["normalized_unit"] = "sheet"
            attributes["sheets_per_ream"] = REAM_SHEET_COUNT
            flags.append(f"ream_converted_to_sheets:{REAM_SHEET_COUNT}")
            normalized_unit = "each"
        else:
            flags.append("ambiguous_ream_conversion")
            if requirement.is_required:
                manual_review_required = True
            else:
                review_deferred = True

    is_cart_eligible = (
        requirement.is_purchasable
        and canonical_item in ALLOWED_CATEGORIES
    )
    is_budget_eligible = is_cart_eligible and requirement.is_required
    is_display_only = not is_cart_eligible

    if not requirement.is_purchasable:
        flags.append("non_purchasable_display_only")
    if manual_review_required:
        flags.append("manual_review_required")
    if review_deferred:
        flags.append("review_deferred_until_add_on_selected")

    return NormalizedRequirement(
        source=requirement,
        canonical_item=canonical_item,
        quantity=quantity,
        quantity_is_range=requirement.quantity_is_range,
        quantity_max=quantity_max,
        unit_type=normalized_unit,
        attributes=attributes,
        assumption_flags=tuple(flags),
        is_cart_eligible=is_cart_eligible,
        is_budget_eligible=is_budget_eligible,
        is_display_only=is_display_only,
        manual_review_required=manual_review_required,
        review_deferred=review_deferred,
    )


def normalize_requirements(
    requirements: Iterable[Requirement],
) -> NormalizationResult:
    """Normalize all extracted lines without any model calls (FR-10, FR-11)."""

    return NormalizationResult(
        requirements=tuple(
            normalize_requirement(requirement)
            for requirement in requirements
        )
    )
