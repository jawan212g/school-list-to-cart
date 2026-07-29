"""Named business-rule constants from BRD Section 9.7."""

from decimal import Decimal
import re
from typing import Literal


MINOR_SUBSTITUTION_TYPES = frozenset(
    {"different_unlocked_brand", "allowed_pack_size", "same_attributes"}
)  # BR-01: substitutions that do not require approval.
MAJOR_SUBSTITUTION_TYPES = frozenset(
    {
        "brand_lock_break",
        "pack_count_difference",
        "different_category",
        "attribute_change",
        "non_returnable_swap",
    }
)  # BR-01: substitutions that require approval.
MAJOR_PACK_DIFFERENCE_PERCENT = 20  # BR-01: pack-count approval threshold.
SUBSTITUTION_NONE = "none"  # BR-01: no substitution occurred.
SUBSTITUTION_MINOR = "minor"  # BR-01: substitution may proceed automatically.
SUBSTITUTION_MAJOR = "major"  # BR-01: substitution requires approval.
EXACT_NON_RETURNABLE_ITEM_IS_SUBSTITUTION = False  # BR-01/BR-08 reconciliation: an exact item is not a swap; only BR-08 can interrupt based on its non-returnable price.

DEFAULT_TAX_BASIS_POINTS = 700  # BR-02: default tax rate is 7.0%.
BASIS_POINTS_DENOMINATOR = 10_000  # BR-02: integer tax-rate scale.
TAX_ROUNDING_METHOD = "half_up_to_nearest_cent"  # BR-02: fractional cents.
TAX_ROUNDING_OFFSET = BASIS_POINTS_DENOMINATOR // 2  # BR-02: half-up offset.

TOTAL_INCLUDES_TAX_AND_FEES = True  # BR-03: totals are always landed cost.

REQUIRED_ITEM_AUTO_DROP_ALLOWED = False  # BR-04: required items stay in the cart.

OPTIONAL_ITEMS_INCLUDED_BY_DEFAULT = False  # BR-05: optional items start excluded.
OPTIONAL_ITEM_HEADROOM_PERCENT = 90  # BR-05: add-ons appear at 90% of budget.
OPTIONAL_ITEM_HEADROOM_BYPASSED_WITHOUT_BUDGET = True
# BR-05 reconciliation: without a budget constraint there is no 90% threshold,
# so optional items may be offered after required coverage is complete.
MINIMUM_BUDGET_CENTS = 1  # E-37: zero and negative budgets are invalid.
MAX_CHILDREN_PER_SESSION = 10  # E-38: reasonable live-session child limit.

OVERAGE_PERCENT = 50  # BR-06: relative package overage ceiling.
PERCENT_DENOMINATOR = 100  # BR-06: integer percentage scale.
OVERAGE_ABSOLUTE_UNITS = 6  # BR-06: minimum absolute overage allowance.

ADDITIONAL_STORE_PENALTY_CENTS = 600  # BR-07: $6 per store after the first.
TRIP_PENALTY_SHOWN_IN_TOTAL = False  # BR-07: comparison-only penalty.

NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS = 1_500  # BR-08: above $15.

SHARED_COST_ALLOCATION_METHOD = "proportional_by_units"  # BR-09.

INTERRUPT_TARGET_COUNT = 3  # BR-10: target approval-interrupt maximum.
INTERRUPT_DESIGN_FAILURE_COUNT = 6  # BR-10: more than six is a failure.

MODEL_CALL_TIMEOUT_SECONDS = 30.0  # Operational ceiling for one model request.
VISION_MODEL_CALL_TIMEOUT_SECONDS = 120.0  # Rendered-page vision requests need more time.
MODEL_CALL_MAX_RETRIES = 1  # One transient-service retry per model request.
MODEL_MAX_CONCURRENCY = 4  # Bound parallel model requests in one session.
BUDGET_ALTERNATIVE_PLAN_COUNT = 2  # At most two whole-plan alternatives.
BUDGET_PLAN_CANDIDATE_LIMIT = 50  # Bound deterministic bundle validation work.

CONFIDENCE_FLOOR = Decimal("0.7")  # BR-11: extraction/match review threshold.
CLEAR_EXTRACTION_CONFIDENCE = Decimal("0.9")  # Parent-facing confidence-band boundary.
CORRECTED_EXTRACTION_CONFIDENCE = Decimal("0.69")  # BR-11: source-proven extraction repairs route to review.
MAXIMUM_MATCH_CONFIDENCE = Decimal("1.0")  # FR-18: exact structured match.
MINIMUM_MATCH_CONFIDENCE = Decimal("0.0")  # FR-18: missing judgment is blocked.

CART_REVALIDATION_REQUIRED = True  # BR-12: revalidate before checkout.

DUPLICATE_SUPPRESSION_REQUIRED = True  # BR-13: combine identical needs.

SECTION_MATCHING_GRADE_ACTION = "auto_select"
# BR-14: a source-language section with the student's grade token is selected.
SECTION_OTHER_GRADE_ACTION = "rule_out"
# BR-15: a section with a different grade token is excluded without a question.
SECTION_TRANSLATED_DUPLICATE_ACTION = "provenance_only"
# BR-16: a translated duplicate is evidence for its original, never a choice.
SECTION_WITHOUT_GRADE_ACTION = "ask_parent"
# BR-17: only a source-language section without any grade token asks the parent.
SECTION_NO_MATCH_ACTION = "stop"
# BR-18: zero matching source-language sections stops extraction for that student.
PRIMARY_LANGUAGE_FALLBACK_INDEX = 0
# BR-18: when the model does not name a primary language, use the first detected one.
GRADE_TOKEN_NUMBER_INDEX = 0
# BR-14: when a grade token contains a number, its first number is the grade.
NONPAGINATED_SOURCE_PAGE = 1
# BR-19: pasted and TXT source evidence uses page 1 for uniform provenance.

REQUIREMENT_MERGE_EQUAL_QUANTITY_ACTION = "use_once"
# BR-20: the same normalized item for one student with agreeing quantities is one requirement.

REQUIREMENT_MERGE_CONFLICT_DEFAULT_ACTION = "largest"
# BR-30: cross-section/document restatements default to the largest requested
# quantity; adding every source quantity remains an explicit parent choice.

SYSTEM_DECISION_MERGED_QUANTITY_PREFIX = "merged_quantity:"
# BR-30: the deterministic quantity selected for a consolidated item remains
# visible at the mandatory parent review.

REQUIREMENT_SOURCE_DEDUPLICATION_FIELDS = (
    "document_name",
    "section_name",
    "page_number",
    "exact_line",
    "quantity",
)
# BR-22: consolidated requirements retain every distinct document, section, page, line, and quantity source.

EXPLICIT_PACKAGE_COUNT_PATTERNS = (
    r"\b(\d+)\s*(?:count|ct)\b",
    r"\b(?:pack|box|set|package)\s+of\s+(\d+)\b",
    r"\b(\d+)-(?:pack|box|set)\b",
    r"\b(\d+)\s+(?:per|in each)\s+(?:pack|box|set|package)\b",
    r"\b(?:pack|box|set|package)\s+(\d+)\b",
)
# BR-23: only these source-text forms establish an explicit package count.

EXACT_BRAND_REQUIREMENT_SIGNALS = (
    "brand required",
    "brand name only",
    "no substitutes",
    "no substitutions",
)
# BR-24: exact-brand status requires explicit source language; a brand mention alone is not enough.

BRAND_PREFERENCE_SIGNALS = (
    "are best",
    "is best",
    "preferred",
    "we like",
)
# BR-24: preference wording never creates an exact-brand requirement.

BRAND_PREFERENCE_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9&'’-]*(?:\s+[A-Za-z][A-Za-z0-9&'’-]*){0,2})"
    r"\s+(?:is\s+best|are\s+best|preferred)\b",
    flags=re.IGNORECASE,
)
# BR-24: a brand named as a preference is retained as a matching hint while
# equivalent brands remain allowed.

REQUIREMENT_ITEM_IDENTITY_FIELDS = (
    "child_id",
    "requirement_type",
    "supply_scope",
    "canonical_item",
    "unit_type",
    "condition_group_id",
    "condition_option",
)
# BR-25: same-student merge identity is the normalized item, not brand or descriptor attributes.

REQUIREMENT_CONSTRAINT_CONFLICT_ACTION = "parent_choice"
# BR-26: genuinely incompatible constraints merge once but cannot proceed without one parent choice.

REQUIREMENT_MERGE_ORIGIN_FIELDS = (
    "document_name",
    "section_name",
)
# BR-27: same-item rows from one document section remain distinct and additive; rows from different sections or documents may consolidate.

PARENT_EDITABLE_DETAIL_FIELDS = (
    "size",
    "material",
    "acceptable_colors",
)
# BR-28: show an editable detail only when the source supplied it or in-scope catalog products differ on it.

SYSTEM_DECISION_CONSOLIDATED_SOURCES = "consolidated_sources"
SYSTEM_DECISION_RECONCILED_BRAND = "reconciled_brand"
SYSTEM_DECISION_RECONCILED_EXCLUSIONS = "reconciled_exclusions"
SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX = "reconciled_attribute:"
# BR-29: every deterministic choice made while interpreting an item is visible beside that item.

PRODUCT_DEFINING_ATTRIBUTE_FIELDS = frozenset(
    {
        "ruling",
        "tip_style",
        "format",
        "size",
        "material",
        "style",
        "tab_count",
        "connector",
        "character",
        "sharpened",
    }
)
PRODUCT_DEFINING_ATTRIBUTE_VALUES = {
    "ruling": frozenset(
        {
            "graph",
            "quad",
            "wide-ruled",
            "college-ruled",
            "lined",
            "plain",
        }
    ),
    "tip_style": frozenset(
        {"fine", "ultra-fine", "chisel", "pointed", "blunt"}
    ),
    "format": frozenset({"wide", "narrow"}),
}
INCIDENTAL_REQUIREMENT_ATTRIBUTE_FIELDS = frozenset(
    {"binding", "acceptable_colors", "count"}
)
AMBIGUOUS_PRODUCT_DESCRIPTORS = frozenset({"regular"})
# BR-31: different non-null product-defining values are different products.
# Binding, brand preference, color, and packaging are incidental to merge identity.

AMBIGUOUS_DESCRIPTOR_DEFAULT = "same_product"
SYSTEM_DECISION_AMBIGUOUS_DESCRIPTOR_PREFIX = "ambiguous_descriptor_default:"
# BR-32: an unclassifiable descriptor becomes one parent question; the stated
# default treats the rows as one product because that is the smaller error.

CLASSROOM_SHARED_SCOPE = "shared"
CLASSROOM_UNSPECIFIED_SCOPE_DEFAULT = "individual"
# BR-33: classroom-group individual items scale by student count; shared items
# do not. An unspecified scope retains the conservative individual-item default.

ITEM_FULFILLMENT_PREFERENCE_DEFAULT = "minimum_cost_at_least"
ITEM_FULFILLMENT_PREFERENCES = (
    ITEM_FULFILLMENT_PREFERENCE_DEFAULT,
    "closest_quantity",
)
# BR-34: per-item fulfillment defaults to meeting at least the requested units
# with the cheapest package combination.

PACKAGE_QUANTITY_STATE_DEFAULT = "unspecified"
PACKAGE_QUANTITY_STATES = (
    "specified",
    "assumed",
    "any",
    PACKAGE_QUANTITY_STATE_DEFAULT,
)
# BR-35: package quantity distinguishes an explicit number, a visible editable
# assumption, "any pack size is fine", and genuinely unspecified source data.

SectionResolutionAction = Literal[
    "auto_select",
    "rule_out",
    "provenance_only",
    "ask_parent",
]

GRADE_WORD_IDENTIFIERS = {
    "prekindergarten": "pre-k",
    "prek": "pre-k",
    "kindergarten": "k",
    "kindergarden": "k",
    "kinder": "k",
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
    "eleventh": "11",
    "twelfth": "12",
}


ALLOWED_CATEGORIES = frozenset(
    {
        "pencils",
        "glue_sticks",
        "scissors",
        "crayons",
        "colored_pencils",
        "markers",
        "composition_notebooks",
        "spiral_notebooks",
        "notebook_paper",
        "binders",
        "dividers",
        "pens",
        "highlighters",
        "erasers",
        "pencil_boxes",
        "backpacks",
        "headphones",
        "rulers",
        "folders",
        "index_cards",
        "tissues",
        "disinfecting_wipes",
        "zip_top_bags",
        "cardstock",
        "hand_sanitizer",
        "play_dough",
        "modeling_compound",
        "watercolor_paints",
        "dry_erase_markers",
        "permanent_markers",
        "sticky_notes",
        "baby_wipes",
        "water_bottles",
        "pencil_sharpeners",
        "pencil_pouches",
    }
)

NON_PURCHASABLE_CATEGORY = "non_purchasable"
MAX_UPLOAD_BYTES = 10_000_000  # BRD 11.2: local upload size cap.

CANONICAL_ITEM_ALIASES = {
    "#2_pencil": "pencils",
    "#2_pencils": "pencils",
    "pencil": "pencils",
    "glue_stick": "glue_sticks",
    "scissor": "scissors",
    "pair_of_scissors": "scissors",
    "crayon": "crayons",
    "colored_pencil": "colored_pencils",
    "marker": "markers",
    "composition_notebook": "composition_notebooks",
    "spiral_notebook": "spiral_notebooks",
    "loose_leaf_paper": "notebook_paper",
    "wide_ruled_notebook_paper": "notebook_paper",
    "binder": "binders",
    "divider": "dividers",
    "pen": "pens",
    "highlighter": "highlighters",
    "eraser": "erasers",
    "pencil_box": "pencil_boxes",
    "backpack": "backpacks",
    "headphone": "headphones",
    "ruler": "rulers",
    "folder": "folders",
    "index_card": "index_cards",
    "tissue": "tissues",
    "disinfecting_wipe": "disinfecting_wipes",
    "zip_top_bag": "zip_top_bags",
    "zipper_bags": "zip_top_bags",
    "card_stock": "cardstock",
    "sanitizer": "hand_sanitizer",
    "play_doh": "play_dough",
    "playdough": "play_dough",
    "modeling_clay": "modeling_compound",
    "modelling_compound": "modeling_compound",
    "watercolor_paint": "watercolor_paints",
    "watercolors": "watercolor_paints",
    "dry_erase_marker": "dry_erase_markers",
    "expo_marker": "dry_erase_markers",
    "permanent_marker": "permanent_markers",
    "sharpie": "permanent_markers",
    "sticky_note": "sticky_notes",
    "post_it_notes": "sticky_notes",
    "baby_wipe": "baby_wipes",
    "water_bottle": "water_bottles",
    "pencil_sharpener": "pencil_sharpeners",
    "pencil_pouch": "pencil_pouches",
    "pencil_case": "pencil_pouches",
}  # Deterministic canonical-name aliases for FR-11.

STANDARD_PACK_COUNTS = {
    "pencils": 12,
    "glue_sticks": 4,
    "crayons": 24,
    "colored_pencils": 12,
    "markers": 10,
    "composition_notebooks": 3,
    "spiral_notebooks": 3,
    "folders": 5,
    "pens": 12,
    "highlighters": 5,
    "erasers": 3,
    "play_dough": 4,
    "modeling_compound": 4,
    "dry_erase_markers": 4,
    "permanent_markers": 2,
    "sticky_notes": 3,
    "pencil_sharpeners": 2,
}  # E-02: standard sizes used only when a count is omitted.

DETERMINISTIC_PACKAGE_COUNTS = STANDARD_PACK_COUNTS
# BR-23: an unstated package count is looked up by normalized item identity, never supplied by the model.

STANDARD_CONTAINER_CONTENT_COUNTS = {
    "notebook_paper": 150,
}  # E-02: assumed contents for catalog units sold as one container.

COUNT_BASED_CATEGORIES = frozenset(STANDARD_PACK_COUNTS)
PAPER_CATEGORIES = frozenset({"notebook_paper", "cardstock"})
REAM_SHEET_COUNT = 500  # E-17: one ream contains 500 sheets.

ATTRIBUTE_SENSITIVE_FIELDS = frozenset(
    {
        "acceptable_colors",
        "character",
        "size",
        "ruling",
        "tab_count",
        "tip_style",
        "format",
        "material",
        "style",
        "connector",
        "sharpened",
    }
)  # FR-19: changes to specified preference-sensitive attributes need approval.

PREFERENCE_DEPENDENT_ATTRIBUTES = frozenset(
    {"acceptable_colors", "color", "character", "style"}
)  # FR-26 condition 4: these parent preferences get their own interrupt type.

CATEGORY_IMPLIED_EXCLUSION_TERMS = {
    "composition_notebooks": frozenset({"spiral"}),
}  # BR-13: category identity already excludes these alternatives.

CATEGORY_IMPLIED_ATTRIBUTE_TERMS = {
    "composition_notebooks": frozenset({"spiral"}),
}  # BR-13: redundant free-text attributes must not split identical needs.


def explicit_package_count(source_line: str) -> int | None:
    """Return only a package count stated in a BR-23 source form."""

    for pattern in EXPLICIT_PACKAGE_COUNT_PATTERNS:
        match = re.search(pattern, source_line, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group(1))
    return None


def required_brand_from_source(
    source_line: str,
    proposed_brand: str | None,
) -> str | None:
    """Apply BR-24 to a model-proposed brand lock."""

    if proposed_brand is None or not proposed_brand.strip():
        return None
    source = source_line.casefold()
    brand = proposed_brand.strip()
    brand_text = brand.casefold()
    explicit = any(
        signal in source for signal in EXACT_BRAND_REQUIREMENT_SIGNALS
    ) or bool(
        re.search(
            rf"\bmust\s+be\s+{re.escape(brand_text)}\b",
            source,
        )
    ) or bool(
        re.search(
            rf"\b{re.escape(brand_text)}\s+only\b",
            source,
        )
    )
    if not explicit:
        return None
    return brand


def preferred_brand_from_source(
    source_line: str,
    proposed_brand: str | None,
) -> str | None:
    """Retain a BR-24 preferred brand without turning it into a lock."""

    source = source_line.casefold()
    if not any(signal in source for signal in BRAND_PREFERENCE_SIGNALS):
        return None
    if proposed_brand is not None and proposed_brand.strip():
        return proposed_brand.strip()
    match = BRAND_PREFERENCE_PATTERN.search(source_line)
    if match is None:
        return None
    candidate = match.group(1).strip()
    leading_quantity = re.sub(r"^\d+\s+", "", candidate).strip()
    return leading_quantity or None


def pack_count_difference_is_major(
    offered_count: int,
    requested_count: int,
) -> bool:
    """Return whether a pack-count difference exceeds BR-01's threshold."""

    if offered_count <= 0 or requested_count <= 0:
        raise ValueError("Pack counts must be positive")
    difference = abs(offered_count - requested_count)
    return (
        difference * PERCENT_DENOMINATOR
        > requested_count * MAJOR_PACK_DIFFERENCE_PERCENT
    )


def non_returnable_offer_requires_approval(
    is_returnable: bool,
    pack_price_cents: int,
) -> bool:
    """Apply BR-08 to a single offered package without cart arithmetic."""

    return (
        not is_returnable
        and pack_price_cents
        > NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS
    )


def grade_token_identifier(value: str) -> str:
    """Normalize an explicit grade token for BR-14 and BR-15."""

    normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if not normalized:
        return ""
    if normalized in {"k", "gradek"}:
        return "k"
    for word, identifier in GRADE_WORD_IDENTIFIERS.items():
        if word in normalized:
            return identifier
    numbers = re.findall(r"\d+", normalized)
    return numbers[GRADE_TOKEN_NUMBER_INDEX] if numbers else normalized


def choose_primary_document_language(
    stated_primary_language: str | None,
    detected_languages: tuple[str, ...],
    original_section_languages: tuple[str, ...],
) -> str | None:
    """Apply BR-18's deterministic source-language fallback."""

    if stated_primary_language:
        return stated_primary_language
    if detected_languages:
        return detected_languages[PRIMARY_LANGUAGE_FALLBACK_INDEX]
    return next(
        (language for language in original_section_languages if language),
        None,
    )


def section_is_in_primary_language(
    section_language: str | None,
    primary_language: str | None,
) -> bool:
    """Keep only source-language originals for BR-14 through BR-18."""

    if not primary_language:
        return True
    if not section_language:
        return False
    return section_language.casefold() == primary_language.casefold()


def section_is_parent_selectable(
    translated_duplicate_of: str | None,
) -> bool:
    """Apply BR-16 before a section reaches any parent control."""

    return translated_duplicate_of is None


def document_section_action(
    student_grade: str,
    section_grade_tokens: tuple[str, ...],
    *,
    translated_duplicate_of: str | None,
) -> SectionResolutionAction:
    """Resolve one model-detected section fact using BR-14 through BR-17."""

    if translated_duplicate_of is not None:
        return SECTION_TRANSLATED_DUPLICATE_ACTION
    if not section_grade_tokens:
        return SECTION_WITHOUT_GRADE_ACTION
    student_grade_id = grade_token_identifier(student_grade)
    if student_grade_id and any(
        grade_token_identifier(token) == student_grade_id
        for token in section_grade_tokens
    ):
        return SECTION_MATCHING_GRADE_ACTION
    return SECTION_OTHER_GRADE_ACTION
