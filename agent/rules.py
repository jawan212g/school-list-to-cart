"""Named business-rule constants from BRD Section 9.7."""

from collections.abc import Sequence
from dataclasses import dataclass
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

TOTAL_INCLUDES_TAX_AND_FEES = True  # BR-03: total cost includes tax and fees.
# Internal ``landed_cost`` identifiers are presented to users as "total cost".

REQUIRED_ITEM_AUTO_DROP_ALLOWED = False  # BR-04: required items stay in the cart.

OPTIONAL_ITEMS_INCLUDED_BY_DEFAULT = False  # BR-05: optional items start excluded.
OPTIONAL_ITEM_HEADROOM_PERCENT = 90  # BR-05: add-ons appear at 90% of budget.
OPTIONAL_ITEMS_REQUIRE_FEASIBLE_PLAN = True
# BR-05: an optional item enters the effective cart only when exact
# re-optimization satisfies the budget and the selected shopping preferences.
OPTIONAL_ITEM_HEADROOM_BYPASSED_WITHOUT_BUDGET = True
# BR-05 reconciliation: without a budget constraint there is no 90% threshold,
# so optional items may be offered after required coverage is complete.
MINIMUM_BUDGET_CENTS = 1  # E-37: zero and negative budgets are invalid.
MAX_CHILDREN_PER_SESSION = 10  # E-38: reasonable live-session child limit.
STARTING_BUDGET_CENTS_PER_STUDENT = 7_500
# BR-71: untouched Setup budget fields start at $75 per covered student;
# classroom entries use their stated student count.

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
VISION_MODEL_CALL_TIMEOUT_SECONDS = 180.0
# BR-51: rendered-page vision extraction receives a three-minute ceiling.
# The primary Machias demo document took 113.23 seconds at the prior
# 120-second ceiling, leaving too little operational headroom.
EXTRACTION_TEXT_MODEL_TIMEOUT_SECONDS = 120.0
# BR-39: text extraction retains a 120-second ceiling because observed
# structured text reads routinely exceed 60 seconds.
MODEL_CALL_MAX_RETRIES = 1  # One transient-service retry per model request.
MODEL_MAX_CONCURRENCY = 4  # Bound parallel model requests in one session.
BUDGET_ALTERNATIVE_PLAN_COUNT = 2  # At most two whole-plan alternatives.
BUDGET_PLAN_CANDIDATE_LIMIT = 50  # Bound deterministic bundle validation work.

CONFIDENCE_FLOOR = Decimal("0.7")  # BR-11: extraction/match review threshold.
CLEAR_EXTRACTION_CONFIDENCE = Decimal("0.9")  # Parent-facing confidence-band boundary.
CORRECTED_EXTRACTION_CONFIDENCE = Decimal("0.69")
# BR-11: repairs to identity, quantity, units, or unsupported model details
# route below the confidence floor. A literal attribute read directly from the
# source line does not become uncertain merely because deterministic code
# supplied or normalized it.
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
# BR-17 amended by BR-59: a source-language section without a grade token asks
# the parent only when the document names at least one grade elsewhere.
SECTION_NO_MATCH_ACTION = "stop"
# BR-18 amended by BR-59: when a document names one or more grades, zero
# matching source-language sections stops extraction for that student.
PRIMARY_LANGUAGE_FALLBACK_INDEX = 0
# BR-18: when the model does not name a primary language, use the first detected one.
GRADE_TOKEN_NUMBER_INDEX = 0
# BR-14: when a grade token contains a number, its first number is the grade.
NONPAGINATED_SOURCE_PAGE = 1
# BR-19: source evidence without page boundaries uses page 1 for uniform
# provenance. BR-64 adds deterministic page boundaries for direct paste.

REQUIREMENT_MERGE_EQUAL_QUANTITY_ACTION = "use_once"
# BR-20 amended by BR-47: agreeing duplicates are one requirement. Repeated
# single-instance goods still expose the combined quantity as a parent option
# while preselecting the largest one-source amount.

REQUIREMENT_MERGE_CONFLICT_DEFAULT_ACTION = "plausible_annual_max"
# BR-30: cross-section/document restatements offer combined, named-source, and
# custom quantities; BR-40 deterministically selects the initial option.

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

QUANTITY_ONLY_SOURCE_LINE_PATTERN = re.compile(
    r"^\s*[\d.,]+\s*$"
)
# BR-36: a purchasable requirement's exact source evidence must contain item
# wording; a bare quantity is not an exact list line and cannot enter a merge.

CONFLICT_IDENTITY_SAME = "same"
CONFLICT_IDENTITY_DIFFERENT = "different"
CONFLICT_IDENTITY_DEFAULTS = {
    "quantity_only": CONFLICT_IDENTITY_SAME,
    "different_products": CONFLICT_IDENTITY_DIFFERENT,
    "ambiguous": CONFLICT_IDENTITY_SAME,
}
# BR-37 amended: BR-31/BR-32 classification supplies the default. Only BR-32
# ambiguity asks on the main card; other classifications remain overridable in
# the item's detail view.

FAILED_DOCUMENT_SEQUENTIAL_FALLBACK = True
# BR-38: after concurrent extraction, retry only each failed document
# sequentially; never repeat a document whose concurrent extraction succeeded.

PLAUSIBLE_ANNUAL_MAXIMUM_BY_ITEM = {
    "backpacks": 2,
    "baby_wipes": 6,
    "binders": 6,
    "cardstock": 4,
    "colored_pencils": 48,
    "composition_notebooks": 10,
    "crayons": 96,
    "disinfecting_wipes": 6,
    "dividers": 4,
    "dry_erase_markers": 24,
    "erasers": 24,
    "folders": 10,
    "glue_sticks": 12,
    "hand_sanitizer": 6,
    "headphones": 2,
    "highlighters": 12,
    "index_cards": 6,
    "markers": 24,
    "modeling_compound": 12,
    "notebook_paper": 6,
    "pencil_boxes": 2,
    "pencil_pouches": 2,
    "pencil_sharpeners": 2,
    "pencils": 48,
    "pens": 24,
    "permanent_markers": 8,
    "play_dough": 12,
    "rulers": 2,
    "scissors": 2,
    "spiral_notebooks": 12,
    "sticky_notes": 12,
    "tissues": 6,
    "water_bottles": 2,
    "watercolor_paints": 4,
    "zip_top_bags": 6,
}
PLAUSIBLE_ANNUAL_MAXIMUM_FALLBACK = 12
# BR-40: combine same-student source quantities when their sum is no more
# than the canonical item's plausible annual maximum; otherwise select the
# largest single source amount. Unlisted school supplies use the fallback.
# These values are unsourced prototype inputs, not published
# student-consumption statistics. They require review before any use beyond
# this demonstration.

SOURCE_LINK_DOCUMENT_LABEL_MAX_CHARS = 30
# BR-41 amended: source controls keep document labels within a typical table
# column while a hover tooltip always exposes the full document reference.

DISPLAY_LEADING_QUANTITY_PATTERN = re.compile(r"^\s*\d+\s+")
# BR-42: parent-facing source descriptions omit a duplicated leading quantity;
# BR-22/BR-36 stored exact evidence remains unchanged.

SOURCE_EVIDENCE_SEPARATOR = "|"
SOURCE_NONDESCRIPTIVE_WORDS = frozenset(
    {
        "box",
        "boxes",
        "count",
        "ct",
        "each",
        "grade",
        "item",
        "items",
        "nd",
        "pack",
        "package",
        "pkg",
        "rd",
        "set",
        "st",
        "th",
    }
)
# BR-46: matrix evidence may place the selected quantity on either side of the
# separator. Display and identity comparison use the side containing item
# wording while the complete exact source evidence remains stored unchanged.

SINGLE_INSTANCE_REQUIREMENT_ITEMS = frozenset(
    {
        "backpacks",
        "headphones",
        "pencil_boxes",
        "pencil_pouches",
        "pencil_sharpeners",
        "rulers",
        "scissors",
        "water_bottles",
    }
)
# BR-47: a reusable single-instance item defaults to the largest quantity from
# one source, never the sum of repeated mentions. The combined choice remains
# available to the parent.

PERSONALIZE_DECISION_DETAIL_LABEL = "More detail"
# BR-49: a completed Lists decision appears in Personalize as its outcome,
# quantity, and sources. Its earlier rationale remains available only in the
# item's collapsed detail under this label.

PERSONALIZE_SUMMARY_COLUMNS = (
    "Student",
    "In cart",
    "Needs a decision",
    "Buy elsewhere",
    "Left out",
)
# BR-52 amended: Personalize summary and vertical student tabs consume one
# deterministic per-student state for cart, decision, unavailable, and
# parent-excluded counts.

PERSONALIZE_SOURCE_CONTROL_REASONS = frozenset(
    {"assumption", "uncertain"}
)
# BR-53: an item-level source control stays on the main card only for an
# assumption or uncertain extraction. Every source remains in More detail.

PACKAGE_EXTRAS_ACCEPTABLE_LABEL = (
    "Extras are okay when they make the purchase cost less"
)
PACKAGE_EXTRAS_AVOID_LABEL = (
    "Avoid extra items, even if that costs more"
)
# BR-54: package preference uses parent intent, and is not shown for reusable
# single-instance goods where a pack-size preference has no useful meaning.

# BR-55 amended: plausible annual maximums remain internal inputs to the
# deterministic BR-40 preselection. Parent-facing rationale never surfaces
# the threshold values or describes them as working limits.

EXCLUDED_REQUIREMENT_QUANTITY = 0
MINIMUM_ACTIVE_REQUIREMENT_QUANTITY = 1
# BR-56: excluding a merge decision, marking an item already owned, or
# removing an incorrect item sets its visible cart quantity to zero. Removing
# the exclusion restores the last positive quantity, or one when none exists.

CATALOG_UNAVAILABLE_SOURCE_IDENTITY_FIELDS = (
    "document_name",
    "page_number",
    "source_line",
)
# BR-57: unavailable-item evidence is displayed once per document, page, and
# exact source line, even if selected sections contribute the same metadata.

EXTRACTED_SCOPE_LABEL = "Extracted"
# BR-58: parent-facing document scope uses "extracted", not "read", so the
# interface names the actual structured-output operation consistently.

DOCUMENT_GRADE_SCOPE_NO_GRADE = "no_named_grade"
# BR-59: a document that names no grade is one whole list; it is extracted
# without a section question, grade warning, or BR-18 stop. When any grade is
# named, matching and no-match behavior remains governed by BR-14 and BR-18.

SECTION_LAYOUT_HEADER_MIN_DISTINCT_FIELDS = 2
SECTION_LAYOUT_HEADER_FIELDS = frozenset(
    {
        "amount",
        "count",
        "description",
        "item",
        "items",
        "notes",
        "qty",
        "quantity",
    }
)
INVENTED_SECTION_LABELS = frozenset(
    {
        "unlabeled supply list",
        "unlabelled supply list",
    }
)
# BR-60: table and column headers are layout evidence, not parent-selectable
# document sections. Model-invented placeholder section names are discarded.

SECTION_PROCEED_UPLOAD_ACTION = "Upload a different document"
SECTION_PROCEED_STUDENTS_ACTION_PREFIX = "Go to Your students"
# BR-61: every grade-mismatch proceed control performs its named navigation
# immediately; the screen never presents a control that has no effect.

DOCUMENT_GRADE_SCOPE_MATCH = "matching_grade"
DOCUMENT_GRADE_SCOPE_MISMATCH = "named_grades_without_match"
# BR-62: one deterministic grade-scope classification is the sole authority
# for every Lists-screen consumer: no named grade extracts the whole document,
# a named matching grade uses its matching sections, and named grades without
# a match require parent resolution.

STUDENT_SCOPED_LIST_REPLACEMENT = True
# BR-63: replacing one student's document invalidates only that student's
# document, section choice, and extraction; every other student's list and
# section choice remain intact.

PASTED_SOURCE_LINES_PER_PAGE = 48
# BR-64: typed or pasted text is retained exactly as entered. Deterministic
# pagination may be used internally to preserve item-level location references,
# but the parent sees one entry labeled "What you typed," with no filename or
# page numbers.

EXPLICIT_COMPOUND_REQUIREMENT_COMPONENTS = {
    "three-ring binder with dividers": ("binders", "dividers"),
}
# BR-65: an explicit source line naming two separately purchasable catalog
# items produces one source-backed requirement for each item. A deterministic
# completeness repair is marked for parent review rather than hidden.

PARENT_BOOLEAN_ATTRIBUTE_LABELS = {
    "sharpened": {
        True: "pre-sharpened",
        False: "unsharpened",
    },
}
PARENT_ATTRIBUTE_NAMES = {
    "acceptable_colors": "color",
    "character": "character",
    "connector": "connector",
    "format": "format",
    "material": "material",
    "ruling": "ruling",
    "sharpened": "sharpening",
    "size": "size",
    "style": "style",
    "tab_count": "tab count",
    "tip_style": "tip style",
}
# BR-50: parent-facing explanations translate booleans and schema field names
# into product language; raw True/False values and internal identifiers never
# appear.


@dataclass(frozen=True)
class RequirementQuantityDefault:
    """Deterministic BR-40 evidence for one conflict-card preselection."""

    selected_action: Literal["total", "largest"]
    selected_quantity: int
    combined_quantity: int
    plausible_annual_maximum: int


def requirement_quantity_default(
    canonical_item: str,
    quantities: Sequence[int],
) -> RequirementQuantityDefault:
    """Select BR-40's combined or largest quantity without model judgment."""

    if not quantities or any(quantity < 1 for quantity in quantities):
        raise ValueError("Requirement quantities must be positive")
    combined_quantity = sum(quantities)
    largest_quantity = max(quantities)
    plausible_maximum = PLAUSIBLE_ANNUAL_MAXIMUM_BY_ITEM.get(
        canonical_item,
        PLAUSIBLE_ANNUAL_MAXIMUM_FALLBACK,
    )
    selected_action: Literal["total", "largest"] = (
        "largest"
        if canonical_item in SINGLE_INSTANCE_REQUIREMENT_ITEMS
        else (
            "total"
            if combined_quantity <= plausible_maximum
            else "largest"
        )
    )
    return RequirementQuantityDefault(
        selected_action=selected_action,
        selected_quantity=(
            combined_quantity
            if selected_action == "total"
            else largest_quantity
        ),
        combined_quantity=combined_quantity,
        plausible_annual_maximum=plausible_maximum,
    )


def source_item_description(source_line: str) -> str:
    """Return BR-46's descriptive evidence without altering provenance."""

    segments = tuple(
        segment.strip()
        for segment in source_line.split(SOURCE_EVIDENCE_SEPARATOR)
        if segment.strip()
    )
    if not segments:
        return ""

    def descriptive_text(segment: str) -> str:
        return DISPLAY_LEADING_QUANTITY_PATTERN.sub(
            "",
            segment,
            count=1,
        ).strip()

    descriptions = tuple(descriptive_text(segment) for segment in segments)
    return max(
        descriptions,
        key=lambda description: sum(
            token not in SOURCE_NONDESCRIPTIVE_WORDS
            for token in re.findall(r"[a-z]+", description.casefold())
        ),
    )

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
AMBIGUOUS_PRODUCT_DESCRIPTORS: frozenset[str] = frozenset()
NOTEBOOK_REGULAR_RULING = "lined"
REQUIREMENT_DESCRIPTION_IGNORED_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "best",
        "box",
        "boxes",
        "count",
        "ct",
        "each",
        "for",
        "is",
        "of",
        "or",
        "pack",
        "package",
        "packages",
        "packs",
        "pkg",
        "set",
        "sized",
        "the",
        "tip",
        "with",
    }
)
REQUIREMENT_ATTRIBUTE_EVIDENCE_WORDS = frozenset(
    {
        "blunt",
        "cardboard",
        "chisel",
        "college",
        "fabric",
        "fastener",
        "fasteners",
        "fine",
        "graph",
        "lined",
        "metal",
        "narrow",
        "paper",
        "plain",
        "plastic",
        "pointed",
        "quad",
        "regular",
        "ruled",
        "sharpened",
        "spiral",
        "standard",
        "ultra",
        "unsharpened",
        "wide",
        "wood",
    }
)
# BR-31: different non-null product-defining values are different products.
# Binding, brand preference, color, and packaging are incidental to merge identity.

AMBIGUOUS_DESCRIPTOR_DEFAULT = "same_product"
SYSTEM_DECISION_AMBIGUOUS_DESCRIPTOR_PREFIX = "ambiguous_descriptor_default:"
# BR-32 amended: "regular" means lined ruling for notebooks. The explicit
# ambiguous-descriptor list is currently empty; unresolved residual wording
# still becomes one same-product/different-products question under BR-43.

# BR-43: descriptions differing only by quantity, filler, word order, brand,
# or already-resolved attribute evidence do not ask an identity question.
# Residual wording with no product-defining explanation asks exactly once.

SAME_PRODUCT_OVERRIDE_SOURCE_PREFIX = "same_product_override_source:"
SYSTEM_DECISION_PARENT_CONFIRMED_PRODUCT_IDENTITY = (
    "parent_confirmed_product_identity"
)
SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY = "parent_confirmed_quantity"
SYSTEM_DECISION_PARENT_CHOSE_SCHOOL_PROVIDED_ITEM = (
    "parent_chose_to_buy_school_provided_item"
)
SYSTEM_DECISION_PARENT_REMOVED_MERGED_ITEM = (
    "parent_removed_merged_item"
)
# FR-12: a parent may put a school-provided line into the proposed cart; retain
# that explicit choice so the shopping plan can explain why the item is present.
LOW_CONFIDENCE_IDENTITY_ISSUE = "low_confidence_identity"
LOW_CONFIDENCE_QUANTITY_ISSUE = "low_confidence_quantity"
LOW_CONFIDENCE_OTHER_DETAILS_ISSUE = "low_confidence_other_details"
# BR-44: one resolved identity state drives the radio, rationale, and quantity
# controls and remains consumed downstream. Once the parent submits that
# source-evidence decision, record its field-specific scope: same/different
# confirms product identity only, while an actively selected quantity confirms
# only that quantity. Neither answer suppresses uncertainty in an unconfirmed
# field. If a parent merges rule-distinct products, retain the first complete
# source-backed variant rather than synthesizing attributes across products.


def quantity_preselection_rationale(
    canonical_item: str,
    item_name: str,
    combined_quantity: int,
    largest_quantity: int,
    selected_action: Literal["total", "largest"],
) -> str:
    """Generate BR-40/BR-47/BR-48's parent-facing quantity rationale."""

    if canonical_item in SINGLE_INSTANCE_REQUIREMENT_ITEMS:
        return (
            f"We think {item_name} are more likely to be reused than used up, "
            "so we've preselected one instead of adding both requests together."
        )
    if selected_action == "total":
        return (
            f"Both parts of the list ask for {item_name}. We expect "
            f"{item_name} to get used up, so we've added the amounts together. "
            "Change it if that's more than you need."
        )
    return (
        f"Adding both amounts would come to {combined_quantity} {item_name}, "
        "which looked like more than one student would need, so we've "
        f"preselected the larger single request of {largest_quantity} instead."
    )


def parent_attribute_value(field_name: str, value: object) -> str:
    """Translate BR-50 schema values into product language."""

    if isinstance(value, bool):
        field_labels = PARENT_BOOLEAN_ATTRIBUTE_LABELS.get(field_name)
        if field_labels is not None:
            return field_labels[value]
        return "included" if value else "not included"
    if isinstance(value, (tuple, list, set)):
        return " or ".join(
            parent_attribute_value(field_name, member)
            for member in value
        )
    return str(value or "").strip()

def product_identity_rationale(
    conflict_type: Literal[
        "quantity_only",
        "different_products",
        "ambiguous",
    ],
    item_name: str,
    source_values: Sequence[tuple[str, str]],
    source_lines: Sequence[str] = (),
) -> str:
    """Generate BR-43/BR-45's default product-identity rationale."""

    if conflict_type != "different_products":
        normalized_lines = tuple(
            source_line.strip().casefold()
            for source_line in source_lines
        )
        if (
            len(normalized_lines) > 1
            and len(set(normalized_lines)) == 1
        ):
            return (
                "Both lines match exactly, so we've treated them as the "
                "same product."
            )
        return (
            "We believe both lines describe the same thing, just worded "
            "differently."
        )
    first_source, first_value = source_values[0]
    second_source, second_value = source_values[1]
    return (
        f"{first_source} asks for {first_value} and {second_source} asks for "
        f"{second_value}. Those look like different {item_name} to us, so "
        "we've kept them separate."
    )


def same_product_override_rationale(
    source_name: str,
) -> str:
    """Explain BR-44's source-backed result after a parent override."""

    return (
        "You chose to treat these lines as the same product. The cart will "
        f"use the product details from {source_name}."
    )


def different_product_override_rationale() -> str:
    """Explain a parent's override of a same-product preselection."""

    return "You chose to treat these lines as different products."


def personalize_same_product_override_rationale(
    source_name: str,
    retained_details: Sequence[str],
) -> str:
    """Keep BR-49's existing Personalize outcome outside Lists copy."""

    detail_text = (
        "; ".join(retained_details)
        if retained_details
        else "the complete product description"
    )
    return (
        f"You chose one product, so the cart will use {detail_text} from "
        f"{source_name}. This keeps one real source description instead of "
        "mixing details from different products."
    )


# BR-45 amended/BR-48/BR-55: rationale uses the deterministic, appropriately
# hedged templates above. Identity rationale is visible only for the
# preselected identity. Quantity rationale remains visible for any option
# whose quantity equals the preselected quantity, even when its named source
# differs.

CLASSROOM_SHARED_SCOPE = "shared"
CLASSROOM_UNSPECIFIED_SCOPE_DEFAULT = "individual"
# BR-33: classroom-group individual items scale by student count; shared items
# do not. An unspecified scope retains the conservative individual-item default.

ITEM_FULFILLMENT_PREFERENCE_DEFAULT = "minimum_cost_at_least"
ITEM_FULFILLMENT_PREFERENCES = (
    ITEM_FULFILLMENT_PREFERENCE_DEFAULT,
    "closest_quantity",
)
# Deferred package-selection preference, retained in the review schema for a
# future optimizer-scoped change. It is intentionally not numbered as a
# business rule until deterministic package selection enforces it.

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
    "book_bag": "backpacks",
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

DETERMINISTIC_BRAND_ITEMS = {
    "kleenex": ("Kleenex", "tissues"),
    "kleenexes": ("Kleenex", "tissues"),
    "post it": ("Post-It", "sticky_notes"),
    "post its": ("Post-It", "sticky_notes"),
    "ziploc": ("Ziploc", "zip_top_bags"),
    "ziplocs": ("Ziploc", "zip_top_bags"),
    "clorox": ("Clorox", "disinfecting_wipes"),
    "sharpie": ("Sharpie", "permanent_markers"),
    "sharpies": ("Sharpie", "permanent_markers"),
    "expo": ("Expo", "dry_erase_markers"),
    "expo marker": ("Expo", "dry_erase_markers"),
    "expo markers": ("Expo", "dry_erase_markers"),
    "crayola": ("Crayola", "crayons"),
    "purell": ("Purell", "hand_sanitizer"),
    "elmer": ("Elmer's", "glue_sticks"),
    "elmers": ("Elmer's", "glue_sticks"),
    "ticonderoga": ("Ticonderoga", "pencils"),
    "fiskars": ("Fiskars", "scissors"),
}
# BR-66: recognized brand wording deterministically supplies canonical brand
# spelling and the product category implied by that brand.

DETERMINISTIC_ITEM_SYNONYMS = {
    "composition book": "composition_notebooks",
    "composition books": "composition_notebooks",
    "single subject notebook": "spiral_notebooks",
    "single subject notebooks": "spiral_notebooks",
    "college ruled paper": "notebook_paper",
    "wide ruled paper": "notebook_paper",
    "loose leaf paper": "notebook_paper",
    "graph paper": "graph_paper",
    "liquid glue": "liquid_glue",
}
# BR-67: these source phrases override a missing or conflicting model category.
# Loose graph paper and liquid glue are recognized out-of-catalog items and
# therefore remain visible as unavailable; neither may be silently equated to
# a different stocked product.

# BR-72: a recognized brand supplies its implied canonical item only when the
# source line names no product noun that resolves on its own. A resolvable
# product noun wins; the brand contributes only canonical spelling and brand
# strength. Product phrases are compared together so the most specific phrase
# wins, including composition notebook over the contained graph paper phrase.

BRAND_STRENGTH_NONE = "none"
BRAND_STRENGTH_PREFERRED = "preferred"
BRAND_STRENGTH_REQUIRED = "required"
# BR-68: brand strength is derived from source wording after deterministic
# brand recognition, never from the model's chosen brand-strength field.

AMBIGUOUS_UNNAMED_BRAND_REQUIREMENT_ISSUE = (
    "brand_requirement_without_named_brand"
)
# BR-69: explicit no-substitute wording without a recognized brand is a
# parent-review question, not an invented brand lock.

CATALOG_UNAVAILABLE_RECONCILES_WITH_ACCEPTED_REQUIREMENT = True
# BR-70: a model-proposed unavailable record is removed when deterministic
# recognition proves that its named item is an accepted requirement from the
# same source line. Distinct unavailable components remain visible.

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


def _recognition_text(value: str) -> str:
    """Normalize punctuation without losing source-word boundaries."""

    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    )


def _recognized_brand_match(
    source_line: str,
) -> tuple[str, tuple[str, str]] | None:
    """Return the longest BR-66 brand phrase and its deterministic identity."""

    source = f" {_recognition_text(source_line)} "
    matches = tuple(
        (alias, identity)
        for alias, identity in DETERMINISTIC_BRAND_ITEMS.items()
        if f" {alias} " in source
    )
    if not matches:
        return None
    return max(matches, key=lambda match: len(match[0]))


def recognized_brand_from_source(
    source_line: str,
) -> tuple[str, str] | None:
    """Return BR-66's canonical brand and implied category from source text."""

    match = _recognized_brand_match(source_line)
    return match[1] if match is not None else None


def canonical_items_from_source(source_line: str) -> tuple[str, ...]:
    """Return deterministic BR-65/BR-66/BR-67/BR-72 source categories."""

    source = _recognition_text(source_line)
    compound = tuple(
        categories
        for phrase, categories in EXPLICIT_COMPOUND_REQUIREMENT_COMPONENTS.items()
        if _recognition_text(phrase) in source
    )
    if compound:
        return tuple(dict.fromkeys(compound[0]))

    brand_match = _recognized_brand_match(source_line)
    noun_source = source
    if brand_match is not None:
        brand_phrase, _ = brand_match
        noun_source = (
            f" {noun_source} "
            .replace(f" {brand_phrase} ", " ", 1)
            .strip()
        )
    aliases = {
        **{category: category for category in ALLOWED_CATEGORIES},
        **CANONICAL_ITEM_ALIASES,
    }
    noun_matches = tuple(
        (
            _recognition_text(phrase),
            canonical_item,
        )
        for phrase, canonical_item in (
            *DETERMINISTIC_ITEM_SYNONYMS.items(),
            *aliases.items(),
        )
        if (
            f" {_recognition_text(phrase)} "
            in f" {noun_source} "
        )
    )
    if noun_matches:
        _, canonical_item = max(
            noun_matches,
            key=lambda match: (
                len(match[0].split()),
                len(match[0]),
            ),
        )
        return (canonical_item,)
    if brand_match is not None:
        return (brand_match[1][1],)
    return ()


def canonical_item_from_source(source_line: str) -> str | None:
    """Return one deterministic source category when the line is not compound."""

    items = canonical_items_from_source(source_line)
    return items[0] if len(items) == 1 else None


def source_brand_strength(
    source_line: str,
) -> Literal["none", "preferred", "required"]:
    """Classify BR-68 from source evidence and a recognized brand."""

    if recognized_brand_from_source(source_line) is None:
        return BRAND_STRENGTH_NONE
    source = source_line.casefold()
    if (
        any(signal in source for signal in EXACT_BRAND_REQUIREMENT_SIGNALS)
        or "must be" in source
    ):
        return BRAND_STRENGTH_REQUIRED
    return BRAND_STRENGTH_PREFERRED


def unnamed_brand_requirement_needs_review(source_line: str) -> bool:
    """Return BR-69's unresolved strict-brand condition."""

    source = source_line.casefold()
    return (
        recognized_brand_from_source(source_line) is None
        and (
            any(
                signal in source
                for signal in EXACT_BRAND_REQUIREMENT_SIGNALS
            )
            or "must be" in source
        )
    )


def deterministic_source_quantity(source_line: str) -> int:
    """Read a leading quantity for a deterministically restored source item."""

    match = re.match(r"^\s*(\d+)\b", source_line)
    return int(match.group(1)) if match is not None else 1


def deterministic_source_unit(
    source_line: str,
) -> Literal["each", "pack", "box", "ream"]:
    """Read the explicitly named source container without package arithmetic."""

    source = _recognition_text(source_line)
    if re.match(r"^\d+\s+(?:box|boxes)\b", source):
        return "box"
    if re.match(r"^\d+\s+(?:pack|packs|package|packages)\b", source):
        return "pack"
    if re.match(r"^\d+\s+(?:ream|reams)\b", source):
        return "ream"
    return "each"


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
    """Apply BR-24/BR-68 using deterministic source recognition first."""

    recognized = recognized_brand_from_source(source_line)
    if recognized is not None:
        brand = recognized[0]
    elif proposed_brand is not None and proposed_brand.strip():
        brand = proposed_brand.strip()
        if _recognition_text(brand) not in _recognition_text(source_line):
            return None
    else:
        return None
    source = source_line.casefold()
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
    """Return BR-24/BR-68's source-backed brand without creating a lock."""

    recognized = recognized_brand_from_source(source_line)
    if recognized is not None:
        return recognized[0]
    source = source_line.casefold()
    if not any(signal in source for signal in BRAND_PREFERENCE_SIGNALS):
        if (
            proposed_brand is None
            or not proposed_brand.strip()
            or _recognition_text(proposed_brand)
            not in _recognition_text(source_line)
        ):
            return None
        return proposed_brand.strip()
    if (
        proposed_brand is not None
        and proposed_brand.strip()
        and _recognition_text(proposed_brand)
        in _recognition_text(source_line)
    ):
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


def section_is_layout_artifact(label: str, source_line: str) -> bool:
    """Reject BR-60 table headers and invented pseudo-sections."""

    normalized_label = " ".join(label.casefold().split())
    if normalized_label in INVENTED_SECTION_LABELS:
        return True
    for candidate in (source_line, label):
        tokens = frozenset(
            re.findall(r"[a-z]+", candidate.casefold())
        )
        if (
            tokens
            and tokens.issubset(SECTION_LAYOUT_HEADER_FIELDS)
            and len(tokens) >= SECTION_LAYOUT_HEADER_MIN_DISTINCT_FIELDS
        ):
            return True
    return False
