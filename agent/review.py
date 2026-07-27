"""Deterministic organization and confirmation of extracted supply items."""

from __future__ import annotations

from collections.abc import Iterable

from agent.rules import CONFIDENCE_FLOOR
from agent.schema import (
    ExtractionEnvelope,
    Requirement,
    RequirementAttributes,
    SupplyItemReview,
)


def _review_issues(requirement: Requirement) -> tuple[str, ...]:
    """Return deterministic review flags for one extracted item (FR-12)."""

    issues: list[str] = []
    if requirement.quantity < 1:
        issues.append("missing_quantity")
    if requirement.extraction_confidence < float(CONFIDENCE_FLOOR):
        issues.append("low_confidence")
    if requirement.quantity_is_range:
        issues.append("quantity_range")
    if requirement.unit_type in {"pack", "box"}:
        if requirement.attributes.count is None:
            issues.append("ambiguous_package_size")
    if requirement.is_purchasable and not requirement.canonical_item:
        issues.append("ambiguous_item")
    return tuple(issues)


def organize_extractions(
    extractions: dict[str, ExtractionEnvelope],
) -> tuple[SupplyItemReview, ...]:
    """Create stable, sorted review rows without model calls (FR-07–FR-12)."""

    rows = [
        SupplyItemReview(
            review_id=f"{requirement.child_id}:{requirement.req_id}",
            req_id=requirement.req_id,
            child_id=requirement.child_id,
            item_name=requirement.canonical_item,
            required_quantity=(
                requirement.quantity if requirement.quantity > 0 else None
            ),
            unit=requirement.unit_type,
            package_size=requirement.attributes.count,
            brand=requirement.brand_lock,
            brand_required=requirement.brand_lock is not None,
            size=requirement.attributes.size,
            color=requirement.attributes.acceptable_colors,
            material=requirement.attributes.material,
            required_attributes=requirement.attributes.model_dump(
                exclude_none=True,
                exclude={
                    "acceptable_colors",
                    "count",
                    "size",
                    "material",
                },
            ),
            optional=not requirement.is_required,
            notes=None,
            source_text=requirement.raw_text,
            confidence=requirement.extraction_confidence,
            review_status="pending",
            already_owned=False,
            allow_equivalents=requirement.brand_lock is None,
            issue_codes=_review_issues(requirement),
        )
        for child_id in sorted(extractions)
        for requirement in extractions[child_id].requirements
    ]
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.child_id.casefold(),
                row.item_name.casefold(),
                row.source_text.casefold(),
                row.review_id,
            ),
        )
    )


def unresolved_required_items(
    rows: Iterable[SupplyItemReview],
) -> tuple[SupplyItemReview, ...]:
    """Return active required rows that are not ready for planning."""

    return tuple(
        row
        for row in rows
        if not row.optional
        and not row.already_owned
        and row.review_status != "deleted"
        and (
            row.review_status != "confirmed"
            or row.required_quantity is None
        )
    )


def confirmed_requirements(
    rows: Iterable[SupplyItemReview],
    *,
    allow_unresolved: bool = False,
) -> tuple[Requirement, ...]:
    """Convert only user-confirmed active rows to the cart contract (FR-12)."""

    active_rows = tuple(
        row
        for row in rows
        if row.review_status != "deleted" and not row.already_owned
    )
    unresolved = unresolved_required_items(active_rows)
    if unresolved and not allow_unresolved:
        raise ValueError(
            "Required items remain unresolved: "
            + ", ".join(row.item_name for row in unresolved)
        )

    confirmed: list[Requirement] = []
    for row in active_rows:
        if row.review_status != "confirmed" and not allow_unresolved:
            continue
        if row.required_quantity is None:
            if not allow_unresolved:
                continue
            quantity = 1
        else:
            quantity = row.required_quantity
        attributes = dict(row.required_attributes)
        attributes.update(
            {
                "acceptable_colors": row.color,
                "count": row.package_size,
                "size": row.size,
                "material": row.material,
            }
        )
        confirmed.append(
            Requirement(
                req_id=row.req_id,
                child_id=row.child_id,
                raw_text=row.source_text,
                canonical_item=row.item_name,
                quantity=quantity,
                unit_type=row.unit,
                brand_lock=(
                    row.brand if row.brand_required else None
                ),
                exclusions=(),
                is_required=not row.optional,
                is_purchasable=True,
                requirement_type=(
                    "optional" if row.optional else "required"
                ),
                attributes=RequirementAttributes.model_validate(attributes),
                extraction_confidence=row.confidence,
            )
        )
    return tuple(confirmed)


def reviewed_envelopes(
    original: dict[str, ExtractionEnvelope],
    rows: Iterable[SupplyItemReview],
    *,
    allow_unresolved: bool = False,
) -> dict[str, ExtractionEnvelope]:
    """Rebuild extraction envelopes from confirmed review rows."""

    requirements = confirmed_requirements(
        rows,
        allow_unresolved=allow_unresolved,
    )
    by_child: dict[str, list[Requirement]] = {
        child_id: [] for child_id in original
    }
    for requirement in requirements:
        by_child.setdefault(requirement.child_id, []).append(requirement)
    return {
        child_id: ExtractionEnvelope(
            stated_grades=envelope.stated_grades,
            stated_teachers=envelope.stated_teachers,
            requirements=tuple(by_child.get(child_id, ())),
        )
        for child_id, envelope in original.items()
    }
