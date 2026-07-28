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
    NONPAGINATED_SOURCE_PAGE,
)


UnitType = Literal["each", "pack", "box", "ream"]
RequirementType = Literal["required", "optional", "donation"]
ReviewStatus = Literal["pending", "confirmed", "unresolved", "deleted"]
SupplyScope = Literal["individual", "shared", "unspecified"]
DocumentLayout = Literal[
    "single_section",
    "multi_section",
    "grade_matrix",
    "multilingual",
    "mixed",
]
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
    if (
        canonical_item == "spiral_notebooks"
        and corrected.get("count") is not None
        and re.search(r"\b\d+\s*[- ]subject\b", raw_evidence)
    ):
        corrected["count"] = None
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
    if (
        corrected.get("material") == "paper"
        and (
            canonical_item
            in {
                "composition_notebooks",
                "notebook_paper",
                "spiral_notebooks",
                "pens",
                "sticky_notes",
                "cardstock",
            }
            or "paper mate" in raw_evidence
        )
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
    supply_scope: SupplyScope = "unspecified"
    provided_by_school: bool = False
    condition: str | None = None
    condition_applies: bool | None = None
    condition_group_id: str | None = None
    condition_question: str | None = None
    condition_option: str | None = None
    source_document: str | None = None
    source_section: str | None = None
    source_page: int = Field(default=NONPAGINATED_SOURCE_PAGE, ge=1)
    source_language: str | None = None
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
        if (
            normalized.get("provided_by_school") is True
            or (
                normalized.get("condition")
                and normalized.get("condition_applies") is False
            )
        ):
            normalized["is_purchasable"] = False
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
        if isinstance(attributes, Mapping) and "|" in raw_text:
            selected_cell = raw_text.split("|", 1)[1]
            selected_cell = selected_cell.split(":", 1)[-1].strip()
            container_match = re.match(
                r"^1\s+(?:box|pack|pkg\.?)\b",
                selected_cell,
                re.IGNORECASE,
            )
            count = attributes.get("count")
            quantity = normalized.get("quantity")
            if (
                container_match is not None
                and isinstance(count, int)
                and quantity == count
            ):
                normalized["quantity"] = 1
                corrected = True
            individual_units = re.match(
                r"^\d+\s+(?!box\b|boxes\b|pack\b|pkg\b|set\b|dozen\b)"
                r"[A-Za-z#]",
                selected_cell,
                re.IGNORECASE,
            )
            if (
                individual_units is not None
                and normalized.get("unit_type") in {"box", "pack"}
            ):
                normalized["unit_type"] = "each"
                mutable_attributes = dict(attributes)
                if mutable_attributes.get("count") == quantity:
                    mutable_attributes["count"] = None
                normalized["attributes"] = mutable_attributes
                attributes = mutable_attributes
                corrected = True
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


class DocumentSection(BaseModel):
    """One parent-selectable grade, teacher, or named document section."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    section_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    label: str = Field(min_length=1)
    grades: tuple[str, ...] = ()
    teachers: tuple[str, ...] = ()
    named_sections: tuple[str, ...] = ()
    page_numbers: tuple[int, ...] = ()
    language: str | None = None
    column_label: str | None = None
    source_line: str = Field(min_length=1)
    duplicate_of_section_id: str | None = None

    @field_validator("grades", "teachers", "named_sections")
    @classmethod
    def normalize_section_labels(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Keep detected labels concise and unique."""

        normalized: list[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned.casefold() not in {
                item.casefold() for item in normalized
            }:
                normalized.append(cleaned)
        return tuple(normalized)


class DocumentStructureEnvelope(BaseModel):
    """Schema-validated description produced before item extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    document_title: str | None = None
    layouts: tuple[DocumentLayout, ...] = ("single_section",)
    languages: tuple[str, ...] = ()
    primary_language: str | None = None
    sections: tuple[DocumentSection, ...] = ()
    unreadable_regions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_parent_selectable_structure(self) -> Self:
        """Reject a structure response that silently identifies no sections."""

        if not self.sections:
            raise ValueError("Document structure contains no selectable sections")
        section_ids = tuple(section.section_id for section in self.sections)
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("Document section identifiers must be unique")
        return self


class DocumentSelection(BaseModel):
    """Parent-confirmed structure scope attached to an extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_section_ids: tuple[str, ...]
    selected_section_labels: tuple[str, ...]
    selected_page_numbers: tuple[int, ...] = ()
    selected_column_labels: tuple[str, ...] = ()
    selected_named_sections: tuple[str, ...] = ()
    ignored_section_ids: tuple[str, ...] = ()
    ignored_section_labels: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_selected_section(self) -> Self:
        """Require at least one section before item extraction."""

        if not self.selected_section_ids:
            raise ValueError("Select at least one document section")
        if len(self.selected_section_ids) != len(
            self.selected_section_labels
        ):
            raise ValueError("Selected section identifiers and labels differ")
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
    document_selection: DocumentSelection | None = None
    uninterpreted_lines: tuple[str, ...] = ()
    skipped_lines: tuple[str, ...] = ()

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
    quantity_is_range: bool = False
    quantity_max: int | None = Field(default=None, ge=1)
    unit: UnitType = "each"
    package_size: int | None = Field(default=None, ge=1)
    brand: str | None = None
    brand_required: bool = False
    size: str | None = None
    color: tuple[str, ...] = ()
    material: str | None = None
    required_attributes: dict[str, AttributeValue] = Field(default_factory=dict)
    optional: bool = False
    is_purchasable: bool = True
    supply_scope: SupplyScope = "unspecified"
    provided_by_school: bool = False
    condition: str | None = None
    condition_applies: bool | None = None
    condition_group_id: str | None = None
    condition_question: str | None = None
    condition_option: str | None = None
    source_document: str | None = None
    source_section: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_language: str | None = None
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
