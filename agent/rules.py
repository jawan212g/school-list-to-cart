"""Named business-rule constants from BRD Section 9.7."""

from decimal import Decimal


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
CORRECTED_EXTRACTION_CONFIDENCE = Decimal("0.69")  # BR-11: source-proven extraction repairs route to review.
MAXIMUM_MATCH_CONFIDENCE = Decimal("1.0")  # FR-18: exact structured match.
MINIMUM_MATCH_CONFIDENCE = Decimal("0.0")  # FR-18: missing judgment is blocked.

CART_REVALIDATION_REQUIRED = True  # BR-12: revalidate before checkout.

DUPLICATE_SUPPRESSION_REQUIRED = True  # BR-13: combine identical needs.


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
