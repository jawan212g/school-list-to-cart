"""Pydantic schemas for structured school-list extraction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


UnitType = Literal["each", "pack", "box", "ream"]
RequirementType = Literal["required", "optional", "donation"]
ReviewStatus = Literal["pending", "confirmed", "unresolved", "deleted"]
AttributeValue = str | int | float | bool | tuple[str, ...] | None
UNRESTRICTED_COLOR_VALUES = frozenset(
    {"any", "any color", "any colors", "assorted", "no preference"}
)


class RequirementAttributes(BaseModel):
    """Structured product details carried by a requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    acceptable_colors: tuple[str, ...] = ()
    character: str | None = None
    size: str | None = None
    count: int | None = Field(default=None, ge=1)
    ruling: str | None = None
    tab_count: int | None = Field(default=None, ge=1)
    tip_style: str | None = None
    material: str | None = None
    style: str | None = None
    connector: str | None = None
    sharpened: bool | None = None
    other_details: str | None = None

    @field_validator("acceptable_colors")
    @classmethod
    def normalize_acceptable_colors(
        cls,
        colors: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Store color alternatives as a unique acceptable-value collection."""

        normalized: list[str] = []
        for color in colors:
            value = color.strip().casefold()
            if (
                value
                and value not in UNRESTRICTED_COLOR_VALUES
                and value not in normalized
            ):
                normalized.append(value)
        return tuple(normalized)


class Requirement(BaseModel):
    """One normalized school-list line matching BRD Section 8 (FR-07)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    req_id: str = Field(min_length=1)
    child_id: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)
    canonical_item: str = Field(min_length=1)
    quantity: int = Field(ge=0)
    quantity_is_range: bool = False
    quantity_max: int | None = Field(default=None, ge=0)
    unit_type: UnitType = "each"
    brand_lock: str | None = None
    exclusions: tuple[str, ...] = ()
    is_required: bool = True
    is_purchasable: bool = True
    requirement_type: RequirementType = "required"
    attributes: RequirementAttributes = Field(
        default_factory=RequirementAttributes
    )
    extraction_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_requirement_consistency(self) -> Self:
        """Reject internally inconsistent structured extraction (FR-07)."""

        if self.is_purchasable and self.quantity < 1:
            raise ValueError("Purchasable requirements need a positive quantity")
        if self.quantity_is_range:
            if self.quantity_max is None:
                raise ValueError("Quantity ranges require quantity_max")
            if self.quantity_max < self.quantity:
                raise ValueError("quantity_max cannot be below quantity")
        expected_required = self.requirement_type == "required"
        if self.is_required != expected_required:
            raise ValueError(
                "is_required must agree with requirement_type"
            )
        return self


class ExtractionEnvelope(BaseModel):
    """Schema-validated model response with explicit manual-review state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stated_grades: tuple[str, ...] = ()
    stated_teachers: tuple[str, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    manual_review_required: bool = False
    review_reasons: tuple[str, ...] = ()
    deferred_review_reasons: tuple[str, ...] = ()

    @field_validator("stated_grades", "stated_teachers")
    @classmethod
    def normalize_document_metadata(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Keep stated list metadata concise, unique, and display-safe."""

        normalized: list[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned.casefold() not in {
                item.casefold() for item in normalized
            }:
                normalized.append(cleaned)
        return tuple(normalized)


class SupplyItemReview(BaseModel):
    """Editable item between extraction and shopping-plan generation (FR-12)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    review_id: str = Field(min_length=1)
    req_id: str = Field(min_length=1)
    child_id: str = Field(min_length=1)
    item_name: str = Field(min_length=1)
    required_quantity: int | None = Field(default=None, ge=1)
    unit: UnitType = "each"
    package_size: int | None = Field(default=None, ge=1)
    brand: str | None = None
    brand_required: bool = False
    size: str | None = None
    color: tuple[str, ...] = ()
    material: str | None = None
    required_attributes: dict[str, AttributeValue] = Field(default_factory=dict)
    optional: bool = False
    notes: str | None = None
    source_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    review_status: ReviewStatus = "pending"
    already_owned: bool = False
    allow_equivalents: bool = True
    issue_codes: tuple[str, ...] = ()

    @field_validator("color")
    @classmethod
    def normalize_review_colors(
        cls,
        colors: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Normalize user-editable colors without inventing preferences."""

        return RequirementAttributes(
            acceptable_colors=colors
        ).acceptable_colors


def validate_extraction_envelope(
    value: ExtractionEnvelope | BaseModel | Mapping[str, Any],
) -> ExtractionEnvelope:
    """Return the current extraction contract at every boundary (FR-07)."""

    if isinstance(value, ExtractionEnvelope):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump()
    return ExtractionEnvelope.model_validate(value)
