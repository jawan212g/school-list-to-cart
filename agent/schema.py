"""Pydantic schemas for structured school-list extraction."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.rules import (
    AMBIGUOUS_PRODUCT_DESCRIPTORS,
    CORRECTED_EXTRACTION_CONFIDENCE,
    ITEM_FULFILLMENT_PREFERENCE_DEFAULT,
    NONPAGINATED_SOURCE_PAGE,
    NOTEBOOK_REGULAR_RULING,
    PACKAGE_QUANTITY_STATE_DEFAULT,
    QUANTITY_ONLY_SOURCE_LINE_PATTERN,
    canonical_item_from_source,
    explicit_package_count,
    preferred_brand_from_source,
    required_brand_from_source,
)


UnitType = Literal["each", "pack", "box", "ream"]
RequirementType = Literal["required", "optional", "donation"]
ReviewStatus = Literal["pending", "confirmed", "unresolved", "deleted"]
SupplyScope = Literal["individual", "shared", "unspecified"]
ItemFulfillmentPreference = Literal[
    "minimum_cost_at_least",
    "closest_quantity",
]
PackageQuantityState = Literal["specified", "assumed", "any", "unspecified"]
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
    "graph paper": "graph",
    "graph ruled": "graph",
    "quad ruled": "quad",
    "quad paper": "quad",
    "lined": "lined",
    "plain paper": "plain",
    "plain": "plain",
}


def _evidence_text(value: object) -> str:
    return " ".join(
        ATTRIBUTE_TEXT_PATTERN.sub(" ", str(value).casefold()).split()
    )


def _main_item_text(raw_text: str) -> str:
    return raw_text.split("(", 1)[0]


def _canonical_item_from_raw(raw_text: str) -> str | None:
    return canonical_item_from_source(_main_item_text(raw_text))


def _correct_attribute_fields(
    raw_text: str,
    canonical_item: str,
    attributes: Mapping[str, Any],
) -> tuple[dict[str, Any], bool, bool]:
    """Return source-corrected attributes and whether unsupported data was removed."""

    corrected = dict(attributes)
    changed = False
    unsupported_value_removed = False
    original_material = attributes.get("material")
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
        unsupported_value_removed = True

    style = _evidence_text(corrected.get("style") or "")
    for evidence, ruling in RULING_VALUES.items():
        if evidence not in raw_evidence:
            continue
        if corrected.get("ruling") is None:
            corrected["ruling"] = ruling
            changed = True
        if style in {evidence, ruling.replace("-", " ")}:
            corrected["style"] = None
            changed = True

    if (
        canonical_item
        in {"composition_notebooks", "spiral_notebooks"}
        and re.search(r"\bregular\b", raw_evidence)
    ):
        if corrected.get("ruling") != NOTEBOOK_REGULAR_RULING:
            corrected["ruling"] = NOTEBOOK_REGULAR_RULING
            changed = True
        if style == "regular":
            corrected["style"] = None
            changed = True

    if re.search(
        r"\bultra[\s-]+fine(?:\s+(?:tip|point))?\b",
        raw_evidence,
    ):
        if corrected.get("tip_style") != "ultra-fine":
            corrected["tip_style"] = "ultra-fine"
            changed = True
    elif re.search(r"\bfine(?:\s+(?:tip|point))?\b", raw_evidence):
        if corrected.get("tip_style") != "fine":
            corrected["tip_style"] = "fine"
            changed = True
    if re.search(r"\bchisel(?:\s+(?:tip|point))?\b", raw_evidence):
        if corrected.get("tip_style") != "chisel":
            corrected["tip_style"] = "chisel"
            changed = True

    for format_value in ("wide", "narrow"):
        if f"{format_value} format" in raw_evidence:
            if corrected.get("format") is None:
                corrected["format"] = format_value
                changed = True
            break

    for binding_value in ("sewn", "spiral"):
        if (
            f"{binding_value} binding" in raw_evidence
            or f"{binding_value} bound" in raw_evidence
        ):
            if corrected.get("binding") is None:
                corrected["binding"] = binding_value
                changed = True
            if style in {
                f"{binding_value} binding",
                f"{binding_value} bound",
                binding_value,
            }:
                corrected["style"] = None
                changed = True
            break

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

    if "blunt tip" in raw_evidence or "rounded tip" in raw_evidence:
        if corrected.get("tip_style") != "blunt":
            corrected["tip_style"] = "blunt"
            changed = True
        if style == "blunt tip":
            corrected["style"] = None
            changed = True

    if canonical_item == "erasers" and re.search(
        r"\b(?:pencil[ -]?(?:top|cap)(?:\s+erasers?)?|"
        r"(?:cap|arrowhead cap)\s+erasers?)\b",
        raw_evidence,
    ):
        if corrected.get("style") != "cap":
            corrected["style"] = "cap"
            changed = True

    if canonical_item == "folders":
        has_bottom_pockets = re.search(
            r"\bbottom\s+pockets?\b",
            raw_evidence,
        ) is not None
        has_fasteners = re.search(
            r"\b(?:w|with)\s+fasteners?\b",
            raw_evidence,
        ) is not None
        source_style = (
            "bottom pockets with fasteners"
            if has_bottom_pockets and has_fasteners
            else "bottom pockets"
            if has_bottom_pockets
            else "with fasteners"
            if has_fasteners
            else None
        )
        if source_style is not None and corrected.get("style") != source_style:
            corrected["style"] = source_style
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

    material_alias_evidence = frozenset(
        word
        for word in ("poly", "polypropylene")
        if word in raw_evidence.split()
    )
    if material_alias_evidence and corrected.get("material") != "plastic":
        corrected["material"] = "plastic"
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
        and not (
            material == "plastic"
            and bool(material_alias_evidence)
        )
    ):
        corrected["material"] = None
        changed = True
        unsupported_value_removed = (
            unsupported_value_removed or original_material is not None
        )
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
        unsupported_value_removed = (
            unsupported_value_removed or original_material is not None
        )

    return corrected, changed, unsupported_value_removed


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
    format: str | None = None
    binding: str | None = None
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


class RequirementSource(BaseModel):
    """One exact source contributing to a consolidated requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    source_req_id: str = Field(min_length=1)
    document_name: str | None = None
    section_name: str | None = None
    page_number: int = Field(default=NONPAGINATED_SOURCE_PAGE, ge=1)
    exact_line: str = Field(min_length=1)
    quantity: int = Field(ge=0)

    @field_validator("exact_line")
    @classmethod
    def require_item_wording_in_exact_line(cls, value: str) -> str:
        """Preserve BR-22/BR-36 evidence instead of a selected-cell quantity."""

        if QUANTITY_ONLY_SOURCE_LINE_PATTERN.fullmatch(value):
            raise ValueError(
                "An exact source line cannot be only a quantity"
            )
        return value


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
    brand_hint: str | None = None
    exclusions: tuple[str, ...] = ()
    is_required: bool = True
    is_purchasable: bool = True
    requirement_type: RequirementType = "required"
    supply_scope: SupplyScope = "unspecified"
    package_quantity_state: PackageQuantityState = PACKAGE_QUANTITY_STATE_DEFAULT
    item_fulfillment_preference: ItemFulfillmentPreference = (
        ITEM_FULFILLMENT_PREFERENCE_DEFAULT
    )
    ambiguous_descriptors: tuple[str, ...] = ()
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
    sources: tuple[RequirementSource, ...] = ()
    variant_sources: tuple[RequirementSource, ...] = ()
    product_variant_id: str | None = None
    system_decisions: tuple[str, ...] = ()
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
        normalized["system_decisions"] = ()
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
        source_category = str(normalized.get("canonical_item", ""))
        normalized["ambiguous_descriptors"] = tuple(
            descriptor
            for descriptor in AMBIGUOUS_PRODUCT_DESCRIPTORS
            if source_category == "composition_notebooks"
            and re.search(
                rf"\b{re.escape(descriptor)}\b",
                _evidence_text(raw_text),
            )
        )
        proposed_brand = next(
            (
                str(value)
                for value in (
                    normalized.get("brand_lock"),
                    normalized.get("brand_hint"),
                )
                if value is not None and str(value).strip()
            ),
            None,
        )
        brand_hint = preferred_brand_from_source(
            raw_text,
            proposed_brand,
        )
        normalized["brand_hint"] = brand_hint
        normalized["brand_lock"] = required_brand_from_source(
            raw_text,
            brand_hint or proposed_brand,
        )
        canonical_item = str(normalized.get("canonical_item", ""))
        review_worthy_correction = False
        detected_item = _canonical_item_from_raw(raw_text)
        if (
            detected_item is not None
            and canonical_item != detected_item
            and canonical_item != "non_purchasable"
        ):
            canonical_item = detected_item
            normalized["canonical_item"] = detected_item
            review_worthy_correction = True
        attributes = normalized.get("attributes")
        if attributes is None:
            attributes = {}
            normalized["attributes"] = attributes
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
                review_worthy_correction = True
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
                review_worthy_correction = True
        if isinstance(attributes, Mapping):
            explicit_count = explicit_package_count(raw_text)
            mutable_attributes = dict(attributes)
            if (
                mutable_attributes.get("count") is not None
                and explicit_count is None
            ):
                review_worthy_correction = True
            mutable_attributes["count"] = explicit_count
            attributes = mutable_attributes
            (
                corrected_attributes,
                _,
                unsupported_attribute_removed,
            ) = (
                _correct_attribute_fields(
                    raw_text,
                    canonical_item,
                    attributes,
                )
            )
            normalized["attributes"] = corrected_attributes
            review_worthy_correction = (
                review_worthy_correction or unsupported_attribute_removed
            )
            brand_hint = normalized.get("brand_hint")
            other_details = corrected_attributes.get("other_details")
            if (
                isinstance(brand_hint, str)
                and isinstance(other_details, str)
                and brand_hint.casefold() in other_details.casefold()
                and any(
                    signal in other_details.casefold()
                    for signal in ("preferred", "is best", "are best", "we like")
                )
            ):
                corrected_attributes["other_details"] = None
                normalized["attributes"] = corrected_attributes
        confidence = normalized.get("extraction_confidence")
        if (
            review_worthy_correction
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
        if (
            self.is_purchasable
            and QUANTITY_ONLY_SOURCE_LINE_PATTERN.fullmatch(self.raw_text)
        ):
            raise ValueError(
                "A purchasable requirement must preserve the item wording "
                "in raw_text, not only its quantity"
            )
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
    def validate_section_identifiers(self) -> Self:
        """Allow a plain whole-document list and reject duplicate section IDs."""

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


class CatalogUnavailableItem(BaseModel):
    """A list item understood by extraction but absent from the catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    child_id: str = Field(min_length=1)
    item_name: str = Field(min_length=1)
    source_line: str = Field(min_length=1)
    document_name: str | None = None
    section_name: str | None = None
    page_number: int = Field(default=NONPAGINATED_SOURCE_PAGE, ge=1)
    is_required: bool = True


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
    catalog_unavailable_items: tuple["CatalogUnavailableItem", ...] = ()

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
    required_quantity: int | None = Field(default=None, ge=0)
    quantity_is_range: bool = False
    quantity_max: int | None = Field(default=None, ge=1)
    unit: UnitType = "each"
    package_size: int | None = Field(default=None, ge=1)
    package_quantity_state: PackageQuantityState = PACKAGE_QUANTITY_STATE_DEFAULT
    item_fulfillment_preference: ItemFulfillmentPreference = (
        ITEM_FULFILLMENT_PREFERENCE_DEFAULT
    )
    brand: str | None = None
    brand_hint: str | None = None
    brand_required: bool = False
    size: str | None = None
    color: tuple[str, ...] = ()
    material: str | None = None
    required_attributes: dict[str, AttributeValue] = Field(default_factory=dict)
    exclusions: tuple[str, ...] = ()
    optional: bool = False
    is_purchasable: bool = True
    supply_scope: SupplyScope = "unspecified"
    ambiguous_descriptors: tuple[str, ...] = ()
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
    sources: tuple[RequirementSource, ...] = ()
    variant_sources: tuple[RequirementSource, ...] = ()
    product_variant_id: str | None = None
    system_decisions: tuple[str, ...] = ()
    source_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    review_status: ReviewStatus = "pending"
    already_owned: bool = False
    allow_equivalents: bool = True
    issue_codes: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def keep_brand_choice_mutually_exclusive(cls, value: Any) -> Any:
        """Represent exact brand versus equivalents as one choice."""

        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        if (
            normalized.get("package_size") is not None
            and normalized.get(
                "package_quantity_state",
                PACKAGE_QUANTITY_STATE_DEFAULT,
            )
            == PACKAGE_QUANTITY_STATE_DEFAULT
        ):
            normalized["package_quantity_state"] = "specified"
        brand = normalized.get("brand")
        if normalized.get("brand_required") is True and not (
            isinstance(brand, str) and brand.strip()
        ):
            normalized["brand_required"] = False
            normalized["allow_equivalents"] = True
        if normalized.get("brand_required") is True:
            normalized["allow_equivalents"] = False
        return normalized

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
