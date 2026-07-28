"""Pydantic schemas for structured school-list extraction."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.rules import (
    ALLOWED_CATEGORIES,
    CANONICAL_ITEM_ALIASES,
    CORRECTED_EXTRACTION_CONFIDENCE,
)


UnitType = Literal["each", "pack", "box", "ream"]
RequirementType = Literal["required", "optional", "donation"]
ReviewStatus = Literal["pending", "confirmed", "unresolved", "deleted"]
AttributeValue = str | int | float | bool | tuple[str, ...] | None
UNRESTRICTED_COLOR_VALUES = frozenset(
    {"any", "any color", "any colors", "assorted", "no preference"}
)
ATTRIBUTE_TEXT_PATTERN = re.compile(r"[^a-z0-9#.]+")
ATTRIBUTE_MATERIALS = frozenset(
    {"cardboard", "fabric", "metal", "paper", "plastic", "wood"}
)
RULING_VALUES = {
    "wide ruled": "wide-ruled",
    "college ruled": "college-ruled",
}


def _evidence_text(value: object) -> str:
    return " ".join(
        ATTRIBUTE_TEXT_PATTERN.sub(" ", str(value).casefold()).split()
    )


def _main_item_text(raw_text: str) -> str:
    return raw_text.split("(", 1)[0]


def _canonical_item_from_raw(raw_text: str) -> str | None:
    normalized_raw = f"_{_evidence_text(_main_item_text(raw_text)).replace(' ', '_')}_"
    aliases = {
        **{category: category for category in ALLOWED_CATEGORIES},
        **CANONICAL_ITEM_ALIASES,
    }
    candidates = [
        (len(alias), canonical_item)
        for alias, canonical_item in aliases.items()
        if f"_{_evidence_text(alias).replace(' ', '_')}_" in normalized_raw
    ]
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _correct_attribute_fields(
    raw_text: str,
    canonical_item: str,
    attributes: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    corrected = dict(attributes)
    changed = False
    raw_evidence = _evidence_text(raw_text)

    if corrected.get("character") == "#2":
        corrected["character"] = None
        corrected["other_details"] = corrected.get("other_details") or "#2"
        changed = True
    if (
        corrected.get("size") == "standard"
        and "standard" not in raw_evidence.split()
    ):
        corrected["size"] = None
        changed = True

    style = _evidence_text(corrected.get("style") or "")
    for evidence, ruling in RULING_VALUES.items():
        if evidence not in raw_evidence:
            continue
        if corrected.get("ruling") is None:
            corrected["ruling"] = ruling
            changed = True
        if style == evidence:
            corrected["style"] = None
            changed = True

    if "three ring" in raw_evidence:
        if corrected.get("connector") is None:
            corrected["connector"] = "three-ring"
            changed = True
        if style == "three ring":
            corrected["style"] = None
            changed = True

    if (
        canonical_item == "colored_pencils"
        and style == "colored"
    ):
        corrected["style"] = None
        changed = True

    count_match = re.search(r"\b(\d+)\s*count\b", raw_evidence)
    if count_match is not None and corrected.get("count") is None:
        corrected["count"] = int(count_match.group(1))
        changed = True

    if "blunt tip" in raw_evidence:
        if corrected.get("tip_style") is None:
            corrected["tip_style"] = "blunt"
            changed = True
        if style == "blunt tip":
            corrected["style"] = None
            changed = True

    if (
        canonical_item == "glue_sticks"
        and "large" in raw_evidence.split()
        and corrected.get("size") is None
    ):
        corrected["size"] = "large"
        changed = True

    size_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:inch(?:es)?|[\"″])",
        raw_text.casefold(),
    )
    if size_match is not None and corrected.get("size") is None:
        size_value = f"{size_match.group(1)} inch"
        if "approx" in raw_text.casefold():
            size_value = f"approx. {size_value}"
        corrected["size"] = size_value
        changed = True

    for material in ATTRIBUTE_MATERIALS:
        if material in raw_evidence.split():
            if corrected.get("material") is None:
                corrected["material"] = material
                changed = True
            break
    material = corrected.get("material")
    if (
        isinstance(material, str)
        and _evidence_text(material) not in raw_evidence.split()
    ):
        corrected["material"] = None
        changed = True

    return corrected, changed


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

    @model_validator(mode="before")
    @classmethod
    def enforce_objective_extraction_invariants(
        cls,
        value: Any,
    ) -> Any:
        """Enforce FR-09–FR-11 invariants independent of model quality."""

        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        if normalized.get("quantity_is_range") is not True:
            normalized["quantity_max"] = None
        if normalized.get("is_purchasable") is False:
            normalized["is_required"] = False
            if normalized.get("requirement_type", "required") == "required":
                normalized["requirement_type"] = "optional"
        raw_text = str(normalized.get("raw_text", ""))
        canonical_item = str(normalized.get("canonical_item", ""))
        corrected = False
        detected_item = _canonical_item_from_raw(raw_text)
        if (
            detected_item is not None
            and canonical_item != detected_item
            and canonical_item != "non_purchasable"
        ):
            canonical_item = detected_item
            normalized["canonical_item"] = detected_item
            corrected = True
        attributes = normalized.get("attributes")
        if isinstance(attributes, Mapping):
            corrected_attributes, attributes_changed = (
                _correct_attribute_fields(
                    raw_text,
                    canonical_item,
                    attributes,
                )
            )
            normalized["attributes"] = corrected_attributes
            corrected = corrected or attributes_changed
        confidence = normalized.get("extraction_confidence")
        if (
            corrected
            and confidence is not None
            and Decimal(str(confidence)) > CORRECTED_EXTRACTION_CONFIDENCE
        ):
            normalized["extraction_confidence"] = (
                CORRECTED_EXTRACTION_CONFIDENCE
            )
        return normalized

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
