"""Streamlit interface for Ready, Set, School."""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from io import BytesIO
from collections.abc import Mapping, MutableMapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import pypdfium2 as pdfium

from agent.aggregate import UnitNeed
from agent.addons import AddOnSelectionEvaluation, evaluate_addon_selection
from agent.approval_options import (
    CatalogApprovalChoice,
    RemovalCostContext,
    build_catalog_approval_choices,
    build_required_item_removal_choices,
    removal_cost_context,
)
from agent.budget_plans import (
    BudgetAction,
    BudgetAnalysis,
    BudgetPlan,
    BudgetSelectionEvaluation,
    apply_authorized_budget,
    evaluate_budget_actions,
)
from agent.decisions import Decision, DecisionLog
from agent.demo import DEMO_LIST_TEXT, extract_demo_document
from agent.extract import (
    MODEL_NAME,
    PDF_RENDER_SCALE,
    build_document_selection,
    extract_document,
    inspect_document_structure,
    selectable_document_sections,
)
from agent.gate import ApprovalBatch, ApprovalInterrupt
from agent.match import (
    ATTRIBUTE_OFFER_KEYS,
    MatchResult,
    StructuredSuitabilityJudge,
    SuitabilityJudge,
)
from agent.optimize import (
    CartLine,
    CartPlan,
    OptimizationConfig,
    OptimizationResult,
    _allocate_cents,
    optimize_cart,
)
from agent.pipeline import (
    ListInput,
    PipelineResult,
    PipelineSession,
    ReplanTransition,
    detect_cart_staleness,
    replan_after_catalog_change,
    run_pipeline_from_confirmed_extractions,
)
from agent.review import (
    apply_conditional_answers,
    apply_review_confirmations,
    conditional_review_questions,
    conditional_answers_for_selection,
    confidence_band,
    deduplicate_conditional_questions,
    organize_extractions,
    review_flag_groups,
    review_issue_explanations,
    reviewed_envelopes,
    teacher_note_groups,
    unresolved_required_items,
)
from agent.provider import (
    ProviderConfig,
    create_model_client,
    default_openai_config,
    get_provider_config,
    get_provider_diagnostic,
)
from agent.rules import (
    ALLOWED_CATEGORIES,
    DEFAULT_TAX_BASIS_POINTS,
    MAX_CHILDREN_PER_SESSION,
    MAX_UPLOAD_BYTES,
    MINIMUM_BUDGET_CENTS,
    MODEL_MAX_CONCURRENCY,
    NONPAGINATED_SOURCE_PAGE,
    NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS,
    PARENT_EDITABLE_DETAIL_FIELDS,
    SYSTEM_DECISION_CONSOLIDATED_SOURCES,
    SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX,
    SYSTEM_DECISION_RECONCILED_BRAND,
    SYSTEM_DECISION_RECONCILED_EXCLUSIONS,
    SUBSTITUTION_NONE,
    grade_token_identifier,
)
from agent.requirement_merge import (
    RequirementMergeResult,
    consolidate_extractions,
    item_decisions,
    requirement_source,
)
from agent.sections import (
    ResolvedSectionChoice,
    SectionResolution,
    build_resolved_section_choice,
    choice_to_document_selection,
    resolve_document_sections,
)
from agent.schema import (
    DocumentSection,
    DocumentSelection,
    DocumentStructureEnvelope,
    ExtractionEnvelope,
    RequirementSource,
    SupplyItemReview,
    validate_extraction_envelope,
)
from agent.store_scope import (
    FulfillmentPreference,
    pickup_trip_is_within_radius,
    store_supports_fulfillment,
)
from data.loader import Offer, Store, load_catalog, load_stores


LOGGER = logging.getLogger(__name__)
APP_NAME = "Ready, Set, School"
APP_TAGLINE = "Sorted before the first bell."
CENTS_PER_DOLLAR = 100
BASIS_POINTS_PER_PERCENT = 100
MAX_TAX_PERCENT = Decimal("25")
MAX_STORE_RADIUS_MILES = 25.0
MAX_CLASSROOM_STUDENTS = 100
DEFAULT_BUDGET_TEXT = "150.00"
DEFAULT_RADIUS_MILES = 10.0
NO_SET_BUDGET_LABEL = "No set budget"
DEFAULT_TAX_STATE_OPTION = "Choose a state — use the 7.0% default"
DEVELOPMENT_DEBUG_ENV = "SCHOOL_CART_DEBUG"
DEBUG_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})
INTAKE_ENTRY_VALUE_PREFIXES = (
    "child_label",
    "student_name",
    "teacher_name",
    "child_grade",
    "student_grade",
    "classroom_grade",
    "student_count",
    "budget",
    "list_mode",
    "list_upload",
    "list_upload_draft",
    "list_paste",
)
INTAKE_ENTRY_TYPE_TRACKER_PREFIX = "intake_previous_entity_type"
INTAKE_ENTRY_GRADE_TRACKER_PREFIX = "intake_previous_grade"
NAVIGATION_STATE_PREFIX = "navigation_saved::"
INTAKE_WIDGET_STATE_PREFIX = "_intake_widget::"
INTAKE_WIDGET_TOUCHED_PREFIX = "intake_widget_touched::"
NAVIGATION_WIDGET_KEYS = frozenset(
    {
        "child_count",
        "demo_mode",
        "budget_mode_label",
        "combined_budget_text",
        "shopping_preference_label",
        "selected_store_names",
        "maximum_stores",
        "store_radius_miles",
        "fulfillment_label",
        "sales_tax_state",
        "tax_rate_text",
        "shared_list_for_all",
        "shared_list_mode",
        "shared_list_paste",
    }
)
NAVIGATION_WIDGET_PREFIXES = (
    "entity_type_",
    "student_name_",
    "teacher_name_",
    "child_grade_",
    "student_grade_",
    "classroom_grade_",
    "student_count_",
    "budget_",
    "list_mode_",
    "list_paste_",
    "document_sections_",
)
STATE_GENERAL_SALES_TAX_PERCENT: Mapping[str, str] = {
    # State-level general rates as of January 1, 2026. City and county rates
    # are deliberately excluded. Source: Tax Foundation, Facts & Figures 2026,
    # Table 18, which includes mandatory statewide local add-ons in CA, UT, VA.
    DEFAULT_TAX_STATE_OPTION: "7.0",
    "Alabama": "4.0",
    "Alaska": "0.0",
    "Arizona": "5.6",
    "Arkansas": "6.5",
    "California": "7.25",
    "Colorado": "2.9",
    "Connecticut": "6.35",
    "Delaware": "0.0",
    "District of Columbia": "6.0",
    "Florida": "6.0",
    "Georgia": "4.0",
    "Hawaii": "4.0",
    "Idaho": "6.0",
    "Illinois": "6.25",
    "Indiana": "7.0",
    "Iowa": "6.0",
    "Kansas": "6.5",
    "Kentucky": "6.0",
    "Louisiana": "5.0",
    "Maine": "5.5",
    "Maryland": "6.0",
    "Massachusetts": "6.25",
    "Michigan": "6.0",
    "Minnesota": "6.875",
    "Mississippi": "7.0",
    "Missouri": "4.225",
    "Montana": "0.0",
    "Nebraska": "5.5",
    "Nevada": "6.85",
    "New Hampshire": "0.0",
    "New Jersey": "6.625",
    "New Mexico": "4.875",
    "New York": "4.0",
    "North Carolina": "4.75",
    "North Dakota": "5.0",
    "Ohio": "5.75",
    "Oklahoma": "4.5",
    "Oregon": "0.0",
    "Pennsylvania": "6.0",
    "Rhode Island": "7.0",
    "South Carolina": "6.0",
    "South Dakota": "4.2",
    "Tennessee": "7.0",
    "Texas": "6.25",
    "Utah": "6.1",
    "Vermont": "6.0",
    "Virginia": "5.3",
    "Washington": "6.5",
    "West Virginia": "6.0",
    "Wisconsin": "5.0",
    "Wyoming": "4.0",
}
SUPPORTED_UPLOADS: Mapping[str, str] = {
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".txt": "text/plain",
}
SCREEN_ORDER = (
    "intake",
    "lists",
    "working",
    "sections",
    "review",
    "approval",
    "summary",
)
JOURNEY_STAGES = (
    "Your students",
    "Their lists",
    "Personalize",
    "Your shopping plan",
)
SCREEN_PHASES: Mapping[str, tuple[str, str]] = {
    "intake": ("1", JOURNEY_STAGES[0]),
    "lists": ("2", JOURNEY_STAGES[1]),
    "working": ("4", JOURNEY_STAGES[3]),
    "sections": ("2", JOURNEY_STAGES[1]),
    "requirement_merge": ("2", JOURNEY_STAGES[1]),
    "review": ("3", JOURNEY_STAGES[2]),
    "approval": ("4", JOURNEY_STAGES[3]),
    "summary": ("4", JOURNEY_STAGES[3]),
}
GRADE_OPTIONS = (
    "Pre-K",
    "Kindergarten",
    *(f"Grade {grade}" for grade in range(1, 13)),
)
SHOPPING_MODES: Mapping[str, str] = {
    "Lowest landed cost": "budget",
    "Single store when possible": "single_stop",
    "Custom store limits": "custom",
}
FULFILLMENT_OPTIONS: Mapping[str, str] = {
    "Best available": "either",
    "Pickup only": "pickup",
    "Delivery only": "delivery",
}
ITEM_DISPLAY_NAMES: Mapping[str, str] = {
    "backpacks": "Backpack",
    "baby_wipes": "Baby wipes",
    "binders": "Binder",
    "colored_pencils": "Colored pencils",
    "composition_notebooks": "Composition notebook",
    "crayons": "Crayons",
    "dividers": "Dividers",
    "dry_erase_markers": "Dry-erase markers",
    "glue_sticks": "Glue sticks",
    "headphones": "Headphones",
    "highlighters": "Highlighters",
    "modeling_compound": "Modeling compound",
    "notebook_paper": "Notebook paper",
    "pencil_boxes": "Pencil box",
    "pencil_pouches": "Pencil pouch",
    "pencil_sharpeners": "Pencil sharpener",
    "pencils": "Pencils",
    "pens": "Pens",
    "permanent_markers": "Permanent markers",
    "play_dough": "Play dough",
    "rulers": "Ruler",
    "scissors": "Scissors",
    "sticky_notes": "Sticky notes",
    "tissues": "Tissues",
    "water_bottles": "Water bottle",
    "watercolor_paints": "Watercolor paints",
}
ATTRIBUTE_DISPLAY_NAMES: Mapping[str, str] = {
    "acceptable_colors": "color",
    "character": "character",
    "connector": "connector",
    "material": "material",
    "ruling": "ruling",
    "sharpened": "sharpening",
    "size": "size",
    "style": "style",
    "tab_count": "tab count",
    "tip_style": "tip style",
}
SUBSTITUTION_REASON_LABELS: Mapping[str, str] = {
    "allowed_pack_size": "Package size is within the allowed overage",
    "attribute_change:acceptable_colors": "Requested color differs",
    "attribute_change:character": "Requested character differs",
    "attribute_change:connector": "Requested connector differs",
    "attribute_change:material": "Requested material differs",
    "attribute_change:ruling": "Requested ruling differs",
    "attribute_change:sharpened": "Requested sharpening differs",
    "attribute_change:size": "Requested size differs",
    "attribute_change:style": "Requested style differs",
    "attribute_change:tab_count": "Requested tab count differs",
    "attribute_change:tip_style": "Requested tip style differs",
    "brand_lock_break": "Required brand differs",
    "different_unlocked_brand": "Different brand; no brand was required",
    "pack_count_difference": "Package count differs materially",
}
SUBSTITUTION_SEVERITY_LABELS: Mapping[str, str] = {
    "major": "Parent approval required",
    "minor": "Equivalent alternative",
    "none": "Exact match",
}
GRADE_NAME_VALUES: Mapping[str, str] = {
    "prekindergarten": "pk",
    "pre-kindergarten": "pk",
    "pre k": "pk",
    "pre-k": "pk",
    "kindergarten": "k",
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


@dataclass(frozen=True)
class ApprovalDisplayOption:
    """One parent-facing choice with cents retained until rendering."""

    alternative_id: str
    label: str
    cost_delta_cents: int
    explanation: str | None = None
    sku: str | None = None
    source_requirement_ids: tuple[str, ...] = ()
    affected_lines: tuple[str, ...] = ()
    affected_children: tuple[str, ...] = ()
    item_name: str | None = None
    is_current_product: bool = False
    leaves_required_unmet: bool = False
    is_recommended: bool = False
    budget_action_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApprovalDisplayDecision:
    """Plain-language approval content assembled without changing the gate."""

    interrupt: ApprovalInterrupt
    item_name: str
    heading: str
    message: str
    recommendation: str
    affected_children: tuple[str, ...]
    options: tuple[ApprovalDisplayOption, ...]


@dataclass(frozen=True)
class ListIdentityWarning:
    """A non-blocking warning that list metadata differs from intake."""

    child_label: str
    entered_grade: str
    stated_grades: tuple[str, ...]
    stated_teachers: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class SelfSourcedSelection:
    """One required item the parent chose to obtain outside this cart."""

    presentation: ApprovalDisplayDecision
    option: ApprovalDisplayOption
    item_name: str
    affected_children: tuple[str, ...]


@dataclass(frozen=True)
class InterruptResolution:
    """One downstream interrupt made unnecessary by an upstream choice."""

    interrupt_id: str
    message: str
    source_requirement_ids: tuple[str, ...]


@dataclass(frozen=True)
class ApprovalSelectionState:
    """Active selections and dynamically resolved approval interrupts."""

    active_outcomes: Mapping[str, str]
    resolutions: Mapping[str, InterruptResolution]


@dataclass(frozen=True)
class ToneState:
    """Plan conditions that switch the entire screen to plain language."""

    has_shortfall: bool = False
    has_unmet_required: bool = False
    has_extraction_failure: bool = False
    has_error: bool = False

    @property
    def requires_plain_copy(self) -> bool:
        """Return whether any plan condition requires the plain register."""

        return any(
            (
                self.has_shortfall,
                self.has_unmet_required,
                self.has_extraction_failure,
                self.has_error,
            )
        )


@dataclass(frozen=True)
class CopySet:
    """All state-sensitive chrome copy, selected in one place."""

    register: str
    tagline: str
    summary_heading: str
    headline_heading: str
    complete_status: str
    attention_clear: str


WARM_COPY = CopySet(
    register="warm",
    tagline=APP_TAGLINE,
    summary_heading="Your shopping plan is ready",
    headline_heading="The plan at a glance",
    complete_status="Required items covered",
    attention_clear="Nothing needs your attention.",
)
PLAIN_COPY = CopySet(
    register="plain",
    tagline=APP_TAGLINE,
    summary_heading="Shopping plan",
    headline_heading="Plan status",
    complete_status="Required items covered",
    attention_clear="Nothing needs your attention.",
)


def select_copy_set(state: ToneState) -> CopySet:
    """Select the warm or plain register with one state check."""

    return PLAIN_COPY if state.requires_plain_copy else WARM_COPY


def screen_phase_label(screen: str, substep: str | None = None) -> str:
    """Return the canonical four-stage journey label for one screen."""

    del substep
    return SCREEN_PHASES[screen][1]


def progress_narration(
    stage: str,
    completed: int,
    total: int,
) -> str:
    """Translate pipeline progress into warm, concrete parent-facing copy."""

    if stage == "extraction":
        noun = "list" if total == 1 else "lists"
        return f"Extracting {completed} of {total} {noun}"
    if stage == "normalization":
        return "Combining shared items across the lists"
    if stage == "matching":
        if completed:
            return f"Comparing stores for {completed} of {total} item types"
        return f"Comparing stores for {total} item types"
    if stage == "optimization":
        if completed:
            return "Checking package sizes, store fees, and the budget"
        return "Comparing package sizes and single-store plans"
    if stage == "approval":
        return "Looking for anything that needs your decision"
    return "Building the shopping plan"


def money_to_cents(value: str) -> int:
    """Parse a positive display amount into integer cents (E-37)."""

    raw_value = value.strip()
    if any(
        unicodedata.category(character) == "Sc" and character != "$"
        for character in raw_value
    ):
        raise ValueError(
            "Amounts are in US dollars. Use $ or no currency symbol."
        )
    if "$" in raw_value:
        if not raw_value.startswith("$") or raw_value.count("$") != 1:
            raise ValueError(
                "Amounts are in US dollars. Put $ only at the beginning."
            )
        raw_value = raw_value[1:].strip()
    integer_part = raw_value.split(".", maxsplit=1)[0]
    if "," in integer_part:
        comma_groups = integer_part.split(",")
        if (
            not comma_groups[0].isdigit()
            or not 1 <= len(comma_groups[0]) <= 3
            or any(
                len(group) != 3 or not group.isdigit()
                for group in comma_groups[1:]
            )
        ):
            raise ValueError(
                "Use commas only as thousands separators, such as 1,200."
            )
    cleaned = raw_value.replace(",", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError("Enter a budget such as 150 or 75.50.") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Budget must be greater than zero.")
    cents = amount * CENTS_PER_DOLLAR
    if cents != cents.to_integral_value():
        raise ValueError("Budget may contain no more than two decimal places.")
    parsed = int(cents)
    if parsed < MINIMUM_BUDGET_CENTS:
        raise ValueError("Budget must be greater than zero.")
    return parsed


def budget_entry_error(value: str) -> str | None:
    """Return an E-37 message while the parent is entering a budget."""

    try:
        money_to_cents(value)
    except ValueError as error:
        return str(error)
    return None


def tax_percent_to_basis_points(value: str) -> int:
    """Convert an editable display percentage to integer basis points."""

    try:
        percent = Decimal(value.strip().replace("%", ""))
    except InvalidOperation as error:
        raise ValueError("Enter a tax rate such as 7.0.") from error
    if (
        not percent.is_finite()
        or percent < 0
        or percent > MAX_TAX_PERCENT
    ):
        raise ValueError(
            f"Tax rate must be between 0 and {MAX_TAX_PERCENT}%."
        )
    return int(
        (percent * BASIS_POINTS_PER_PERCENT).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def state_tax_rate_percent(state_name: str) -> str:
    """Return the state-level general rate used to prefill BR-02 intake."""

    try:
        return STATE_GENERAL_SALES_TAX_PERCENT[state_name]
    except KeyError as error:
        raise ValueError(f"Unknown state selection: {state_name}") from error


def initialize_state_tax_prefill(
    state: MutableMapping[str, Any],
    state_name: str,
) -> None:
    """Prefill tax when the state changes without overwriting later edits."""

    if (
        state.get("tax_prefill_state") == state_name
        and str(state.get("tax_rate_text", "")).strip()
    ):
        return
    state["tax_rate_text"] = state_tax_rate_percent(state_name)
    state["tax_prefill_state"] = state_name


def initialize_preference_defaults(
    state: MutableMapping[str, Any],
) -> None:
    """Set first-render FR-04/BR-02 defaults without overwriting edits."""

    if bool(state.get("preferences_defaults_initialized", False)):
        return
    radius_value = state.get("store_radius_miles")
    if radius_value is None or float(radius_value) == 0:
        state["store_radius_miles"] = DEFAULT_RADIUS_MILES
        state[
            NAVIGATION_STATE_PREFIX + "store_radius_miles"
        ] = DEFAULT_RADIUS_MILES
    if not str(state.get("tax_rate_text", "")).strip():
        state_name = str(
            state.get("sales_tax_state", DEFAULT_TAX_STATE_OPTION)
        )
        state["tax_rate_text"] = state_tax_rate_percent(state_name)
        state[
            NAVIGATION_STATE_PREFIX + "tax_rate_text"
        ] = state["tax_rate_text"]
        state["tax_prefill_state"] = state_name
    state["preferences_defaults_initialized"] = True


def student_input_errors(
    student_name: str,
    grade: str,
) -> tuple[str, ...]:
    """Return immediate FR-01/FR-05 intake messages for one student."""

    errors: list[str] = []
    if not student_name.strip():
        errors.append("Enter a student name or nickname.")
    if not grade.strip():
        errors.append("Enter the student's grade.")
    return tuple(errors)


def format_money(cents: int) -> str:
    """Format integer cents for plain-text artifacts."""

    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return (
        f"{sign}${absolute // CENTS_PER_DOLLAR:,}."
        f"{absolute % CENTS_PER_DOLLAR:02d}"
    )


def escape_streamlit_dollars(text: str) -> str:
    """Escape unescaped dollar signs before Streamlit Markdown rendering."""

    return re.sub(r"(?<!\\)\$", r"\\$", text)


def escape_streamlit_data(value: Any) -> Any:
    """Escape dollar signs recursively in values sent to Streamlit."""

    if isinstance(value, str):
        return escape_streamlit_dollars(value)
    if isinstance(value, Mapping):
        return {
            escape_streamlit_dollars(key) if isinstance(key, str) else key:
            escape_streamlit_data(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(escape_streamlit_data(item) for item in value)
    if isinstance(value, list):
        return [escape_streamlit_data(item) for item in value]
    return value


def format_streamlit_money(cents: int) -> str:
    """Format cents for a Streamlit Markdown-capable display call."""

    return escape_streamlit_dollars(format_money(cents))


def format_cost_delta(cents: int) -> str:
    """Format one approval alternative's landed-cost change."""

    if cents == 0:
        return "no cost change"
    direction = "adds" if cents > 0 else "saves"
    return f"{direction} {format_money(abs(cents))}"


def format_streamlit_cost_delta(cents: int) -> str:
    """Format a landed-cost delta safely for Streamlit rendering."""

    return escape_streamlit_dollars(format_cost_delta(cents))


def development_diagnostics_enabled(st: Any) -> bool:
    """Keep deployment diagnostics hidden unless explicitly requested."""

    query_value: object = None
    query_params = getattr(st, "query_params", {})
    try:
        query_value = query_params.get("debug")
    except (AttributeError, TypeError):
        query_value = None
    if isinstance(query_value, Sequence) and not isinstance(
        query_value,
        str,
    ):
        query_value = query_value[-1] if query_value else None
    if (
        isinstance(query_value, str)
        and query_value.strip().casefold() in DEBUG_ENABLED_VALUES
    ):
        return True
    return (
        os.getenv(DEVELOPMENT_DEBUG_ENV, "").strip().casefold()
        in DEBUG_ENABLED_VALUES
    )


def _grade_tokens(value: str) -> frozenset[str]:
    """Normalize common grade spellings for deterministic comparison."""

    cleaned = re.sub(r"[.,:()]", " ", value.casefold())
    tokens: set[str] = set()
    for name, canonical in GRADE_NAME_VALUES.items():
        if re.search(rf"\b{re.escape(name)}\b", cleaned):
            tokens.add(canonical)
    if re.search(r"\b(?:grade\s*)?k\b", cleaned):
        tokens.add("k")
    tokens.update(
        match.group(1)
        for match in re.finditer(
            r"\b(?:grade\s*)?(1[0-2]|[1-9])(?:st|nd|rd|th)?\b",
            cleaned,
        )
    )
    return frozenset(tokens)


def _grade_rank(value: str) -> int | None:
    if value == "pk":
        return -1
    if value == "k":
        return 0
    if value.isdigit():
        return int(value)
    return None


def _grade_statement_matches(
    entered_grade: str,
    stated_grade: str,
) -> bool:
    entered = _grade_tokens(entered_grade)
    stated = _grade_tokens(stated_grade)
    if entered.intersection(stated):
        return True

    range_match = re.search(
        (
            r"\b(k|1[0-2]|[1-9])(?:st|nd|rd|th)?\s*"
            r"(?:-|–|—|through|to)\s*"
            r"(k|1[0-2]|[1-9])(?:st|nd|rd|th)?\b"
        ),
        stated_grade.casefold(),
    )
    if range_match is None:
        return False
    start = _grade_rank(range_match.group(1))
    end = _grade_rank(range_match.group(2))
    entered_ranks = tuple(
        rank
        for token in entered
        if (rank := _grade_rank(token)) is not None
    )
    if start is None or end is None:
        return False
    lower, upper = sorted((start, end))
    return any(lower <= rank <= upper for rank in entered_ranks)


def _grade_display(value: str) -> str:
    tokens = _grade_tokens(value)
    if len(tokens) == 1:
        token = next(iter(tokens))
        if token == "pk":
            return "pre-K"
        if token == "k":
            return "kindergarten"
        return f"grade {token}"
    cleaned = value.strip()
    if cleaned.casefold().startswith(("grade ", "grades ")):
        return cleaned.casefold()
    return f"grade {cleaned}"


def _grade_display_title(value: str) -> str:
    """Return one grade label that cannot acquire a second prefix."""

    displayed = _grade_display(value)
    if displayed == "pre-K":
        return displayed
    return displayed[:1].upper() + displayed[1:]


def detect_list_identity_warnings(
    extractions: Mapping[str, object],
    children: Sequence[Mapping[str, Any]],
    structures: Mapping[str, DocumentStructureEnvelope] | None = None,
) -> tuple[ListIdentityWarning, ...]:
    """Compare whole-document grades with intake grades before cart build."""

    warnings: list[ListIdentityWarning] = []
    for child in children:
        child_id = str(child["child_id"])
        extracted_value = extractions.get(child_id)
        if extracted_value is None:
            continue
        extraction = validate_extraction_envelope(extracted_value)
        if (
            extraction.document_selection is not None
            and extraction.document_selection.selected_section_ids
        ):
            continue
        structure = (structures or {}).get(child_id)
        stated_grades = (
            tuple(
                dict.fromkeys(
                    grade
                    for section in structure.sections
                    for grade in section.grades
                )
            )
            if structure is not None
            else extraction.stated_grades
        )
        if not stated_grades:
            continue
        entered_grade = str(child["grade"])
        if any(
            _grade_statement_matches(entered_grade, stated_grade)
            for stated_grade in stated_grades
        ):
            continue
        stated_text = _join_names(
            tuple(
                _grade_display(grade)
                for grade in stated_grades
            )
        )
        entered_text = _grade_display(entered_grade)
        warnings.append(
            ListIdentityWarning(
                child_label=str(child["label"]),
                entered_grade=entered_grade,
                stated_grades=stated_grades,
                stated_teachers=extraction.stated_teachers,
                message=(
                    f"This list appears to be for {stated_text}, but you "
                    f"entered {entered_text}. Continue anyway?"
                ),
            )
        )
    return tuple(warnings)


def store_radius_rows(
    stores: Sequence[Store],
    radius_miles: float,
    fulfillment_preference: FulfillmentPreference,
) -> tuple[Mapping[str, str], ...]:
    """Describe simulated pickup-radius scope for the intake screen (FR-04)."""

    rows: list[Mapping[str, str]] = []
    for store in stores:
        pickup_in_radius = pickup_trip_is_within_radius(
            store,
            radius_miles,
        )
        if not store.pickup_available:
            pickup_status = "Not offered (online-only)"
        elif pickup_in_radius:
            pickup_status = "Inside radius"
        else:
            pickup_status = "Outside radius"

        included = store_supports_fulfillment(
            store,
            radius_miles,
            fulfillment_preference,
        )
        if fulfillment_preference == "delivery":
            current_scope = "Included for delivery; radius does not apply"
        elif fulfillment_preference == "either" and not pickup_in_radius:
            current_scope = "Included for delivery only"
        elif included:
            current_scope = "Included"
        else:
            current_scope = "Not included"

        rows.append(
            {
                "Store": store.name,
                "Simulated distance": (
                    f"{store.distance_miles:.1f} miles"
                    if store.pickup_available
                    else "Online only"
                ),
                "Pickup trip": pickup_status,
                "Current scope": current_scope,
            }
        )
    return tuple(rows)


def _exact_exception_message(error: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return " | caused by ".join(parts)


def probe_openai_connection(
    client: Any | None = None,
    provider_config: ProviderConfig | None = None,
) -> tuple[bool, str]:
    """Make one minimal call against the configured provider endpoint."""

    try:
        active_config = (
            provider_config
            or (
                default_openai_config()
                if client is not None
                else get_provider_config()
            )
        )
        active_client = client or create_model_client(active_config)
        response = active_client.models.list()
        available_models = {
            str(model.id)
            for model in getattr(response, "data", ())
            if getattr(model, "id", None)
        }
        configured_models = {
            active_config.text_model,
            *(
                ()
                if active_config.vision_model is None
                else (active_config.vision_model,)
            ),
        }
        missing_models = configured_models - available_models
        if missing_models:
            missing = ", ".join(sorted(missing_models))
            raise RuntimeError(
                f"Configured model not listed by the endpoint: {missing}"
            )
    except Exception as error:
        LOGGER.exception(
            "Model-provider development diagnostic failed: %r",
            error,
        )
        return False, _exact_exception_message(error)
    return (
        True,
        (
            f"{active_config.provider_name} connection succeeded. "
            f"Text model {active_config.text_model} is available."
        ),
    )


def validate_uploaded_document(
    filename: str,
    data: bytes,
) -> str:
    """Validate extension, size, and signature before extraction (FR-06, E-35)."""

    suffix = Path(filename).suffix.casefold()
    mime_type = SUPPORTED_UPLOADS.get(suffix)
    if mime_type is None:
        raise ValueError("Use a DOCX, PDF, JPG, JPEG, PNG, or TXT file.")
    if len(data) > MAX_UPLOAD_BYTES:
        maximum_mb = MAX_UPLOAD_BYTES // 1_000_000
        raise ValueError(f"File exceeds the {maximum_mb} MB size limit.")
    if not data:
        raise ValueError("The uploaded file is empty.")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("This file is not a valid PDF.")
    if suffix == ".docx" and not data.startswith(b"PK"):
        raise ValueError("This file is not a valid DOCX.")
    if suffix in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("This file is not a valid JPG image.")
    if suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("This file is not a valid PNG image.")
    if suffix == ".txt":
        if b"\x00" in data:
            raise ValueError("TXT uploads cannot contain binary data.")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("TXT uploads must use UTF-8 text.") from error
    if suffix in {".pdf", ".jpg", ".jpeg", ".png"}:
        diagnostic = get_provider_diagnostic()
        if diagnostic.vision_model is None:
            raise ValueError(
                "PDF and image uploads are unavailable because "
                "LLM_VISION_MODEL is not configured. Configure a vision "
                "model or upload a TXT or DOCX list."
            )
    return mime_type


def _plans(optimization: OptimizationResult) -> tuple[CartPlan, ...]:
    return (optimization.plan,) + (
        ()
        if optimization.minimum_second_trip is None
        else (optimization.minimum_second_trip,)
    )


def _all_interrupts(batch: ApprovalBatch) -> tuple[ApprovalInterrupt, ...]:
    visible: list[ApprovalInterrupt] = []
    for interrupt in batch.interrupts:
        if interrupt.grouped_interrupts:
            visible.extend(interrupt.grouped_interrupts)
        else:
            visible.append(interrupt)
    return tuple(visible)


def _active_catalog_offers(
    stockout_skus: frozenset[str],
    price_overrides: Mapping[str, int] | None = None,
) -> tuple[Offer, ...]:
    overrides = price_overrides or {}
    active = []
    for offer in load_catalog():
        updated = offer
        if offer.sku in overrides:
            pack_price = overrides[offer.sku]
            if pack_price <= 0:
                raise ValueError("Catalog price overrides must be positive")
            updated = replace(
                updated,
                pack_price=pack_price,
            )
        if offer.sku in stockout_skus:
            updated = replace(updated, stock_qty=0)
        active.append(updated)
    return tuple(active)


def _optimization_config(result: PipelineResult) -> OptimizationConfig:
    session = result.session
    return OptimizationConfig(
        shopping_mode=session.shopping_mode,
        budget_cents=session.budget_total,
        allowed_store_ids=session.allowed_stores,
        max_stores=session.max_stores,
        store_radius_miles=session.store_radius_miles,
        fulfillment_preference=session.fulfillment_pref,
        tax_basis_points=session.tax_basis_points,
    )


def authorize_budget_increase(
    result: PipelineResult,
    optimization: OptimizationResult,
    decision_log: DecisionLog,
) -> tuple[PipelineResult, OptimizationResult]:
    """Apply a parent-authorized BR-04 increase to the selected landed cost."""

    previous_budget = result.session.budget_total
    if previous_budget is None:
        raise ValueError("A budget increase requires an existing budget")
    new_budget = optimization.landed_cost
    if new_budget < previous_budget:
        raise ValueError("A budget increase cannot lower the session budget")
    updated_optimization = apply_authorized_budget(
        optimization,
        new_budget,
    )
    updated_result = replace(
        result,
        session=replace(result.session, budget_total=new_budget),
        proposed_cart=apply_authorized_budget(
            result.proposed_cart,
            new_budget,
        ),
    )
    decision_log.record(
        "budget_action",
        (
            "Parent authorized a budget increase from "
            f"{previous_budget} cents to {new_budget} cents so the selected "
            "required-item plan is fully funded."
        ),
        actor="parent",
        affected_lines=tuple(
            line.line_id
            for plan in _plans(updated_optimization)
            for line in plan.lines
        ),
    )
    return updated_result, updated_optimization


def budget_increase_was_selected(
    presentations: Sequence[ApprovalDisplayDecision],
    selections: Mapping[str, ApprovalDisplayOption],
) -> bool:
    """Return whether the parent selected BR-04's budget increase action."""

    return any(
        presentation.interrupt.kind == "budget_exceeded"
        and selections[presentation.interrupt.interrupt_id]
        .alternative_id.endswith("-raise")
        for presentation in presentations
        if presentation.interrupt.interrupt_id in selections
    )


def _interrupt_line(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
) -> CartLine | None:
    affected = frozenset(interrupt.affected_lines)
    return next(
        (
            line
            for plan in _plans(result.proposed_cart)
            for line in plan.lines
            if line.line_id in affected
        ),
        None,
    )


def _item_display_name(canonical_item: str) -> str:
    return ITEM_DISPLAY_NAMES.get(
        canonical_item,
        canonical_item.replace("_", " ").title(),
    )


def _product_name(line: CartLine, matches: MatchResult) -> str:
    candidate = matches.candidate(
        line.source_requirement_ids,
        line.sku,
    )
    if candidate is not None:
        return candidate.offer.title
    return _item_display_name(line.canonical_item)


def _substitution_reason(reason: str) -> str:
    return SUBSTITUTION_REASON_LABELS.get(
        reason,
        reason.replace("_", " ").capitalize(),
    )


def _humanize_internal_text(
    text: str,
    offers: Sequence[Offer],
    stores: Sequence[Store],
) -> str:
    visible = text
    for offer in sorted(offers, key=lambda item: -len(item.sku)):
        visible = visible.replace(offer.sku, offer.title)
    for store in sorted(stores, key=lambda item: -len(item.store_id)):
        visible = visible.replace(store.store_id, store.name)
    for internal, label in SUBSTITUTION_REASON_LABELS.items():
        visible = visible.replace(internal, label.lower())
    for internal, label in SUBSTITUTION_SEVERITY_LABELS.items():
        visible = re.sub(
            rf"\b{re.escape(internal)}\b",
            label.lower(),
            visible,
        )
    visible = re.sub(
        r"(-?\d+) cents\b",
        lambda match: format_money(int(match.group(1))),
        visible,
    )
    visible = re.sub(
        r"\bchild\s+entry\b",
        "student",
        visible,
        flags=re.I,
    )
    visible = re.sub(r"\bchildren\b", "students", visible, flags=re.I)
    visible = re.sub(r"\bchild\b", "student", visible, flags=re.I)
    visible = re.sub(r"\bentries\b", "students", visible, flags=re.I)
    return re.sub(r"\bentry\b", "student", visible, flags=re.I)


def _catalog_product_label(
    sku: str,
    offers: Sequence[Offer],
    stores: Sequence[Store],
) -> str:
    offer = next(
        (candidate for candidate in offers if candidate.sku == sku),
        None,
    )
    if offer is None:
        return "Selected product"
    store = next(
        (
            candidate
            for candidate in stores
            if candidate.store_id == offer.store_id
        ),
        None,
    )
    store_name = store.name if store is not None else "Unknown store"
    return f"{offer.title} — {store_name}"


def _join_names(names: Sequence[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _child_display_label(
    child_id: str,
    child_labels: Mapping[str, str],
) -> str:
    """Return a parent-entered label without exposing an internal ID."""

    return child_labels.get(child_id, "Unknown student")


def _affected_children(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    child_labels: Mapping[str, str],
) -> tuple[str, ...]:
    affected_ids: list[str] = []
    affected_lines = frozenset(interrupt.affected_lines)
    for plan in _plans(result.proposed_cart):
        for line in plan.lines:
            if line.line_id not in affected_lines:
                continue
            for child_id in line.allocated_to:
                if child_id not in affected_ids:
                    affected_ids.append(child_id)
    if not affected_ids:
        requirement_ids = frozenset(interrupt.source_requirement_ids)
        for need in result.purchase_needs:
            if (
                requirement_ids
                and not requirement_ids.intersection(
                    need.source_requirement_ids
                )
            ):
                continue
            for child_id in need.allocated_to:
                if child_id not in affected_ids:
                    affected_ids.append(child_id)
    if not affected_ids:
        affected_ids.extend(result.session.children)
    return tuple(
        _child_display_label(child_id, child_labels)
        for child_id in affected_ids
    )


def _attribute_labels(
    result: PipelineResult,
    line: CartLine | None,
) -> tuple[str, ...]:
    if line is None:
        return ()
    candidate = result.matches.candidate(
        line.source_requirement_ids,
        line.sku,
    )
    if candidate is None:
        return ()
    prefix = "attribute_change:"
    return tuple(
        ATTRIBUTE_DISPLAY_NAMES.get(
            reason.removeprefix(prefix),
            reason.removeprefix(prefix).replace("_", " "),
        )
        for reason in candidate.substitution_reasons
        if reason.startswith(prefix)
    )


def _source_lines(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
) -> tuple[str, ...]:
    source_ids = frozenset(interrupt.source_requirement_ids)
    return tuple(
        dict.fromkeys(
            requirement.source.raw_text
            for requirement in result.normalization.cart_requirements
            if requirement.source.req_id in source_ids
        )
    )


def _has_exact_catalog_match(
    result: PipelineResult,
    line: CartLine,
) -> bool:
    need_matches = next(
        (
            item
            for item in result.matches.needs
            if item.unit_need.source_requirement_ids
            == line.source_requirement_ids
        ),
        None,
    )
    return bool(
        need_matches
        and any(
            candidate.attribute_status == "exact"
            for candidate in need_matches.candidates
        )
    )


def _short_cost_component(label: str, cents: int) -> str | None:
    if cents == 0:
        return None
    if cents > 0:
        return f"{format_money(cents)} {label}"
    return f"{format_money(abs(cents))} {label} saving"


def _catalog_choice_explanation(
    choice: CatalogApprovalChoice,
) -> str | None:
    if choice.is_current:
        return None
    return _landed_delta_explanation(
        choice.cost_delta_cents,
        choice.item_subtotal_delta_cents,
        choice.tax_delta_cents,
        choice.fulfillment_fee_delta_cents,
    )


def _landed_delta_explanation(
    cost_delta_cents: int,
    item_subtotal_delta_cents: int,
    tax_delta_cents: int,
    fulfillment_fee_delta_cents: int,
) -> str:
    components = tuple(
        component
        for component in (
            _short_cost_component(
                "item",
                item_subtotal_delta_cents,
            ),
            _short_cost_component("tax", tax_delta_cents),
            _short_cost_component(
                "fees",
                fulfillment_fee_delta_cents,
            ),
        )
        if component is not None
    )
    direction = "Adds" if cost_delta_cents > 0 else "Saves"
    detail = f" ({', '.join(components)})" if components else ""
    return (
        f"{direction} {format_money(abs(cost_delta_cents))} "
        f"landed{detail}"
    )


def _removal_explanation(
    cost_delta_cents: int,
    context: RemovalCostContext | None,
    stores_by_id: Mapping[str, Store],
) -> str | None:
    if (
        context is None
        or cost_delta_cents == -context.line_cost_cents
    ):
        return None
    store = stores_by_id.get(context.store_id)
    store_name = store.name if store is not None else "The store"
    if (
        context.fee_returns_cents
        and context.fee_threshold_cents is not None
    ):
        return (
            "This saves the item and its tax, but "
            f"{store_name}'s "
            f"{format_money(context.fee_returns_cents)} "
            f"{context.fulfillment_method} fee returns because the remaining "
            "item subtotal falls below "
            f"{format_money(context.fee_threshold_cents)}."
        )
    if context.tax_changes:
        return (
            "This differs from the item price because the cart's sales tax "
            "changes too."
        )
    return (
        "This is the change to the full landed cart, including fulfillment "
        "fees."
    )


def _fallback_option_label(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    alternative_id: str,
    original_label: str,
    item_name: str,
) -> str:
    if alternative_id.endswith("-raise"):
        return (
            "Raise the budget by "
            f"{format_money(result.proposed_cart.shortfall_cents)}"
        )
    if alternative_id.endswith(("-omit", "-parent-remove")):
        return (
            "Do not buy this — I will source it myself "
            f"(leaves required {item_name.lower()} unmet)"
        )
    if alternative_id.endswith("-approve"):
        return f"Keep the recommended {item_name.lower()}"
    return original_label


def _with_one_recommended_option(
    options: Sequence[ApprovalDisplayOption],
) -> tuple[ApprovalDisplayOption, ...]:
    """Mark exactly one non-removal choice as the recommendation."""

    if not options:
        return ()
    covered_indices = tuple(
        index
        for index, option in enumerate(options)
        if not option.leaves_required_unmet
    )
    if not covered_indices:
        raise ValueError(
            "Every approval decision needs a covered or pending recommendation"
        )
    recommended_index = next(
        (
            index
            for index, option in enumerate(options)
            if option.is_recommended and not option.leaves_required_unmet
        ),
        covered_indices[0],
    )
    return tuple(
        replace(
            option,
            is_recommended=(index == recommended_index),
        )
        for index, option in enumerate(options)
    )


def _legacy_budget_approval_content(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
) -> tuple[str, tuple[ApprovalDisplayOption, ...]]:
    """Build item-specific BR-04 evidence and actionable budget choices."""

    optimization = result.proposed_cart
    config = _optimization_config(result)
    offers_by_sku = {offer.sku: offer for offer in offers}
    stores_by_id = {store.store_id: store for store in stores}
    lines_by_id = {
        line.line_id: line
        for plan in _plans(optimization)
        for line in plan.lines
    }
    removal_choices = build_required_item_removal_choices(
        optimization,
        result.matches,
        result.purchase_needs,
        offers,
        stores,
        config,
    )
    affected_child_ids = tuple(
        dict.fromkeys(
            child_id
            for removal in removal_choices
            for child_id in removal.allocated_to
        )
    ) or result.session.children
    all_children = tuple(
        _child_display_label(child_id, child_labels)
        for child_id in affected_child_ids
    )
    options: list[ApprovalDisplayOption] = [
        ApprovalDisplayOption(
            alternative_id=f"{interrupt.interrupt_id}-raise",
            label=(
                "Raise the budget by "
                f"{format_money(optimization.shortfall_cents)}"
            ),
            cost_delta_cents=0,
            explanation=(
                "Keeps every required item covered at the minimum achievable "
                f"landed cost of {format_money(optimization.landed_cost)}."
            ),
            affected_children=all_children,
            is_recommended=True,
        )
    ]
    ranked_lines: list[str] = []
    substitution_options: list[ApprovalDisplayOption] = []
    self_source_options: list[ApprovalDisplayOption] = []
    for rank, removal in enumerate(removal_choices, start=1):
        line = next(
            (
                lines_by_id[line_id]
                for line_id in removal.affected_line_ids
                if line_id in lines_by_id
            ),
            None,
        )
        if line is None:
            continue
        item_name = _item_display_name(removal.canonical_item)
        affected_children = tuple(
            _child_display_label(child_id, child_labels)
            for child_id in removal.allocated_to
        )
        line_interrupt = replace(
            interrupt,
            affected_lines=removal.affected_line_ids,
            source_requirement_ids=removal.source_requirement_ids,
            sku=line.sku,
        )
        cheaper_choices = tuple(
            choice
            for choice in build_catalog_approval_choices(
                line_interrupt,
                optimization,
                result.matches,
                result.purchase_needs,
                offers,
                stores,
                config,
            )
            if not choice.is_current and choice.cost_delta_cents < 0
        )
        cheaper_descriptions = []
        for choice in cheaper_choices:
            offer = offers_by_sku[choice.sku]
            store = stores_by_id.get(choice.store_id)
            store_name = store.name if store is not None else "Unknown store"
            cheaper_descriptions.append(
                (
                    f"{offer.title} from {store_name}, saving "
                    f"{format_money(abs(choice.cost_delta_cents))} landed"
                )
            )
            substitution_options.append(
                ApprovalDisplayOption(
                    alternative_id=(
                        f"{interrupt.interrupt_id}-item-{rank}-catalog-"
                        f"{choice.sku}"
                    ),
                    label=(
                        f"Switch {item_name} for "
                        f"{_join_names(affected_children)} to "
                        f"{offer.title} — {store_name}"
                    ),
                    cost_delta_cents=choice.cost_delta_cents,
                    explanation=_catalog_choice_explanation(choice),
                    sku=choice.sku,
                    source_requirement_ids=(
                        removal.source_requirement_ids
                    ),
                    affected_lines=removal.affected_line_ids,
                    affected_children=affected_children,
                    item_name=item_name,
                )
            )
        cheaper_text = (
            "; ".join(cheaper_descriptions)
            if cheaper_descriptions
            else "none available"
        )
        contribution = abs(min(removal.cost_delta_cents, 0))
        ranked_lines.append(
            (
                f"{rank}. {item_name} for "
                f"{_join_names(affected_children)} — "
                f"{format_money(contribution)} marginal landed "
                "contribution. Cheaper catalog alternatives: "
                f"{cheaper_text}."
            )
        )
        self_source_options.append(
            ApprovalDisplayOption(
                alternative_id=(
                    f"{interrupt.interrupt_id}-item-{rank}-self-source"
                ),
                label=(
                    f"Do not buy {item_name} for "
                    f"{_join_names(affected_children)} — "
                    "I will source it myself "
                    "(leaves a required item unmet)"
                ),
                cost_delta_cents=removal.cost_delta_cents,
                explanation=_landed_delta_explanation(
                    removal.cost_delta_cents,
                    removal.item_subtotal_delta_cents,
                    removal.tax_delta_cents,
                    removal.fulfillment_fee_delta_cents,
                ),
                source_requirement_ids=removal.source_requirement_ids,
                affected_lines=removal.affected_line_ids,
                affected_children=affected_children,
                item_name=item_name,
                leaves_required_unmet=True,
            )
        )
    message_lines = [
        (
            "Minimum achievable landed cost: "
            f"{format_money(optimization.landed_cost)}."
        ),
        (
            f"Entered budget: {format_money(result.session.budget_total or 0)}. "
            f"Shortfall: {format_money(optimization.shortfall_cents)}."
        ),
        "",
        "Required lines ranked by marginal landed contribution:",
        *ranked_lines,
    ]
    options.extend(substitution_options)
    options.extend(self_source_options)
    return (
        "\n".join(message_lines),
        _with_one_recommended_option(options),
    )


def _budget_approval_content(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
) -> tuple[str, tuple[ApprovalDisplayOption, ...]]:
    """Render precomputed whole-plan BR-04 choices without recalculation."""

    analysis = result.budget_analysis
    optimization = result.proposed_cart
    all_children = tuple(
        _child_display_label(child_id, child_labels)
        for child_id in result.session.children
    )
    if analysis is None:
        return _legacy_budget_approval_content(
            result,
            interrupt,
            offers,
            stores,
            child_labels,
        )

    substitution_saving = (
        analysis.baseline_landed_cost_cents
        - analysis.substitution_only_landed_cost_cents
    )
    if analysis.substitutions_reach_budget:
        message = (
            "Cheaper substitutions alone can reach the entered budget. "
            "Current required-cart landed cost: "
            f"{format_money(analysis.baseline_landed_cost_cents)}; current "
            f"shortfall: {format_money(analysis.original_shortfall_cents)}. "
            f"The listed substitutions save {format_money(substitution_saving)}."
        )
    else:
        remaining_shortfall = max(
            analysis.substitution_only_landed_cost_cents
            - analysis.budget_cents,
            0,
        )
        message = (
            "Cheaper substitutions alone cannot reach the entered budget. "
            "Current required-cart landed cost: "
            f"{format_money(analysis.baseline_landed_cost_cents)}; shortfall: "
            f"{format_money(analysis.original_shortfall_cents)}. The listed "
            f"substitutions save {format_money(substitution_saving)}, leaving "
            f"{format_money(remaining_shortfall)} still to resolve."
        )
    actions_by_id = analysis.actions_by_id

    def unmet_text(plan: BudgetPlan) -> str:
        details = []
        for action_id in plan.unmet_action_ids:
            action = actions_by_id[action_id]
            children = tuple(
                _child_display_label(child_id, child_labels)
                for child_id in action.allocated_to
            )
            details.append(
                f"{_item_display_name(action.canonical_item)} for "
                f"{_join_names(children)}"
            )
        return _join_names(tuple(details)) if details else "nothing"

    def plan_explanation(plan: BudgetPlan) -> str:
        return (
            f"Result: {format_money(plan.resulting_landed_cost_cents)} landed. "
            f"You would source: {unmet_text(plan)}."
        )

    options: list[ApprovalDisplayOption] = []
    if analysis.substitutions_reach_budget:
        options.append(
            ApprovalDisplayOption(
                alternative_id=f"{interrupt.interrupt_id}-substitutions",
                label="Apply all cheaper substitutions",
                cost_delta_cents=(
                    analysis.substitution_only_landed_cost_cents
                    - analysis.baseline_landed_cost_cents
                ),
                explanation=(
                    "Resulting landed cost: "
                    f"{format_money(analysis.substitution_only_landed_cost_cents)}; "
                    "all required items remain covered."
                ),
                affected_children=all_children,
                is_recommended=True,
                budget_action_ids=analysis.preferred_substitution_action_ids,
            )
        )
    elif analysis.recommended_plan is not None:
        plan = analysis.recommended_plan
        options.append(
            ApprovalDisplayOption(
                alternative_id=plan.plan_id,
                label="Recommended plan — meet the entered budget",
                cost_delta_cents=(
                    plan.resulting_landed_cost_cents
                    - analysis.baseline_landed_cost_cents
                ),
                explanation=plan_explanation(plan),
                affected_children=all_children,
                is_recommended=True,
                budget_action_ids=plan.action_ids,
            )
        )
        for plan in analysis.alternative_plans:
            options.append(
                ApprovalDisplayOption(
                    alternative_id=plan.plan_id,
                    label=f"Alternative plan — preserve {plan.preserves}",
                    cost_delta_cents=(
                        plan.resulting_landed_cost_cents
                        - analysis.baseline_landed_cost_cents
                    ),
                    explanation=plan_explanation(plan),
                    affected_children=all_children,
                    budget_action_ids=plan.action_ids,
                )
            )

    options.append(
        ApprovalDisplayOption(
            alternative_id=f"{interrupt.interrupt_id}-raise",
            label=(
                "Raise the budget by "
                f"{format_money(optimization.shortfall_cents)}"
            ),
            cost_delta_cents=0,
            explanation=(
                "Keeps every required item covered at "
                f"{format_money(optimization.landed_cost)} landed."
            ),
            affected_children=all_children,
            is_recommended=not options,
        )
    )
    options.append(
        ApprovalDisplayOption(
            alternative_id=f"{interrupt.interrupt_id}-custom",
            label="Let me choose",
            cost_delta_cents=0,
            explanation=(
                "Use the checkboxes below to combine substitutions and items "
                "you will source yourself."
            ),
            affected_children=all_children,
        )
    )
    return message, _with_one_recommended_option(options)


def _approval_options(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
) -> tuple[ApprovalDisplayOption, ...]:
    if interrupt.kind == "budget_exceeded":
        _, options = _budget_approval_content(
            result,
            interrupt,
            offers,
            stores,
            child_labels,
        )
        return options

    line = _interrupt_line(result, interrupt)
    item_name = (
        _item_display_name(line.canonical_item)
        if line is not None
        else "item"
    )
    offers_by_sku = {offer.sku: offer for offer in offers}
    stores_by_id = {store.store_id: store for store in stores}
    catalog_choices = build_catalog_approval_choices(
        interrupt,
        result.proposed_cart,
        result.matches,
        result.purchase_needs,
        offers,
        stores,
        _optimization_config(result),
    )
    if catalog_choices:
        options = []
        for choice in catalog_choices:
            offer = offers_by_sku[choice.sku]
            store = stores_by_id.get(choice.store_id)
            store_name = store.name if store is not None else "Unknown store"
            verb = "Keep" if choice.is_current else "Choose"
            options.append(
                ApprovalDisplayOption(
                    alternative_id=(
                        f"{interrupt.interrupt_id}-catalog-{choice.sku}"
                    ),
                    label=f"{verb} {offer.title} — {store_name}",
                    cost_delta_cents=choice.cost_delta_cents,
                    explanation=_catalog_choice_explanation(choice),
                    sku=choice.sku,
                    source_requirement_ids=line.source_requirement_ids,
                    affected_lines=(line.line_id,),
                    is_current_product=choice.is_current,
                    is_recommended=choice.is_current,
                )
            )
        should_offer_self_source = (
            not _has_exact_catalog_match(result, line)
            or len(catalog_choices) <= 1
        )
        if not should_offer_self_source:
            return _with_one_recommended_option(options)

        removal = next(
            (
                alternative
                for alternative in interrupt.alternatives
                if alternative.alternative_id.endswith("-omit")
            ),
            None,
        )
        if removal is not None:
            context = removal_cost_context(
                interrupt,
                result.proposed_cart,
                stores,
            )
            cost_explanation = _removal_explanation(
                removal.cost_delta_cents,
                context,
                stores_by_id,
            )
            availability_explanation = (
                "No exact catalog match is available. "
                if len(catalog_choices) > 1
                else "No other stocked catalog match is available. "
            )
            options.append(
                ApprovalDisplayOption(
                    alternative_id=removal.alternative_id,
                    label=(
                        "Do not buy this — I will source it myself "
                        f"(leaves required {item_name.lower()} unmet)"
                    ),
                    cost_delta_cents=removal.cost_delta_cents,
                    explanation=(
                        availability_explanation
                        + (
                            cost_explanation
                            or "This removes the required item from the cart."
                        )
                    ),
                    source_requirement_ids=line.source_requirement_ids,
                    affected_lines=(line.line_id,),
                    leaves_required_unmet=True,
                )
            )
        return _with_one_recommended_option(options)

    fallback_options = tuple(
        ApprovalDisplayOption(
            alternative_id=alternative.alternative_id,
            label=_fallback_option_label(
                result,
                interrupt,
                alternative.alternative_id,
                alternative.label,
                item_name,
            ),
            cost_delta_cents=alternative.cost_delta_cents,
            source_requirement_ids=interrupt.source_requirement_ids,
            affected_lines=interrupt.affected_lines,
            leaves_required_unmet=(
                bool(interrupt.source_requirement_ids)
                and alternative.alternative_id.endswith(
                    ("-omit", "-parent-remove")
                )
            ),
            is_recommended=(index == 0),
        )
        for index, alternative in enumerate(interrupt.alternatives)
    )
    ordered = tuple(
        sorted(
            fallback_options,
            key=lambda option: option.leaves_required_unmet,
        )
    )
    return _with_one_recommended_option(ordered)


def _approval_heading(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    line: CartLine | None,
) -> str:
    item_name = (
        _item_display_name(line.canonical_item)
        if line is not None
        else "Cart"
    )
    if interrupt.kind == "non_returnable_threshold":
        return (
            f"{item_name} — non-returnable, over "
            f"{format_money(NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS)}"
        )
    attributes = _attribute_labels(result, line)
    if attributes:
        detail = _join_names(attributes) if attributes else "requested details"
        return f"{item_name} — choose an acceptable {detail}"
    if interrupt.kind == "major_substitution":
        return f"{item_name} — choose an acceptable substitute"
    if interrupt.kind == "brand_lock_break":
        return f"{item_name} — required brand is unavailable"
    if interrupt.kind == "budget_exceeded":
        return "Budget — the required-item cart costs more"
    if interrupt.kind == "low_confidence":
        return f"{item_name} — confirm the list interpretation"
    return f"{item_name} — required item is unavailable"


def _approval_message(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    line: CartLine | None,
    offers_by_sku: Mapping[str, Offer],
    stores_by_id: Mapping[str, Store],
) -> str:
    if line is not None:
        offer = offers_by_sku.get(line.sku)
        store = stores_by_id.get(line.store_id)
        product_name = (
            offer.title if offer is not None else _item_display_name(
                line.canonical_item
            )
        )
        store_name = store.name if store is not None else "the selected store"
        if interrupt.kind == "non_returnable_threshold":
            return (
                f"{product_name} from {store_name} costs "
                f"{format_money(line.line_cost)} and cannot be returned."
            )
        if _attribute_labels(result, line):
            source_lines = _source_lines(result, interrupt)
            request = source_lines[0] if source_lines else line.canonical_item
            return (
                f'The list requests “{request}.” Choose from the stocked '
                "catalog matches below."
            )
        return (
            f"{product_name} from {store_name} needs your approval before "
            "the required item can proceed."
        )
    if interrupt.kind == "budget_exceeded":
        return (
            "The required-item cart is over budget by "
            f"{format_money(result.proposed_cart.shortfall_cents)}."
        )
    return interrupt.message.replace("_", " ")


def _approval_recommendation(
    result: PipelineResult,
    interrupt: ApprovalInterrupt,
    line: CartLine | None,
    options: Sequence[ApprovalDisplayOption],
) -> str:
    recommended_option = next(
        (option for option in options if option.is_recommended),
        None,
    )
    recommended = (
        recommended_option.label
        if recommended_option is not None
        else "Leave this decision pending"
    )
    if interrupt.kind == "non_returnable_threshold":
        return (
            f"{recommended}, but only after confirming that the exact product "
            "is wanted because it cannot be returned."
        )
    attribute_labels = _attribute_labels(result, line)
    if attribute_labels:
        return (
            f"{recommended}; it is the current lowest-landed-cost stocked "
            "match, but the parent should choose the acceptable "
            f"{_join_names(attribute_labels)}."
        )
    if line is not None:
        return f"{recommended}; it preserves coverage for the required item."
    return interrupt.recommendation.replace("_", " ")


def build_approval_presentations(
    result: PipelineResult,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
) -> tuple[ApprovalDisplayDecision, ...]:
    """Build the parent-facing FR-28 decision batch without changing the gate."""

    offers_by_sku = {offer.sku: offer for offer in offers}
    stores_by_id = {store.store_id: store for store in stores}
    presentations = []
    for interrupt in _all_interrupts(result.approval_batch):
        line = _interrupt_line(result, interrupt)
        item_name = (
            _item_display_name(line.canonical_item)
            if line is not None
            else "Required item"
        )
        if interrupt.kind == "budget_exceeded":
            message, options = _budget_approval_content(
                result,
                interrupt,
                offers,
                stores,
                child_labels,
            )
        else:
            options = _approval_options(
                result,
                interrupt,
                offers,
                stores,
                child_labels,
            )
            message = _approval_message(
                result,
                interrupt,
                line,
                offers_by_sku,
                stores_by_id,
            )
        presentations.append(
            ApprovalDisplayDecision(
                interrupt=interrupt,
                item_name=item_name,
                heading=_approval_heading(result, interrupt, line),
                message=message,
                recommendation=_approval_recommendation(
                    result,
                    interrupt,
                    line,
                    options,
                ),
                affected_children=_affected_children(
                    result,
                    interrupt,
                    child_labels,
                ),
                options=options,
            )
        )
    return tuple(presentations)


def approval_option_label(option: ApprovalDisplayOption) -> str:
    """Render one concise radio label safely."""

    return escape_streamlit_dollars(
        f"{option.label} "
        f"({format_streamlit_cost_delta(option.cost_delta_cents)})"
    )


def approval_option_caption(option: ApprovalDisplayOption) -> str:
    """Attach explanatory text to the corresponding radio option."""

    parts = []
    if option.is_recommended:
        parts.append("Recommended.")
    if option.leaves_required_unmet:
        parts.append(
            "Source-it-yourself choice — required item remains unmet."
        )
    if option.explanation:
        parts.append(option.explanation)
    if not parts:
        parts.append("Alternative.")
    return escape_streamlit_dollars(" ".join(parts))


def approval_default_index(
    options: Sequence[ApprovalDisplayOption],
) -> int:
    """Default every interrupt to its sole recommended, covered choice."""

    return next(
        (
            index
            for index, option in enumerate(options)
            if option.is_recommended
        ),
        0,
    )


def _all_presentation_options(
    presentation: ApprovalDisplayDecision,
) -> tuple[ApprovalDisplayOption, ...]:
    """Return every selectable option for one interrupt."""

    return presentation.options


def reconcile_interrupt_selections(
    presentations: Sequence[ApprovalDisplayDecision],
    budget_analysis: BudgetAnalysis | None,
    budget_action_ids: Sequence[str],
    outcomes: Mapping[str, str],
    offers: Sequence[Offer] = (),
) -> ApprovalSelectionState:
    """Resolve downstream interrupts made moot by current budget choices."""

    actions_by_id = (
        budget_analysis.actions_by_id
        if budget_analysis is not None
        else {}
    )
    selected_actions = tuple(
        actions_by_id[action_id]
        for action_id in dict.fromkeys(budget_action_ids)
        if action_id in actions_by_id
    )
    offers_by_sku = {offer.sku: offer for offer in offers}
    resolutions: dict[str, InterruptResolution] = {}
    active: dict[str, str] = {}
    for presentation in presentations:
        interrupt = presentation.interrupt
        if interrupt.kind == "budget_exceeded":
            selected_id = outcomes.get(interrupt.interrupt_id)
            if selected_id is not None:
                active[interrupt.interrupt_id] = selected_id
            continue
        source_ids = frozenset(interrupt.source_requirement_ids)
        resolving_action = next(
            (
                action
                for action in selected_actions
                if source_ids.intersection(action.source_requirement_ids)
            ),
            None,
        )
        if resolving_action is not None:
            if resolving_action.kind == "omit":
                message = (
                    "Resolved by your budget choice — "
                    f"{presentation.item_name.lower()} will not be purchased."
                )
            else:
                offer = (
                    offers_by_sku.get(resolving_action.replacement_sku)
                    if resolving_action.replacement_sku is not None
                    else None
                )
                product = (
                    offer.title
                    if offer is not None
                    else presentation.item_name
                )
                message = (
                    "Resolved by your budget choice — "
                    f"{product} will be used."
                )
            resolutions[interrupt.interrupt_id] = InterruptResolution(
                interrupt_id=interrupt.interrupt_id,
                message=message,
                source_requirement_ids=interrupt.source_requirement_ids,
            )
            continue
        selected_id = outcomes.get(interrupt.interrupt_id)
        valid_ids = {
            option.alternative_id
            for option in _all_presentation_options(presentation)
        }
        if selected_id in valid_ids:
            active[interrupt.interrupt_id] = selected_id
    return ApprovalSelectionState(
        active_outcomes=active,
        resolutions=resolutions,
    )


def _selected_requirement_constraints(
    result: PipelineResult,
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
    budget_action_ids: Sequence[str],
) -> tuple[
    frozenset[tuple[str, ...]],
    Mapping[tuple[str, ...], frozenset[str]],
]:
    """Return omissions and forced products represented by current choices."""

    omitted: set[tuple[str, ...]] = set()
    forced: dict[tuple[str, ...], frozenset[str]] = {}
    if result.budget_analysis is not None:
        for action_id in dict.fromkeys(budget_action_ids):
            action = result.budget_analysis.actions_by_id.get(action_id)
            if action is None:
                continue
            if action.kind == "omit":
                omitted.add(action.source_requirement_ids)
            elif action.replacement_sku is not None:
                forced[action.source_requirement_ids] = frozenset(
                    {action.replacement_sku}
                )
    for _, option in _selected_approval_options(presentations, outcomes):
        if option.leaves_required_unmet:
            omitted.add(option.source_requirement_ids)
        elif option.sku is not None and not option.is_current_product:
            forced[option.source_requirement_ids] = frozenset({option.sku})
    return frozenset(omitted), forced


def approval_selection_contradictions(
    optimization: OptimizationResult,
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
) -> tuple[str, ...]:
    """Return selected interrupts that the submitted plan does not honor."""

    selected_lines = tuple(
        line for plan in _plans(optimization) for line in plan.lines
    )
    contradictions: list[str] = []
    for presentation, option in _selected_approval_options(
        presentations,
        outcomes,
    ):
        if presentation.interrupt.kind == "budget_exceeded":
            continue
        source_ids = option.source_requirement_ids
        matching_lines = tuple(
            line
            for line in selected_lines
            if line.source_requirement_ids == source_ids
        )
        if option.leaves_required_unmet and matching_lines:
            contradictions.append(presentation.interrupt.interrupt_id)
        elif (
            option.sku is not None
            and not any(line.sku == option.sku for line in matching_lines)
        ):
            contradictions.append(presentation.interrupt.interrupt_id)
    return tuple(contradictions)


def _reprice_approval_presentation(
    presentation: ApprovalDisplayDecision,
    result: PipelineResult,
    presentations: Sequence[ApprovalDisplayDecision],
    active_outcomes: Mapping[str, str],
    budget_action_ids: Sequence[str],
    current_optimization: OptimizationResult,
    offers: Sequence[Offer],
    stores: Sequence[Store],
) -> ApprovalDisplayDecision:
    """Price every option against the same current selected plan."""

    current_item, current_tax, current_fees = _combined_costs(
        current_optimization
    )
    repriced: list[ApprovalDisplayOption] = []
    for option in presentation.options:
        hypothetical_outcomes = dict(active_outcomes)
        hypothetical_outcomes[
            presentation.interrupt.interrupt_id
        ] = option.alternative_id
        alternative = _apply_approval_outcomes(
            result.proposed_cart,
            result.matches,
            result.purchase_needs,
            presentations,
            hypothetical_outcomes,
            offers,
            stores,
            _optimization_config(result),
            budget_analysis=result.budget_analysis,
            budget_action_ids=budget_action_ids,
        )
        alternative_item, alternative_tax, alternative_fees = (
            _combined_costs(alternative)
        )
        delta = alternative.landed_cost - current_optimization.landed_cost
        repriced.append(
            replace(
                option,
                cost_delta_cents=delta,
                explanation=(
                    "Current selected plan."
                    if delta == 0
                    else _landed_delta_explanation(
                        delta,
                        alternative_item - current_item,
                        alternative_tax - current_tax,
                        alternative_fees - current_fees,
                    )
                ),
            )
        )
    return replace(presentation, options=tuple(repriced))


def _attribute_value_signature(
    result: PipelineResult,
    option: ApprovalDisplayOption,
    offers_by_sku: Mapping[str, Offer],
) -> tuple[tuple[str, str], ...]:
    """Return requested attribute values that make a catalog choice distinct."""

    if option.sku is None:
        return ()
    need = next(
        (
            candidate
            for candidate in result.purchase_needs
            if candidate.source_requirement_ids
            == option.source_requirement_ids
        ),
        None,
    )
    offer = offers_by_sku.get(option.sku)
    if need is None or offer is None:
        return ()
    signature: list[tuple[str, str]] = []
    for field_name in sorted(need.attributes):
        aliases = ATTRIBUTE_OFFER_KEYS.get(field_name, (field_name,))
        value = next(
            (
                offer.attributes[key]
                for key in aliases
                if key in offer.attributes
            ),
            "not recorded",
        )
        signature.append((field_name, repr(value)))
    return tuple(signature)


def group_approval_options(
    result: PipelineResult,
    presentation: ApprovalDisplayDecision,
    offers: Sequence[Offer],
) -> tuple[
    tuple[ApprovalDisplayOption, ...],
    tuple[ApprovalDisplayOption, ...],
]:
    """Keep meaningful attribute choices visible and collapse equivalent ones."""

    catalog_options = tuple(
        option for option in presentation.options if option.sku is not None
    )
    if len(catalog_options) <= 1:
        return presentation.options, ()
    offers_by_sku = {offer.sku: offer for offer in offers}
    always_visible_ids: set[str] = set()
    grouped: dict[
        tuple[tuple[str, str], ...],
        list[ApprovalDisplayOption],
    ] = {}
    for option in catalog_options:
        candidate = result.matches.candidate(
            option.source_requirement_ids,
            option.sku or "",
        )
        if (
            option.is_recommended
            or option.is_current_product
            or (
                candidate is not None
                and candidate.attribute_status == "exact"
            )
        ):
            always_visible_ids.add(option.alternative_id)
            continue
        signature = _attribute_value_signature(
            result,
            option,
            offers_by_sku,
        )
        grouped.setdefault(signature, []).append(option)
    for group in grouped.values():
        cheapest = min(
            group,
            key=lambda option: (
                option.cost_delta_cents,
                option.alternative_id,
            ),
        )
        always_visible_ids.add(cheapest.alternative_id)

    primary = tuple(
        option
        for option in presentation.options
        if (
            option.sku is None
            or option.alternative_id in always_visible_ids
        )
    )
    other = tuple(
        option
        for option in catalog_options
        if option.alternative_id not in always_visible_ids
    )
    return primary, other


def _selected_approval_options(
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
) -> tuple[
    tuple[ApprovalDisplayDecision, ApprovalDisplayOption],
    ...,
]:
    selected = []
    for presentation in presentations:
        selected_id = outcomes.get(presentation.interrupt.interrupt_id)
        option = next(
            (
                candidate
                for candidate in _all_presentation_options(presentation)
                if candidate.alternative_id == selected_id
            ),
            None,
        )
        if option is not None:
            selected.append((presentation, option))
    return tuple(selected)


def _self_sourced_decisions(
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
    budget_analysis: BudgetAnalysis | None = None,
    budget_action_ids: Sequence[str] = (),
    child_labels: Mapping[str, str] | None = None,
) -> tuple[SelfSourcedSelection, ...]:
    selections = []
    seen_requirement_ids: set[tuple[str, ...]] = set()
    for presentation, option in _selected_approval_options(
        presentations,
        outcomes,
    ):
        if not option.leaves_required_unmet:
            continue
        if option.source_requirement_ids in seen_requirement_ids:
            continue
        seen_requirement_ids.add(option.source_requirement_ids)
        selections.append(
            SelfSourcedSelection(
                presentation=presentation,
                option=option,
                item_name=option.item_name or presentation.item_name,
                affected_children=(
                    option.affected_children
                    or presentation.affected_children
                ),
            )
        )
    if budget_analysis is not None:
        labels = child_labels or {}
        budget_presentation = next(
            (
                presentation
                for presentation in presentations
                if presentation.interrupt.kind == "budget_exceeded"
            ),
            None,
        )
        for action_id in budget_action_ids:
            action = budget_analysis.actions_by_id.get(action_id)
            if (
                action is None
                or action.kind != "omit"
                or action.source_requirement_ids in seen_requirement_ids
                or budget_presentation is None
            ):
                continue
            seen_requirement_ids.add(action.source_requirement_ids)
            affected_children = tuple(
                _child_display_label(child_id, labels)
                for child_id in action.allocated_to
            )
            option = ApprovalDisplayOption(
                alternative_id=action.action_id,
                label=(
                    f"Source {_item_display_name(action.canonical_item)} "
                    "myself"
                ),
                cost_delta_cents=action.landed_delta_cents,
                source_requirement_ids=action.source_requirement_ids,
                affected_lines=action.affected_line_ids,
                affected_children=affected_children,
                item_name=_item_display_name(action.canonical_item),
                leaves_required_unmet=True,
            )
            selections.append(
                SelfSourcedSelection(
                    presentation=budget_presentation,
                    option=option,
                    item_name=_item_display_name(action.canonical_item),
                    affected_children=affected_children,
                )
            )
    return tuple(selections)


def _apply_approval_outcomes(
    optimization: OptimizationResult,
    matches: MatchResult,
    unit_needs: Sequence[UnitNeed],
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
    offers: Sequence[Offer],
    stores: Sequence[Store],
    config: OptimizationConfig,
    budget_analysis: BudgetAnalysis | None = None,
    budget_action_ids: Sequence[str] = (),
    precomputed_budget_optimization: OptimizationResult | None = None,
) -> OptimizationResult:
    selected = _selected_approval_options(presentations, outcomes)
    generic_unmet_source_ids = {
        option.source_requirement_ids
        for _, option in selected
        if option.leaves_required_unmet
    }
    generic_forced_skus = {
        option.source_requirement_ids: frozenset({option.sku})
        for _, option in selected
        if (
            option.sku is not None
            and not option.is_current_product
            and not option.leaves_required_unmet
        )
    }
    unmet_source_ids = set(generic_unmet_source_ids)
    forced_skus = dict(generic_forced_skus)
    if budget_analysis is not None:
        actions_by_id = budget_analysis.actions_by_id
        for action_id in dict.fromkeys(budget_action_ids):
            action = actions_by_id.get(action_id)
            if action is None:
                continue
            if action.kind == "omit":
                unmet_source_ids.add(action.source_requirement_ids)
                continue
            if action.replacement_sku is None:
                continue
            existing = forced_skus.get(action.source_requirement_ids)
            replacement = frozenset({action.replacement_sku})
            if existing is not None and existing != replacement:
                raise ValueError(
                    "Select only one cheaper substitution for each required line"
                )
            forced_skus[action.source_requirement_ids] = replacement
    if (
        precomputed_budget_optimization is not None
        and not generic_unmet_source_ids
        and not generic_forced_skus
    ):
        return precomputed_budget_optimization
    if not unmet_source_ids and not forced_skus:
        return optimization

    remaining_needs = tuple(
        need
        for need in unit_needs
        if need.source_requirement_ids not in unmet_source_ids
    )
    candidate_skus = dict(matches.candidate_skus_by_need)
    candidate_skus.update(forced_skus)
    return optimize_cart(
        remaining_needs,
        offers,
        stores,
        config,
        candidate_skus_by_need=candidate_skus,
    )


def _combined_costs(
    optimization: OptimizationResult,
) -> tuple[int, int, int]:
    plans = _plans(optimization)
    return (
        sum(plan.item_subtotal for plan in plans),
        sum(plan.tax for plan in plans),
        sum(plan.fulfillment_fees for plan in plans),
    )


def _decision_log(
    result: PipelineResult,
    parent_decisions: Sequence[Decision],
) -> tuple[Decision, ...]:
    return result.decisions + tuple(parent_decisions)


def _has_parent_selected_unmet_item(
    state: Mapping[str, Any],
    result: PipelineResult | None,
) -> bool:
    """Return whether a recorded parent choice leaves a required item unmet."""

    if result is not None and result.budget_analysis is not None:
        for action_id in state.get("budget_action_ids", ()):
            action = result.budget_analysis.actions_by_id.get(action_id)
            if action is not None and action.kind == "omit":
                return True
    outcomes = state.get("approval_outcomes", {})
    presentations = state.get("approval_presentations_cache") or ()
    for presentation in presentations:
        selected_id = outcomes.get(presentation.interrupt.interrupt_id)
        if any(
            option.alternative_id == selected_id
            and option.leaves_required_unmet
            for option in presentation.options
        ):
            return True
    return False


def tone_state_from_session(
    state: Mapping[str, Any],
) -> ToneState:
    """Build the single application-wide tone state without recalculating."""

    result = state.get("result")
    if not isinstance(result, PipelineResult):
        return ToneState(has_error=bool(state.get("ui_error_active", False)))
    optimization = (
        state.get("approved_optimization") or result.proposed_cart
    )
    return ToneState(
        has_shortfall=optimization.shortfall_cents > 0,
        has_unmet_required=(
            not optimization.is_complete
            or _has_parent_selected_unmet_item(state, result)
        ),
        has_extraction_failure=bool(result.extraction_failures),
        has_error=bool(state.get("ui_error_active", False)),
    )


def build_text_summary(
    result: PipelineResult,
    optimization: OptimizationResult,
    matches: MatchResult,
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
    approval_outcomes: Mapping[str, str],
    self_sourced_decisions: Sequence[SelfSourcedSelection],
    parent_decisions: Sequence[Decision],
) -> str:
    """Build the manual-shopping export artifact (FR-34, FR-36)."""

    stores_by_id = {store.store_id: store for store in stores}
    catalog_offers = tuple(load_catalog())
    item_subtotal, tax, fees = _combined_costs(optimization)
    lines = [
        "READY, SET, SCHOOL",
    ]
    if result.session.budget_total is not None:
        variance = result.session.budget_total - optimization.landed_cost
        lines.append(
            (
                f"BUDGET REMAINING: {format_money(variance)}"
                if variance >= 0
                else (
                    "BUDGET SHORTFALL: "
                    f"{format_money(abs(variance))}"
                )
            )
        )
    else:
        lines.append("BUDGET: NO SET BUDGET")
    lines.extend([
        "Simulated catalog; fictional stores; no payment was collected.",
        "",
        f"ITEM SUBTOTAL: {format_money(item_subtotal)}",
        f"TAX: {format_money(tax)}",
        f"FULFILLMENT FEES: {format_money(fees)}",
        f"LANDED COST: {format_money(optimization.landed_cost)}",
        "",
    ])
    export_is_complete = (
        optimization.is_complete
        and not self_sourced_decisions
        and not result.extraction_failures
    )
    if not export_is_complete:
        lines.extend(
            [
                (
                    "STATUS: REQUIRED ITEMS OR LISTS ARE MISSING — one or "
                    "more are not represented in this cart."
                ),
                "",
            ]
        )
        if self_sourced_decisions:
            lines.append("ITEMS YOU CHOSE TO SOURCE YOURSELF")
            lines.extend(
                (
                    f"  {selection.item_name} | "
                    f"{_join_names(selection.affected_children)} | "
                    "UNFULFILLED BY PARENT CHOICE"
                )
                for selection in self_sourced_decisions
            )
        if not optimization.is_complete:
            lines.append("REQUIRED ITEMS NOT IN THE CART")
            lines.extend(
                f"  {_item_display_name(item)} | UNAVAILABLE"
                for item in optimization.gap_items
            )
        if result.extraction_failures:
            lines.append("LISTS NOT INCLUDED")
            lines.extend(
                (
                    f"  {_child_display_label(child_id, child_labels)} | "
                    f"{reason}"
                )
                for child_id, reason in result.extraction_failures.items()
            )
        lines.append("")
    else:
        lines.extend(["STATUS: ALL REQUIRED ITEMS COVERED", ""])
    lines.extend(
        [
            "HOW TO CHECK THIS PLAN",
            (
                "A language model read and interpreted the source lines below. "
                "Quantities, package choices, prices, tax, fees, and totals were "
                "calculated deterministically from confirmed items and the "
                "simulated catalog."
            ),
            "",
        ]
    )
    scope_rows = document_scope_rows(result, child_labels)
    if scope_rows:
        lines.append("DOCUMENT SECTIONS")
        lines.extend(
            (
                f"  {row['For']} | {row['Treatment']} | "
                f"{row['Document section']}"
            )
            for row in scope_rows
        )
        lines.append("")
    lines.append("SOURCE LINES")
    lines.extend(
        (
            f"  {row['For']} | {row['Interpreted as']} | "
            f"{row['Status']} | {row['Exact source line']}"
        )
        for row in source_interpretation_rows(result, child_labels)
    )
    uninterpreted = uninterpreted_source_rows(result, child_labels)
    if uninterpreted:
        lines.append("SOURCE CONTENT NOT INTERPRETED")
        lines.extend(
            (
                f"  {row['For']} | {row['Treatment']} | "
                f"{row['Source content']}"
            )
            for row in uninterpreted
        )
    skipped = skipped_source_rows(result, child_labels)
    if skipped:
        lines.append("SOURCE CONTENT DELIBERATELY SKIPPED")
        lines.extend(
            (
                f"  {row['For']} | {row['Treatment']} | "
                f"{row['Source content']}"
            )
            for row in skipped
        )
    lines.append("")
    for plan in _plans(optimization):
        for order in plan.store_orders:
            store_name = stores_by_id.get(order.store_id)
            lines.append(
                (
                    f"{store_name.name if store_name else 'Unknown store'} "
                    f"— {order.fulfillment_method.title()}"
                )
            )
            for cart_line in order.lines:
                allocations = ", ".join(
                    f"{_child_display_label(child_id, child_labels)}: {units}"
                    for child_id, units in cart_line.allocated_to.items()
                )
                lines.append(
                    (
                        f"  {_product_name(cart_line, matches)} | "
                        f"{cart_line.packs_purchased} pack(s) | "
                        f"{cart_line.units_needed} needed / "
                        f"{cart_line.units_purchased} bought | "
                        f"{format_money(cart_line.line_cost)} | {allocations}"
                    )
                )
            lines.extend(
                [
                    f"  ITEM SUBTOTAL: {format_money(order.item_subtotal)}",
                    f"  TAX: {format_money(order.tax)}",
                    (
                        "  FULFILLMENT FEE: "
                        f"{format_money(order.fulfillment_fee)}"
                    ),
                    f"  LANDED COST: {format_money(order.landed_cost)}",
                    "",
                ]
            )
    lines.append("APPROVAL OUTCOMES")
    if approval_outcomes:
        lines.extend(
            f"  {interrupt_id}: {outcome}"
            for interrupt_id, outcome in approval_outcomes.items()
        )
    else:
        lines.append("  No approvals were required.")
    lines.extend(["", "DECISION LOG"])
    lines.extend(
        (
            f"  {decision.timestamp.isoformat()} | {decision.actor} | "
            f"{decision.type.replace('_', ' ').title()} | "
            f"{_humanize_internal_text(decision.rationale, catalog_offers, stores)}"
        )
        for decision in _decision_log(result, parent_decisions)
    )
    return "\n".join(lines)


def _initialize_state(st: Any) -> None:
    defaults: Mapping[str, Any] = {
        "screen": "intake",
        "demo_mode": False,
        "child_count": 1,
        "intake_step": 1,
        "max_intake_step_reached": 1,
        "max_stage_reached": 1,
        "student_validation_attempted": False,
        "budget_validation_attempted": False,
        "preferences_validation_attempted": False,
        "budget_mode_label": "One combined budget",
        "previous_budget_mode_label": "One combined budget",
        "combined_budget_text": DEFAULT_BUDGET_TEXT,
        "shopping_preference_label": next(iter(SHOPPING_MODES)),
        "store_radius_miles": DEFAULT_RADIUS_MILES,
        "fulfillment_label": next(iter(FULFILLMENT_OPTIONS)),
        "preferences_defaults_initialized": False,
        "sales_tax_state": DEFAULT_TAX_STATE_OPTION,
        "tax_rate_text": STATE_GENERAL_SALES_TAX_PERCENT[
            DEFAULT_TAX_STATE_OPTION
        ],
        "tax_prefill_state": DEFAULT_TAX_STATE_OPTION,
        "intake": None,
        "list_inputs": (),
        "document_structures": {},
        "document_selections": {},
        "source_reference_cache": {},
        "structure_errors": {},
        "structure_cache_ready": False,
        "extracted_lists": {},
        "unmerged_extracted_lists": {},
        "extraction_errors": {},
        "extraction_cache_ready": False,
        "requirement_merge_result": None,
        "requirement_merge_resolved": False,
        "requirement_merge_choices": {},
        "requirement_constraint_choices": {},
        "requirement_variant_quantity_choices": {},
        "requirement_merge_validation_errors": (),
        "review_items": (),
        "organized_list_confirmed": False,
        "allow_unresolved_items": False,
        "list_identity_confirmed": False,
        "result": None,
        "approval_outcomes": {},
        "resolved_interrupts": {},
        "approval_presentations_cache": None,
        "approval_generation": 0,
        "approved_optimization": None,
        "budget_action_ids": (),
        "parent_decisions": (),
        "include_addons": False,
        "addon_selection_token": None,
        "addon_evaluation": None,
        "checkout_confirmation": None,
        "stockout_skus": frozenset(),
        "price_overrides": {},
        "replan_preserved_approval_ids": frozenset(),
        "replan_preserved_budget_action_ids": frozenset(),
        "catalog_change_notice": None,
        "ui_error_active": False,
        "progress_substep": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_session_data(st: Any) -> None:
    """Remove every in-memory session value; nothing is persisted (BRD 11.3)."""

    st.session_state.clear()


def _persistent_notice(st: Any) -> None:
    with st.expander(
        "How Ready, Set, School works",
        expanded=False,
    ):
        st.write(
            "Ready, Set, School turns a school supply list into a shopping "
            "plan you control."
        )
        st.markdown("**How it works**")
        st.write(
            "Add your students, upload their lists, personalize what goes in "
            "the cart, and get a plan with prices, stores, and totals."
        )
        st.markdown("**What's real and what isn't**")
        st.write(
            "A language model reads the list. Everything after that — "
            "quantities, package sizes, prices, tax, totals — is calculated, "
            "not guessed. The catalog, stores, prices, and distances are "
            "simulated for this demonstration."
        )
        st.markdown("**Your privacy**")
        st.write(
            "We don't store anything about your kids. Close the tab and it's "
            "gone. Checkout is simulated and never asks for payment."
        )


def journey_stage_statuses(
    current_stage: int,
    max_stage_reached: int,
) -> tuple[str, ...]:
    """Classify four FR-01-FR-04 banner destinations."""

    if current_stage not in {1, 2, 3, 4}:
        raise ValueError("Current journey stage is outside the supported range")
    reached = min(4, max(current_stage, max_stage_reached))
    return tuple(
        (
            "current"
            if stage == current_stage
            else "completed"
            if stage <= reached
            else "unavailable"
        )
        for stage in range(1, 5)
    )


def navigate_to_journey_stage(
    state: MutableMapping[str, Any],
    target_stage: int,
) -> None:
    """Jump to a reached stage without discarding FR-01-FR-06 values."""

    max_stage = int(state.get("max_stage_reached", 1))
    if target_stage < 1 or target_stage > min(4, max_stage):
        raise ValueError("That journey stage has not been reached yet")
    preserve_navigation_state(state)
    if target_stage == 1:
        state["screen"] = "intake"
        state["intake_step"] = 1
        return
    allowed_targets: Mapping[int, frozenset[str]] = {
        2: frozenset({"lists", "sections", "requirement_merge"}),
        3: frozenset({"review"}),
        4: frozenset({"working", "approval", "summary"}),
    }
    default_targets = {2: "lists", 3: "review", 4: "working"}
    stored_target = str(
        state.get(
            f"journey_stage_screen_{target_stage}",
            default_targets[target_stage],
        )
    )
    state["screen"] = (
        stored_target
        if stored_target in allowed_targets[target_stage]
        else default_targets[target_stage]
    )


def _screen_progress(
    st: Any,
    screen: str,
    substep: str | None = None,
) -> None:
    """Show one compact, clickable four-stage parent journey."""

    del substep
    current_stage = int(SCREEN_PHASES[screen][0])
    st.session_state["max_stage_reached"] = max(
        current_stage,
        int(st.session_state.get("max_stage_reached", 1)),
    )
    st.session_state[f"journey_stage_screen_{current_stage}"] = screen
    statuses = journey_stage_statuses(
        current_stage,
        int(st.session_state["max_stage_reached"]),
    )
    columns = st.columns(4)
    for stage, (column, label, status) in enumerate(
        zip(columns, JOURNEY_STAGES, statuses, strict=True),
        start=1,
    ):
        marker = (
            "✓ "
            if status == "completed"
            else ""
        )
        clicked = column.button(
            f"{marker}{label}",
            key=f"journey_stage_navigation_{stage}",
            type="primary" if status == "current" else "secondary",
            disabled=status != "completed",
            use_container_width=True,
            help=(
                "Current stage"
                if status == "current"
                else "Go to this completed stage"
                if status == "completed"
                else "Complete the earlier stages first"
            ),
        )
        if clicked:
            navigate_to_journey_stage(st.session_state, stage)
            st.rerun()


def _render_development_diagnostic(st: Any) -> None:
    with st.expander("Development use: model connection diagnostic"):
        st.checkbox(
            "Use stable offline demo mode",
            key="demo_mode",
            help=(
                "Uses the built-in sample list, deterministic document "
                "organization and extraction, and the seeded fictional "
                "catalog. It does not process a real uploaded list offline."
            ),
        )
        st.caption(
            "This is a presentation fallback, not a parent shopping "
            "preference."
        )
        diagnostic = get_provider_diagnostic()
        st.write(
            escape_streamlit_dollars(
                f"Active provider: {diagnostic.provider_name}"
            )
        )
        st.write(
            escape_streamlit_dollars(
                f"Base URL: {diagnostic.base_url}"
            )
        )
        st.write(
            escape_streamlit_dollars(
                f"API key found: {'Yes' if diagnostic.found else 'No'}"
            )
        )
        st.write(
            escape_streamlit_dollars(
                "Credential: "
                f"{diagnostic.credential_name} from "
                f"{diagnostic.source or 'no source'}"
            )
        )
        st.write(
            escape_streamlit_dollars(
                "Key preview: "
                f"{diagnostic.masked_key or 'Not available'}"
            )
        )
        st.write(
            escape_streamlit_dollars(
                f"Text model: {diagnostic.text_model or 'Not configured'}"
            )
        )
        st.write(
            escape_streamlit_dollars(
                "Vision model: "
                f"{diagnostic.vision_model or 'Not configured — images rejected'}"
            )
        )
        if diagnostic.configuration_error is not None:
            st.error(
                escape_streamlit_dollars(
                    f"Configuration: {diagnostic.configuration_error}"
                )
            )
        st.caption(
            "The preview contains only the first 8 and last 4 characters. "
            "The full key is never displayed."
        )
        if st.button(
            "Test configured endpoint",
            key="development_model_connection_test",
        ):
            success, message = probe_openai_connection()
            if success:
                st.success(escape_streamlit_dollars(message))
            else:
                st.error(escape_streamlit_dollars(message))
                st.caption(
                    "The complete exception and traceback were written to "
                    "the Streamlit application logs."
                )


def _intake_students_from_state(
    state: Mapping[str, Any],
    student_count: int,
) -> tuple[dict[str, Any], ...]:
    """Rebuild FR-01/FR-05 student records from Streamlit widget state."""

    students: list[dict[str, Any]] = []
    for index in range(student_count):
        grade_value = state.get(f"child_grade_{index}")
        grade = "" if grade_value is None else str(grade_value).strip()
        entity_label = str(
            state.get(f"entity_type_{index}", "One student")
        )
        is_classroom = entity_label in {
            "A classroom group",
            "Classroom",
        }
        students.append(
            {
                "child_id": f"child-{index + 1}",
                "label": str(
                    state.get(f"child_label_{index}", "")
                ).strip(),
                "grade": grade,
                "student_count": (
                    int(state.get(f"student_count_{index}", 20))
                    if is_classroom
                    else 1
                ),
                "entity_type": (
                    "classroom"
                    if is_classroom
                    else "student"
                ),
            }
        )
    return tuple(students)


@dataclass(frozen=True)
class ListUploadDraft:
    """One uploaded list retained while the parent navigates (FR-06)."""

    name: str
    data: bytes


@dataclass(frozen=True)
class SourceReference:
    """One-click evidence for a detected section or extracted source line."""

    document_name: str
    page_number: int | None
    source_line: str
    rendered_page: bytes | None
    mime_type: str | None


def _list_input_bytes(list_input: ListInput) -> bytes | None:
    """Return retained session-only source bytes for an evidence preview."""

    source = list_input.source
    if isinstance(source, bytes):
        return source
    if isinstance(source, Path):
        return source.read_bytes()
    if list_input.mime_type == "text/plain":
        return source.encode("utf-8")
    try:
        path = Path(source)
        return path.read_bytes() if path.is_file() else None
    except (OSError, ValueError):
        return None


def build_source_reference(
    list_input: ListInput,
    *,
    page_number: int | None,
    source_line: str,
) -> SourceReference:
    """Render the named source page while retaining its exact evidence line."""

    data = _list_input_bytes(list_input)
    rendered_page: bytes | None = None
    if (
        data is not None
        and list_input.mime_type == "application/pdf"
        and page_number is not None
    ):
        document = pdfium.PdfDocument(data)
        try:
            page_index = page_number - 1
            if page_index < 0 or page_index >= len(document):
                raise ValueError(
                    f"Page {page_number} is not present in the uploaded document."
                )
            page = document[page_index]
            bitmap = None
            try:
                bitmap = page.render(scale=PDF_RENDER_SCALE)
                image = bitmap.to_pil()
                output = BytesIO()
                image.save(output, format="PNG")
                rendered_page = output.getvalue()
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
        finally:
            document.close()
    elif (
        data is not None
        and list_input.mime_type in {"image/jpeg", "image/png"}
    ):
        rendered_page = data
    return SourceReference(
        document_name=list_input.resolved_document_name,
        page_number=page_number,
        source_line=source_line,
        rendered_page=rendered_page,
        mime_type=list_input.mime_type,
    )


def _source_reference_cache_key(
    list_input: ListInput,
    page_number: int | None,
) -> tuple[str, str, int, int | None]:
    return (
        list_input.child_id,
        list_input.resolved_document_name,
        hash(list_input.source),
        page_number,
    )


def _render_source_reference(
    st: Any,
    list_input: ListInput,
    *,
    page_number: int | None,
    source_line: str,
    key: str,
) -> None:
    """Place the exact source line and rendered uploaded page one click away."""

    del key
    cache = st.session_state.setdefault("source_reference_cache", {})
    cache_key = _source_reference_cache_key(list_input, page_number)
    reference = cache.get(cache_key)
    if reference is None:
        reference = build_source_reference(
            list_input,
            page_number=page_number,
            source_line=source_line,
        )
        cache[cache_key] = reference
    elif reference.source_line != source_line:
        reference = replace(reference, source_line=source_line)
    page_text = (
        f" · page {reference.page_number}"
        if reference.page_number is not None
        else ""
    )
    with st.popover(
        f"View source · {reference.document_name}{page_text}",
    ):
        st.caption(
            escape_streamlit_dollars(
                f"Exact source line: {reference.source_line}"
            )
        )
        if reference.rendered_page is not None:
            st.image(
                reference.rendered_page,
                caption=(
                    f"{reference.document_name}{page_text}. "
                    "Use the exact line above to locate the source."
                ),
                use_container_width=True,
            )
        elif reference.mime_type == "text/plain":
            source_bytes = _list_input_bytes(list_input) or b""
            st.code(
                source_bytes.decode("utf-8", errors="replace"),
                language=None,
                wrap_lines=True,
            )
        else:
            st.info(
                "A rendered preview is unavailable. The document name, page, "
                "and exact source line are shown above."
            )


def _is_navigation_widget_key(key: str) -> bool:
    """Return whether a widget value should survive screen navigation."""

    if key.startswith(
        (
            NAVIGATION_STATE_PREFIX,
            INTAKE_WIDGET_STATE_PREFIX,
            INTAKE_WIDGET_TOUCHED_PREFIX,
        )
    ):
        return False
    return (
        key in NAVIGATION_WIDGET_KEYS
        or key.startswith(NAVIGATION_WIDGET_PREFIXES)
        or ":" in key
    )


def intake_widget_key(durable_key: str) -> str:
    """Return the temporary Streamlit key for a durable intake value."""

    return INTAKE_WIDGET_STATE_PREFIX + durable_key


def mount_intake_widget_value(
    state: MutableMapping[str, Any],
    durable_key: str,
    default: Any,
) -> str:
    """Mount a widget from durable FR-01-FR-04 state.

    Streamlit deletes a keyed widget value when the widget is not rendered.
    Keeping the application value under ``durable_key`` and giving the widget
    a separate temporary key preserves both user edits and untouched defaults
    across conditional sections and banner navigation.
    """

    if durable_key not in state:
        state[durable_key] = default
    temporary_key = intake_widget_key(durable_key)
    state[temporary_key] = state[durable_key]
    return temporary_key


def commit_intake_widget_value(durable_key: str) -> None:
    """Copy one changed Streamlit widget value into durable intake state."""

    import streamlit as st

    temporary_key = intake_widget_key(durable_key)
    if temporary_key not in st.session_state:
        return
    value = st.session_state[temporary_key]
    st.session_state[durable_key] = value
    st.session_state[NAVIGATION_STATE_PREFIX + durable_key] = value
    st.session_state[INTAKE_WIDGET_TOUCHED_PREFIX + durable_key] = True


def _intake_section_for_navigation_key(key: str) -> int | None:
    """Return the intake section that owns a widget-backed value."""

    if key == "child_count" or key.startswith(
        (
            "entity_type_",
            "student_name_",
            "teacher_name_",
            "child_grade_",
            "student_grade_",
            "classroom_grade_",
            "student_count_",
        )
    ):
        return 1
    if key in {"budget_mode_label", "combined_budget_text"} or key.startswith(
        "budget_"
    ):
        return 2
    if key in {
        "shopping_preference_label",
        "selected_store_names",
        "maximum_stores",
        "store_radius_miles",
        "fulfillment_label",
        "sales_tax_state",
        "tax_rate_text",
    }:
        return 3
    return None


def preserve_navigation_state(state: MutableMapping[str, Any]) -> None:
    """Snapshot and restore reversible form navigation state (FR-01–FR-06)."""

    active_intake_section = int(state.get("intake_step", 1))
    widget_keys: set[str] = set()
    for key in tuple(state):
        if key.startswith(NAVIGATION_STATE_PREFIX):
            widget_keys.add(key.removeprefix(NAVIGATION_STATE_PREFIX))
        elif _is_navigation_widget_key(key):
            widget_keys.add(key)
    for key in widget_keys:
        saved_key = NAVIGATION_STATE_PREFIX + key
        owner_section = _intake_section_for_navigation_key(key)
        if owner_section is not None and owner_section != active_intake_section:
            if saved_key in state:
                state[key] = state[saved_key]
            continue
        if key in state:
            state[saved_key] = state[key]
        elif saved_key in state:
            state[key] = state[saved_key]


def restore_intake_section_values(
    state: MutableMapping[str, Any],
    section: int,
    entry_count: int,
) -> None:
    """Restore saved FR-01-FR-04 widgets when a banner reopens a section."""

    if section not in {1, 2, 3}:
        raise ValueError("Unsupported intake section")
    shared_keys: Mapping[int, tuple[str, ...]] = {
        1: ("child_count",),
        2: ("budget_mode_label", "combined_budget_text"),
        3: (
            "shopping_preference_label",
            "selected_store_names",
            "maximum_stores",
            "store_radius_miles",
            "fulfillment_label",
            "sales_tax_state",
            "tax_rate_text",
        ),
    }
    keys = list(shared_keys[section])
    saved_child_count = state.get(
        NAVIGATION_STATE_PREFIX + "child_count",
        state.get("child_count", entry_count),
    )
    effective_entry_count = int(saved_child_count)
    if section == 1:
        for index in range(effective_entry_count):
            keys.extend(
                (
                    f"entity_type_{index}",
                    f"student_name_{index}",
                    f"teacher_name_{index}",
                    f"child_grade_{index}",
                    f"student_grade_{index}",
                    f"classroom_grade_{index}",
                    f"student_count_{index}",
                )
            )
    elif section == 2:
        keys.extend(
            f"budget_{index}" for index in range(effective_entry_count)
        )
    for key in keys:
        saved_key = NAVIGATION_STATE_PREFIX + key
        if saved_key in state:
            state[key] = state[saved_key]


def navigate_intake_step(
    state: MutableMapping[str, Any],
    target_step: int,
) -> None:
    """Preserve FR-01-FR-04 values before moving within intake."""

    if target_step not in {1, 2, 3}:
        raise ValueError("Intake step must be Students, Budget, or Preferences")
    preserve_navigation_state(state)
    state["intake_step"] = target_step
    state["max_intake_step_reached"] = max(
        target_step,
        int(state.get("max_intake_step_reached", 1)),
    )


def navigate_back_to_screen(
    state: MutableMapping[str, Any],
    target_screen: str,
) -> None:
    """Preserve FR-01-FR-06 values before backward screen navigation."""

    preserve_navigation_state(state)
    state["screen"] = target_screen


def _delete_navigation_value(
    state: MutableMapping[str, Any],
    key: str,
) -> None:
    """Delete both a live widget value and its navigation snapshot."""

    state.pop(key, None)
    state.pop(NAVIGATION_STATE_PREFIX + key, None)
    state.pop(intake_widget_key(key), None)
    state.pop(INTAKE_WIDGET_TOUCHED_PREFIX + key, None)


def _remember_upload_draft(
    state: MutableMapping[str, Any],
    draft_key: str,
    upload: Any,
) -> ListUploadDraft | None:
    """Retain uploaded bytes without trying to repopulate a file widget."""

    if upload is not None:
        state[draft_key] = ListUploadDraft(
            name=str(upload.name),
            data=bytes(upload.getvalue()),
        )
    draft = state.get(draft_key)
    return draft if isinstance(draft, ListUploadDraft) else None


def _limit_reached_stage(
    state: MutableMapping[str, Any],
    latest_valid_stage: int,
) -> None:
    """Prevent navigation to work invalidated by a parent edit."""

    if "max_stage_reached" in state:
        state["max_stage_reached"] = min(
            int(state["max_stage_reached"]),
            latest_valid_stage,
        )


def _invalidate_plan_state(state: MutableMapping[str, Any]) -> None:
    """Clear only shopping-plan state after an upstream edit."""

    reset_values: Mapping[str, Any] = {
        "result": None,
        "approved_optimization": None,
        "approval_outcomes": {},
        "resolved_interrupts": {},
        "approval_presentations_cache": None,
        "budget_action_ids": (),
        "parent_decisions": (),
        "checkout_confirmation": None,
    }
    for key, value in reset_values.items():
        if key in state:
            state[key] = value


def clear_inactive_intake_entries(
    state: MutableMapping[str, Any],
    active_count: int,
) -> tuple[str, ...]:
    """Delete hidden intake widget values when an entry is removed (FR-01)."""

    if not 0 <= active_count <= MAX_CHILDREN_PER_SESSION:
        raise ValueError("Active intake entry count is outside the allowed range")
    notices: list[str] = []
    for index in range(active_count, MAX_CHILDREN_PER_SESSION):
        child_id = f"child-{index + 1}"
        label = str(
            state.get(f"child_label_{index}")
            or state.get(f"student_name_{index}")
            or state.get(f"teacher_name_{index}")
            or f"Student or classroom {index + 1}"
        ).strip()
        budget_key = f"budget_{index}"
        had_budget = (
            budget_key in state
            or NAVIGATION_STATE_PREFIX + budget_key in state
        )
        list_value_keys = tuple(
            f"{prefix}_{index}"
            for prefix in (
                "list_upload",
                "list_upload_draft",
                "list_paste",
            )
        )
        saved_inputs = tuple(state.get("list_inputs", ()))
        had_list = any(
            state.get(key)
            or state.get(NAVIGATION_STATE_PREFIX + key)
            for key in list_value_keys
        ) or any(
            getattr(list_input, "child_id", None) == child_id
            for list_input in saved_inputs
        )
        selections = state.get("document_selections", {})
        had_selection = (
            isinstance(selections, Mapping)
            and child_id in selections
        )
        had_entry = any(
            (
                f"entity_type_{index}" in state,
                f"child_label_{index}" in state,
                f"student_name_{index}" in state,
                f"teacher_name_{index}" in state,
            )
        )
        for prefix in INTAKE_ENTRY_VALUE_PREFIXES:
            _delete_navigation_value(state, f"{prefix}_{index}")
        _delete_navigation_value(state, f"entity_type_{index}")
        _delete_navigation_value(
            state,
            f"{INTAKE_ENTRY_TYPE_TRACKER_PREFIX}_{index}",
        )
        _delete_navigation_value(
            state,
            f"{INTAKE_ENTRY_GRADE_TRACKER_PREFIX}_{index}",
        )
        _delete_navigation_value(
            state,
            f"document_sections_{child_id}",
        )
        if saved_inputs:
            state["list_inputs"] = tuple(
                list_input
                for list_input in saved_inputs
                if getattr(list_input, "child_id", None) != child_id
            )
        source_cache = state.get("source_reference_cache")
        if isinstance(source_cache, Mapping):
            state["source_reference_cache"] = {
                cache_key: value
                for cache_key, value in source_cache.items()
                if not (
                    isinstance(cache_key, tuple)
                    and cache_key
                    and cache_key[0] == child_id
                )
            }
        intake = state.get("intake")
        if isinstance(intake, Mapping):
            updated_intake = dict(intake)
            updated_intake["children"] = tuple(
                child
                for child in tuple(intake.get("children", ()))
                if str(child.get("child_id", "")) != child_id
            )
            allocations = dict(intake.get("budget_allocations", {}))
            allocations.pop(child_id, None)
            updated_intake["budget_allocations"] = allocations
            state["intake"] = updated_intake
        for mapping_key in (
            "document_structures",
            "document_selections",
            "structure_errors",
            "extracted_lists",
            "unmerged_extracted_lists",
            "extraction_errors",
        ):
            mapping = state.get(mapping_key)
            if isinstance(mapping, Mapping) and child_id in mapping:
                updated = dict(mapping)
                updated.pop(child_id, None)
                state[mapping_key] = updated
        review_items = tuple(state.get("review_items", ()))
        if review_items:
            state["review_items"] = tuple(
                item
                for item in review_items
                if getattr(item, "child_id", None) != child_id
            )
        if had_entry or had_budget or had_list or had_selection:
            if had_budget:
                notices.append(f"{label}'s budget allocation was removed.")
            if had_list:
                notices.append(f"{label}'s supply list was removed.")
            if had_selection:
                notices.append(
                    f"{label}'s document section selection was removed."
                )
            _limit_reached_stage(state, 1)
            if "max_intake_step_reached" in state:
                state["max_intake_step_reached"] = 1
            _invalidate_plan_state(state)
            if "organized_list_confirmed" in state:
                state["organized_list_confirmed"] = False
    return tuple(notices)


def reset_intake_entry_after_type_change(
    state: MutableMapping[str, Any],
    index: int,
    entity_type: str | None,
) -> bool:
    """Clear incompatible entry values after Student/Classroom changes (FR-05)."""

    normalized_type = (
        entity_type if entity_type in {"Student", "Classroom"} else None
    )
    tracker_key = f"{INTAKE_ENTRY_TYPE_TRACKER_PREFIX}_{index}"
    previous_type = state.get(tracker_key)
    changed = (
        previous_type in {"Student", "Classroom"}
        and normalized_type in {"Student", "Classroom"}
        and previous_type != normalized_type
    )
    if changed:
        for prefix in INTAKE_ENTRY_VALUE_PREFIXES:
            _delete_navigation_value(state, f"{prefix}_{index}")
        _delete_navigation_value(
            state,
            f"document_sections_child-{index + 1}",
        )
        _delete_navigation_value(
            state,
            f"{INTAKE_ENTRY_GRADE_TRACKER_PREFIX}_{index}",
        )
    if normalized_type is None:
        _delete_navigation_value(state, tracker_key)
    else:
        state[tracker_key] = normalized_type
    return changed


def entry_type_change_discards_details(
    state: Mapping[str, Any],
    index: int,
) -> bool:
    """Return whether an FR-05 type change will discard entered details."""

    meaningful_prefixes = (
        "child_label",
        "student_name",
        "teacher_name",
        "child_grade",
        "student_grade",
        "classroom_grade",
        "budget",
        "list_upload",
        "list_upload_draft",
        "list_paste",
    )
    if any(
        bool(state.get(f"{prefix}_{index}"))
        for prefix in meaningful_prefixes
    ):
        return True
    student_count = state.get(f"student_count_{index}")
    count_was_edited = bool(
        state.get(
            INTAKE_WIDGET_TOUCHED_PREFIX + f"student_count_{index}",
            False,
        )
    )
    return (
        student_count not in (None, "")
        and (int(student_count) != 20 or count_was_edited)
    )


def clear_section_selection_after_grade_change(
    state: MutableMapping[str, Any],
    index: int,
    grade: str | None,
    label: str,
) -> tuple[str, ...]:
    """Clear only one FR-06 selection when its entry grade changes."""

    tracker_key = f"{INTAKE_ENTRY_GRADE_TRACKER_PREFIX}_{index}"
    normalized_grade = "" if grade is None else str(grade)
    previous_grade = state.get(tracker_key)
    state[tracker_key] = normalized_grade
    if previous_grade is None or str(previous_grade) == normalized_grade:
        return ()
    child_id = f"child-{index + 1}"
    selections = state.get("document_selections", {})
    had_selection = (
        isinstance(selections, Mapping)
        and child_id in selections
    )
    _delete_navigation_value(state, f"document_sections_{child_id}")
    if had_selection:
        updated = dict(selections)
        updated.pop(child_id, None)
        state["document_selections"] = updated
        state["extraction_cache_ready"] = False
        state["unmerged_extracted_lists"] = {}
        state["requirement_merge_result"] = None
        state["requirement_merge_resolved"] = False
        state["requirement_merge_choices"] = {}
        state["requirement_constraint_choices"] = {}
        state["requirement_variant_quantity_choices"] = {}
        state["requirement_merge_validation_errors"] = ()
        state["organized_list_confirmed"] = False
        _limit_reached_stage(state, 2)
        _invalidate_plan_state(state)
        return (
            f"{label}'s document section selection was removed because "
            "the grade changed.",
        )
    return ()


def _budget_text_from_cents(cents: int) -> str:
    """Format exact cents as an editable US-dollar budget value."""

    return format_money(cents).removeprefix("$")


def prepare_budget_mode_drafts(
    state: MutableMapping[str, Any],
    current_mode: str,
    entry_count: int,
) -> None:
    """Seed reversible FR-03 drafts when the parent changes budget mode."""

    tracker_key = "previous_budget_mode_label"
    previous_mode = state.get(tracker_key)
    state[tracker_key] = current_mode
    if previous_mode is None or str(previous_mode) == current_mode:
        return
    if (
        previous_mode == "One combined budget"
        and current_mode == "A budget for each student or classroom"
        and entry_count > 0
        and all(
            not str(state.get(f"budget_{index}", "")).strip()
            for index in range(entry_count)
        )
    ):
        try:
            total_cents = money_to_cents(
                str(state.get("combined_budget_text", ""))
            )
        except ValueError:
            total_cents = 0
        if total_cents:
            allocations = _allocate_cents(
                total_cents,
                {
                    str(index): 1
                    for index in range(entry_count)
                },
            )
            for index in range(entry_count):
                key = f"budget_{index}"
                value = _budget_text_from_cents(
                    allocations[str(index)]
                )
                state[key] = value
                state[NAVIGATION_STATE_PREFIX + key] = value
    elif (
        previous_mode == "A budget for each student or classroom"
        and current_mode == "One combined budget"
        and not str(state.get("combined_budget_text", "")).strip()
    ):
        try:
            allocation_cents = tuple(
                money_to_cents(str(state.get(f"budget_{index}", "")))
                for index in range(entry_count)
            )
        except ValueError:
            allocation_cents = ()
        if len(allocation_cents) == entry_count and allocation_cents:
            value = _budget_text_from_cents(sum(allocation_cents))
            state["combined_budget_text"] = value
            state[
                NAVIGATION_STATE_PREFIX + "combined_budget_text"
            ] = value
    _limit_reached_stage(state, 3)
    _invalidate_plan_state(state)


def commit_budget_mode_drafts(
    state: MutableMapping[str, Any],
    current_mode: str,
    entry_count: int,
) -> tuple[str, ...]:
    """Clear actual unused FR-03 drafts only after Continue."""

    notices: list[str] = []
    clear_combined = current_mode != "One combined budget"
    clear_allocations = (
        current_mode != "A budget for each student or classroom"
    )
    if clear_combined:
        combined_value = str(
            state.get(
                "combined_budget_text",
                state.get(
                    NAVIGATION_STATE_PREFIX + "combined_budget_text",
                    "",
                ),
            )
        ).strip()
        if combined_value:
            _delete_navigation_value(state, "combined_budget_text")
            notices.append("The unused combined budget draft was cleared.")
    if clear_allocations:
        cleared_allocation = False
        for index in range(entry_count):
            key = f"budget_{index}"
            value = str(
                state.get(
                    key,
                    state.get(NAVIGATION_STATE_PREFIX + key, ""),
                )
            ).strip()
            if value:
                cleared_allocation = True
            _delete_navigation_value(state, key)
        if cleared_allocation:
            notices.append(
                "The unused individual budget drafts were cleared."
            )
    return tuple(notices)


def update_pickup_radius_for_fulfillment(
    state: MutableMapping[str, Any],
    fulfillment_preference: str,
) -> bool:
    """Disable irrelevant FR-04 pickup distance and reset it on return."""

    if fulfillment_preference not in {"pickup", "delivery", "either"}:
        raise ValueError("Unsupported fulfillment preference")
    tracker_key = "pickup_radius_previous_fulfillment"
    previous_preference = state.get(tracker_key)
    if (
        previous_preference == "delivery"
        and fulfillment_preference != "delivery"
    ):
        state["store_radius_miles"] = DEFAULT_RADIUS_MILES
        state[
            NAVIGATION_STATE_PREFIX + "store_radius_miles"
        ] = DEFAULT_RADIUS_MILES
    state[tracker_key] = fulfillment_preference
    return fulfillment_preference == "delivery"


def intake_entry_display_number(
    state: Mapping[str, Any],
    index: int,
    entry_type: str,
) -> int:
    """Return a display-only Student or Classroom counter (FR-01/FR-05)."""

    if entry_type not in {"Student", "Classroom"}:
        raise ValueError(f"Unsupported intake entry type: {entry_type}")
    matching_prior_entries = sum(
        str(state.get(f"entity_type_{prior_index}") or "") in {
            entry_type,
            (
                "One student"
                if entry_type == "Student"
                else "A classroom group"
            ),
        }
        for prior_index in range(index)
    )
    return matching_prior_entries + 1


def budget_entry_fields(
    entries: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, str, str, str], ...]:
    """Return one FR-03 budget field specification for every intake entry."""

    return tuple(
        (
            index,
            str(entry["child_id"]),
            str(entry["label"]),
            f"budget_{index}",
        )
        for index, entry in enumerate(entries)
    )


def _render_intake_step_progress(st: Any, step: int) -> None:
    """Render clickable completed sections within FR-01-FR-04 intake."""

    labels = (
        "Students",
        "Budget",
        "Shopping preferences",
    )
    max_reached = max(
        step,
        int(st.session_state.get("max_intake_step_reached", 1)),
    )
    st.session_state["max_intake_step_reached"] = max_reached
    columns = st.columns(3)
    for section, (column, label) in enumerate(
        zip(columns, labels, strict=True),
        start=1,
    ):
        status = (
            "current"
            if section == step
            else "completed"
            if section <= max_reached
            else "unavailable"
        )
        marker = (
            "✓ "
            if status == "completed"
            else ""
        )
        clicked = column.button(
            f"{marker}{label}",
            key=f"intake_section_navigation_{section}",
            type="primary" if status == "current" else "secondary",
            disabled=status != "completed",
            use_container_width=True,
            help=(
                "Current section"
                if status == "current"
                else "Go to this completed section"
                if status == "completed"
                else "Complete the earlier sections first"
            ),
        )
        if clicked:
            navigate_intake_step(st.session_state, section)
            st.rerun()


def _navigation_button_columns(st: Any) -> tuple[Any, Any]:
    """Return equal-width columns for paired Back and Continue actions."""

    back_column, continue_column = st.columns(2)
    return back_column, continue_column


def _render_student_step(st: Any) -> None:
    """Render type-first FR-01/FR-05 intake with exit validation."""

    child_count_widget_key = mount_intake_widget_value(
        st.session_state,
        "child_count",
        1,
    )
    student_count = int(
        st.number_input(
            "How many students or classrooms are you shopping for?",
            min_value=1,
            max_value=MAX_CHILDREN_PER_SESSION,
            step=1,
            key=child_count_widget_key,
            on_change=commit_intake_widget_value,
            args=("child_count",),
            help=(
                f"A session can include up to {MAX_CHILDREN_PER_SESSION} "
                "students or classroom groups."
            ),
        )
    )
    for notice in clear_inactive_intake_entries(
        st.session_state,
        student_count,
    ):
        st.info(escape_streamlit_dollars(notice))
    validation_attempted = bool(
        st.session_state.get("student_validation_attempted", False)
    )
    validation_errors: list[str] = []
    for index in range(student_count):
        name_key = f"child_label_{index}"
        student_name_key = f"student_name_{index}"
        teacher_name_key = f"teacher_name_{index}"
        grade_key = f"child_grade_{index}"
        entity_key = f"entity_type_{index}"
        st.session_state.setdefault(name_key, "")
        st.session_state.setdefault(entity_key, None)
        stored_entity_type = str(st.session_state.get(entity_key) or "")
        st.session_state[entity_key] = (
            "Classroom"
            if stored_entity_type in {
                "Classroom",
                "A classroom group",
            }
            else (
                "Student"
                if stored_entity_type in {"Student", "One student"}
                else None
            )
        )
        existing_grade = st.session_state.get(grade_key)
        if existing_grade == "Classroom group":
            st.session_state[entity_key] = "Classroom"
            st.session_state[grade_key] = None
            existing_grade = None
        if existing_grade not in (None, *GRADE_OPTIONS):
            normalized = str(existing_grade).strip().casefold()
            if normalized in {"pk", "pre-k", "prekindergarten"}:
                st.session_state[grade_key] = "Pre-K"
            elif normalized in {"k", "kindergarten"}:
                st.session_state[grade_key] = "Kindergarten"
            elif normalized.isdigit() and 1 <= int(normalized) <= 12:
                st.session_state[grade_key] = f"Grade {int(normalized)}"
            else:
                st.session_state[grade_key] = None
        current_type = st.session_state.get(entity_key)
        previous_entry_name = str(
            st.session_state.get(f"child_label_{index}")
            or st.session_state.get(f"student_name_{index}")
            or st.session_state.get(f"teacher_name_{index}")
            or f"Student or classroom {index + 1}"
        ).strip()
        discarded_entry_details = entry_type_change_discards_details(
            st.session_state,
            index,
        )
        type_changed = reset_intake_entry_after_type_change(
            st.session_state,
            index,
            (
                str(current_type)
                if current_type in {"Student", "Classroom"}
                else None
            ),
        )
        st.session_state.setdefault(name_key, "")
        active_grade_key = (
            f"{str(current_type).casefold()}_grade_{index}"
            if current_type in {"Student", "Classroom"}
            else None
        )
        if (
            not type_changed
            and active_grade_key is not None
            and active_grade_key not in st.session_state
            and grade_key in st.session_state
        ):
            st.session_state[active_grade_key] = st.session_state[grade_key]
        if current_type == "Classroom":
            st.session_state.setdefault(
                teacher_name_key,
                str(st.session_state.get(name_key, "")),
            )
            current_name = str(
                st.session_state.get(teacher_name_key, "")
            ).strip()
        elif current_type == "Student":
            st.session_state.setdefault(
                student_name_key,
                str(st.session_state.get(name_key, "")),
            )
            current_name = str(
                st.session_state.get(student_name_key, "")
            ).strip()
        else:
            current_name = ""
        default_heading = (
            "Classroom "
            + str(
                intake_entry_display_number(
                    st.session_state,
                    index,
                    "Classroom",
                )
            )
            if current_type == "Classroom"
            else (
                "Student "
                + str(
                    intake_entry_display_number(
                        st.session_state,
                        index,
                        "Student",
                    )
                )
                if current_type == "Student"
                else f"Student or classroom {index + 1}"
            )
        )
        with st.container(border=True):
            st.markdown(
                "**"
                + escape_streamlit_dollars(
                    current_name or default_heading
                )
                + "**"
            )
            entity_widget_key = mount_intake_widget_value(
                st.session_state,
                entity_key,
                None,
            )
            entity_type = st.radio(
                "Who are you adding?",
                ("Student", "Classroom"),
                horizontal=True,
                index=None,
                key=entity_widget_key,
                on_change=commit_intake_widget_value,
                args=(entity_key,),
            )
            st.session_state[entity_key] = entity_type
            if entity_type is None:
                type_error = "Choose Student or Classroom."
                validation_errors.append(
                    f"{default_heading}: {type_error}"
                )
                if validation_attempted:
                    st.error(type_error)
                continue
            is_classroom = entity_type == "Classroom"
            field_columns = st.columns(
                [2, 1.2, 1.2] if is_classroom else [2, 1.2]
            )
            name_column, grade_column = field_columns[:2]
            name_label = (
                "Teacher name"
                if is_classroom
                else "Student name or nickname"
            )
            name_placeholder = (
                "Ms. Rivera"
                if is_classroom
                else "Maya"
            )
            active_name_key = (
                teacher_name_key
                if is_classroom
                else student_name_key
            )
            st.session_state.setdefault(active_name_key, "")
            active_name_widget_key = mount_intake_widget_value(
                st.session_state,
                active_name_key,
                "",
            )
            name = name_column.text_input(
                name_label,
                key=active_name_widget_key,
                on_change=commit_intake_widget_value,
                args=(active_name_key,),
                placeholder=name_placeholder,
            )
            st.session_state[active_name_key] = name
            st.session_state[name_key] = name
            if active_grade_key is None:
                raise RuntimeError("An entry type is required before grade")
            active_grade_widget_key = mount_intake_widget_value(
                st.session_state,
                active_grade_key,
                None,
            )
            grade = grade_column.selectbox(
                "Grade",
                GRADE_OPTIONS,
                index=None,
                key=active_grade_widget_key,
                on_change=commit_intake_widget_value,
                args=(active_grade_key,),
                placeholder="Select a grade",
            )
            st.session_state[active_grade_key] = grade
            st.session_state[grade_key] = grade
            grade_text = "" if grade is None else str(grade)
            for notice in clear_section_selection_after_grade_change(
                st.session_state,
                index,
                grade_text,
                name.strip() or previous_entry_name,
            ):
                st.info(escape_streamlit_dollars(notice))
            if type_changed and discarded_entry_details:
                st.info(
                    escape_streamlit_dollars(
                        f"{previous_entry_name}'s previous entry details "
                        "were cleared because the entry type changed."
                    )
                )
            if not name.strip():
                name_error = (
                    "Enter the teacher name."
                    if is_classroom
                    else "Enter a student name or nickname."
                )
                validation_errors.append(
                    f"{default_heading}: {name_error}"
                )
                if validation_attempted:
                    name_column.error(name_error)
            if not grade_text:
                grade_error = (
                    "Choose the classroom grade."
                    if is_classroom
                    else "Choose the student's grade."
                )
                validation_errors.append(
                    f"{default_heading}: {grade_error}"
                )
                if validation_attempted:
                    grade_column.error(grade_error)
            if is_classroom:
                count_key = f"student_count_{index}"
                st.session_state.setdefault(count_key, 20)
                count_widget_key = mount_intake_widget_value(
                    st.session_state,
                    count_key,
                    20,
                )
                field_columns[2].number_input(
                    "Students in this classroom",
                    min_value=1,
                    max_value=MAX_CLASSROOM_STUDENTS,
                    step=1,
                    key=count_widget_key,
                    on_change=commit_intake_widget_value,
                    args=(count_key,),
                    help=(
                        "Every quantity on the supply list will be multiplied "
                        "by this number."
                    ),
                )
    st.session_state["ui_error_active"] = (
        validation_attempted and bool(validation_errors)
    )
    _, continue_column = _navigation_button_columns(st)
    continue_clicked = continue_column.button(
        "Continue to budget",
        type="primary",
        use_container_width=True,
    )
    if not continue_clicked:
        return
    if validation_errors:
        st.session_state["student_validation_attempted"] = True
        st.session_state["ui_error_active"] = True
        st.rerun()
    else:
        st.session_state["student_validation_attempted"] = False
        st.session_state["ui_error_active"] = False
        navigate_intake_step(st.session_state, 2)
        st.rerun()


def _render_budget_step(st: Any) -> None:
    """Render FR-03 budget entry with E-37 validation on exit."""

    students = _intake_students_from_state(
        st.session_state,
        int(st.session_state["child_count"]),
    )
    st.caption(
        "Choose one total, one amount for each student or classroom, or no "
        "set budget."
    )
    budget_mode_widget_key = mount_intake_widget_value(
        st.session_state,
        "budget_mode_label",
        "One combined budget",
    )
    budget_mode_label = st.radio(
        "Budget setup",
        (
            "One combined budget",
            "A budget for each student or classroom",
            NO_SET_BUDGET_LABEL,
        ),
        horizontal=True,
        key=budget_mode_widget_key,
        on_change=commit_intake_widget_value,
        args=("budget_mode_label",),
    )
    st.session_state["budget_mode_label"] = budget_mode_label
    prepare_budget_mode_drafts(
        st.session_state,
        str(budget_mode_label),
        len(students),
    )
    validation_attempted = bool(
        st.session_state.get("budget_validation_attempted", False)
    )
    budget_errors: list[str] = []
    if budget_mode_label == "One combined budget":
        combined_budget_widget_key = mount_intake_widget_value(
            st.session_state,
            "combined_budget_text",
            DEFAULT_BUDGET_TEXT,
        )
        combined_budget = st.text_input(
            r"Combined budget (\$)",
            key=combined_budget_widget_key,
            on_change=commit_intake_widget_value,
            args=("combined_budget_text",),
            help=(
                "Enter the total you want to spend, for example 75 or 85.50."
            ),
        )
        st.session_state["combined_budget_text"] = combined_budget
        error = budget_entry_error(combined_budget)
        if error is not None:
            budget_errors.append(error)
            if validation_attempted:
                st.error(escape_streamlit_dollars(error))
    elif budget_mode_label == "A budget for each student or classroom":
        for _, _, label, budget_key in budget_entry_fields(students):
            st.session_state.setdefault(budget_key, "75.00")
            budget_widget_key = mount_intake_widget_value(
                st.session_state,
                budget_key,
                "75.00",
            )
            budget_text = st.text_input(
                escape_streamlit_dollars(
                    f"{label} budget (\\$)"
                ),
                key=budget_widget_key,
                on_change=commit_intake_widget_value,
                args=(budget_key,),
            )
            st.session_state[budget_key] = budget_text
            error = budget_entry_error(budget_text)
            if error is not None:
                message = f"{label}: {error}"
                budget_errors.append(message)
                if validation_attempted:
                    st.error(escape_streamlit_dollars(message))
    else:
        st.info(
            "The plan will still minimize landed cost. Budget comparisons "
            "and budget approval questions will be skipped."
        )
    st.session_state["ui_error_active"] = (
        validation_attempted and bool(budget_errors)
    )
    back, forward = _navigation_button_columns(st)
    if back.button("Back to students", use_container_width=True):
        navigate_intake_step(st.session_state, 1)
        st.session_state["budget_validation_attempted"] = False
        st.session_state["ui_error_active"] = False
        st.rerun()
    continue_clicked = forward.button(
        "Continue to shopping preferences",
        type="primary",
        use_container_width=True,
    )
    if not continue_clicked:
        return
    if budget_errors:
        st.session_state["budget_validation_attempted"] = True
        st.session_state["ui_error_active"] = True
        st.rerun()
    else:
        st.session_state["budget_validation_attempted"] = False
        notices = commit_budget_mode_drafts(
            st.session_state,
            str(budget_mode_label),
            len(students),
        )
        if notices:
            st.session_state["pending_intake_notices"] = notices
        navigate_intake_step(st.session_state, 3)
        st.session_state["ui_error_active"] = False
        st.rerun()


def _budget_from_intake_state(
    state: Mapping[str, Any],
    students: Sequence[Mapping[str, Any]],
) -> tuple[str, int | None, Mapping[str, int]]:
    """Convert already-validated FR-03 widget values at the UI boundary."""

    if state.get("budget_mode_label") == "One combined budget":
        return (
            "combined",
            money_to_cents(str(state.get("combined_budget_text", ""))),
            {},
        )
    if state.get("budget_mode_label") == NO_SET_BUDGET_LABEL:
        return "none", None, {}
    allocations = {
        child_id: money_to_cents(
            str(state.get(budget_key, ""))
        )
        for _, child_id, _, budget_key in budget_entry_fields(students)
    }
    return "per_child", sum(allocations.values()), allocations


def _render_preferences_step(st: Any) -> None:
    """Render guided FR-04 preferences and advanced BR-02 controls."""

    initialize_preference_defaults(st.session_state)
    students = _intake_students_from_state(
        st.session_state,
        int(st.session_state["child_count"]),
    )
    for notice in tuple(
        st.session_state.pop("pending_intake_notices", ())
    ):
        st.info(escape_streamlit_dollars(str(notice)))
    st.caption(
        "Choose how you want the plan to balance cost, stores, and "
        "convenience."
    )
    shopping_mode_widget_key = mount_intake_widget_value(
        st.session_state,
        "shopping_preference_label",
        next(iter(SHOPPING_MODES)),
    )
    mode_label = st.selectbox(
        "Shopping preferences",
        tuple(SHOPPING_MODES),
        key=shopping_mode_widget_key,
        on_change=commit_intake_widget_value,
        args=("shopping_preference_label",),
        help=(
            "Lowest landed cost finds the cheapest full amount, including "
            "tax and pickup or delivery fees, and may use multiple stores. "
            "A second store must save more than a few dollars to justify the "
            "extra trip. Single store keeps everything at one store; if no "
            "store carries everything, you will see the best option and what "
            "is missing. Custom lets you choose stores, a maximum number of "
            "stores, and a pickup distance. Landed cost always means the full "
            "amount including tax and fees, never just the item subtotal."
        ),
    )
    st.session_state["shopping_preference_label"] = mode_label
    shopping_mode = SHOPPING_MODES[mode_label]
    validation_attempted = bool(
        st.session_state.get("preferences_validation_attempted", False)
    )
    stores = tuple(load_stores())
    allowed_stores: frozenset[str] | None = None
    max_stores: int | None = None
    preference_errors: list[str] = []
    if shopping_mode == "custom":
        store_options = tuple(store.name for store in stores)
        selected_stores_widget_key = mount_intake_widget_value(
            st.session_state,
            "selected_store_names",
            store_options,
        )
        selected_names = st.multiselect(
            "Stores to consider",
            store_options,
            key=selected_stores_widget_key,
            on_change=commit_intake_widget_value,
            args=("selected_store_names",),
            help="Choose which fictional stores may appear in the plan.",
        )
        st.session_state["selected_store_names"] = selected_names
        if not selected_names:
            message = "Choose at least one store to build a custom plan."
            preference_errors.append(message)
            if validation_attempted:
                st.error(message)
        store_ids_by_name = {
            store.name: store.store_id for store in stores
        }
        allowed_stores = frozenset(
            store_ids_by_name[name] for name in selected_names
        )
        max_stores = int(
            st.number_input(
                "Maximum number of stores",
                min_value=1,
                max_value=len(stores),
                step=1,
                key=mount_intake_widget_value(
                    st.session_state,
                    "maximum_stores",
                    2,
                ),
                on_change=commit_intake_widget_value,
                args=("maximum_stores",),
                help="The plan will not use more than this many stores.",
            )
        )
        st.session_state["maximum_stores"] = max_stores

    with st.expander("Advanced shopping and tax options"):
        st.caption(
            "Adjust distance, pickup or delivery, and tax."
        )
        fulfillment_widget_key = mount_intake_widget_value(
            st.session_state,
            "fulfillment_label",
            next(iter(FULFILLMENT_OPTIONS)),
        )
        fulfillment_label = st.selectbox(
            "Pickup or delivery preference",
            tuple(FULFILLMENT_OPTIONS),
            key=fulfillment_widget_key,
            on_change=commit_intake_widget_value,
            args=("fulfillment_label",),
            help=(
                "Best available compares pickup and delivery. Pickup only "
                "requires a trip within the selected radius. Delivery only "
                "does not use the pickup radius."
            ),
        )
        st.session_state["fulfillment_label"] = fulfillment_label
        fulfillment_preference = FULFILLMENT_OPTIONS[fulfillment_label]
        radius_disabled = update_pickup_radius_for_fulfillment(
            st.session_state,
            fulfillment_preference,
        )
        radius = float(
            st.number_input(
                "Pickup-trip radius (simulated miles)",
                min_value=0.0,
                max_value=MAX_STORE_RADIUS_MILES,
                step=0.5,
                key=mount_intake_widget_value(
                    st.session_state,
                    "store_radius_miles",
                    DEFAULT_RADIUS_MILES,
                ),
                on_change=commit_intake_widget_value,
                args=("store_radius_miles",),
                help=(
                    "Limits pickup trips only. Delivery stores are always "
                    "available."
                ),
                disabled=radius_disabled,
            )
        )
        st.session_state["store_radius_miles"] = radius
        if radius_disabled:
            st.caption("Not needed for delivery.")
        st.caption(
            "These are simulated distances from a notional home location, "
            "not distances calculated from an address."
        )
        st.dataframe(
            escape_streamlit_data(
                store_radius_rows(
                    stores,
                    radius,
                    fulfillment_preference,
                )
            ),
            use_container_width=True,
            hide_index=True,
        )

        state_widget_key = mount_intake_widget_value(
            st.session_state,
            "sales_tax_state",
            DEFAULT_TAX_STATE_OPTION,
        )
        state_name = st.selectbox(
            "State used for the tax estimate",
            tuple(STATE_GENERAL_SALES_TAX_PERCENT),
            key=state_widget_key,
            on_change=commit_intake_widget_value,
            args=("sales_tax_state",),
            help=(
                "Prefills a general state sales-tax rate. City and county "
                "rates are not estimated."
            ),
        )
        st.session_state["sales_tax_state"] = state_name
        initialize_state_tax_prefill(st.session_state, state_name)
        tax_widget_key = mount_intake_widget_value(
            st.session_state,
            "tax_rate_text",
            STATE_GENERAL_SALES_TAX_PERCENT[DEFAULT_TAX_STATE_OPTION],
        )
        tax_rate_text = st.text_input(
            "Sales tax rate override (%)",
            key=tax_widget_key,
            on_change=commit_intake_widget_value,
            args=("tax_rate_text",),
            help=(
                "Optional. Keep the prefilled state rate, or enter a "
                "different percentage if you know the rate you want used."
            ),
        )
        st.session_state["tax_rate_text"] = tax_rate_text
        try:
            tax_percent_to_basis_points(tax_rate_text)
        except ValueError as error:
            preference_errors.append(str(error))
            if validation_attempted:
                st.error(escape_streamlit_dollars(str(error)))
        st.caption(
            "State-level defaults are dated January 1, 2026. City and county "
            "rates, state-specific school-supply exemptions, and "
            "back-to-school tax holidays are not modeled."
        )

    student_errors = tuple(
        error
        for student in students
        for error in student_input_errors(
            str(student["label"]),
            str(student["grade"]),
        )
    )
    try:
        budget_mode, budget_total, budget_allocations = (
            _budget_from_intake_state(st.session_state, students)
        )
    except ValueError as error:
        preference_errors.append(str(error))
        budget_mode, budget_total, budget_allocations = "combined", 0, {}
    preference_errors.extend(student_errors)
    st.session_state["ui_error_active"] = (
        validation_attempted and bool(preference_errors)
    )
    back, forward = _navigation_button_columns(st)
    if back.button("Back to budget", use_container_width=True):
        navigate_intake_step(st.session_state, 2)
        st.session_state["preferences_validation_attempted"] = False
        st.session_state["ui_error_active"] = False
        st.rerun()
    continue_clicked = forward.button(
        "Continue to the lists",
        type="primary",
        use_container_width=True,
    )
    if not continue_clicked:
        return
    if preference_errors:
        st.session_state["preferences_validation_attempted"] = True
        st.session_state["ui_error_active"] = True
        st.rerun()
        return

    tax_basis_points = tax_percent_to_basis_points(
        str(st.session_state["tax_rate_text"])
    )
    st.session_state["intake"] = {
        "session_id": str(uuid4()),
        "children": tuple(students),
        "budget_total": budget_total,
        "budget_mode": budget_mode,
        "budget_allocations": budget_allocations,
        "shopping_mode": shopping_mode,
        "store_radius_miles": radius,
        "allowed_stores": allowed_stores,
        "max_stores": max_stores,
        "fulfillment_pref": fulfillment_preference,
        "tax_basis_points": tax_basis_points,
        "demo_mode": bool(st.session_state["demo_mode"]),
    }
    st.session_state["result"] = None
    st.session_state["list_identity_confirmed"] = False
    st.session_state["approval_outcomes"] = {}
    st.session_state["resolved_interrupts"] = {}
    st.session_state["parent_decisions"] = ()
    st.session_state["checkout_confirmation"] = None
    st.session_state["preferences_validation_attempted"] = False
    st.session_state["ui_error_active"] = False
    _limit_reached_stage(st.session_state, 3)
    st.session_state["progress_substep"] = "adding the lists"
    st.session_state["screen"] = "lists"
    st.rerun()


def _render_intake(st: Any) -> None:
    debug_enabled = development_diagnostics_enabled(st)
    if debug_enabled:
        _render_development_diagnostic(st)
    else:
        st.session_state["demo_mode"] = False
    step = min(3, max(1, int(st.session_state.get("intake_step", 1))))
    previous_step = st.session_state.get("last_rendered_intake_step")
    if previous_step is None or int(previous_step) != step:
        restore_intake_section_values(
            st.session_state,
            step,
            int(st.session_state.get("child_count", 1)),
        )
    st.session_state["last_rendered_intake_step"] = step
    _render_intake_step_progress(st, step)
    with st.container(border=True):
        if step == 1:
            _render_student_step(st)
        elif step == 2:
            _render_budget_step(st)
        else:
            _render_preferences_step(st)


def _build_list_inputs(
    st: Any,
    children: Sequence[Mapping[str, Any]],
) -> tuple[ListInput, ...]:
    if bool(st.session_state.get("shared_list_for_all")):
        mode = st.session_state.get(
            "shared_list_mode",
            "Upload a file",
        )
        if mode == "Upload a file":
            draft = _remember_upload_draft(
                st.session_state,
                "shared_list_upload_draft",
                st.session_state.get("shared_list_upload"),
            )
            if draft is None:
                raise ValueError("Choose the shared district file.")
            data = draft.data
            mime_type = validate_uploaded_document(draft.name, data)
            return tuple(
                ListInput(
                    child_id=str(child["child_id"]),
                    source=data,
                    mime_type=mime_type,
                    document_name=draft.name,
                )
                for child in children
            )
        pasted = str(
            st.session_state.get("shared_list_paste", "")
        ).strip()
        if not pasted:
            raise ValueError("Paste the shared district list.")
        if len(pasted.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise ValueError(
                "The shared pasted list exceeds the size limit."
            )
        return tuple(
            ListInput(
                child_id=str(child["child_id"]),
                source=pasted,
                mime_type="text/plain",
                document_name="Pasted district list",
            )
            for child in children
        )

    inputs: list[ListInput] = []
    errors: list[str] = []
    for index, child in enumerate(children):
        mode = st.session_state.get(f"list_mode_{index}", "Paste text")
        if mode == "Upload a file":
            draft = _remember_upload_draft(
                st.session_state,
                f"list_upload_draft_{index}",
                st.session_state.get(f"list_upload_{index}"),
            )
            if draft is None:
                errors.append(f"{child['label']}: choose a file.")
                continue
            data = draft.data
            try:
                mime_type = validate_uploaded_document(draft.name, data)
            except ValueError as error:
                errors.append(f"{child['label']}: {error}")
                continue
            inputs.append(
                ListInput(
                    child_id=str(child["child_id"]),
                    source=data,
                    mime_type=mime_type,
                    document_name=draft.name,
                )
            )
        else:
            pasted = str(
                st.session_state.get(f"list_paste_{index}", "")
            ).strip()
            if not pasted:
                errors.append(f"{child['label']}: paste the supply list.")
                continue
            if len(pasted.encode("utf-8")) > MAX_UPLOAD_BYTES:
                errors.append(
                    f"{child['label']}: pasted text exceeds the size limit."
                )
                continue
            inputs.append(
                ListInput(
                    child_id=str(child["child_id"]),
                    source=pasted,
                    mime_type="text/plain",
                    document_name=f"{child['label']}'s pasted list",
                )
            )
    if errors:
        raise ValueError("\n".join(errors))
    return tuple(inputs)


def _saved_list_page_count(list_input: ListInput) -> int:
    """Return the visible page count for one retained session-only list."""

    if list_input.mime_type != "application/pdf":
        return NONPAGINATED_SOURCE_PAGE
    data = _list_input_bytes(list_input)
    if data is None:
        return NONPAGINATED_SOURCE_PAGE
    document = pdfium.PdfDocument(data)
    try:
        return len(document)
    finally:
        document.close()


def _render_lists(st: Any) -> None:
    intake = st.session_state["intake"]
    if intake is None:
        st.session_state["screen"] = "intake"
        st.rerun()
    children = intake["children"]
    st.header("Add the lists")
    st.write(
        "Paste or upload the list for each student. If one district document "
        "contains several grades, upload it once and choose a section for "
        "each student. Every file is checked before items are extracted."
    )
    saved_inputs = tuple(st.session_state["list_inputs"])
    expected_child_ids = tuple(
        child["child_id"] for child in children
    )
    if (
        saved_inputs
        and tuple(item.child_id for item in saved_inputs)
        == expected_child_ids
    ):
        st.success("Your previously supplied lists are still available.")
        labels_by_child = {
            str(child["child_id"]): str(child["label"])
            for child in children
        }
        st.table(
            escape_streamlit_data(
                tuple(
                    {
                        "Saved list": item.resolved_document_name,
                        "Pages": _saved_list_page_count(item),
                        "For": labels_by_child.get(
                            item.child_id,
                            item.child_id,
                        ),
                    }
                    for item in saved_inputs
                )
            )
        )
        if st.button("Rebuild using the saved lists"):
            st.session_state["result"] = None
            st.session_state["list_identity_confirmed"] = False
            st.session_state["document_structures"] = {}
            st.session_state["document_selections"] = {}
            st.session_state["source_reference_cache"] = {}
            st.session_state["structure_errors"] = {}
            st.session_state["structure_cache_ready"] = False
            st.session_state["review_items"] = ()
            st.session_state["organized_list_confirmed"] = False
            _limit_reached_stage(st.session_state, 2)
            st.session_state["progress_substep"] = "extracting the lists"
            st.session_state["screen"] = "working"
            st.rerun()
    shared_list_for_all = False
    if len(children) > 1:
        shared_list_for_all = st.checkbox(
            "One district document contains sections for all entries",
            value=bool(
                st.session_state.get("shared_list_for_all", False)
            ),
            key="shared_list_for_all",
        )
    source_entries: Sequence[tuple[int, Mapping[str, Any]]]
    if shared_list_for_all:
        source_entries = (
            (
                -1,
                {
                    "label": "Shared district document",
                    "grade": "multiple grades",
                },
            ),
        )
    else:
        source_entries = tuple(enumerate(children))

    for index, child in source_entries:
        shared_source = index == -1
        mode_key = (
            "shared_list_mode"
            if shared_source
            else f"list_mode_{index}"
        )
        upload_key = (
            "shared_list_upload"
            if shared_source
            else f"list_upload_{index}"
        )
        upload_draft_key = (
            "shared_list_upload_draft"
            if shared_source
            else f"list_upload_draft_{index}"
        )
        paste_key = (
            "shared_list_paste"
            if shared_source
            else f"list_paste_{index}"
        )
        with st.container(border=True):
            st.subheader(
                escape_streamlit_dollars(
                    (
                        "Shared district document"
                        if shared_source
                        else (
                            f"{child['label']} · "
                            f"{_grade_display_title(str(child['grade']))}"
                        )
                    )
                )
            )
            if shared_source:
                st.caption(
                    "Upload it once. You will choose a separate grade or "
                    "teacher section for each student next."
                )
            st.radio(
                "List source",
                ("Paste text", "Upload a file"),
                horizontal=True,
                key=mode_key,
            )
            if st.session_state[mode_key] == "Upload a file":
                upload = st.file_uploader(
                    (
                        "District supply-list document"
                        if shared_source
                        else "Supply list"
                    ),
                    type=("docx", "pdf", "jpg", "jpeg", "png", "txt"),
                    key=upload_key,
                )
                upload_draft = _remember_upload_draft(
                    st.session_state,
                    upload_draft_key,
                    upload,
                )
                if upload is None and upload_draft is not None:
                    st.caption(
                        escape_streamlit_dollars(
                            f"Saved file: {upload_draft.name}. Upload another "
                            "file to replace it."
                        )
                    )
                st.caption(
                    f"Maximum size: {MAX_UPLOAD_BYTES // 1_000_000} MB."
                )
            else:
                st.text_area(
                    (
                        "Paste the complete district list"
                        if shared_source
                        else "Paste the complete list"
                    ),
                    value=(
                        DEMO_LIST_TEXT
                        if bool(intake.get("demo_mode"))
                        else ""
                    ),
                    height=220,
                    key=paste_key,
                    placeholder="Paste required items and optional sections…",
                )
    left, right = _navigation_button_columns(st)
    if left.button("Back", use_container_width=True):
        st.session_state["progress_substep"] = "setup"
        navigate_back_to_screen(st.session_state, "intake")
        st.rerun()
    if right.button(
        "Organize my list",
        type="primary",
        use_container_width=True,
    ):
        try:
            list_inputs = _build_list_inputs(st, children)
        except ValueError as error:
            st.session_state["ui_error_active"] = True
            for message in str(error).splitlines():
                st.error(escape_streamlit_dollars(message))
            return
        st.session_state["list_inputs"] = list_inputs
        st.session_state["document_structures"] = {}
        st.session_state["document_selections"] = {}
        st.session_state["source_reference_cache"] = {}
        st.session_state["structure_errors"] = {}
        st.session_state["structure_cache_ready"] = False
        st.session_state["extracted_lists"] = {}
        st.session_state["unmerged_extracted_lists"] = {}
        st.session_state["extraction_errors"] = {}
        st.session_state["extraction_cache_ready"] = False
        st.session_state["requirement_merge_result"] = None
        st.session_state["requirement_merge_resolved"] = False
        st.session_state["requirement_merge_choices"] = {}
        st.session_state["requirement_constraint_choices"] = {}
        st.session_state["requirement_variant_quantity_choices"] = {}
        st.session_state["requirement_merge_validation_errors"] = ()
        st.session_state["review_items"] = ()
        st.session_state["organized_list_confirmed"] = False
        _limit_reached_stage(st.session_state, 2)
        st.session_state["allow_unresolved_items"] = False
        st.session_state["list_identity_confirmed"] = False
        st.session_state["result"] = None
        st.session_state["ui_error_active"] = False
        st.session_state["progress_substep"] = "extracting the lists"
        st.session_state["screen"] = "working"
        st.rerun()


def _pipeline_session(intake: Mapping[str, Any]) -> PipelineSession:
    children = intake["children"]
    raw_budget_total = intake["budget_total"]
    return PipelineSession(
        session_id=str(intake["session_id"]),
        children=tuple(child["child_id"] for child in children),
        budget_total=(
            None
            if raw_budget_total is None
            else int(raw_budget_total)
        ),
        budget_mode=str(intake["budget_mode"]),  # type: ignore[arg-type]
        shopping_mode=str(intake["shopping_mode"]),  # type: ignore[arg-type]
        store_radius_miles=float(intake["store_radius_miles"]),
        allowed_stores=intake["allowed_stores"],
        fulfillment_pref=str(  # type: ignore[arg-type]
            intake["fulfillment_pref"]
        ),
        tax_basis_points=int(intake["tax_basis_points"]),
        max_stores=intake["max_stores"],
        student_counts={
            child["child_id"]: int(child["student_count"])
            for child in children
        },
        budget_allocations=intake["budget_allocations"],
    )


def _demo_document_structure(
    child: Mapping[str, Any],
) -> DocumentStructureEnvelope:
    """Return one deterministic section for the offline demonstration."""

    grade = str(child.get("grade") or "").strip()
    label = (
        f"{grade} supply list"
        if grade
        else f"{child.get('label', 'Selected student')} supply list"
    )
    return DocumentStructureEnvelope(
        document_title="Offline demonstration list",
        layouts=("single_section",),
        languages=("English",),
        primary_language="English",
        sections=(
            DocumentSection(
                section_id="demo-section",
                label=label,
                grades=((grade,) if grade else ()),
                named_sections=("Required supplies",),
                page_numbers=(1,),
                language="English",
                source_line=label,
            ),
        ),
    )


def _inspect_list_inputs(
    list_inputs: Sequence[ListInput],
    children: Sequence[Mapping[str, Any]],
    *,
    demo_mode: bool = False,
    inspector: Callable[..., DocumentStructureEnvelope] = (
        inspect_document_structure
    ),
    progress_callback: (
        Callable[[str, int, int, str], None] | None
    ) = None,
) -> tuple[
    dict[str, DocumentStructureEnvelope],
    dict[str, Exception],
]:
    """Inspect grades and named sections before item extraction (FR-06)."""

    child_by_id = {
        str(child["child_id"]): child for child in children
    }
    structures: dict[str, DocumentStructureEnvelope] = {}
    errors: dict[str, Exception] = {}

    def inspect_one(list_input: ListInput) -> DocumentStructureEnvelope:
        if demo_mode:
            return _demo_document_structure(
                child_by_id[list_input.child_id]
            )
        return inspector(
            list_input.source,
            mime_type=list_input.mime_type,
        )

    grouped_inputs: list[tuple[ListInput, ...]]
    if demo_mode:
        grouped_inputs = [(list_input,) for list_input in list_inputs]
    else:
        by_source: dict[
            tuple[str | None, object],
            list[ListInput],
        ] = {}
        for list_input in list_inputs:
            by_source.setdefault(
                (list_input.mime_type, list_input.source),
                [],
            ).append(list_input)
        grouped_inputs = [
            tuple(group) for group in by_source.values()
        ]

    with ThreadPoolExecutor(
        max_workers=min(max(len(grouped_inputs), 1), MODEL_MAX_CONCURRENCY)
    ) as executor:
        futures = {
            executor.submit(inspect_one, group[0]): group
            for group in grouped_inputs
        }
        done_count = 0
        completed: dict[str, DocumentStructureEnvelope] = {}
        for future in as_completed(futures):
            group = futures[future]
            done_count += len(group)
            if progress_callback is not None:
                progress_callback(
                    "structure",
                    done_count,
                    len(list_inputs),
                    (
                        f"Found sections in {done_count} of "
                        f"{len(list_inputs)} lists"
                    ),
                )
            try:
                structure = future.result()
                for list_input in group:
                    completed[list_input.child_id] = structure
            except Exception as error:
                for list_input in group:
                    errors[list_input.child_id] = error
        for list_input in list_inputs:
            structure = completed.get(list_input.child_id)
            if structure is not None:
                structures[list_input.child_id] = structure
    return structures, errors


def document_section_rows(
    structure: DocumentStructureEnvelope,
) -> tuple[dict[str, str], ...]:
    """Return only document-section columns that help a parent choose."""

    sections = selectable_document_sections(structure)
    labels_by_id = {
        section.section_id: section.label for section in sections
    }
    grade_values = tuple(_join_names(section.grades) for section in sections)
    teacher_values = tuple(
        _join_names(section.teachers) for section in sections
    )
    named_part_values = tuple(
        _join_names(section.named_sections) for section in sections
    )
    page_values = tuple(
        ", ".join(str(page) for page in section.page_numbers)
        for section in sections
    )
    document_languages = {
        language.casefold()
        for language in structure.languages
        if language.strip()
    } | {
        section.language.casefold()
        for section in sections
        if section.language is not None and section.language.strip()
    }
    show_grades = any(
        grade
        and re.sub(r"[^a-z0-9]+", "", grade.casefold())
        != re.sub(r"[^a-z0-9]+", "", section.label.casefold())
        for section, grade in zip(sections, grade_values, strict=True)
    )
    show_teachers = (
        any(teacher_values) and len(set(teacher_values)) > 1
    )
    show_named_parts = (
        any(named_part_values) and len(set(named_part_values)) > 1
    )
    show_pages = (
        any(page_values)
        and len(set(page_values)) > 1
    )
    show_language = len(document_languages) > 1

    rows: list[dict[str, str]] = []
    for index, section in enumerate(sections):
        row = {"Section": section.label}
        if show_grades:
            row["Grade"] = grade_values[index]
        if show_teachers:
            row["Teacher"] = teacher_values[index]
        if show_named_parts:
            row["Includes"] = named_part_values[index]
        if show_pages:
            row["Page"] = page_values[index]
        if show_language:
            language = section.language or ""
            if section.duplicate_of_section_id is not None:
                original_label = labels_by_id.get(
                    section.duplicate_of_section_id,
                    "the original section",
                )
                language = (
                    f"{language} — translated copy of {original_label}"
                    if language
                    else f"Translated copy of {original_label}"
                )
            row["Language"] = language
        rows.append(row)
    return tuple(rows)


def document_sections_need_table(
    rows: Sequence[Mapping[str, str]],
) -> bool:
    """Use a table only when it conveys more than the section choices."""

    return any(set(row) != {"Section"} for row in rows)


def _grade_identifier(value: str) -> str:
    """Normalize entered and detected grade labels for picker preselection."""

    return grade_token_identifier(value)


def section_picker_default_ids(
    structure: DocumentStructureEnvelope,
    entered_grade: str,
) -> tuple[str, ...]:
    """Suggest matching grade sections without deciding for the parent."""

    return tuple(
        section.section_id
        for section in resolve_document_sections(
            structure,
            entered_grade,
        ).auto_selected
    )


def initialize_section_picker_state(
    state: MutableMapping[str, Any],
    key: str,
    section_ids: Sequence[str],
) -> bool:
    """Seed Streamlit's keyed widget once so its grade default is honored."""

    if key in state:
        return False
    state[key] = list(section_ids)
    return bool(section_ids)


def _extract_list_inputs(
    list_inputs: Sequence[ListInput],
    *,
    extractor: Callable[..., ExtractionEnvelope] = extract_document,
    selections: Mapping[str, DocumentSelection] | None = None,
    progress_callback: (
        Callable[[str, int, int, str], None] | None
    ) = None,
) -> tuple[
    dict[str, ExtractionEnvelope],
    dict[str, Exception],
]:
    """Extract each list once so identity checks precede cart construction."""

    extractions: dict[str, ExtractionEnvelope] = {}
    errors: dict[str, Exception] = {}
    completed: dict[str, ExtractionEnvelope] = {}
    active_selections = selections or {}

    def extract_one(list_input: ListInput) -> ExtractionEnvelope:
        options: dict[str, Any] = {
            "child_id": list_input.child_id,
            "mime_type": list_input.mime_type,
        }
        selection = active_selections.get(list_input.child_id)
        if selection is not None:
            options["section_selection"] = selection
        return validate_extraction_envelope(
            extractor(
                list_input.source,
                **options,
            )
        )

    with ThreadPoolExecutor(
        max_workers=min(max(len(list_inputs), 1), MODEL_MAX_CONCURRENCY)
    ) as executor:
        futures = {
            executor.submit(extract_one, list_input): list_input
            for list_input in list_inputs
        }
        done_count = 0
        for future in as_completed(futures):
            list_input = futures[future]
            done_count += 1
            if progress_callback is not None:
                progress_callback(
                    "extraction",
                    done_count,
                    len(list_inputs),
                    f"Extracted {done_count} of {len(list_inputs)} lists",
                )
            try:
                extraction = future.result()
                completed[list_input.child_id] = extraction.model_copy(
                    update={
                        "requirements": tuple(
                            stamped.model_copy(
                                update={
                                    "sources": (
                                        requirement_source(stamped),
                                    )
                                }
                            )
                            for requirement in extraction.requirements
                            for stamped in (
                                requirement.model_copy(
                                    update={
                                        "source_document": (
                                            list_input.resolved_document_name
                                        )
                                    }
                                ),
                            )
                        )
                    }
                )
            except Exception as error:
                errors[list_input.child_id] = error
    for list_input in list_inputs:
        extraction = completed.get(list_input.child_id)
        if extraction is not None:
            extractions[list_input.child_id] = extraction
    return extractions, errors


def _run_pipeline_from_cached_extractions(
    session: PipelineSession,
    list_inputs: Sequence[ListInput],
    extractions: Mapping[str, ExtractionEnvelope],
    extraction_errors: Mapping[str, Exception],
    offers: Sequence[Offer],
    suitability_judge: SuitabilityJudge | None = None,
    progress_callback: (
        Callable[[str, int, int, str], None] | None
    ) = None,
) -> PipelineResult:
    """Run later pipeline stages without making a second extraction call."""

    del list_inputs
    return run_pipeline_from_confirmed_extractions(
        session,
        extractions,
        extraction_errors=extraction_errors,
        offers=offers,
        suitability_judge=suitability_judge,
        progress_callback=progress_callback,
    )


def _store_replan_transition(
    st: Any,
    transition: ReplanTransition,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
    notice: str,
) -> None:
    """Store one FR-32 transition while retaining only valid parent choices."""

    result = transition.result
    presentations = build_approval_presentations(
        result,
        offers,
        stores,
        child_labels,
    )
    options_by_interrupt = {
        presentation.interrupt.interrupt_id: {
            option.alternative_id
            for option in _all_presentation_options(presentation)
        }
        for presentation in presentations
    }
    preserved_outcomes = {
        interrupt_id: outcome
        for interrupt_id, outcome in (
            transition.preserved_approval_outcomes.items()
        )
        if outcome in options_by_interrupt.get(interrupt_id, set())
    }
    st.session_state["result"] = result
    st.session_state["approval_generation"] = (
        int(st.session_state["approval_generation"]) + 1
    )
    st.session_state["approval_presentations_cache"] = presentations
    st.session_state["approval_outcomes"] = preserved_outcomes
    st.session_state["replan_preserved_approval_ids"] = frozenset(
        preserved_outcomes
    )
    st.session_state["budget_action_ids"] = (
        transition.preserved_budget_action_ids
    )
    st.session_state["replan_preserved_budget_action_ids"] = frozenset(
        transition.preserved_budget_action_ids
    )
    st.session_state["approved_optimization"] = None
    st.session_state["resolved_interrupts"] = {}
    st.session_state["addon_selection_token"] = None
    st.session_state["addon_evaluation"] = None
    st.session_state["checkout_confirmation"] = None
    st.session_state["catalog_change_notice"] = notice
    st.session_state["progress_substep"] = (
        "re-planning after a catalog change"
    )
    st.session_state["screen"] = "working"


def _apply_stockout_replan(
    st: Any,
    result: PipelineResult,
    stockout_sku: str,
    offers: Sequence[Offer],
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
) -> None:
    """Apply the FR-33 stockout overlay and store its FR-32 transition."""

    new_stockouts = (
        frozenset(st.session_state["stockout_skus"])
        | {stockout_sku}
    )
    st.session_state["stockout_skus"] = new_stockouts
    changed_offers = _active_catalog_offers(
        new_stockouts,
        st.session_state["price_overrides"],
    )
    transition = replan_after_catalog_change(
        result,
        changed_offers,
        stores,
        change_kind="stockout",
        changed_sku=stockout_sku,
        approval_outcomes=st.session_state["approval_outcomes"],
        budget_action_ids=st.session_state["budget_action_ids"],
    )
    _store_replan_transition(
        st,
        transition,
        changed_offers,
        stores,
        child_labels,
        (
            f"{_catalog_product_label(stockout_sku, offers, stores)} "
            "was marked out of stock. The cart was rebuilt and "
            f"{len(transition.preserved_approval_outcomes)} prior "
            "decision(s) remained valid."
        ),
    )


def _render_list_identity_warnings(
    st: Any,
    warnings: Sequence[ListIdentityWarning],
) -> None:
    """Show extracted grade conflicts as one non-blocking confirmation."""

    st.header("Check the list details")
    st.write(
        "The list can still be used. Confirm that you want to continue before "
        "the cart is built."
    )
    for warning in warnings:
        with st.container(border=True):
            st.warning(
                escape_streamlit_dollars(
                    f"{warning.child_label}: {warning.message}"
                )
            )
            if warning.stated_teachers:
                st.caption(
                    escape_streamlit_dollars(
                        "Teacher named on the list: "
                        + _join_names(warning.stated_teachers)
                    )
                )
    with st.form("list_identity_confirmation"):
        left, right = _navigation_button_columns(st)
        continue_anyway = left.form_submit_button(
            "Continue anyway",
            type="primary",
            use_container_width=True,
        )
        return_to_lists = right.form_submit_button(
            "Return to lists",
            use_container_width=True,
        )
    if continue_anyway:
        st.session_state["list_identity_confirmed"] = True
        st.session_state["progress_substep"] = "building the cart"
        st.rerun()
    if return_to_lists:
        st.session_state["progress_substep"] = "adding the lists"
        navigate_back_to_screen(st.session_state, "lists")
        st.rerun()


def _review_editor_rows(
    items: Sequence[SupplyItemReview],
    child_labels: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Convert review models to editable, parent-facing table rows."""

    return [
        {
            "review_id": item.review_id,
            "req_id": item.req_id,
            "child_id": item.child_id,
            "For": child_labels.get(item.child_id, item.child_id),
            "Item": item.item_name,
            "Quantity": item.required_quantity,
            "Unit": item.unit,
            "Package size": item.package_size,
            "Brand": item.brand or "",
            "Exact brand": item.brand_required,
            "Size": item.size or "",
            "Color": ", ".join(item.color),
            "Required details": (
                item.required_attributes.get("other_details") or ""
            ),
            "Optional": item.optional,
            "Supply use": item.supply_scope.title(),
            "Provided by school": item.provided_by_school,
            "Condition": item.condition or "",
            "Condition applies": (
                "Choose above"
                if item.condition is not None
                and item.condition_applies is None
                else (
                    "Yes"
                    if item.condition_applies is True
                    else (
                        "No"
                        if item.condition_applies is False
                        else "Not conditional"
                    )
                )
            ),
            "Already owned": item.already_owned,
            "Allow equivalents": item.allow_equivalents,
            "Notes": item.notes or "",
            "Source text": item.source_text,
            "Source document": item.source_document or "",
            "Source section": item.source_section or "",
            "Source page": item.source_page,
            "Source language": item.source_language or "",
            "Confidence": round(item.confidence, 2),
            "Needs attention": ", ".join(item.issue_codes),
            "Confirmed": item.review_status == "confirmed",
            "Delete": item.review_status == "deleted",
        }
        for item in items
    ]


def _editor_records(value: Any) -> list[Mapping[str, Any]]:
    """Return records from Streamlit's list or DataFrame editor result."""

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return list(to_dict("records"))
    return list(value)


def _review_items_from_editor(
    value: Any,
    prior_items: Sequence[SupplyItemReview],
    children: Sequence[Mapping[str, Any]],
) -> tuple[SupplyItemReview, ...]:
    """Validate editable rows and preserve stable source evidence."""

    prior_by_id = {item.review_id: item for item in prior_items}
    child_ids_by_label = {
        str(child["label"]): str(child["child_id"])
        for child in children
    }
    default_child_id = str(children[0]["child_id"])
    parsed: list[SupplyItemReview] = []
    for index, record in enumerate(_editor_records(value)):
        item_name = str(record.get("Item") or "").strip()
        if not item_name:
            continue
        review_id = str(record.get("review_id") or "").strip()
        prior = prior_by_id.get(review_id)
        child_id = child_ids_by_label.get(
            str(record.get("For") or ""),
            str(record.get("child_id") or "").strip() or default_child_id,
        )
        if not review_id:
            review_id = f"manual:{child_id}:{index + 1}"
        raw_quantity = record.get("Quantity")
        quantity = (
            None
            if raw_quantity in {None, ""}
            else int(raw_quantity)
        )
        raw_package_size = record.get("Package size")
        package_size = (
            None
            if raw_package_size in {None, ""}
            else int(raw_package_size)
        )
        colors = tuple(
            color.strip()
            for color in str(record.get("Color") or "").split(",")
            if color.strip()
        )
        details = str(record.get("Required details") or "").strip()
        issue_codes = (
            prior.issue_codes
            if prior is not None
            else (("missing_quantity",) if quantity is None else ())
        )
        condition = str(record.get("Condition") or "").strip() or None
        condition_applies = (
            prior.condition_applies if prior is not None else None
        )
        provided_by_school = bool(record.get("Provided by school"))
        is_purchasable = (
            (prior.is_purchasable if prior is not None else True)
            and not provided_by_school
            and not (condition is not None and condition_applies is False)
        )
        parsed.append(
            SupplyItemReview(
                review_id=review_id,
                req_id=(
                    prior.req_id
                    if prior is not None
                    else f"manual-{index + 1}"
                ),
                child_id=child_id,
                item_name=item_name,
                required_quantity=quantity,
                quantity_is_range=(
                    prior.quantity_is_range
                    if prior is not None
                    else False
                ),
                quantity_max=(
                    prior.quantity_max if prior is not None else None
                ),
                unit=str(record.get("Unit") or "each"),  # type: ignore[arg-type]
                package_size=package_size,
                brand=str(record.get("Brand") or "").strip() or None,
                brand_required=bool(record.get("Exact brand")),
                size=str(record.get("Size") or "").strip() or None,
                color=colors,
                material=(prior.material if prior is not None else None),
                required_attributes=(
                    {"other_details": details} if details else {}
                ),
                optional=bool(record.get("Optional")),
                is_purchasable=is_purchasable,
                supply_scope=str(
                    record.get("Supply use") or "Unspecified"
                ).casefold(),  # type: ignore[arg-type]
                provided_by_school=provided_by_school,
                condition=condition,
                condition_applies=condition_applies,
                condition_group_id=(
                    prior.condition_group_id
                    if prior is not None
                    else None
                ),
                condition_question=(
                    prior.condition_question
                    if prior is not None
                    else None
                ),
                condition_option=(
                    prior.condition_option
                    if prior is not None
                    else None
                ),
                source_document=(
                    prior.source_document if prior is not None else None
                ),
                source_section=(
                    prior.source_section if prior is not None else None
                ),
                source_page=(
                    prior.source_page if prior is not None else None
                ),
                source_language=(
                    prior.source_language if prior is not None else None
                ),
                notes=str(record.get("Notes") or "").strip() or None,
                source_text=(
                    prior.source_text
                    if prior is not None
                    else f"Added by user: {item_name}"
                ),
                confidence=(
                    prior.confidence if prior is not None else 1.0
                ),
                review_status=(
                    "deleted"
                    if bool(record.get("Delete"))
                    else (
                        "confirmed"
                        if bool(record.get("Confirmed"))
                        else "pending"
                    )
                ),
                already_owned=bool(record.get("Already owned")),
                allow_equivalents=bool(record.get("Allow equivalents")),
                issue_codes=issue_codes,
            )
        )
    return tuple(parsed)


REVIEW_SINGULAR_ITEM_NAMES: Mapping[str, str] = {
    "backpacks": "backpack",
    "baby_wipes": "container of baby wipes",
    "binders": "binder",
    "colored_pencils": "pack of colored pencils",
    "composition_notebooks": "composition notebook",
    "crayons": "crayon",
    "dividers": "set of dividers",
    "dry_erase_markers": "dry-erase marker",
    "erasers": "eraser",
    "folders": "folder",
    "glue_sticks": "glue stick",
    "headphones": "pair of headphones",
    "highlighters": "highlighter",
    "index_cards": "pack of index cards",
    "markers": "marker",
    "notebook_paper": "pack of notebook paper",
    "pencil_boxes": "pencil box",
    "pencil_pouches": "pencil pouch",
    "pencil_sharpeners": "pencil sharpener",
    "pencils": "pencil",
    "pens": "pen",
    "permanent_markers": "permanent marker",
    "rulers": "ruler",
    "scissors": "pair of scissors",
    "spiral_notebooks": "spiral notebook",
    "sticky_notes": "pack of sticky notes",
    "tissues": "box of tissues",
    "water_bottles": "water bottle",
}

REVIEW_PLURAL_ITEM_NAMES: Mapping[str, str] = {
    "backpacks": "backpacks",
    "binders": "binders",
    "composition_notebooks": "composition notebooks",
    "folders": "folders",
    "pencil_boxes": "pencil boxes",
    "pencil_pouches": "pencil pouches",
    "pencil_sharpeners": "pencil sharpeners",
    "rulers": "rulers",
    "spiral_notebooks": "spiral notebooks",
    "water_bottles": "water bottles",
}


def review_understanding_text(item: SupplyItemReview) -> str:
    """Describe one extracted purchase in plain parent-facing language."""

    quantity = item.required_quantity
    display_name = _item_display_name(item.item_name).casefold()
    singular_name = REVIEW_SINGULAR_ITEM_NAMES.get(
        item.item_name,
        display_name,
    )
    branded_name = (
        f"{item.brand} {display_name}"
        if item.brand
        else display_name
    )
    if quantity is None:
        text = f"Quantity needed for {branded_name}"
    elif item.unit == "each":
        name = (
            singular_name
            if quantity == 1
            else REVIEW_PLURAL_ITEM_NAMES.get(
                item.item_name,
                display_name,
            )
        )
        if item.brand and quantity != 1:
            name = f"{item.brand} {name}"
        if item.brand and quantity == 1:
            name = f"{item.brand} {singular_name}"
        text = f"{quantity} {name}"
    else:
        container = {
            "pack": "pack",
            "box": "box",
            "ream": "ream",
        }.get(item.unit, item.unit)
        if quantity != 1:
            container += "es" if container.endswith("x") else "s"
        count_text = (
            f" of {item.package_size} {display_name}"
            if item.package_size is not None
            else f" of {branded_name}"
        )
        text = f"{quantity} {container}{count_text}"

    details: list[str] = []
    if item.brand_required:
        details.append("brand required")
    if item.size:
        details.append(item.size)
    if item.color:
        details.append(" or ".join(item.color))
    if item.supply_scope == "individual":
        details.append("individual supply")
    elif item.supply_scope == "shared":
        details.append("shared supply")
    if item.optional:
        details.append("optional")
    if item.condition:
        details.append(f"only if {item.condition}")
    return ", ".join((text, *details))


def review_system_decision_messages(
    item: SupplyItemReview,
) -> tuple[str, ...]:
    """Translate BR-29 interpretation choices into parent language."""

    messages: list[str] = []
    if SYSTEM_DECISION_CONSOLIDATED_SOURCES in item.system_decisions:
        messages.append(
            f"Combined from {len(item.sources)} places in the list."
        )
    if SYSTEM_DECISION_RECONCILED_BRAND in item.system_decisions:
        messages.append(
            "The sources differed on brand detail; the explicit requirement "
            "was kept."
        )
    if SYSTEM_DECISION_RECONCILED_EXCLUSIONS in item.system_decisions:
        messages.append(
            "The exclusions from every contributing source were kept."
        )
    for decision in item.system_decisions:
        if not decision.startswith(
            SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX
        ):
            continue
        field_name = decision.removeprefix(
            SYSTEM_DECISION_RECONCILED_ATTRIBUTE_PREFIX
        )
        field_label = ATTRIBUTE_DISPLAY_NAMES.get(
            field_name,
            field_name.replace("_", " "),
        )
        messages.append(
            f"The sources described {field_label} differently; the compatible "
            "details were combined."
        )
    return tuple(messages)


def review_child_framing(
    child_id: str,
    child_label: str,
    envelope: ExtractionEnvelope,
    items: Sequence[SupplyItemReview],
) -> str:
    """Frame extracted items as choices about what enters the cart."""

    child_items = tuple(
        item
        for item in items
        if item.child_id == child_id
        and item.is_purchasable
        and not item.provided_by_school
        and item.review_status != "deleted"
    )
    needs_check = sum(
        bool(review_issue_explanations(item))
        or (
            item.condition is not None
            and item.condition_applies is None
        )
        for item in child_items
    )
    clear_count = len(child_items) - needs_check
    selection = envelope.document_selection
    section_text = (
        _join_names(selection.selected_section_labels)
        if selection is not None
        else f"{child_label}'s list"
    )
    if needs_check:
        return (
            f"{section_text}: {clear_count} "
            f"{'item is' if clear_count == 1 else 'items are'} ready for the "
            f"cart. Choose how to handle {needs_check} "
            f"{'item' if needs_check == 1 else 'items'} before moving on."
        )
    return (
        f"{section_text}: {len(child_items)} "
        f"{'item is' if len(child_items) == 1 else 'items are'} ready for the "
        "cart. You can edit, remove, or mark anything you already have."
    )


def _review_control_update(
    item: SupplyItemReview,
    *,
    item_name: str,
    quantity: int,
    unit: str,
    package_size: int | None,
    brand: str,
    brand_required: bool,
    size: str,
    material: str,
    colors: str,
    required_details: str,
    optional: bool,
    supply_scope: str,
    allow_equivalents: bool,
    already_owned: bool,
    notes: str,
    delete: bool,
) -> SupplyItemReview:
    """Apply secondary form controls without changing source evidence."""

    required_attributes = dict(item.required_attributes)
    if required_details.strip():
        required_attributes["other_details"] = required_details.strip()
    else:
        required_attributes.pop("other_details", None)
    return item.model_copy(
        update={
            "item_name": item_name,
            "required_quantity": quantity,
            "unit": unit,
            "package_size": package_size,
            "brand": brand.strip() or None,
            "brand_required": brand_required,
            "size": size.strip() or None,
            "material": material.strip() or None,
            "color": tuple(
                value.strip()
                for value in colors.split(",")
                if value.strip()
            ),
            "required_attributes": required_attributes,
            "optional": optional,
            "supply_scope": supply_scope,
            "already_owned": already_owned,
            "allow_equivalents": (
                allow_equivalents and not brand_required
            ),
            "notes": notes.strip() or None,
            "review_status": (
                "deleted" if delete else item.review_status
            ),
        }
    )


def review_detail_field_visibility(
    item: SupplyItemReview,
    offers: Sequence[Offer],
) -> Mapping[str, bool]:
    """Apply BR-28 using the same catalog attribute keys as matching."""

    supplied_values: Mapping[str, object] = {
        "size": item.size,
        "material": item.material,
        "acceptable_colors": item.color,
    }
    visibility: dict[str, bool] = {}
    for field_name in PARENT_EDITABLE_DETAIL_FIELDS:
        catalog_values: set[str] = set()
        for offer in offers:
            if offer.category != item.item_name or offer.stock_qty <= 0:
                continue
            for key in ATTRIBUTE_OFFER_KEYS[field_name]:
                value = offer.attributes.get(key)
                if value not in (None, "", (), [], {}):
                    catalog_values.add(repr(value).casefold())
        visibility[field_name] = (
            supplied_values[field_name] not in (None, "", (), [], {})
            or len(catalog_values) > 1
        )
    return visibility


def _render_review_detail_controls(
    st: Any,
    item: SupplyItemReview,
    *,
    key_prefix: str,
    offers: Sequence[Offer],
) -> SupplyItemReview:
    """Render secondary item editing controls inside a collapsed expander."""

    visibility = review_detail_field_visibility(item, offers)
    with st.expander("More detail"):
        first, second = st.columns(2)
        item_name = first.selectbox(
            "Item",
            options=tuple(sorted(ALLOWED_CATEGORIES)),
            index=tuple(sorted(ALLOWED_CATEGORIES)).index(item.item_name),
            format_func=_item_display_name,
            key=f"{key_prefix}:item",
        )
        quantity = int(
            second.number_input(
                "Quantity",
                min_value=1,
                value=item.required_quantity or 1,
                step=1,
                key=f"{key_prefix}:quantity",
            )
        )
        unit = first.selectbox(
            "Unit",
            options=("each", "pack", "box", "ream"),
            index=("each", "pack", "box", "ream").index(item.unit),
            key=f"{key_prefix}:unit",
        )
        package_size_value = second.number_input(
            "Units in one package",
            min_value=1,
            value=item.package_size,
            step=1,
            key=f"{key_prefix}:package",
        )
        brand = first.text_input(
            "Brand",
            value=item.brand or "",
            key=f"{key_prefix}:brand",
        )
        size = item.size or ""
        if visibility["size"]:
            size = second.text_input(
                "Size or dimensions",
                value=size,
                key=f"{key_prefix}:size",
            )
        colors = ", ".join(item.color)
        if visibility["acceptable_colors"]:
            colors = first.text_input(
                "Acceptable colors",
                value=colors,
                key=f"{key_prefix}:colors",
            )
        material = item.material or ""
        if visibility["material"]:
            material = second.text_input(
                "Material",
                value=material,
                key=f"{key_prefix}:material",
            )
        required_details = st.text_input(
            "Other required details",
            value=str(
                item.required_attributes.get("other_details") or ""
            ),
            key=f"{key_prefix}:required-details",
        )
        supply_scope = second.selectbox(
            "Supply use",
            options=("individual", "shared", "unspecified"),
            index=("individual", "shared", "unspecified").index(
                item.supply_scope
            ),
            key=f"{key_prefix}:scope",
        )
        brand_mode = first.radio(
            "Brand choice",
            (
                "Equivalent brands are okay",
                "Exact brand required",
            ),
            index=1 if item.brand_required else 0,
            key=f"{key_prefix}:brand-choice",
        )
        brand_required = brand_mode == "Exact brand required"
        allow_equivalents = not brand_required
        optional = second.checkbox(
            "Optional item",
            value=item.optional,
            key=f"{key_prefix}:optional",
        )
        already_owned = first.checkbox(
            "We already own this",
            value=item.already_owned,
            key=f"{key_prefix}:owned",
        )
        delete = second.checkbox(
            "Remove this incorrect item",
            value=item.review_status == "deleted",
            key=f"{key_prefix}:delete",
        )
        notes = st.text_input(
            "Parent note",
            value=item.notes or "",
            key=f"{key_prefix}:notes",
        )
    return _review_control_update(
        item,
        item_name=item_name,
        quantity=quantity,
        unit=unit,
        package_size=(
            int(package_size_value)
            if package_size_value is not None
            else None
        ),
        brand=brand,
        brand_required=brand_required,
        size=size,
        material=material,
        colors=colors,
        required_details=required_details,
        optional=optional,
        supply_scope=supply_scope,
        allow_equivalents=allow_equivalents,
        already_owned=already_owned,
        notes=notes,
        delete=delete,
    )


def _copy_shared_review_edits(
    source: SupplyItemReview,
    target: SupplyItemReview,
) -> SupplyItemReview:
    """Apply one deduplicated ambiguity edit to every affected child row."""

    return target.model_copy(
        update={
            "item_name": source.item_name,
            "required_quantity": source.required_quantity,
            "quantity_is_range": source.quantity_is_range,
            "quantity_max": source.quantity_max,
            "unit": source.unit,
            "package_size": source.package_size,
            "brand": source.brand,
            "brand_required": source.brand_required,
            "size": source.size,
            "color": source.color,
            "material": source.material,
            "required_attributes": source.required_attributes,
            "optional": source.optional,
            "supply_scope": source.supply_scope,
            "notes": source.notes,
            "already_owned": source.already_owned,
            "allow_equivalents": source.allow_equivalents,
            "review_status": source.review_status,
            "system_decisions": source.system_decisions,
        }
    )


def _render_compact_review_row(
    st: Any,
    members: Sequence[SupplyItemReview],
    child_labels: Mapping[str, str],
    *,
    key_prefix: str,
    offers: Sequence[Offer],
    flag_messages: Sequence[str] = (),
) -> tuple[dict[str, SupplyItemReview], bool]:
    """Render source, interpretation, and only the needed confirmation."""

    representative = members[0]
    with st.container(border=True):
        if flag_messages:
            st.warning(
                escape_streamlit_dollars(
                    " ".join(flag_messages)
                )
            )
        affected_labels = tuple(
            dict.fromkeys(
                child_labels.get(member.child_id, member.child_id)
                for member in members
            )
        )
        if len(affected_labels) > 1:
            st.caption(
                escape_streamlit_dollars(
                    "Affects " + _join_names(affected_labels)
                )
            )
        decision_messages = tuple(
            dict.fromkeys(
                message
                for member in members
                for message in review_system_decision_messages(member)
            )
        )
        for message in decision_messages:
            st.info(escape_streamlit_dollars(message))
        show_item_sources = bool(flag_messages or decision_messages)
        if show_item_sources:
            source_column, understanding_column, confirm_column = st.columns(
                [5, 4, 2]
            )
        else:
            understanding_column, confirm_column = st.columns([9, 2])
            source_column = None
        if source_column is not None:
            with source_column:
                st.caption("Source details")
                source_inputs = {
                    (
                        list_input.child_id,
                        list_input.resolved_document_name,
                    ): list_input
                    for list_input in st.session_state.get("list_inputs", ())
                }
                for member in members:
                    if len(members) > 1:
                        st.caption(
                            escape_streamlit_dollars(
                                child_labels.get(
                                    member.child_id,
                                    member.child_id,
                                )
                            )
                        )
                    sources = member.sources
                    source_rows = sources or (
                        RequirementSource(
                            source_req_id=member.req_id,
                            document_name=member.source_document,
                            section_name=member.source_section,
                            page_number=(
                                member.source_page
                                or NONPAGINATED_SOURCE_PAGE
                            ),
                            exact_line=member.source_text,
                            quantity=member.required_quantity or 0,
                        ),
                    )
                    for source in source_rows:
                        page_text = (
                            f"Page {source.page_number}: "
                            if source.page_number is not None
                            else ""
                        )
                        st.write(
                            escape_streamlit_dollars(
                                page_text
                                + _display_source_line(source.exact_line)
                            )
                        )
                        list_input = source_inputs.get(
                            (member.child_id, source.document_name)
                        ) or next(
                            (
                                candidate
                                for (
                                    child_id,
                                    _,
                                ), candidate in source_inputs.items()
                                if child_id == member.child_id
                            ),
                            None,
                        )
                        if list_input is not None:
                            _render_source_reference(
                                st,
                                list_input,
                                page_number=source.page_number,
                                source_line=source.exact_line,
                                key=(
                                    f"{key_prefix}:item-source:"
                                    f"{source.source_req_id}"
                                ),
                            )
        with understanding_column:
            st.write(
                escape_streamlit_dollars(
                    review_understanding_text(representative)
                )
            )
            st.caption(
                f"List detail: {confidence_band(representative.confidence)}"
            )
        with confirm_column:
            if flag_messages:
                confirmed = st.checkbox(
                    "Use this in the cart",
                    value=all(
                        member.review_status == "confirmed"
                        for member in members
                    ),
                    key=f"{key_prefix}:confirmed",
                )
            else:
                confirmed = True
        edited_representative = _render_review_detail_controls(
            st,
            representative,
            key_prefix=key_prefix,
            offers=offers,
        )
    edited = {
        member.review_id: (
            edited_representative
            if member.review_id == representative.review_id
            else _copy_shared_review_edits(
                edited_representative,
                member,
            )
        )
        for member in members
    }
    return edited, confirmed


def _new_review_item_from_controls(
    st: Any,
    child_id: str,
    *,
    key_prefix: str,
) -> SupplyItemReview | None:
    """Offer one secondary form for adding a missing item."""

    with st.expander("Add a missing item"):
        add_item = st.checkbox(
            "Add this item to the list",
            key=f"{key_prefix}:add",
        )
        first, second = st.columns(2)
        item_name = first.selectbox(
            "Item",
            options=tuple(sorted(ALLOWED_CATEGORIES)),
            format_func=_item_display_name,
            key=f"{key_prefix}:item",
        )
        quantity = int(
            second.number_input(
                "Quantity",
                min_value=1,
                value=1,
                step=1,
                key=f"{key_prefix}:quantity",
            )
        )
        unit = first.selectbox(
            "Unit",
            options=("each", "pack", "box", "ream"),
            key=f"{key_prefix}:unit",
        )
        scope = second.selectbox(
            "Supply use",
            options=("individual", "shared", "unspecified"),
            index=2,
            key=f"{key_prefix}:scope",
        )
        optional = first.checkbox(
            "Optional item",
            key=f"{key_prefix}:optional",
        )
        source_text = st.text_input(
            "What the list says",
            value="Added by parent during review",
            key=f"{key_prefix}:source",
        )
    if not add_item:
        return None
    identifier = str(uuid4())
    return SupplyItemReview(
        review_id=f"parent:{child_id}:{identifier}",
        req_id=f"parent-{identifier}",
        child_id=child_id,
        item_name=item_name,
        required_quantity=quantity,
        unit=unit,  # type: ignore[arg-type]
        optional=optional,
        supply_scope=scope,  # type: ignore[arg-type]
        source_text=source_text.strip() or "Added by parent during review",
        confidence=1.0,
        review_status="confirmed",
        allow_equivalents=True,
    )


def _document_scope_fingerprint(
    list_input: ListInput,
    structure: DocumentStructureEnvelope,
    grade: str,
) -> int:
    """Keep section widget state tied to one document and entered grade."""

    return abs(
        hash(
            (
                list_input.resolved_document_name,
                list_input.source,
                grade,
                tuple(
                    (
                        section.section_id,
                        section.grades,
                        section.duplicate_of_section_id,
                    )
                    for section in structure.sections
                ),
            )
        )
    )


def _section_choice_from_state(
    state: MutableMapping[str, Any],
    resolution: SectionResolution,
    *,
    key_prefix: str,
    initial_section_ids: tuple[str, ...],
) -> ResolvedSectionChoice:
    """Derive displayed and submitted scope from one durable state."""

    override_toggle_key = f"{key_prefix}:override-enabled"
    override_selection_key = f"{key_prefix}:override-sections"
    state.setdefault(override_toggle_key, False)
    state.setdefault(override_selection_key, list(initial_section_ids))
    selected_question_ids = []
    for section in resolution.parent_questions:
        question_key = f"{key_prefix}:question:{section.section_id}"
        state.setdefault(
            question_key,
            section.section_id in initial_section_ids,
        )
        if bool(state[question_key]):
            selected_question_ids.append(section.section_id)
    override_enabled = bool(state[override_toggle_key])
    override_ids = (
        tuple(state[override_selection_key])
        if override_enabled
        else None
    )
    choice = build_resolved_section_choice(
        resolution,
        selected_question_ids=tuple(selected_question_ids),
        override_section_ids=override_ids,
    )
    if not override_enabled:
        state[override_selection_key] = list(choice.selected_section_ids)
    return choice


def _render_section_source_links(
    st: Any,
    list_input: ListInput,
    sections: Sequence[DocumentSection],
    *,
    key_prefix: str,
    rendered_sources: set[tuple[str, int | None]] | None = None,
) -> None:
    """Render each document-page source once, even through two UI paths."""

    seen = rendered_sources if rendered_sources is not None else set()
    for section in sections:
        for page_number in section.page_numbers or (None,):
            source_key = (list_input.resolved_document_name, page_number)
            if source_key in seen:
                continue
            seen.add(source_key)
            _render_source_reference(
                st,
                list_input,
                page_number=page_number,
                source_line=section.source_line,
                key=(
                    f"{key_prefix}:{section.section_id}:{page_number}"
                ),
            )


def _section_exclusion_summary(
    resolution: SectionResolution,
    choice: ResolvedSectionChoice,
) -> str:
    """Name excluded section counts without listing irrelevant rows."""

    parts = []
    other_grade_sections = tuple(
        section
        for section in resolution.other_grade_sections
        if section.section_id not in choice.selected_section_ids
    )
    if other_grade_sections:
        count = len(other_grade_sections)
        parts.append(
            f"{count} "
            + (
                "section was for another grade"
                if count == 1
                else "sections were for other grades"
            )
        )
    return "; ".join(parts)


def _translation_context(
    structure: DocumentStructureEnvelope,
    resolution: SectionResolution,
) -> str:
    """Explain multilingual repetition in terms useful to a parent."""

    translated_languages = tuple(
        dict.fromkeys(
            section.language
            for section in resolution.translated_duplicates
            if section.language
            and (
                resolution.primary_language is None
                or section.language.casefold()
                != resolution.primary_language.casefold()
            )
        )
    )
    if not translated_languages:
        return ""
    read_language = resolution.primary_language or "source-language"
    return (
        "This document repeats the lists in "
        + _join_names(translated_languages)
        + f". Items were extracted from the {read_language} version."
    )


def _render_sections(st: Any) -> None:
    """State deterministic scope and ask only unresolved section questions."""

    intake = st.session_state["intake"]
    structures: Mapping[str, DocumentStructureEnvelope] = (
        st.session_state["document_structures"]
    )
    if intake is None or not structures:
        st.session_state["screen"] = "working"
        st.rerun()
        return
    child_by_id = {
        str(child["child_id"]): child
        for child in intake["children"]
    }
    input_by_child = {
        list_input.child_id: list_input
        for list_input in st.session_state["list_inputs"]
    }
    selections = dict(st.session_state["document_selections"])

    st.header("What will be extracted from each list")
    st.write(
        "The matching grade is selected automatically. You only need to "
        "answer when a section has no grade or the document does not contain "
        "the grade entered for a student."
    )
    if st.session_state["structure_errors"]:
        st.error(
            "The documents named below could not be organized. They will not "
            "be extracted, but the other lists can continue."
        )
        for child_id, error in st.session_state["structure_errors"].items():
            child = child_by_id.get(child_id, {})
            st.write(
                escape_streamlit_dollars(
                    f"{child.get('label', child_id)}: {error}"
                )
            )

    choices: dict[str, ResolvedSectionChoice] = {}
    blocked_actions: dict[str, str] = {}
    for child_id, structure in structures.items():
        child = child_by_id[child_id]
        list_input = input_by_child[child_id]
        grade = str(child["grade"])
        resolution = resolve_document_sections(structure, grade)
        current = selections.get(child_id)
        initial_ids = (
            tuple(current.selected_section_ids)
            if current is not None
            else tuple(
                section.section_id
                for section in resolution.auto_selected
            )
        )
        key_prefix = (
            f"document_scope:{child_id}:"
            f"{_document_scope_fingerprint(list_input, structure, grade)}"
        )
        choice = _section_choice_from_state(
            st.session_state,
            resolution,
            key_prefix=key_prefix,
            initial_section_ids=initial_ids,
        )
        choices[child_id] = choice
        document_name = list_input.resolved_document_name

        with st.container(border=True):
            rendered_sources: set[tuple[str, int | None]] = set()
            st.subheader(
                escape_streamlit_dollars(
                    f"{child['label']} · {grade}"
                )
            )
            st.caption(
                escape_streamlit_dollars(f"Document: {document_name}")
            )

            if not resolution.has_primary_language_source:
                languages = _join_names(
                    structure.languages
                    or tuple(
                        section.language
                        for section in structure.sections
                        if section.language
                    )
                )
                st.error(
                    escape_streamlit_dollars(
                        f"{document_name} contains {languages or 'translated'} "
                        "sections, but no source-language original that can be "
                        f"resolved for {child['label']}. Nothing will be extracted "
                        "until you choose how to proceed."
                    )
                )
                blocked_actions[child_id] = st.radio(
                    f"How would you like to proceed for {child['label']}?",
                    (
                        "Upload a different document",
                        f"Go to Your students to remove {child['label']}",
                    ),
                    key=f"{key_prefix}:blocked-action",
                )
            elif not resolution.has_grade_match and not choice.can_continue:
                covered = (
                    _join_names(resolution.covered_grades)
                    or "no identified grades"
                )
                st.error(
                    escape_streamlit_dollars(
                        f"No section in {document_name} matches "
                        f"{child['label']} ({grade}). The document covers "
                        f"{covered}. Nothing will be extracted until you choose "
                        "how to proceed."
                    )
                )
                blocked_actions[child_id] = st.radio(
                    f"How would you like to proceed for {child['label']}?",
                    (
                        "Pick a section manually",
                        "Upload a different document",
                        f"Go to Your students to remove {child['label']}",
                    ),
                    key=f"{key_prefix}:blocked-action",
                )
            elif choice.selected_section_labels:
                st.success(
                    escape_streamlit_dollars(
                        "Will extract "
                        + _join_names(choice.selected_section_labels)
                        + f" from {document_name}."
                    )
                )
                if not resolution.has_grade_match:
                    st.warning(
                        escape_streamlit_dollars(
                            f"{document_name} has no section matching {grade}. "
                            "You chose "
                            + _join_names(choice.selected_section_labels)
                            + ", so the list can continue."
                        )
                    )
                labels_by_id = {
                    section.section_id: section.label
                    for section in resolution.primary_language_sections
                }
                for section_id in choice.automatically_selected_ids:
                    st.caption(
                        escape_streamlit_dollars(
                            f"{labels_by_id[section_id]} was matched to "
                            f"{child['label']}'s entered grade."
                        )
                    )
                for section_id in choice.parent_selected_ids:
                    st.caption(
                        escape_streamlit_dollars(
                            f"{labels_by_id[section_id]} was chosen by you."
                        )
                    )

            override_toggle_key = f"{key_prefix}:override-enabled"
            for section in resolution.parent_questions:
                st.checkbox(
                    f"Also use {section.label} for {child['label']}?",
                    key=f"{key_prefix}:question:{section.section_id}",
                    help=(
                        "This section has no grade token, so it cannot be "
                        "included or excluded automatically."
                    ),
                )
                page_text = (
                    "page " + ", ".join(map(str, section.page_numbers))
                    if section.page_numbers
                    else "the uploaded list"
                )
                st.caption(
                    escape_streamlit_dollars(
                        f"From {page_text}: {section.source_line}"
                    )
                )
                _render_section_source_links(
                    st,
                    list_input,
                    (section,),
                    key_prefix=f"{key_prefix}:question-source",
                    rendered_sources=rendered_sources,
                )

            selected_sections_by_id = {
                section.section_id: section
                for section in resolution.primary_language_sections
            }
            _render_section_source_links(
                st,
                list_input,
                tuple(
                    selected_sections_by_id[section_id]
                    for section_id in choice.selected_section_ids
                    if section_id in selected_sections_by_id
                ),
                key_prefix=f"{key_prefix}:selected-source",
                rendered_sources=rendered_sources,
            )

            exclusion_summary = _section_exclusion_summary(
                resolution,
                choice,
            )
            if exclusion_summary:
                st.caption(
                    escape_streamlit_dollars(
                        f"Not extracted: {exclusion_summary}."
                    )
                )

            with st.expander("Change which sections are extracted"):
                st.checkbox(
                    "Use a different section selection",
                    key=override_toggle_key,
                )
                option_ids = tuple(
                    section.section_id
                    for section in resolution.primary_language_sections
                )
                labels_by_id = {
                    section.section_id: section.label
                    for section in resolution.primary_language_sections
                }
                st.multiselect(
                    f"Sections for {child['label']}",
                    option_ids,
                    format_func=lambda section_id, labels=labels_by_id: (
                        labels[section_id]
                    ),
                    key=f"{key_prefix}:override-sections",
                    disabled=not bool(
                        st.session_state[override_toggle_key]
                    ),
                )
                translation_context = _translation_context(
                    structure,
                    resolution,
                )
                if translation_context:
                    st.caption(
                        escape_streamlit_dollars(translation_context)
                    )

    back_column, continue_column = _navigation_button_columns(st)
    return_to_lists = back_column.button(
        "Back to lists",
        use_container_width=True,
    )
    submitted = continue_column.button(
        "Continue with these sections",
        type="primary",
        use_container_width=True,
    )
    if return_to_lists:
        navigate_back_to_screen(st.session_state, "lists")
        st.rerun()
    if submitted:
        if any(
            action == "Upload a different document"
            for action in blocked_actions.values()
        ):
            navigate_back_to_screen(st.session_state, "lists")
            st.rerun()
        if any(
            action.startswith("Go to Your students")
            for action in blocked_actions.values()
        ):
            st.session_state["intake_step"] = 1
            navigate_back_to_screen(st.session_state, "intake")
            st.rerun()
        try:
            for child_id, choice in choices.items():
                selections[child_id] = choice_to_document_selection(
                    structures[child_id],
                    choice,
                )
        except ValueError as error:
            st.session_state["ui_error_active"] = True
            st.error(escape_streamlit_dollars(str(error)))
            return
        st.session_state["document_selections"] = selections
        st.session_state["extraction_cache_ready"] = False
        st.session_state["unmerged_extracted_lists"] = {}
        st.session_state["requirement_merge_result"] = None
        st.session_state["requirement_merge_resolved"] = False
        st.session_state["requirement_merge_choices"] = {}
        st.session_state["requirement_constraint_choices"] = {}
        st.session_state["requirement_variant_quantity_choices"] = {}
        st.session_state["requirement_merge_validation_errors"] = ()
        st.session_state["organized_list_confirmed"] = False
        _limit_reached_stage(st.session_state, 2)
        _invalidate_plan_state(st.session_state)
        st.session_state["progress_substep"] = "extracting selected sections"
        st.session_state["screen"] = "working"
        st.rerun()


def _requirement_source_label(source: Any) -> str:
    """Name one contributing list line without internal identifiers."""

    location = source.document_name or "Supply list"
    if source.section_name:
        location += f" · {source.section_name}"
    location += f" · page {source.page_number}"
    return location


def _display_source_line(source_line: str) -> str:
    """Hide matrix-cell annotations while preserving stored provenance."""

    return source_line.split("|", 1)[0].strip()


def _variant_detail_label(details: Sequence[tuple[str, object]]) -> str:
    """Describe one source-backed variant without internal field names."""

    parts = []
    for field_name, value in details:
        field_label = ATTRIBUTE_DISPLAY_NAMES.get(
            field_name,
            field_name.replace("_", " "),
        )
        value_label = (
            "not specified"
            if value in (None, (), "")
            else (
                " or ".join(map(str, value))
                if isinstance(value, (tuple, list, set))
                else str(value)
            )
        )
        parts.append(f"{field_label}: {value_label}")
    return "; ".join(parts)


def _render_requirement_merge(st: Any) -> None:
    """Resolve same-item quantity or constraint disagreements."""

    result = st.session_state.get("requirement_merge_result")
    if (
        not isinstance(result, RequirementMergeResult)
        or not (result.interrupts or result.constraint_interrupts)
    ):
        st.session_state["requirement_merge_resolved"] = True
        st.session_state["screen"] = "working"
        st.rerun()
        return
    intake = st.session_state["intake"]
    child_labels = {
        str(child["child_id"]): str(child["label"])
        for child in intake["children"]
    }
    input_by_child = {
        list_input.child_id: list_input
        for list_input in st.session_state["list_inputs"]
    }

    st.header("Choose what goes in the cart")
    st.write(
        "The same item appears differently in more than one part of a list. "
        "Choose once before it enters your cart."
    )
    pending_errors = tuple(
        st.session_state.get("requirement_merge_validation_errors", ())
    )
    if pending_errors:
        st.error(
            escape_streamlit_dollars(
                "Choose a quantity for: " + _join_names(pending_errors) + "."
            )
        )
        st.markdown("[Go to the first item that needs attention](#merge-first-error)")

    selections: dict[str, tuple[str, int | None]] = {}
    variant_quantity_choices: dict[str, dict[str, int]] = {}
    validation_errors: list[str] = []
    first_error_anchor_added = False
    for decision in item_decisions(result):
        child_label = child_labels.get(
            decision.child_id,
            decision.child_id,
        )
        with st.container(border=True):
            if (
                pending_errors
                and _item_display_name(decision.canonical_item)
                in pending_errors
                and not first_error_anchor_added
            ):
                st.markdown(
                    '<span id="merge-first-error"></span>',
                    unsafe_allow_html=True,
                )
                first_error_anchor_added = True
            st.subheader(
                escape_streamlit_dollars(
                    f"{_item_display_name(decision.canonical_item)} "
                    f"for {child_label}"
                )
            )
            st.caption("What each source requested")
            for source in decision.sources:
                st.write(
                    escape_streamlit_dollars(
                        f"{_requirement_source_label(source)} — "
                        f"{source.quantity}: "
                        f"{_display_source_line(source.exact_line)}"
                    )
                )

            if decision.variants:
                st.caption(
                    "The sources specify different versions. Adjust how many "
                    "of each version should go in the cart."
                )
                selected_variants: dict[str, int] = {}
                for variant in decision.variants:
                    variant_quantity = int(
                        st.number_input(
                            _variant_detail_label(variant.details),
                            min_value=0,
                            value=variant.default_quantity,
                            step=1,
                            key=f"{variant.variant_id}:quantity",
                            help=(
                                "The starting value is the quantity extracted "
                                "from the source for this version."
                            ),
                        )
                    )
                    selected_variants[variant.variant_id] = variant_quantity
                    for source in variant.sources:
                        st.caption(
                            escape_streamlit_dollars(
                                f"{_requirement_source_label(source)}: "
                                f"{_display_source_line(source.exact_line)}"
                            )
                        )
                variant_quantity_choices[decision.decision_id] = (
                    selected_variants
                )
                if not any(selected_variants.values()):
                    validation_errors.append(
                        _item_display_name(decision.canonical_item)
                    )
            else:
                interrupt = decision.quantity_interrupt
                if interrupt is None:
                    continue
                source_options = tuple(
                    (
                        "Use the quantity from "
                        f"{_requirement_source_label(source)} "
                        f"({source.quantity})",
                        source.quantity,
                    )
                    for source in interrupt.sources
                )
                option_labels = (
                    (
                        "Add every list's quantity together "
                        f"({interrupt.default_quantity}) — default"
                    ),
                    *(label for label, _ in source_options),
                    "Choose my own quantity",
                )
                selected_label = st.radio(
                    "Quantity to purchase",
                    option_labels,
                    index=0,
                    key=f"{interrupt.interrupt_id}:choice",
                )
                if selected_label == option_labels[0]:
                    selections[interrupt.interrupt_id] = (
                        "total",
                        interrupt.default_quantity,
                    )
                    selected_quantity = interrupt.default_quantity
                elif selected_label == option_labels[-1]:
                    selected_quantity = int(
                        st.number_input(
                            "Quantity to purchase",
                            min_value=1,
                            value=interrupt.default_quantity,
                            step=1,
                            key=f"{interrupt.interrupt_id}:custom",
                        )
                    )
                    selections[interrupt.interrupt_id] = (
                        "custom",
                        selected_quantity,
                    )
                else:
                    source_index = option_labels.index(selected_label) - 1
                    selected_quantity = source_options[source_index][1]
                    selections[interrupt.interrupt_id] = (
                        "source",
                        selected_quantity,
                    )
                st.caption(f"The cart quantity will be {selected_quantity}.")

            for source in decision.sources:
                list_input = input_by_child.get(decision.child_id)
                if list_input is not None:
                    _render_source_reference(
                        st,
                        list_input,
                        page_number=source.page_number,
                        source_line=source.exact_line,
                        key=(
                            f"{decision.decision_id}:"
                            f"{source.source_req_id}"
                        )
                    )

    submitted = st.button(
        "Continue with these choices",
        type="primary",
        use_container_width=True,
    )
    if not submitted:
        return
    if validation_errors:
        st.session_state["requirement_merge_validation_errors"] = tuple(
            dict.fromkeys(validation_errors)
        )
        st.rerun()
    st.session_state["requirement_merge_validation_errors"] = ()
    quantity_choices = {
        interrupt_id: int(quantity)
        for interrupt_id, (_, quantity) in selections.items()
        if quantity is not None
    }
    merged, resolved = consolidate_extractions(
        st.session_state["unmerged_extracted_lists"],
        quantity_choices=quantity_choices,
        constraint_choices={},
        variant_quantity_choices=variant_quantity_choices,
    )
    st.session_state["extracted_lists"] = merged
    st.session_state["requirement_merge_result"] = resolved
    st.session_state["requirement_merge_choices"] = selections
    st.session_state["requirement_constraint_choices"] = {}
    st.session_state["requirement_variant_quantity_choices"] = (
        variant_quantity_choices
    )
    st.session_state["requirement_merge_resolved"] = True
    st.session_state["screen"] = "working"
    st.rerun()


def _personalize_source_summary(
    st: Any,
    child_id: str,
    envelope: ExtractionEnvelope,
) -> None:
    """Show one compact source summary and hide excluded content by default."""

    requirements = tuple(envelope.requirements)
    documents = tuple(
        dict.fromkeys(
            source.document_name
            for requirement in requirements
            for source in (
                requirement.sources
                or (requirement_source(requirement),)
            )
            if source.document_name
        )
    )
    selection = envelope.document_selection
    sections = (
        selection.selected_section_labels
        if selection is not None
        else tuple(
            dict.fromkeys(
                requirement.source_section
                for requirement in requirements
                if requirement.source_section
            )
        )
    )
    pages = tuple(
        sorted(
            {
                source.page_number
                for requirement in requirements
                for source in (
                    requirement.sources
                    or (requirement_source(requirement),)
                )
                if source.page_number is not None
            }
        )
    )
    list_input = next(
        (
            candidate
            for candidate in st.session_state.get("list_inputs", ())
            if candidate.child_id == child_id
        ),
        None,
    )
    if not documents and list_input is not None:
        documents = (list_input.resolved_document_name,)
    summary_parts = []
    if documents:
        summary_parts.append("Document: " + _join_names(documents))
    if sections:
        summary_parts.append("Sections: " + _join_names(sections))
    if pages:
        summary_parts.append("Pages: " + ", ".join(map(str, pages)))
    if summary_parts:
        st.caption(
            escape_streamlit_dollars(
                "Extracted from " + " · ".join(summary_parts)
            )
        )

    ignored = (
        selection.ignored_section_labels
        if selection is not None
        else ()
    )
    if ignored or envelope.uninterpreted_lines or envelope.skipped_lines:
        with st.expander("What was not extracted"):
            if ignored:
                st.caption("Other document sections")
                st.write(escape_streamlit_dollars(_join_names(ignored)))
            for line in envelope.uninterpreted_lines:
                st.warning(
                    escape_streamlit_dollars(
                        "Could not interpret: " + _display_source_line(line)
                    )
                )
            for line in envelope.skipped_lines:
                st.info(
                    escape_streamlit_dollars(
                        "Deliberately skipped: " + _display_source_line(line)
                    )
                )


def _render_review(st: Any) -> None:
    """Render a compact source-versus-interpretation review (FR-12)."""

    intake = st.session_state["intake"]
    extractions: Mapping[str, ExtractionEnvelope] = (
        st.session_state["extracted_lists"]
    )
    if intake is None or not extractions:
        st.session_state["screen"] = "lists"
        st.rerun()
    children = tuple(intake["children"])
    child_labels = {
        str(child["child_id"]): str(child["label"])
        for child in children
    }
    child_order = {
        str(child["child_id"]): index
        for index, child in enumerate(children)
    }
    items = tuple(st.session_state["review_items"])
    review_offers = tuple(load_catalog())
    item_by_id = {item.review_id: item for item in items}
    flag_groups = review_flag_groups(items)
    flagged_row_ids = frozenset(
        row_id for group in flag_groups for row_id in group.row_ids
    )
    flag_groups_by_child: dict[str, list[Any]] = {}
    flag_anchor_by_group: dict[str, str] = {}
    for group in flag_groups:
        anchor = min(
            group.child_ids,
            key=lambda child_id: child_order.get(child_id, 10_000),
        )
        flag_anchor_by_group[group.group_id] = anchor
        flag_groups_by_child.setdefault(anchor, []).append(group)
    note_groups = teacher_note_groups(items)
    note_groups_by_child: dict[str, list[Any]] = {}
    for note in note_groups:
        anchor = min(
            note.child_ids,
            key=lambda child_id: child_order.get(child_id, 10_000),
        )
        note_groups_by_child.setdefault(anchor, []).append(note)
    condition_groups = deduplicate_conditional_questions(
        conditional_review_questions(items)
    )
    condition_groups_by_child: dict[str, list[Any]] = {}
    for group in condition_groups:
        anchor = min(
            group.child_ids,
            key=lambda child_id: child_order.get(child_id, 10_000),
        )
        condition_groups_by_child.setdefault(anchor, []).append(group)

    st.header("Personalize what goes in your cart")
    for child_id, error in st.session_state["extraction_errors"].items():
        st.warning(
            escape_streamlit_dollars(
                f"{child_labels.get(child_id, child_id)}: {error}"
            )
        )
    st.caption(
        "Products and prices come next, after you choose what belongs in the "
        "cart."
    )

    condition_answers: dict[str, str | None] = {}
    confirmed_flag_group_ids: list[str] = []
    edited_by_id: dict[str, SupplyItemReview] = {}
    added_items: list[SupplyItemReview] = []

    with st.form("compact_extraction_review"):
        for child in children:
            child_id = str(child["child_id"])
            st.subheader(
                escape_streamlit_dollars(child_labels[child_id])
            )
            envelope = extractions.get(child_id)
            if envelope is not None:
                st.write(
                    escape_streamlit_dollars(
                        review_child_framing(
                            child_id,
                            child_labels[child_id],
                            envelope,
                            items,
                        )
                    )
                )
                _personalize_source_summary(
                    st,
                    child_id,
                    envelope,
                )
            child_condition_groups = tuple(
                condition_groups_by_child.get(child_id, ())
            )
            if child_condition_groups:
                st.markdown("**Questions from the list**")
                for group in child_condition_groups:
                    affected = tuple(
                        child_labels.get(member_id, member_id)
                        for member_id in group.child_ids
                    )
                    if len(affected) > 1:
                        st.caption(
                            escape_streamlit_dollars(
                                "Affects " + _join_names(affected)
                            )
                        )
                    selected = st.radio(
                        group.prompt,
                        options=group.option_labels,
                        index=(
                            group.option_labels.index(group.selected_label)
                            if group.selected_label in group.option_labels
                            else None
                        ),
                        key=f"condition-group:{group.group_id}",
                    )
                    condition_answers.update(
                        conditional_answers_for_selection(
                            group,
                            selected,
                        )
                    )
            st.markdown("**Items for your cart**")

            rendered_any = False
            for group in flag_groups_by_child.get(child_id, ()):
                members = tuple(
                    item_by_id[row_id] for row_id in group.row_ids
                )
                edited, confirmed = _render_compact_review_row(
                    st,
                    members,
                    child_labels,
                    key_prefix=group.group_id,
                    offers=review_offers,
                    flag_messages=group.messages,
                )
                edited_by_id.update(edited)
                if confirmed:
                    confirmed_flag_group_ids.append(group.group_id)
                rendered_any = True

            shared_checks_elsewhere = tuple(
                group
                for group in flag_groups
                if child_id in group.child_ids
                and flag_anchor_by_group[group.group_id] != child_id
            )
            if shared_checks_elsewhere:
                st.caption(
                    "A check shared with another student appears above and "
                    f"also covers {child_labels[child_id]}."
                )

            for item in items:
                if (
                    item.child_id != child_id
                    or item.review_id in flagged_row_ids
                    or not item.is_purchasable
                    or item.provided_by_school
                    or item.review_status == "deleted"
                ):
                    continue
                edited, _ = _render_compact_review_row(
                    st,
                    (item,),
                    child_labels,
                    key_prefix=f"clear:{item.review_id}",
                    offers=review_offers,
                )
                edited_by_id.update(edited)
                rendered_any = True
            if not rendered_any:
                st.caption(
                    "No items are currently selected for this student."
                )

            provided_items = tuple(
                item
                for item in items
                if item.child_id == child_id
                and item.provided_by_school
                and item.review_status != "deleted"
            )
            if provided_items:
                with st.expander("Already provided by school"):
                    for item in provided_items:
                        st.write(
                            escape_streamlit_dollars(
                                _display_source_line(item.source_text)
                            )
                        )
                        st.caption(
                            escape_streamlit_dollars(
                                "Provided by school: "
                                + review_understanding_text(item)
                                + " — not added to the cart"
                            )
                        )

            child_note_groups = tuple(
                note_groups_by_child.get(child_id, ())
            )
            if child_note_groups:
                with st.expander("Notes from the teacher"):
                    for note in child_note_groups:
                        affected = tuple(
                            child_labels.get(member_id, member_id)
                            for member_id in note.child_ids
                        )
                        if len(affected) > 1:
                            st.caption(
                                escape_streamlit_dollars(
                                    "Affects " + _join_names(affected)
                                )
                            )
                        st.write(
                            escape_streamlit_dollars(
                                _display_source_line(note.source_text)
                            )
                        )

            added = _new_review_item_from_controls(
                st,
                child_id,
                key_prefix=f"add:{child_id}",
            )
            if added is not None:
                added_items.append(added)

        back_column, continue_column = _navigation_button_columns(st)
        return_to_lists = back_column.form_submit_button(
            "Back to lists",
            use_container_width=True,
        )
        submitted = continue_column.form_submit_button(
            "Use these choices and build my shopping plan",
            type="primary",
            use_container_width=True,
        )

    if return_to_lists:
        navigate_back_to_screen(st.session_state, "lists")
        st.rerun()
    if not submitted:
        return
    try:
        reviewed = tuple(
            edited_by_id.get(item.review_id, item)
            for item in items
        ) + tuple(added_items)
        reviewed = apply_conditional_answers(
            reviewed,
            condition_answers,
        )
        reviewed = apply_review_confirmations(
            reviewed,
            flag_groups,
            confirmed_flag_group_ids,
        )
        unresolved = unresolved_required_items(reviewed)
        if unresolved:
            names = _join_names(
                tuple(
                    _item_display_name(item.item_name)
                    for item in unresolved
                )
            )
            raise ValueError(
                "Check and confirm the flagged items before continuing: "
                + names
            )
        confirmed = reviewed_envelopes(
            dict(extractions),
            reviewed,
        )
    except (TypeError, ValueError) as error:
        st.session_state["ui_error_active"] = True
        st.error(escape_streamlit_dollars(str(error)))
        return
    st.session_state["review_items"] = reviewed
    st.session_state["extracted_lists"] = confirmed
    st.session_state["organized_list_confirmed"] = True
    st.session_state["allow_unresolved_items"] = False
    _limit_reached_stage(st.session_state, 3)
    _invalidate_plan_state(st.session_state)
    st.session_state["progress_substep"] = (
        "comparing products, stores, and the budget"
    )
    st.session_state["screen"] = "working"
    st.rerun()


def _route_pipeline_result(
    st: Any,
    result: PipelineResult,
    child_labels: Mapping[str, str],
) -> None:
    """Store and route a completed result without rebuilding it."""

    if st.session_state.get("result") is not result:
        st.session_state["approval_generation"] = (
            int(st.session_state.get("approval_generation", 0)) + 1
        )
        st.session_state["approval_presentations_cache"] = None
        st.session_state["approved_optimization"] = None
        st.session_state["budget_action_ids"] = ()
        st.session_state["resolved_interrupts"] = {}
        st.session_state["replan_preserved_approval_ids"] = frozenset()
        st.session_state["replan_preserved_budget_action_ids"] = frozenset()
        st.session_state["addon_selection_token"] = None
        st.session_state["addon_evaluation"] = None
    st.session_state["result"] = result
    if not result.extractions:
        st.session_state["ui_error_active"] = True
        st.error(
            "Every list failed extraction. Return to the lists screen and "
            "check the files or pasted text."
        )
        for child_id, reason in result.extraction_failures.items():
            st.warning(
                escape_streamlit_dollars(
                    f"{_child_display_label(child_id, child_labels)}: {reason}"
                )
            )
        if st.button("Return to lists"):
            navigate_back_to_screen(st.session_state, "lists")
            st.rerun()
        return

    valid_interrupt_ids = {
        interrupt.interrupt_id
        for interrupt in _all_interrupts(result.approval_batch)
    }
    st.session_state["approval_outcomes"] = {
        interrupt_id: outcome
        for interrupt_id, outcome in st.session_state[
            "approval_outcomes"
        ].items()
        if interrupt_id in valid_interrupt_ids
    }
    unresolved = valid_interrupt_ids.difference(
        st.session_state["approval_outcomes"]
    )
    st.session_state["screen"] = (
        "approval" if unresolved else "summary"
    )
    st.session_state["progress_substep"] = (
        "reviewing decisions"
        if unresolved
        else "showing the final shopping plan"
    )
    st.session_state["ui_error_active"] = bool(
        result.extraction_failures
    )
    st.rerun()


def _render_working(st: Any) -> None:
    intake = st.session_state["intake"]
    list_inputs = st.session_state["list_inputs"]
    if intake is None or not list_inputs:
        st.session_state["ui_error_active"] = True
        st.error("Session setup or supply lists are missing.")
        if st.button("Return to lists"):
            navigate_back_to_screen(st.session_state, "lists")
            st.rerun()
        return
    child_labels = {
        child["child_id"]: child["label"]
        for child in intake["children"]
    }
    cached_result: PipelineResult | None = st.session_state["result"]
    if cached_result is not None:
        _route_pipeline_result(st, cached_result, child_labels)
        return

    st.session_state.setdefault("document_structures", {})
    st.session_state.setdefault("document_selections", {})
    st.session_state.setdefault("structure_errors", {})
    st.session_state.setdefault("structure_cache_ready", False)

    if not st.session_state["structure_cache_ready"]:
        st.header("Finding the right part of each list")
        with st.status(
            "Looking at grades, teachers, and document sections",
            expanded=True,
        ) as status:
            status.write(
                "Checking the document layout before extracting supply items."
            )

            def structure_progress(
                stage: str,
                completed: int,
                total: int,
                detail: str,
            ) -> None:
                del stage, detail
                message = (
                    f"Found the layout of {completed} of {total} lists"
                )
                status.update(label=message)
                status.write(message)

            structures, structure_errors = _inspect_list_inputs(
                list_inputs,
                intake["children"],
                demo_mode=bool(intake.get("demo_mode")),
                progress_callback=structure_progress,
            )
            selections: dict[str, DocumentSelection] = {}
            for child_id, structure in structures.items():
                child = next(
                    child
                    for child in intake["children"]
                    if str(child["child_id"]) == child_id
                )
                resolution = resolve_document_sections(
                    structure,
                    str(child["grade"]),
                )
                if (
                    resolution.has_grade_match
                    and not resolution.needs_parent_screen
                ):
                    choice = build_resolved_section_choice(resolution)
                    selections[child_id] = choice_to_document_selection(
                        structure,
                        choice,
                    )
            st.session_state["document_structures"] = structures
            st.session_state["document_selections"] = selections
            st.session_state["structure_errors"] = structure_errors
            st.session_state["structure_cache_ready"] = True
            st.session_state["ui_error_active"] = bool(structure_errors)
            status.update(
                label="Document sections identified",
                state="complete",
            )

    structures = st.session_state["document_structures"]
    selections = st.session_state["document_selections"]
    needs_section_choice = any(
        resolve_document_sections(
            structure,
            str(
                next(
                    child["grade"]
                    for child in intake["children"]
                    if str(child["child_id"]) == child_id
                )
            ),
        ).needs_parent_screen
        and child_id not in selections
        for child_id, structure in structures.items()
    )
    if needs_section_choice:
        st.session_state["progress_substep"] = (
            "choose the document section"
        )
        st.session_state["screen"] = "sections"
        st.rerun()
        return

    if not st.session_state["extraction_cache_ready"]:
        st.header("Extracting the lists")
        with st.status("Extracting the lists", expanded=True) as status:
            status.write(
                "Finding the items, quantities, and details on each list."
            )

            def extraction_progress(
                stage: str,
                completed: int,
                total: int,
                detail: str,
            ) -> None:
                del detail
                message = progress_narration(stage, completed, total)
                status.update(label=message)
                status.write(message)

            readable_inputs = tuple(
                list_input
                for list_input in list_inputs
                if list_input.child_id in structures
            )
            extractions, extraction_errors = _extract_list_inputs(
                readable_inputs,
                extractor=(
                    extract_demo_document
                    if bool(intake.get("demo_mode"))
                    else extract_document
                ),
                selections=selections,
                progress_callback=extraction_progress,
            )
            extraction_errors = {
                **st.session_state["structure_errors"],
                **extraction_errors,
            }
            merged_extractions, merge_result = consolidate_extractions(
                extractions
            )
            st.session_state["unmerged_extracted_lists"] = extractions
            st.session_state["extracted_lists"] = merged_extractions
            st.session_state["requirement_merge_result"] = merge_result
            st.session_state["requirement_merge_resolved"] = (
                not bool(
                    merge_result.interrupts
                    or merge_result.constraint_interrupts
                )
            )
            st.session_state["requirement_merge_choices"] = {}
            st.session_state["requirement_constraint_choices"] = {}
            st.session_state["requirement_variant_quantity_choices"] = {}
            st.session_state["requirement_merge_validation_errors"] = ()
            st.session_state["extraction_errors"] = extraction_errors
            st.session_state["extraction_cache_ready"] = True
            st.session_state["ui_error_active"] = bool(extraction_errors)
            status.update(
                label="The lists are ready",
                state="complete",
            )

    extractions = st.session_state["extracted_lists"]
    extraction_errors = st.session_state["extraction_errors"]
    merge_result = st.session_state.get("requirement_merge_result")
    if (
        isinstance(merge_result, RequirementMergeResult)
        and (
            merge_result.interrupts
            or merge_result.constraint_interrupts
        )
        and not st.session_state["requirement_merge_resolved"]
    ):
        st.session_state["progress_substep"] = (
            "resolving repeated item quantities"
        )
        st.session_state["screen"] = "requirement_merge"
        st.rerun()
        return
    identity_warnings = detect_list_identity_warnings(
        extractions,
        intake["children"],
        structures,
    )
    if (
        identity_warnings
        and not st.session_state["list_identity_confirmed"]
    ):
        _render_list_identity_warnings(st, identity_warnings)
        return

    if not extractions:
        st.session_state["ui_error_active"] = True
        st.error(
            "No readable list content was extracted. Return to the lists "
            "screen and check the files or pasted text."
        )
        for child_id, error in extraction_errors.items():
            st.warning(
                escape_streamlit_dollars(
                    f"{child_labels.get(child_id, child_id)}: {error}"
                )
            )
        if st.button("Return to lists"):
            navigate_back_to_screen(st.session_state, "lists")
            st.rerun()
        return

    if not st.session_state["organized_list_confirmed"]:
        if not st.session_state["review_items"]:
            st.session_state["review_items"] = organize_extractions(
                dict(extractions)
            )
        st.session_state["progress_substep"] = "checking what the lists said"
        st.session_state["screen"] = "review"
        st.rerun()
        return

    st.header("Building your shopping plan")
    with st.status(
        "Combining the lists before shopping",
        expanded=True,
    ) as status:
        status.write("Combining shared items across the lists.")
        last_detail = [""]

        def cart_progress(
            stage: str,
            completed: int,
            total: int,
            detail: str,
        ) -> None:
            del detail
            message = progress_narration(stage, completed, total)
            if message != last_detail[0]:
                status.update(label=message)
                status.write(message)
                last_detail[0] = message

        offers = _active_catalog_offers(
            frozenset(st.session_state["stockout_skus"]),
            st.session_state["price_overrides"],
        )
        try:
            result = _run_pipeline_from_cached_extractions(
                _pipeline_session(intake),
                list_inputs,
                extractions,
                extraction_errors,
                offers=offers,
                suitability_judge=(
                    StructuredSuitabilityJudge()
                    if bool(intake.get("demo_mode"))
                    else None
                ),
                progress_callback=cart_progress,
            )
        except Exception as error:
            st.session_state["ui_error_active"] = True
            status.update(label="Cart build stopped", state="error")
            st.error(
                escape_streamlit_dollars(
                    "The cart could not be built. Your setup and lists are "
                    "still available. Technical detail: "
                    f"{type(error).__name__}: {error}"
                )
            )
            if st.button("Return to lists"):
                navigate_back_to_screen(st.session_state, "lists")
                st.rerun()
            return
        st.session_state["ui_error_active"] = bool(
            result.extraction_failures
        )
        status.update(label="Your shopping plan is ready", state="complete")
    _route_pipeline_result(st, result, child_labels)


def _legacy_render_approval(st: Any) -> None:
    result: PipelineResult | None = st.session_state["result"]
    intake = st.session_state["intake"]
    if result is None:
        st.session_state["screen"] = "working"
        st.rerun()
    if intake is None:
        st.session_state["screen"] = "intake"
        st.rerun()
    child_labels = {
        child["child_id"]: child["label"]
        for child in intake["children"]
    }
    stores = tuple(load_stores())
    offers = _active_catalog_offers(
        frozenset(st.session_state["stockout_skus"]),
        st.session_state["price_overrides"],
    )
    presentations = build_approval_presentations(
        result,
        offers,
        stores,
        child_labels,
    )
    st.header("Review the decisions")
    st.write(
        "Everything needing your input is collected here. "
        "The recommended choice appears first."
    )
    selections: dict[str, ApprovalDisplayOption] = {}
    with st.form("approval_decisions", border=False):
        for index, presentation in enumerate(presentations):
            interrupt = presentation.interrupt
            with st.container(border=True):
                st.subheader(
                    escape_streamlit_dollars(
                        f"{index + 1}. {presentation.heading}"
                    )
                )
                st.caption(
                    escape_streamlit_dollars(
                        "Affects: "
                        f"{_join_names(presentation.affected_children)}"
                    )
                )
                st.write(escape_streamlit_dollars(presentation.message))
                st.info(
                    escape_streamlit_dollars(
                        f"Recommendation: {presentation.recommendation}"
                    )
                )
                selections[interrupt.interrupt_id] = st.radio(
                    "Choose one",
                    presentation.options,
                    index=approval_default_index(
                        presentation.options
                    ),
                    format_func=approval_option_label,
                    captions=tuple(
                        approval_option_caption(option)
                        for option in presentation.options
                    ),
                    key=f"approval_{interrupt.interrupt_id}",
                )
        submitted = st.form_submit_button(
            "Save decisions and continue",
            type="primary",
            use_container_width=True,
        )
    if submitted:
        outcomes = dict(st.session_state["approval_outcomes"])
        response_log = DecisionLog(
            f"{result.session.session_id}-parent"
        )
        for presentation in presentations:
            interrupt = presentation.interrupt
            alternative = selections[interrupt.interrupt_id]
            outcomes[interrupt.interrupt_id] = alternative.alternative_id
            response_log.record_approval_response(
                (
                    f"{presentation.heading}: "
                    f"{alternative.label} "
                    f"({format_cost_delta(alternative.cost_delta_cents)})."
                ),
                affected_lines=(
                    alternative.affected_lines
                    or interrupt.affected_lines
                ),
            )
        st.session_state["approval_outcomes"] = outcomes
        st.session_state["parent_decisions"] = (
            tuple(st.session_state["parent_decisions"])
            + response_log.entries
        )
        st.session_state["screen"] = "summary"
        st.rerun()


def _budget_action_label(
    action: BudgetAction,
    offers_by_sku: Mapping[str, Offer],
    child_labels: Mapping[str, str],
) -> str:
    """Build a parent-facing checkbox label from a precomputed action."""

    children = tuple(
        _child_display_label(child_id, child_labels)
        for child_id in action.allocated_to
    )
    item_name = _item_display_name(action.canonical_item)
    saving = format_money(action.landed_saving_cents)
    if action.kind == "substitute" and action.replacement_sku is not None:
        offer = offers_by_sku.get(action.replacement_sku)
        product_name = offer.title if offer is not None else item_name
        return (
            f"Use {product_name} for {item_name} — "
            f"{_join_names(children)} (saves {saving} landed)"
        )
    return (
        f"Do not buy {item_name} for {_join_names(children)} — "
        f"I will source it myself (saves {saving} landed)"
    )


def _budget_action_caption(action: BudgetAction) -> str:
    """Explain the checkbox delta, including threshold interactions."""

    explanation = _landed_delta_explanation(
        action.landed_delta_cents,
        action.item_subtotal_delta_cents,
        action.tax_delta_cents,
        action.fulfillment_fee_delta_cents,
    )
    if action.kind == "omit":
        return (
            "Leaves a required item unmet by parent choice. "
            f"{explanation}"
        )
    return explanation


def _evaluate_budget_action_margin(
    result: PipelineResult,
    selected_action_ids: Sequence[str],
    action: BudgetAction,
    offers: Sequence[Offer],
    stores: Sequence[Store],
) -> tuple[int, str]:
    """Return one action's exact marginal saving on the current selection."""

    if result.budget_analysis is None:
        return action.landed_saving_cents, _budget_action_caption(action)
    selected = set(selected_action_ids)
    with_action = tuple(
        candidate.action_id
        for candidate in result.budget_analysis.actions
        if candidate.action_id in selected or candidate.action_id == action.action_id
    )
    without_action = tuple(
        candidate.action_id
        for candidate in result.budget_analysis.actions
        if candidate.action_id in selected and candidate.action_id != action.action_id
    )
    with_evaluation = evaluate_budget_actions(
        result.budget_analysis,
        with_action,
        result.proposed_cart,
        result.matches,
        result.purchase_needs,
        offers,
        stores,
        _optimization_config(result),
    )
    without_evaluation = evaluate_budget_actions(
        result.budget_analysis,
        without_action,
        result.proposed_cart,
        result.matches,
        result.purchase_needs,
        offers,
        stores,
        _optimization_config(result),
    )
    with_item, with_tax, with_fees = _combined_costs(
        with_evaluation.optimization
    )
    without_item, without_tax, without_fees = _combined_costs(
        without_evaluation.optimization
    )
    delta = (
        with_evaluation.landed_cost_cents
        - without_evaluation.landed_cost_cents
    )
    explanation = _landed_delta_explanation(
        delta,
        with_item - without_item,
        with_tax - without_tax,
        with_fees - without_fees,
    )
    if action.kind == "omit":
        explanation = (
            "Leaves a required item unmet by parent choice. "
            f"{explanation}"
        )
    return max(-delta, 0), explanation


def _reprice_budget_strategies(
    presentation: ApprovalDisplayDecision,
    result: PipelineResult,
    current_evaluation: BudgetSelectionEvaluation,
    offers: Sequence[Offer],
    stores: Sequence[Store],
) -> ApprovalDisplayDecision:
    """Price every whole strategy against the current checkbox plan."""

    if result.budget_analysis is None:
        return presentation
    repriced = []
    for option in presentation.options:
        action_ids = (
            current_evaluation.selected_action_ids
            if option.alternative_id.endswith("-custom")
            else option.budget_action_ids
        )
        evaluation = evaluate_budget_actions(
            result.budget_analysis,
            action_ids,
            result.proposed_cart,
            result.matches,
            result.purchase_needs,
            offers,
            stores,
            _optimization_config(result),
        )
        delta = (
            evaluation.landed_cost_cents
            - current_evaluation.landed_cost_cents
        )
        status = (
            f"{evaluation.unmet_item_count} required "
            f"{'item' if evaluation.unmet_item_count == 1 else 'items'} "
            "would be unmet."
            if evaluation.unmet_item_count
            else "All required items remain covered."
        )
        repriced.append(
            replace(
                option,
                cost_delta_cents=delta,
                explanation=(
                    "Resulting landed cost: "
                    f"{format_money(evaluation.landed_cost_cents)}. "
                    f"{status}"
                ),
            )
        )
    return replace(presentation, options=tuple(repriced))


def budget_strategy_checkbox_values(
    strategy: ApprovalDisplayOption,
    actions: Sequence[BudgetAction],
) -> Mapping[str, bool]:
    """Return the exact Tier-2 checkbox state for one Tier-1 strategy."""

    selected = frozenset(strategy.budget_action_ids)
    return {
        action.action_id: action.action_id in selected
        for action in actions
    }


OTHER_MATCHES_OPTION_ID = "__other_matches__"


def _approval_selection_key(
    generation: int,
    interrupt_id: str,
) -> str:
    return f"approval_selection_{generation}_{interrupt_id}"


def _initialize_approval_selection(
    st: Any,
    generation: int,
    presentation: ApprovalDisplayDecision,
) -> str:
    """Initialize one stable selected option ID before widgets render."""

    key = _approval_selection_key(
        generation,
        presentation.interrupt.interrupt_id,
    )
    valid_ids = tuple(
        option.alternative_id for option in presentation.options
    )
    selected_id = st.session_state.get(key)
    if selected_id not in valid_ids:
        selected_id = presentation.options[
            approval_default_index(presentation.options)
        ].alternative_id
        st.session_state[key] = selected_id
    return str(selected_id)


def _render_contextual_approval_radio(
    st: Any,
    generation: int,
    result: PipelineResult,
    presentation: ApprovalDisplayDecision,
    offers: Sequence[Offer],
) -> ApprovalDisplayOption:
    """Render meaningful choices first and keep secondary matches collapsed."""

    primary, other = group_approval_options(
        result,
        presentation,
        offers,
    )
    all_by_id = {
        option.alternative_id: option for option in presentation.options
    }
    canonical_key = _approval_selection_key(
        generation,
        presentation.interrupt.interrupt_id,
    )
    selected_id = str(st.session_state[canonical_key])
    primary_key = f"{canonical_key}_primary"
    other_key = f"{canonical_key}_other"
    primary_ids = tuple(option.alternative_id for option in primary)
    radio_ids = primary_ids + (
        (OTHER_MATCHES_OPTION_ID,) if other else ()
    )
    desired_primary = (
        selected_id
        if selected_id in primary_ids
        else OTHER_MATCHES_OPTION_ID
    )
    if st.session_state.get(primary_key) not in radio_ids:
        st.session_state[primary_key] = desired_primary
    elif (
        selected_id in primary_ids
        and st.session_state.get(primary_key) != selected_id
    ):
        st.session_state[primary_key] = selected_id
    elif (
        selected_id not in primary_ids
        and other
        and st.session_state.get(primary_key) != OTHER_MATCHES_OPTION_ID
    ):
        st.session_state[primary_key] = OTHER_MATCHES_OPTION_ID

    def select_primary() -> None:
        selected = st.session_state[primary_key]
        if selected != OTHER_MATCHES_OPTION_ID:
            st.session_state[canonical_key] = selected

    primary_labels = dict(all_by_id)
    primary_choice = st.radio(
        "Choose one",
        radio_ids,
        format_func=lambda option_id: (
            "Choose from other matches"
            if option_id == OTHER_MATCHES_OPTION_ID
            else approval_option_label(primary_labels[option_id])
        ),
        captions=tuple(
            (
                "Additional stocked products with the same requested "
                "attribute value."
                if option_id == OTHER_MATCHES_OPTION_ID
                else approval_option_caption(primary_labels[option_id])
            )
            for option_id in radio_ids
        ),
        key=primary_key,
        on_change=select_primary,
    )
    if primary_choice != OTHER_MATCHES_OPTION_ID:
        selected_id = str(primary_choice)
        st.session_state[canonical_key] = selected_id
        return all_by_id[selected_id]

    other_ids = tuple(option.alternative_id for option in other)
    if st.session_state.get(other_key) not in other_ids:
        st.session_state[other_key] = (
            selected_id if selected_id in other_ids else other_ids[0]
        )

    def select_other() -> None:
        st.session_state[canonical_key] = st.session_state[other_key]

    with st.expander(
        f"Other matches ({len(other)})",
        expanded=True,
    ):
        other_choice = st.radio(
            "Choose another stocked match",
            other_ids,
            format_func=lambda option_id: approval_option_label(
                all_by_id[option_id]
            ),
            captions=tuple(
                approval_option_caption(all_by_id[option_id])
                for option_id in other_ids
            ),
            key=other_key,
            on_change=select_other,
        )
    st.session_state[canonical_key] = other_choice
    return all_by_id[other_choice]


def _render_approval(st: Any) -> None:
    """Render cached decisions and the exact budget-plan builder."""

    result: PipelineResult | None = st.session_state["result"]
    intake = st.session_state["intake"]
    if result is None:
        st.session_state["screen"] = "working"
        st.rerun()
        return
    if intake is None:
        st.session_state["screen"] = "intake"
        st.rerun()
        return

    child_labels = {
        child["child_id"]: child["label"]
        for child in intake["children"]
    }
    stores = tuple(load_stores())
    offers = _active_catalog_offers(
        frozenset(st.session_state["stockout_skus"]),
        st.session_state["price_overrides"],
    )
    cache = st.session_state.get("approval_presentations_cache")
    if cache is None:
        cache = build_approval_presentations(
            result,
            offers,
            stores,
            child_labels,
        )
        st.session_state["approval_presentations_cache"] = cache
    presentations = tuple(
        sorted(
            tuple(cache),
            key=lambda presentation: (
                presentation.interrupt.kind != "budget_exceeded",
                presentation.interrupt.interrupt_id,
            ),
        )
    )
    preserved_replan_ids = frozenset(
        st.session_state["replan_preserved_approval_ids"]
    )
    preserved_replan_budget_ids = frozenset(
        st.session_state["replan_preserved_budget_action_ids"]
    )
    generation = int(st.session_state["approval_generation"])
    offers_by_sku = {offer.sku: offer for offer in offers}

    budget_presentation = next(
        (
            presentation
            for presentation in presentations
            if presentation.interrupt.kind == "budget_exceeded"
        ),
        None,
    )
    budget_selected_ids: tuple[str, ...] = ()
    budget_evaluation: BudgetSelectionEvaluation | None = None
    budget_selection_error: str | None = None
    budget_strategy_key: str | None = None
    if (
        budget_presentation is not None
        and result.budget_analysis is not None
    ):
        interrupt_id = budget_presentation.interrupt.interrupt_id
        budget_strategy_key = (
            f"budget_strategy_{generation}_{interrupt_id}"
        )
        strategy_ids = tuple(
            option.alternative_id
            for option in budget_presentation.options
        )
        recommended_id = budget_presentation.options[
            approval_default_index(budget_presentation.options)
        ].alternative_id
        if st.session_state.get(budget_strategy_key) not in strategy_ids:
            st.session_state[budget_strategy_key] = recommended_id
        strategy_id = str(st.session_state[budget_strategy_key])
        strategy = next(
            option
            for option in budget_presentation.options
            if option.alternative_id == strategy_id
        )
        last_strategy_key = f"{budget_strategy_key}_last"
        last_strategy_id = st.session_state.get(last_strategy_key)
        if not strategy_id.endswith("-custom"):
            checkbox_values = budget_strategy_checkbox_values(
                strategy,
                result.budget_analysis.actions,
            )
            for action in result.budget_analysis.actions:
                checkbox_key = (
                    f"budget_action_{generation}_{action.action_id}"
                )
                st.session_state[checkbox_key] = checkbox_values[
                    action.action_id
                ]
        if last_strategy_id != strategy_id:
            st.session_state[last_strategy_key] = strategy_id
        budget_selected_ids = tuple(
            action.action_id
            for action in result.budget_analysis.actions
            if st.session_state.get(
                f"budget_action_{generation}_{action.action_id}",
                False,
            )
        )
        try:
            budget_evaluation = evaluate_budget_actions(
                result.budget_analysis,
                budget_selected_ids,
                result.proposed_cart,
                result.matches,
                result.purchase_needs,
                offers,
                stores,
                _optimization_config(result),
            )
        except ValueError as error:
            budget_selection_error = str(error)

    widget_outcomes = dict(st.session_state["approval_outcomes"])
    for presentation in presentations:
        if presentation.interrupt.kind == "budget_exceeded":
            continue
        key = _approval_selection_key(
            generation,
            presentation.interrupt.interrupt_id,
        )
        saved_outcome = widget_outcomes.get(
            presentation.interrupt.interrupt_id
        )
        valid_ids = {
            option.alternative_id for option in presentation.options
        }
        if (
            key not in st.session_state
            and saved_outcome in valid_ids
        ):
            st.session_state[key] = saved_outcome
        widget_outcomes[presentation.interrupt.interrupt_id] = (
            _initialize_approval_selection(
                st,
                generation,
                presentation,
            )
        )
    effective_budget_ids = (
        budget_selected_ids if budget_evaluation is not None else ()
    )
    selection_state = reconcile_interrupt_selections(
        presentations,
        result.budget_analysis,
        effective_budget_ids,
        widget_outcomes,
        offers,
    )
    for interrupt_id in selection_state.resolutions:
        st.session_state.pop(
            _approval_selection_key(generation, interrupt_id),
            None,
        )
    current_optimization = _apply_approval_outcomes(
        result.proposed_cart,
        result.matches,
        result.purchase_needs,
        presentations,
        selection_state.active_outcomes,
        offers,
        stores,
        _optimization_config(result),
        budget_analysis=result.budget_analysis,
        budget_action_ids=effective_budget_ids,
        precomputed_budget_optimization=(
            budget_evaluation.optimization
            if (
                budget_evaluation is not None
                and not selection_state.active_outcomes
            )
            else None
        ),
    )

    st.header("Decisions to review")
    if st.session_state.get("catalog_change_notice"):
        st.info(
            escape_streamlit_dollars(
                str(st.session_state["catalog_change_notice"])
            )
        )
    approval_cart_skus = tuple(
        dict.fromkeys(
            line.sku
            for plan in _plans(result.proposed_cart)
            for line in plan.lines
        )
    )
    if approval_cart_skus:
        with st.expander("Test a stock change before deciding"):
            st.write(
                "Mark a selected product out of stock. The list reading is "
                "kept, the cart is rebuilt, and these decisions are refreshed."
            )
            approval_stockout_sku = st.selectbox(
                "Product to mark out of stock",
                approval_cart_skus,
                format_func=lambda sku: escape_streamlit_dollars(
                    _catalog_product_label(sku, offers, stores)
                ),
                key="approval_catalog_stockout_sku",
            )
            if st.button(
                "Mark out of stock and re-plan",
                key="approval_apply_catalog_stockout",
            ):
                _apply_stockout_replan(
                    st,
                    result,
                    approval_stockout_sku,
                    offers,
                    stores,
                    child_labels,
                )
                st.rerun()
    st.write(
        "All required decisions are collected here. "
        "The recommended choice is selected by default."
    )
    selections: dict[str, ApprovalDisplayOption] = {}

    for index, presentation in enumerate(presentations):
        interrupt = presentation.interrupt
        with st.container(border=True):
            st.subheader(
                escape_streamlit_dollars(
                    f"{index + 1}. {presentation.heading}"
                )
            )
            st.caption(
                escape_streamlit_dollars(
                    "Affects: "
                    f"{_join_names(presentation.affected_children)}"
                )
            )
            if interrupt.interrupt_id in preserved_replan_ids:
                preserved_option_id = selection_state.active_outcomes.get(
                    interrupt.interrupt_id
                )
                preserved_option = next(
                    (
                        option
                        for option in _all_presentation_options(presentation)
                        if option.alternative_id == preserved_option_id
                    ),
                    None,
                )
                if preserved_option is not None:
                    selections[interrupt.interrupt_id] = preserved_option
                    st.info(
                        "Your earlier decision still applies after the "
                        "catalog change. No new response is needed."
                    )
                    st.radio(
                        "Preserved decision",
                        (approval_option_label(preserved_option),),
                        captions=(
                            approval_option_caption(preserved_option),
                        ),
                        disabled=True,
                        key=(
                            f"preserved_{generation}_"
                            f"{interrupt.interrupt_id}"
                        ),
                    )
                    continue
            if (
                interrupt.kind == "budget_exceeded"
                and result.budget_analysis is not None
            ):
                if budget_evaluation is None or budget_strategy_key is None:
                    st.error(
                        escape_streamlit_dollars(
                            budget_selection_error
                            or "The budget choices could not be evaluated."
                        )
                    )
                    continue
                presentation = _reprice_budget_strategies(
                    presentation,
                    result,
                    budget_evaluation,
                    offers,
                    stores,
                )
                current_variance = (
                    result.budget_analysis.budget_cents
                    - budget_evaluation.landed_cost_cents
                )
                current_status = (
                    f"{format_money(current_variance)} under budget"
                    if current_variance >= 0
                    else (
                        f"{format_money(abs(current_variance))} over budget"
                    )
                )
                st.write(
                    escape_streamlit_dollars(
                        "Current selected-plan landed cost: "
                        f"{format_money(budget_evaluation.landed_cost_cents)}; "
                        f"{current_status}; "
                        f"{budget_evaluation.unmet_item_count} required "
                        f"{'item' if budget_evaluation.unmet_item_count == 1 else 'items'} "
                        "would be unmet."
                    )
                )
                st.markdown("#### Tier 1 — choose a whole plan")
                strategies_by_id = {
                    option.alternative_id: option
                    for option in presentation.options
                }
                strategy_id = st.radio(
                    "Choose one strategy",
                    tuple(strategies_by_id),
                    format_func=lambda option_id: approval_option_label(
                        strategies_by_id[option_id]
                    ),
                    captions=tuple(
                        approval_option_caption(option)
                        for option in presentation.options
                    ),
                    key=budget_strategy_key,
                )
                selections[interrupt.interrupt_id] = (
                    strategies_by_id[strategy_id]
                )
                custom_option = next(
                    option
                    for option in presentation.options
                    if option.alternative_id.endswith("-custom")
                )

                def mark_budget_as_custom() -> None:
                    st.session_state[budget_strategy_key] = (
                        custom_option.alternative_id
                    )
                    st.session_state[f"{budget_strategy_key}_last"] = (
                        custom_option.alternative_id
                    )

                st.markdown("#### Tier 2 — adjust the plan")
                if not result.budget_analysis.substitution_actions:
                    st.caption(
                        "No cheaper stocked substitutions are available."
                    )
                else:
                    st.write("Cheaper substitutions")
                    for action in result.budget_analysis.substitution_actions:
                        checkbox_key = (
                            f"budget_action_{generation}_{action.action_id}"
                        )
                        marginal_saving, marginal_caption = (
                            _evaluate_budget_action_margin(
                                result,
                                budget_selected_ids,
                                action,
                                offers,
                                stores,
                            )
                        )
                        label = _budget_action_label(
                            action,
                            offers_by_sku,
                            child_labels,
                        )
                        label = re.sub(
                            r"\(saves \$[\d,.]+ landed\)$",
                            (
                                "(saves "
                                f"{format_money(marginal_saving)} landed)"
                            ),
                            label,
                        )
                        st.checkbox(
                            escape_streamlit_dollars(
                                label
                            ),
                            key=checkbox_key,
                            on_change=mark_budget_as_custom,
                        )
                        st.caption(
                            escape_streamlit_dollars(
                                marginal_caption
                            )
                        )

                st.write("Required items you could source yourself")
                for action in result.budget_analysis.omission_actions:
                    checkbox_key = (
                        f"budget_action_{generation}_{action.action_id}"
                    )
                    marginal_saving, marginal_caption = (
                        _evaluate_budget_action_margin(
                            result,
                            budget_selected_ids,
                            action,
                            offers,
                            stores,
                        )
                    )
                    label = _budget_action_label(
                        action,
                        offers_by_sku,
                        child_labels,
                    )
                    label = re.sub(
                        r"\(saves \$[\d,.]+ landed\)$",
                        (
                            "(saves "
                            f"{format_money(marginal_saving)} landed)"
                        ),
                        label,
                    )
                    st.checkbox(
                        escape_streamlit_dollars(
                            label
                        ),
                        key=checkbox_key,
                        on_change=mark_budget_as_custom,
                    )
                    st.caption(
                        escape_streamlit_dollars(
                            marginal_caption
                        )
                    )

                columns = st.columns(3)
                columns[0].metric(
                    "Landed cost",
                    format_streamlit_money(
                        budget_evaluation.landed_cost_cents
                    ),
                )
                variance_label = (
                    "Under budget"
                    if budget_evaluation.reaches_budget
                    else "Still over"
                )
                columns[1].metric(
                    variance_label,
                    format_streamlit_money(
                        abs(budget_evaluation.budget_variance_cents)
                    ),
                )
                columns[2].metric(
                    "Required items unmet",
                    str(budget_evaluation.unmet_item_count),
                )
                if budget_evaluation.reaches_budget:
                    st.success(
                        "This selection reaches the entered budget."
                    )
                else:
                    st.warning(
                        escape_streamlit_dollars(
                            "This selection is still "
                            f"{format_money(abs(budget_evaluation.budget_variance_cents))} "
                            "over budget."
                        )
                    )
                continue

            resolution = selection_state.resolutions.get(
                interrupt.interrupt_id
            )
            if resolution is not None:
                st.info(resolution.message)
                st.radio(
                    "Decision status",
                    ("No separate decision is needed",),
                    disabled=True,
                    key=(
                        f"resolved_{generation}_{interrupt.interrupt_id}"
                    ),
                )
                continue
            st.write(escape_streamlit_dollars(presentation.message))
            presentation = _reprice_approval_presentation(
                presentation,
                result,
                presentations,
                selection_state.active_outcomes,
                effective_budget_ids,
                current_optimization,
                offers,
                stores,
            )
            st.info(
                escape_streamlit_dollars(
                    f"Recommendation: {presentation.recommendation}"
                )
            )
            selections[interrupt.interrupt_id] = (
                _render_contextual_approval_radio(
                    st,
                    generation,
                    result,
                    presentation,
                    offers,
                )
            )

    submitted = st.button(
        "Save decisions and continue",
        type="primary",
        use_container_width=True,
        disabled=budget_selection_error is not None,
    )
    if not submitted:
        return

    outcomes: dict[str, str] = {
        interrupt_id: outcome
        for interrupt_id, outcome in selection_state.active_outcomes.items()
        if interrupt_id in preserved_replan_ids
    }
    response_log = DecisionLog(f"{result.session.session_id}-parent")
    for presentation in presentations:
        interrupt = presentation.interrupt
        if (
            interrupt.interrupt_id in selection_state.resolutions
            or interrupt.interrupt_id in preserved_replan_ids
        ):
            continue
        alternative = selections[interrupt.interrupt_id]
        outcomes[interrupt.interrupt_id] = alternative.alternative_id
        response_log.record_approval_response(
            (
                f"{presentation.heading}: {alternative.label} "
                f"({format_cost_delta(alternative.cost_delta_cents)})."
            ),
            affected_lines=(
                alternative.affected_lines or interrupt.affected_lines
            ),
        )
    for action_id in budget_selected_ids:
        if action_id in preserved_replan_budget_ids:
            continue
        action = (
            result.budget_analysis.actions_by_id[action_id]
            if result.budget_analysis is not None
            else None
        )
        if action is None:
            continue
        if action.kind == "omit":
            rationale = (
                "Parent chose to source "
                f"{_item_display_name(action.canonical_item)} separately; "
                "the required item remains unmet in this cart."
            )
        else:
            offer = (
                offers_by_sku.get(action.replacement_sku)
                if action.replacement_sku is not None
                else None
            )
            rationale = (
                "Parent chose the cheaper "
                f"{offer.title if offer is not None else _item_display_name(action.canonical_item)} "
                f"for {_item_display_name(action.canonical_item)}."
            )
        response_log.record_approval_response(
            rationale,
            affected_lines=action.affected_line_ids,
        )

    try:
        approved_optimization = _apply_approval_outcomes(
            result.proposed_cart,
            result.matches,
            result.purchase_needs,
            presentations,
            outcomes,
            offers,
            stores,
            _optimization_config(result),
            budget_analysis=result.budget_analysis,
            budget_action_ids=budget_selected_ids,
            precomputed_budget_optimization=(
                None
                if budget_evaluation is None
                else budget_evaluation.optimization
            ),
        )
    except ValueError as error:
        st.error(escape_streamlit_dollars(str(error)))
        return
    contradictions = approval_selection_contradictions(
        approved_optimization,
        presentations,
        outcomes,
    )
    if contradictions:
        st.error(
            "The selected decisions do not describe one consistent plan. "
            "Review the affected choices before continuing."
        )
        return

    budget_increase_selected = budget_increase_was_selected(
        presentations,
        selections,
    )
    if budget_increase_selected:
        result, approved_optimization = authorize_budget_increase(
            result,
            approved_optimization,
            response_log,
        )
        updated_intake = dict(intake)
        updated_intake["budget_total"] = result.session.budget_total
        st.session_state["intake"] = updated_intake
        st.session_state["result"] = result

    st.session_state["approval_outcomes"] = outcomes
    st.session_state["resolved_interrupts"] = {
        interrupt_id: resolution.message
        for interrupt_id, resolution in (
            selection_state.resolutions.items()
        )
    }
    st.session_state["budget_action_ids"] = budget_selected_ids
    st.session_state["approved_optimization"] = approved_optimization
    st.session_state["replan_preserved_approval_ids"] = frozenset()
    st.session_state["replan_preserved_budget_action_ids"] = frozenset()
    st.session_state["parent_decisions"] = (
        tuple(st.session_state["parent_decisions"]) + response_log.entries
    )
    st.session_state["progress_substep"] = "showing the final shopping plan"
    st.session_state["screen"] = "summary"
    st.rerun()


def _effective_cart(
    st: Any,
    result: PipelineResult,
    presentations: Sequence[ApprovalDisplayDecision],
    offers: Sequence[Offer],
    stores: Sequence[Store],
) -> tuple[OptimizationResult, MatchResult]:
    cached_approved = st.session_state.get("approved_optimization")
    if cached_approved is not None:
        return cached_approved, result.matches

    return (
        _apply_approval_outcomes(
            result.proposed_cart,
            result.matches,
            result.purchase_needs,
            presentations,
            st.session_state["approval_outcomes"],
            offers,
            stores,
            _optimization_config(result),
            budget_analysis=result.budget_analysis,
            budget_action_ids=st.session_state["budget_action_ids"],
        ),
        result.matches,
    )


def _render_cost_summary(
    st: Any,
    optimization: OptimizationResult,
) -> None:
    item_subtotal, tax, fees = _combined_costs(optimization)
    columns = st.columns(4)
    columns[0].metric(
        "Item subtotal",
        format_streamlit_money(item_subtotal),
    )
    columns[1].metric("Tax", format_streamlit_money(tax))
    columns[2].metric(
        "Fulfillment fees",
        format_streamlit_money(fees),
    )
    columns[3].metric(
        "Landed cost",
        format_streamlit_money(optimization.landed_cost),
    )


def _render_budget_status(
    st: Any,
    optimization: OptimizationResult,
    budget_cents: int,
) -> None:
    """Lead the summary with the effective landed-cost budget status."""

    variance = budget_cents - optimization.landed_cost
    if variance >= 0:
        st.success(
            f"Budget remaining: {format_streamlit_money(variance)}"
        )
    else:
        st.error(
            f"Budget shortfall: {format_streamlit_money(abs(variance))}"
        )


def _render_store_breakdown(
    st: Any,
    optimization: OptimizationResult,
    matches: MatchResult,
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
) -> None:
    stores_by_id = {store.store_id: store for store in stores}
    for plan in _plans(optimization):
        for order in plan.store_orders:
            store = stores_by_id.get(order.store_id)
            store_name = store.name if store else "Unknown store"
            with st.container(border=True):
                st.markdown(
                    escape_streamlit_dollars(
                        (
                            f"#### {store_name} · "
                            f"{order.fulfillment_method.title()} · "
                            "Landed cost "
                            f"{format_money(order.landed_cost)}"
                        )
                    )
                )
                rows = []
                for line in order.lines:
                    allocations = ", ".join(
                        f"{_child_display_label(child_id, child_labels)}: {units}"
                        for child_id, units in line.allocated_to.items()
                    )
                    rows.append(
                        {
                            "Product": _product_name(line, matches),
                            "Packs": line.packs_purchased,
                            "Needed": line.units_needed,
                            "Bought": line.units_purchased,
                            "For": allocations,
                            "Line cost": format_streamlit_money(
                                line.line_cost
                            ),
                        }
                    )
                st.table(escape_streamlit_data(rows))
                a, b, c, d = st.columns(4)
                a.metric(
                    "Item subtotal",
                    format_streamlit_money(order.item_subtotal),
                )
                b.metric("Tax", format_streamlit_money(order.tax))
                c.metric(
                    "Fulfillment fee",
                    format_streamlit_money(order.fulfillment_fee),
                )
                d.metric(
                    "Landed cost",
                    format_streamlit_money(order.landed_cost),
                )


def _render_per_child(
    st: Any,
    optimization: OptimizationResult,
    children: Sequence[Mapping[str, Any]],
    allocations: Mapping[str, int],
) -> None:
    item_costs: dict[str, int] = {}
    landed_costs: dict[str, int] = {}
    for plan in _plans(optimization):
        for child_id, amount in plan.per_child_item_costs.items():
            item_costs[child_id] = item_costs.get(child_id, 0) + amount
        for child_id, amount in plan.per_child_landed_costs.items():
            landed_costs[child_id] = landed_costs.get(child_id, 0) + amount
    rows = []
    for child in children:
        child_id = child["child_id"]
        row = {
            "Student": child["label"],
            "Grade": child["grade"],
            "Item subtotal": format_streamlit_money(
                item_costs.get(child_id, 0)
            ),
            "Landed cost": format_streamlit_money(
                landed_costs.get(child_id, 0)
            ),
        }
        if child_id in allocations:
            variance = allocations[child_id] - landed_costs.get(child_id, 0)
            row["Budget variance"] = format_streamlit_money(variance)
        rows.append(row)
    st.table(escape_streamlit_data(rows))


def _render_substitutions(
    st: Any,
    optimization: OptimizationResult,
    matches: MatchResult,
    stores: Sequence[Store],
) -> None:
    stores_by_id = {store.store_id: store for store in stores}
    decision_rows = []
    package_rows = []
    routine_equivalent_count = 0
    for plan in _plans(optimization):
        for line in plan.lines:
            candidate = matches.candidate(
                line.source_requirement_ids,
                line.sku,
            )
            reasons = (
                candidate.substitution_reasons
                if candidate is not None
                else ()
            )
            if (
                line.substitution_type != SUBSTITUTION_NONE
                and frozenset(reasons) == {"different_unlocked_brand"}
                and line.approval_status != "approved"
            ):
                routine_equivalent_count += 1
                continue
            store = stores_by_id.get(line.store_id)
            if line.substitution_type != SUBSTITUTION_NONE:
                decision_rows.append(
                    {
                        "Product": _product_name(line, matches),
                        "Store": (
                            store.name
                            if store is not None
                            else "Unknown store"
                        ),
                        "Status": SUBSTITUTION_SEVERITY_LABELS.get(
                            line.substitution_type,
                            "Package choice",
                        ),
                        "Reason": (
                            "; ".join(
                                _substitution_reason(reason)
                                for reason in reasons
                            )
                            or "Package-size overage"
                        ),
                    }
                )
            if line.overage_units > 0:
                package_rows.append(
                    {
                        "Product": _product_name(line, matches),
                        "Packs": line.packs_purchased,
                        "Needed": line.units_needed,
                        "Bought": line.units_purchased,
                        "Extra units": line.overage_units,
                    }
                )
    if decision_rows:
        st.warning(
            "These products differ from the stated requirement or involved "
            "a parent decision."
        )
        st.table(escape_streamlit_data(decision_rows))
    if package_rows:
        st.write("Package choices")
        st.table(escape_streamlit_data(package_rows))
    if routine_equivalent_count:
        st.info(
            (
                f"{routine_equivalent_count} store-brand "
                f"{'equivalent was' if routine_equivalent_count == 1 else 'equivalents were'} "
                "chosen — no brand was specified."
            )
        )
    if not decision_rows and not package_rows and not routine_equivalent_count:
        st.write("No substitutions or package overage were needed.")


def _addon_checkbox_key(
    generation: int,
    requirement_id: str,
) -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", requirement_id)
    return f"addon_{generation}_{safe_id}"


def donation_offer_is_visible(
    result: PipelineResult,
    required_plan_is_complete: bool,
) -> bool:
    """Offer BR-05 donations after every required item is covered."""

    return (
        result.addon_proposal.eligible
        and required_plan_is_complete
    )


def _selected_addon_requirement_ids(
    st: Any,
    result: PipelineResult,
) -> tuple[str, ...]:
    """Initialize donations selected and read the current checkbox state."""

    generation = int(st.session_state["approval_generation"])
    token = f"{result.session.session_id}:{generation}"
    if st.session_state.get("addon_selection_token") != token:
        for item in result.addon_proposal.items:
            st.session_state[
                _addon_checkbox_key(generation, item.requirement_id)
            ] = True
        st.session_state["addon_selection_token"] = token
    return tuple(
        item.requirement_id
        for item in result.addon_proposal.items
        if st.session_state.get(
            _addon_checkbox_key(generation, item.requirement_id),
            True,
        )
    )


def _evaluate_selected_addons(
    result: PipelineResult,
    selected_requirement_ids: Sequence[str],
    base_optimization: OptimizationResult,
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
    budget_action_ids: Sequence[str],
    offers: Sequence[Offer],
    stores: Sequence[Store],
) -> AddOnSelectionEvaluation:
    """Evaluate donations without re-running extraction or matching."""

    omitted, forced = _selected_requirement_constraints(
        result,
        presentations,
        outcomes,
        budget_action_ids,
    )
    base_needs = tuple(
        need
        for need in result.purchase_needs
        if need.source_requirement_ids not in omitted
    )
    candidate_skus = dict(result.matches.candidate_skus_by_need)
    candidate_skus.update(forced)
    return evaluate_addon_selection(
        result.addon_proposal,
        selected_requirement_ids,
        base_optimization,
        base_needs,
        result.matches,
        offers,
        stores,
        _optimization_config(result),
        base_candidate_skus_by_need=candidate_skus,
    )


def _render_addons(
    st: Any,
    result: PipelineResult,
    child_labels: Mapping[str, str],
    selected_requirement_ids: Sequence[str] = (),
    evaluation: AddOnSelectionEvaluation | None = None,
    base_optimization: OptimizationResult | None = None,
    presentations: Sequence[ApprovalDisplayDecision] = (),
    offers: Sequence[Offer] = (),
    stores: Sequence[Store] = (),
) -> None:
    proposal = result.addon_proposal
    if not proposal.eligible:
        st.session_state["include_addons"] = False
        return
    if evaluation is None or base_optimization is None:
        raise ValueError(
            "Eligible donations require an exact selection evaluation."
        )
    if result.session.budget_total is None:
        st.success(
            "No set budget was selected, so the 90% threshold does not "
            "apply. Each donation below shows its exact added landed cost."
        )
    else:
        st.success(
            "The required-item cart is at or below 90% of the budget, so "
            "these donation items can be considered. Each amount below is "
            "recalculated against the current selection."
        )
    generation = int(st.session_state["approval_generation"])
    select_all, clear_all = st.columns(2)
    if select_all.button(
        "Select all donations",
        use_container_width=True,
    ):
        for item in proposal.items:
            st.session_state[
                _addon_checkbox_key(generation, item.requirement_id)
            ] = True
        st.rerun()
    if clear_all.button(
        "Clear all donations",
        use_container_width=True,
    ):
        for item in proposal.items:
            st.session_state[
                _addon_checkbox_key(generation, item.requirement_id)
            ] = False
        st.rerun()

    selected_set = frozenset(selected_requirement_ids)
    for item in proposal.items:
        without_ids = tuple(
            requirement_id
            for requirement_id in selected_requirement_ids
            if requirement_id != item.requirement_id
        )
        with_ids = tuple(
            dict.fromkeys(
                tuple(selected_requirement_ids) + (item.requirement_id,)
            )
        )
        without = (
            evaluation
            if item.requirement_id not in selected_set
            else _evaluate_selected_addons(
                result,
                without_ids,
                base_optimization,
                presentations,
                st.session_state["approval_outcomes"],
                st.session_state["budget_action_ids"],
                offers,
                stores,
            )
        )
        with_item = (
            evaluation
            if item.requirement_id in selected_set
            else _evaluate_selected_addons(
                result,
                with_ids,
                base_optimization,
                presentations,
                st.session_state["approval_outcomes"],
                st.session_state["budget_action_ids"],
                offers,
                stores,
            )
        )
        marginal = (
            with_item.resulting_landed_cost_cents
            - without.resulting_landed_cost_cents
        )
        marginal_text = (
            f"adds {format_money(marginal)} landed"
            if marginal > 0
            else (
                f"reduces landed cost by {format_money(abs(marginal))}"
                if marginal < 0
                else "no landed cost change"
            )
        )
        st.checkbox(
            escape_streamlit_dollars(
                f"{item.raw_text} — "
                f"{_child_display_label(item.child_id, child_labels)} — "
                f"{marginal_text}"
            ),
            key=_addon_checkbox_key(
                generation,
                item.requirement_id,
            ),
        )

    budget_cents = result.session.budget_total
    metric_columns = st.columns(2 if budget_cents is None else 3)
    left, middle = metric_columns[:2]
    left.metric(
        "Resulting landed cost",
        format_streamlit_money(
            evaluation.resulting_landed_cost_cents
        ),
    )
    middle.metric(
        "Added landed cost",
        format_streamlit_money(
            evaluation.incremental_landed_cost_cents
        ),
    )
    if budget_cents is not None:
        budget_remaining = (
            budget_cents - evaluation.resulting_landed_cost_cents
        )
        metric_columns[2].metric(
            (
                "Budget remaining"
                if budget_remaining >= 0
                else "Budget shortfall"
            ),
            format_streamlit_money(abs(budget_remaining)),
        )
    blockers = []
    if evaluation.review_requirement_ids:
        blockers.append("one or more add-ons needs review")
    if evaluation.gap_items:
        blockers.append("some add-ons are unavailable")
    if blockers:
        st.warning(
            "This add-on cannot be included yet because "
            + " and ".join(blockers)
            + "."
        )
        st.session_state["include_addons"] = False
        return
    st.session_state["include_addons"] = bool(selected_requirement_ids)


def _render_approvals_summary(
    st: Any,
    presentations: Sequence[ApprovalDisplayDecision],
) -> None:
    outcomes = st.session_state["approval_outcomes"]
    resolved = st.session_state.get("resolved_interrupts", {})
    if not presentations:
        st.write("No approvals were required.")
        return
    rows = []
    for presentation in presentations:
        interrupt = presentation.interrupt
        selected_id = outcomes.get(interrupt.interrupt_id)
        alternative = next(
            (
                option
                for option in presentation.options
                if option.alternative_id == selected_id
            ),
            None,
        )
        rows.append(
            {
                "Decision": presentation.heading,
                "Affects": _join_names(
                    (
                        alternative.affected_children
                        if alternative is not None
                        and alternative.affected_children
                        else presentation.affected_children
                    )
                ),
                "Outcome": (
                    alternative.label
                    if alternative
                    else resolved.get(interrupt.interrupt_id, "Pending")
                ),
            }
        )
    st.table(escape_streamlit_data(rows))


def _render_self_sourced_items(
    st: Any,
    selections: Sequence[SelfSourcedSelection],
) -> None:
    if not selections:
        return
    st.warning(
        "Required items are missing from this shopping plan. The items below "
        "are not included in the store cart."
    )
    st.table(
        escape_streamlit_data([
            {
                "Required item": selection.item_name,
                "For": _join_names(selection.affected_children),
                "Status": (
                    "Unfulfilled by parent choice — you will source this "
                    "item separately"
                ),
            }
            for selection in selections
        ])
    )


def _assumption_text(flag: str) -> str | None:
    """Turn a normalization assumption flag into plain display copy."""

    if flag == "quantity_range_minimum_selected":
        return "Used the minimum quantity from the range on the list."
    if flag.startswith("standard_pack_count_assumed:"):
        count = flag.rsplit(":", 1)[-1]
        return f"Assumed a standard package contains {count} units."
    if flag.startswith("ream_converted_to_sheets:"):
        count = flag.rsplit(":", 1)[-1]
        return f"Converted one ream to {count} sheets."
    return None


def _render_needs_attention(
    st: Any,
    result: PipelineResult,
    optimization: OptimizationResult,
    matches: MatchResult,
    child_labels: Mapping[str, str],
    self_sourced_decisions: Sequence[SelfSourcedSelection],
) -> None:
    """Render only conditions that are genuinely unresolved."""

    if result.extraction_failures:
        st.error(
            "The plan uses only the lists that were read successfully. "
            "The entries below were not included."
        )
        for child_id, reason in result.extraction_failures.items():
            st.write(
                escape_streamlit_dollars(
                    f"{_child_display_label(child_id, child_labels)}: {reason}"
                )
            )

    if self_sourced_decisions:
        _render_self_sourced_items(st, self_sourced_decisions)

    if not optimization.is_complete:
        st.error(
            "Required items unavailable from the selected store scope"
        )
        for item in optimization.gap_items:
            st.write(f"• {_item_display_name(item)}")

    unresolved_notes = _unresolved_catalog_notes(
        optimization,
        matches,
    )
    if unresolved_notes:
        st.warning("Details the catalog could not resolve")
        st.table(escape_streamlit_data(unresolved_notes))


def _unresolved_catalog_notes(
    optimization: OptimizationResult,
    matches: MatchResult,
) -> tuple[dict[str, str], ...]:
    """Collect catalog facts that still require attention."""

    unresolved_notes: list[dict[str, str]] = []
    seen_notes: set[tuple[str, str]] = set()
    for plan in _plans(optimization):
        for line in plan.lines:
            for note in line.notes:
                if not note.startswith("catalog_attribute_unknown:"):
                    continue
                attribute = note.rsplit(":", 1)[-1].replace("_", " ")
                key = (line.sku, attribute)
                if key in seen_notes:
                    continue
                seen_notes.add(key)
                unresolved_notes.append(
                    {
                        "Product": _product_name(line, matches),
                        "Unresolved detail": (
                            f"The catalog does not record {attribute}."
                        ),
                    }
                )
    return tuple(unresolved_notes)


def _has_genuine_attention(
    result: PipelineResult,
    optimization: OptimizationResult,
    matches: MatchResult,
    self_sourced_decisions: Sequence[SelfSourcedSelection],
) -> bool:
    """Return whether the prominent attention heading is warranted."""

    return bool(
        result.extraction_failures
        or self_sourced_decisions
        or not optimization.is_complete
        or _unresolved_catalog_notes(optimization, matches)
    )


def _render_assumptions_and_notes(
    st: Any,
    result: PipelineResult,
    child_labels: Mapping[str, str],
) -> None:
    """Render resolved assumptions and list notes as collapsed detail."""

    grouped_assumptions: dict[
        tuple[str, tuple[str, ...], str],
        list[str],
    ] = {}
    for requirement in result.normalization.requirements:
        for flag in requirement.assumption_flags:
            message = _assumption_text(flag)
            if message is None:
                continue
            aggregate_source_ids = next(
                (
                    need.source_requirement_ids
                    for need in result.purchase_needs
                    if requirement.source.req_id
                    in need.source_requirement_ids
                ),
                (requirement.source.req_id,),
            )
            key = (
                requirement.canonical_item,
                aggregate_source_ids,
                message,
            )
            child_name = _child_display_label(
                requirement.source.child_id,
                child_labels,
            )
            grouped_assumptions.setdefault(key, [])
            if child_name not in grouped_assumptions[key]:
                grouped_assumptions[key].append(child_name)
    assumptions = tuple(
        {
            "Item": _item_display_name(canonical_item),
            "For": _join_names(tuple(children)),
            "Assumption": message,
        }
        for (
            canonical_item,
            _,
            message,
        ), children in grouped_assumptions.items()
    )
    if assumptions:
        st.write("Assumptions used to build the plan")
        st.table(escape_streamlit_data(assumptions))

    display_only = result.normalization.display_only_requirements
    if display_only:
        st.write("List notes kept outside the shopping cart")
        for requirement in display_only:
            st.write(
                escape_streamlit_dollars(
                    f"• {_child_display_label(requirement.source.child_id, child_labels)}: "
                    f"{requirement.source.raw_text}"
                )
            )


def source_interpretation_rows(
    result: PipelineResult,
    child_labels: Mapping[str, str],
    review_items: Sequence[SupplyItemReview] = (),
) -> tuple[dict[str, str], ...]:
    """Expose exact list evidence and its cart treatment on the summary."""

    unfulfillable_ids = {
        source_id
        for need_matches in result.matches.needs
        if need_matches.unfulfillable
        for source_id in need_matches.unit_need.source_requirement_ids
    }
    review_blocked_ids = {
        source_id
        for need_matches in result.matches.needs
        if need_matches.requires_confidence_review
        for source_id in need_matches.unit_need.source_requirement_ids
    }
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for normalized in result.normalization.requirements:
        requirement = normalized.source
        key = (
            requirement.child_id,
            requirement.raw_text,
            requirement.canonical_item,
        )
        seen.add(key)
        if requirement.provided_by_school:
            status = "Already provided by the school — not purchased"
        elif (
            requirement.condition is not None
            and requirement.condition_applies is False
        ):
            status = "Condition does not apply — not purchased"
        elif not requirement.is_purchasable:
            status = "List note — not purchased"
        elif requirement.req_id in unfulfillable_ids:
            status = "No catalog product found"
        elif requirement.req_id in review_blocked_ids:
            status = "Product match needs parent review"
        elif requirement.requirement_type == "donation":
            status = "Classroom donation — outside the required cart"
        elif requirement.requirement_type == "optional":
            status = "Optional item — outside the required cart"
        else:
            status = "Read for the proposed cart"
        rows.append(
            {
                "For": _child_display_label(
                    requirement.child_id,
                    child_labels,
                ),
                "Interpreted as": _item_display_name(
                    requirement.canonical_item
                ),
                "Exact source line": requirement.raw_text,
                "Use": requirement.supply_scope.title(),
                "Section": requirement.source_section or "Not stated",
                "Page": (
                    str(requirement.source_page)
                    if requirement.source_page is not None
                    else "Not stated"
                ),
                "Status": status,
            }
        )
    for item in review_items:
        key = (item.child_id, item.source_text, item.item_name)
        if key in seen or (
            item.review_status != "deleted" and not item.already_owned
        ):
            continue
        rows.append(
            {
                "For": _child_display_label(
                    item.child_id,
                    child_labels,
                ),
                "Interpreted as": _item_display_name(item.item_name),
                "Exact source line": item.source_text,
                "Use": item.supply_scope.title(),
                "Section": item.source_section or "Not stated",
                "Page": (
                    str(item.source_page)
                    if item.source_page is not None
                    else "Not stated"
                ),
                "Status": (
                    "Marked already owned — not purchased"
                    if item.already_owned
                    else "Removed during parent review"
                ),
            }
        )
    return tuple(rows)


def document_scope_rows(
    result: PipelineResult,
    child_labels: Mapping[str, str],
) -> tuple[dict[str, str], ...]:
    """Name selected and ignored document sections without silence."""

    rows: list[dict[str, str]] = []
    for child_id, envelope in result.extractions.items():
        selection = envelope.document_selection
        if selection is None:
            continue
        child = _child_display_label(child_id, child_labels)
        rows.extend(
            {
                "For": child,
                "Document section": label,
                "Treatment": "Read",
            }
            for label in selection.selected_section_labels
        )
        rows.extend(
            {
                "For": child,
                "Document section": label,
                "Treatment": "Not read",
            }
            for label in selection.ignored_section_labels
        )
    return tuple(rows)


def uninterpreted_source_rows(
    result: PipelineResult,
    child_labels: Mapping[str, str],
) -> tuple[dict[str, str], ...]:
    """Name source content that the reading step could not interpret."""

    return tuple(
        {
            "For": _child_display_label(child_id, child_labels),
            "Source content": line,
            "Treatment": "Could not interpret — not purchased",
        }
        for child_id, envelope in result.extractions.items()
        for line in envelope.uninterpreted_lines
    )


def skipped_source_rows(
    result: PipelineResult,
    child_labels: Mapping[str, str],
) -> tuple[dict[str, str], ...]:
    """Name source content deliberately skipped by deterministic safeguards."""

    return tuple(
        {
            "For": _child_display_label(child_id, child_labels),
            "Source content": line,
            "Treatment": "Deliberately skipped — not purchased",
        }
        for child_id, envelope in result.extractions.items()
        for line in envelope.skipped_lines
    )


def _render_list_interpretation(
    st: Any,
    result: PipelineResult,
    child_labels: Mapping[str, str],
    review_items: Sequence[SupplyItemReview],
) -> None:
    """Separate model reading evidence from deterministic cart arithmetic."""

    st.subheader("How your list became the cart")
    st.write(
        "A language model read the supply list. Below are the original lines "
        "and the choices you confirmed. Quantities, package choices, prices, "
        "tax, fees, and totals are calculated by deterministic code from "
        "those choices and the simulated catalog."
    )
    scopes = document_scope_rows(result, child_labels)
    if scopes:
        st.table(escape_streamlit_data(scopes))
    st.table(
        escape_streamlit_data(
            source_interpretation_rows(
                result,
                child_labels,
                review_items,
            )
        )
    )
    uninterpreted = uninterpreted_source_rows(result, child_labels)
    if uninterpreted:
        st.warning(
            "Some source content could not be interpreted and was not added."
        )
        st.table(escape_streamlit_data(uninterpreted))
    skipped = skipped_source_rows(result, child_labels)
    if skipped:
        st.info("Some source content was deliberately skipped and named below.")
        st.table(escape_streamlit_data(skipped))


def _render_summary_headline(
    st: Any,
    optimization: OptimizationResult,
    budget_cents: int | None,
    is_complete: bool,
    copy: CopySet,
) -> None:
    """Lead with cost, budget status, and plan completeness."""

    variance = (
        None
        if budget_cents is None
        else budget_cents - optimization.landed_cost
    )
    if variance is not None and variance < 0:
        st.error(
            "Budget shortfall: "
            f"{format_streamlit_money(abs(variance))}. "
            "The current plan is over the entered budget."
        )
    if not is_complete:
        st.error(
            "Required items are missing because one or more are not in the "
            "cart."
        )
    if (
        is_complete
        and (variance is None or variance >= 0)
        and copy.register == "warm"
    ):
        st.markdown(
            (
                '<div class="rss-plan-ready" role="status">'
                '<span class="rss-plan-ready__check" aria-hidden="true">✓</span>'
                "<span>All set — your shopping plan is ready.</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    st.header(copy.summary_heading)
    st.caption(copy.headline_heading)
    columns = st.columns(2 if budget_cents is None else 3)
    columns[0].metric(
        "Landed cost",
        format_streamlit_money(optimization.landed_cost),
    )
    if budget_cents is None:
        st.caption("No budget comparison selected.")
    else:
        if variance is not None and variance >= 0:
            columns[1].metric(
                "Budget remaining",
                format_streamlit_money(variance),
            )
        else:
            columns[1].metric(
                "Budget shortfall",
                format_streamlit_money(abs(variance or 0)),
            )
    columns[-1].metric(
        "Plan status",
        copy.complete_status if is_complete else "Required items missing",
    )


def _approval_outcome_labels(
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
    resolved_interrupts: Mapping[str, str] | None = None,
) -> dict[str, str]:
    labels: dict[str, str] = {}
    resolved = resolved_interrupts or {}
    for presentation in presentations:
        interrupt = presentation.interrupt
        selected_id = outcomes.get(interrupt.interrupt_id)
        selected = next(
            (
                alternative
                for alternative in presentation.options
                if alternative.alternative_id == selected_id
            ),
            None,
        )
        labels[presentation.heading] = (
            selected.label
            if selected is not None
            else resolved.get(interrupt.interrupt_id, "Pending")
        )
    return labels


def _render_summary(st: Any) -> None:
    result: PipelineResult | None = st.session_state["result"]
    intake = st.session_state["intake"]
    if result is None or intake is None:
        st.session_state["screen"] = "working"
        st.rerun()
    children = intake["children"]
    child_labels = {
        child["child_id"]: child["label"] for child in children
    }
    stores = tuple(load_stores())
    offers = _active_catalog_offers(
        frozenset(st.session_state["stockout_skus"]),
        st.session_state["price_overrides"],
    )
    cached_presentations = st.session_state.get(
        "approval_presentations_cache"
    )
    if cached_presentations is None:
        cached_presentations = build_approval_presentations(
            result,
            offers,
            stores,
            child_labels,
        )
        st.session_state["approval_presentations_cache"] = (
            cached_presentations
        )
    approval_presentations = tuple(cached_presentations)
    self_sourced_decisions = _self_sourced_decisions(
        approval_presentations,
        st.session_state["approval_outcomes"],
        result.budget_analysis,
        st.session_state["budget_action_ids"],
        child_labels,
    )
    required_optimization, required_matches = _effective_cart(
        st,
        result,
        approval_presentations,
        offers,
        stores,
    )
    required_plan_is_complete = (
        required_optimization.is_complete
        and not self_sourced_decisions
        and not result.extraction_failures
    )
    selected_addon_ids: tuple[str, ...] = ()
    addon_evaluation: AddOnSelectionEvaluation | None = None
    if donation_offer_is_visible(result, required_plan_is_complete):
        selected_addon_ids = _selected_addon_requirement_ids(st, result)
        addon_evaluation = _evaluate_selected_addons(
            result,
            selected_addon_ids,
            required_optimization,
            approval_presentations,
            st.session_state["approval_outcomes"],
            st.session_state["budget_action_ids"],
            offers,
            stores,
        )
        optimization = addon_evaluation.optimization
        matches = addon_evaluation.matches
        st.session_state["addon_evaluation"] = addon_evaluation
    else:
        optimization = required_optimization
        matches = required_matches
        st.session_state["addon_evaluation"] = None
        st.session_state["include_addons"] = False
    is_complete = required_plan_is_complete
    budget_total = intake["budget_total"]
    tone_state = ToneState(
        has_shortfall=(
            budget_total is not None
            and optimization.landed_cost > int(budget_total)
        ),
        has_unmet_required=not is_complete,
        has_extraction_failure=bool(result.extraction_failures),
        has_error=bool(st.session_state.get("ui_error_active", False)),
    )
    copy = select_copy_set(tone_state)

    # 1. The plan's condition comes before every detail when it needs attention.
    _render_summary_headline(
        st,
        optimization,
        None if budget_total is None else int(budget_total),
        is_complete,
        copy,
    )
    if st.session_state.get("catalog_change_notice"):
        st.info(
            escape_streamlit_dollars(
                str(st.session_state["catalog_change_notice"])
            )
        )

    # 2. Only genuinely unresolved conditions receive prominent attention.
    if _has_genuine_attention(
        result,
        required_optimization,
        required_matches,
        self_sourced_decisions,
    ):
        st.subheader("Needs your attention")
        _render_needs_attention(
            st,
            result,
            required_optimization,
            required_matches,
            child_labels,
            self_sourced_decisions,
        )
    _render_list_interpretation(
        st,
        result,
        child_labels,
        tuple(st.session_state.get("review_items", ())),
    )
    has_assumptions_or_notes = bool(
        result.normalization.display_only_requirements
        or any(
            _assumption_text(flag) is not None
            for requirement in result.normalization.requirements
            for flag in requirement.assumption_flags
        )
    )
    if has_assumptions_or_notes:
        with st.expander("Assumptions and list notes"):
            _render_assumptions_and_notes(
                st,
                result,
                child_labels,
            )

    # 3. Parent outcomes are summarized; detailed reasoning stays collapsed.
    parent_decisions = tuple(st.session_state["parent_decisions"])
    with st.expander("Decisions made and their outcomes"):
        _render_approvals_summary(st, approval_presentations)
        st.caption("How the plan was built")
        st.table(
            escape_streamlit_data([
                {
                    "Time": decision.timestamp.isoformat(
                        timespec="seconds"
                    ),
                    "Actor": decision.actor.title(),
                    "Decision": decision.type.replace("_", " ").title(),
                    "Reason": _humanize_internal_text(
                        decision.rationale,
                        offers,
                        stores,
                    ),
                }
                for decision in _decision_log(result, parent_decisions)
            ])
        )

    # 4. Shopping details are available without competing with the headline.
    with st.expander("Where to shop"):
        _render_cost_summary(st, optimization)
        _render_store_breakdown(
            st,
            optimization,
            matches,
            stores,
            child_labels,
        )

    # 5. Attribution is useful detail, but not part of the quick read.
    with st.expander("Cost by student or classroom"):
        _render_per_child(
            st,
            optimization,
            children,
            intake["budget_allocations"],
        )

    # 6. Routine equivalents collapse to one line; consequential choices remain.
    with st.expander("Substitutions and package choices"):
        _render_substitutions(st, optimization, matches, stores)

    st.subheader("Try a live catalog change")
    with st.container(border=True):
        st.write(
            "Change simulated stock or price. Ready, Set, School will reuse "
            "the saved list reading and product judgments, rebuild the cart, "
            "and ask only for decisions the change invalidates."
        )
        selected_skus = tuple(
            dict.fromkeys(
                line.sku
                for plan in _plans(optimization)
                for line in plan.lines
            )
        )
        if selected_skus:
            offers_by_sku = {offer.sku: offer for offer in offers}
            stock_column, price_column = st.columns(2)
            with stock_column:
                st.write("Stockout")
                stockout_sku = st.selectbox(
                    "Product to mark out of stock",
                    selected_skus,
                    format_func=lambda sku: escape_streamlit_dollars(
                        _catalog_product_label(sku, offers, stores)
                    ),
                    key="catalog_stockout_sku",
                )
                if st.button(
                    "Mark out of stock and re-plan",
                    type="primary",
                    key="apply_catalog_stockout",
                ):
                    _apply_stockout_replan(
                        st,
                        result,
                        stockout_sku,
                        offers,
                        stores,
                        child_labels,
                    )
                    st.rerun()
            with price_column:
                st.write("Price change")
                price_sku = st.selectbox(
                    "Product whose price changed",
                    selected_skus,
                    format_func=lambda sku: escape_streamlit_dollars(
                        _catalog_product_label(sku, offers, stores)
                    ),
                    key="catalog_price_sku",
                )
                current_price = offers_by_sku[price_sku].pack_price
                price_text = st.text_input(
                    r"New pack price (\$)",
                    value=(
                        f"{current_price // CENTS_PER_DOLLAR}."
                        f"{current_price % CENTS_PER_DOLLAR:02d}"
                    ),
                    key=f"catalog_price_value_{price_sku}",
                )
                if st.button(
                    "Apply price and re-plan",
                    key="apply_catalog_price",
                ):
                    try:
                        new_price = money_to_cents(price_text)
                        if new_price == current_price:
                            raise ValueError(
                                "Enter a price different from the current "
                                "pack price."
                            )
                    except ValueError as error:
                        st.error(escape_streamlit_dollars(str(error)))
                    else:
                        price_overrides = dict(
                            st.session_state["price_overrides"]
                        )
                        price_overrides[price_sku] = new_price
                        st.session_state["price_overrides"] = price_overrides
                        changed_offers = _active_catalog_offers(
                            frozenset(st.session_state["stockout_skus"]),
                            price_overrides,
                        )
                        transition = replan_after_catalog_change(
                            result,
                            changed_offers,
                            stores,
                            change_kind="price_change",
                            changed_sku=price_sku,
                            approval_outcomes=st.session_state[
                                "approval_outcomes"
                            ],
                            budget_action_ids=st.session_state[
                                "budget_action_ids"
                            ],
                        )
                        _store_replan_transition(
                            st,
                            transition,
                            changed_offers,
                            stores,
                            child_labels,
                            (
                                f"{_catalog_product_label(price_sku, offers, stores)} "
                                f"changed from {format_money(current_price)} "
                                f"to {format_money(new_price)}. The cart was "
                                "rebuilt and any new budget decision was "
                                "added to the approval screen."
                            ),
                        )
                        st.rerun()
        else:
            st.info("There are no selected cart products to change.")

    # 7. BR-05 donations are last, collapsed, exact, and individually selectable.
    if addon_evaluation is not None:
        with st.expander("Optional classroom donations"):
            _render_addons(
                st,
                result,
                child_labels,
                selected_addon_ids,
                addon_evaluation,
                required_optimization,
                approval_presentations,
                offers,
                stores,
            )

    summary_text = build_text_summary(
        result,
        optimization,
        matches,
        stores,
        child_labels,
        _approval_outcome_labels(
            approval_presentations,
            st.session_state["approval_outcomes"],
            st.session_state.get("resolved_interrupts", {}),
        ),
        self_sourced_decisions,
        parent_decisions,
    )

    # 8. Checkout stays visible for the parent who needs only the quick read.
    st.subheader("Simulated checkout")
    checkout_staleness = detect_cart_staleness(optimization, offers)
    if checkout_staleness:
        st.error(
            "A simulated catalog change was detected after this cart was "
            "built. Re-plan before checkout."
        )
        for stale in checkout_staleness:
            product = _catalog_product_label(stale.sku, offers, stores)
            if stale.kind == "stock":
                detail = f"{product} no longer has enough stock."
            else:
                detail = (
                    f"{product} changed from "
                    f"{format_money(stale.prior_line_cost_cents)} to "
                    f"{format_money(stale.active_line_cost_cents or 0)}."
                )
            st.warning(escape_streamlit_dollars(detail))
    checkout_label = "Place simulated order"
    if not is_complete:
        st.warning(
            "This checkout covers only the store-supplied items. Required "
            "items are still missing until they are obtained separately."
        )
        checkout_label = "Place partial simulated order"
    else:
        st.caption(
            "This creates an order confirmation only. No retailer account or "
            "payment information is used."
        )
    st.download_button(
        "Download text shopping plan",
        data=summary_text,
        file_name="ready-set-school-plan.txt",
        mime="text/plain",
    )
    if st.button(
        checkout_label,
        type="primary",
        disabled=bool(checkout_staleness),
    ):
        confirmation = {
            "confirmation_id": (
                "SIM-" + result.session.session_id.split("-")[0].upper()
            ),
            "created_at": datetime.now(timezone.utc),
            "landed_cost": optimization.landed_cost,
            "is_partial": not is_complete,
        }
        st.session_state["checkout_confirmation"] = confirmation
    confirmation = st.session_state["checkout_confirmation"]
    if confirmation:
        order_label = (
            "Partial order"
            if confirmation.get("is_partial")
            else "Order"
        )
        st.success(
            f"{order_label} {confirmation['confirmation_id']} confirmed at "
            f"{confirmation['created_at'].strftime('%Y-%m-%d %H:%M UTC')}. "
            "Landed cost: "
            f"{format_streamlit_money(confirmation['landed_cost'])}."
        )

    left, right = _navigation_button_columns(st)
    if left.button(
        "Change shopping settings",
        use_container_width=True,
    ):
        st.session_state["result"] = None
        st.session_state["checkout_confirmation"] = None
        st.session_state["ui_error_active"] = False
        st.session_state["progress_substep"] = "setup"
        navigate_back_to_screen(st.session_state, "intake")
        st.rerun()
    if right.button("Start a new session", use_container_width=True):
        clear_session_data(st)
        st.rerun()


def _apply_custom_css(st: Any) -> None:
    """Apply a high-contrast, school-inspired visual system."""

    st.markdown(
        """
        <style>
        :root {
            --rss-ink: #17231d;
            --rss-muted: #435249;
            --rss-paper: #fbfaf2;
            --rss-card: #ffffff;
            --rss-line: #a9c7d9;
            --rss-pencil: #f5c400;
            --rss-notebook: #006eae;
            --rss-chalkboard: #167149;
            --rss-crayon: #c52f45;
            --rss-soft-blue: #eaf6fc;
            --rss-soft-yellow: #fff7cf;
            --rss-soft-red: #fff0f2;
        }
        .stApp {
            color: var(--rss-ink);
            background-color: var(--rss-paper);
            background-image:
                linear-gradient(
                    to right,
                    transparent 0,
                    transparent 5.2rem,
                    rgba(197, 47, 69, 0.24) 5.2rem,
                    rgba(197, 47, 69, 0.24) 5.32rem,
                    transparent 5.32rem
                ),
                repeating-linear-gradient(
                    to bottom,
                    #fbfaf2 0,
                    #fbfaf2 2rem,
                    rgba(0, 110, 174, 0.17) 2rem,
                    rgba(0, 110, 174, 0.17) 2.08rem
                );
            background-attachment: fixed;
            font-family: "Segoe UI", Arial, sans-serif;
        }
        .block-container {
            max-width: 1040px;
            margin-top: 0.6rem;
            margin-bottom: 3rem;
            padding: 1.25rem 2rem 3rem;
            border: 3px solid var(--rss-notebook);
            border-top: 0.65rem solid var(--rss-pencil);
            border-radius: 1.25rem;
            background-color: var(--rss-card);
            box-shadow: 0 0.8rem 2rem rgba(23, 35, 29, 0.16);
        }
        [data-testid="stVerticalBlock"] {
            gap: 0.75rem;
        }
        [data-testid="stHorizontalBlock"] {
            align-items: flex-start;
            gap: 1rem;
            animation: rss-fields-in 160ms ease-out both;
        }
        h1, h2, h3 {
            color: var(--rss-ink);
            font-family: "Trebuchet MS", "Segoe UI", sans-serif;
            letter-spacing: -0.02em;
            line-height: 1.2;
        }
        [data-testid="stHeaderActionElements"] {
            display: none !important;
        }
        h1 {
            margin: 0 0 0.35rem !important;
            font-size: clamp(2.2rem, 5vw, 3.55rem) !important;
            font-weight: 800 !important;
        }
        .rss-title {
            display: flex;
            flex-wrap: nowrap;
            align-items: baseline;
            gap: 0.22em;
            width: fit-content;
            padding-bottom: 0.22rem;
            border-bottom: 0.35rem solid var(--rss-pencil);
            font-size: clamp(2.15rem, 7.2vw, 3.55rem) !important;
            line-height: 1.05;
            white-space: nowrap;
        }
        .rss-title__ready {color: var(--rss-crayon);}
        .rss-title__set {color: var(--rss-notebook);}
        .rss-title__school {color: var(--rss-chalkboard);}
        h2 {
            margin-top: 1.75rem !important;
            margin-bottom: 0.8rem !important;
            padding-left: 0.9rem;
            border-left: 0.45rem solid var(--rss-pencil);
        }
        h3 {
            color: var(--rss-notebook);
            margin-top: 1.1rem !important;
            margin-bottom: 0.6rem !important;
        }
        p, label, [data-testid="stCaptionContainer"] {
            color: var(--rss-ink);
            line-height: 1.6;
        }
        label {
            font-weight: 700 !important;
        }
        [data-testid="stCaptionContainer"] {
            color: var(--rss-muted);
            font-weight: 525;
        }
        [data-testid="stWidgetLabel"] {
            min-height: 1.55rem;
            display: flex;
            align-items: flex-end;
        }
        .rss-stepper {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.4rem;
            margin: 0.4rem 0 0.25rem;
            padding: 0.35rem;
            border: 2px solid var(--rss-line);
            border-radius: 0.75rem;
            background-color: var(--rss-card);
        }
        .rss-stepper__item {
            display: grid;
            align-items: center;
            justify-items: center;
            min-height: 2.35rem;
            padding: 0.4rem 0.55rem;
            border-radius: 0.5rem;
            color: var(--rss-ink);
            font-size: 0.88rem;
            font-weight: 700;
            line-height: 1.2;
            text-align: center;
            transition:
                background-color 160ms ease,
                color 160ms ease,
                transform 160ms ease;
        }
        .rss-stepper__item--current {
            background-color: var(--rss-notebook);
            color: #ffffff;
            animation: rss-step-in 220ms ease-out both;
        }
        [class*="st-key-journey_stage_navigation_"] button,
        [class*="st-key-intake_section_navigation_"] button {
            min-height: 3rem;
            padding: 0.45rem 0.65rem;
            line-height: 1.2;
        }
        [class*="st-key-journey_stage_navigation_"]
        button[kind="primary"]:disabled,
        [class*="st-key-intake_section_navigation_"]
        button[kind="primary"]:disabled {
            border-color: var(--rss-notebook);
            background-color: var(--rss-notebook);
            color: #ffffff !important;
            opacity: 1;
        }
        [class*="st-key-journey_stage_navigation_"]
        button[kind="primary"]:disabled *,
        [class*="st-key-intake_section_navigation_"]
        button[kind="primary"]:disabled * {
            color: #ffffff !important;
        }
        [class*="st-key-journey_stage_navigation_"]
        button[kind="secondary"]:disabled,
        [class*="st-key-intake_section_navigation_"]
        button[kind="secondary"]:disabled {
            border-color: #c7d2cc;
            background-color: #f1f3f1;
            color: #6d7771;
            opacity: 0.72;
        }
        .rss-intake-sections {
            display: flex;
            gap: 1.5rem;
            align-items: center;
            margin: 0.45rem 0 0.15rem;
            border-bottom: 2px solid var(--rss-line);
        }
        .rss-intake-sections__item {
            padding: 0.35rem 0 0.5rem;
            color: var(--rss-muted);
            font-weight: 700;
        }
        .rss-intake-sections__item--current {
            margin-bottom: -2px;
            border-bottom: 4px solid var(--rss-crayon);
            color: var(--rss-ink);
        }
        [data-testid="stMetric"] {
            border: 2px solid var(--rss-line);
            border-top: 0.35rem solid var(--rss-notebook);
            border-radius: 0.85rem;
            padding: 1.1rem 1.2rem;
            background-color: var(--rss-card);
        }
        [data-testid="stExpander"],
        [data-testid="stForm"],
        [data-testid="stVerticalBlockBorderWrapper"] {
            border: 2px solid var(--rss-line) !important;
            border-radius: 0.9rem !important;
            background-color: var(--rss-card) !important;
            animation: rss-card-in 180ms ease-out both;
        }
        [data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 0.85rem 1.1rem;
        }
        [data-testid="stNotification"] {
            border-radius: 0.8rem;
            border-width: 2px;
            background-color: var(--rss-card) !important;
        }
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stSelectbox"] > div > div {
            color: var(--rss-ink) !important;
            min-height: 2.85rem;
            border-radius: 0.7rem !important;
            background-color: #ffffff !important;
            border-color: #6e8d9e !important;
        }
        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stTextInput"] div:has(> input),
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
        [data-testid="stTextArea"] [data-baseweb="base-input"] {
            min-height: 2.85rem;
            border: 1.5px solid #6e8d9e !important;
            border-radius: 0.7rem !important;
            background-color: #ffffff !important;
            box-shadow: inset 0 0 0 1px rgba(110, 141, 158, 0.24) !important;
            transition:
                border-color 130ms ease,
                box-shadow 130ms ease,
                transform 130ms ease;
        }
        [data-testid="stTextInput"] input {
            border: 0 !important;
            outline: 0 !important;
            background-color: transparent !important;
        }
        [data-testid="stTextInput"] [data-baseweb="input"]:hover,
        [data-testid="stTextInput"] div:has(> input):hover,
        [data-testid="stNumberInput"] [data-baseweb="input"]:hover,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div:hover,
        [data-testid="stTextArea"] [data-baseweb="base-input"]:hover {
            border-color: var(--rss-notebook) !important;
        }
        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTextInput"] div:has(> input):focus-within,
        [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div:focus-within,
        [data-testid="stTextArea"] [data-baseweb="base-input"]:focus-within {
            border-color: var(--rss-notebook) !important;
            box-shadow: 0 0 0 0.18rem rgba(0, 110, 174, 0.16) !important;
        }
        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {
            border: 2px solid var(--rss-chalkboard);
            background-color: #ffffff;
            color: var(--rss-ink);
            border-radius: 0.65rem;
            min-height: 2.85rem;
            padding-inline: 1.25rem;
            font-weight: 750;
            transition:
                background-color 120ms ease,
                border-color 120ms ease,
                box-shadow 120ms ease,
                color 120ms ease,
                transform 120ms ease;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover {
            background-color: var(--rss-soft-yellow);
            color: var(--rss-ink);
            box-shadow: 0 0.3rem 0.7rem rgba(23, 35, 29, 0.14);
            transform: translateY(-1px);
        }
        .stButton > button:active,
        .stDownloadButton > button:active,
        [data-testid="stFormSubmitButton"] > button:active {
            box-shadow: none;
            transform: translateY(0);
        }
        .stButton > button[kind="primary"],
        button[data-testid="baseButton-primary"],
        [data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background-color: var(--rss-chalkboard);
            border-color: var(--rss-chalkboard);
            color: #ffffff !important;
        }
        .stButton > button[kind="primary"] *,
        button[data-testid="baseButton-primary"] *,
        [data-testid="stFormSubmitButton"] > button[kind="primary"] * {
            color: #ffffff !important;
        }
        [data-testid="stProgress"] > div > div > div > div {
            background-color: var(--rss-notebook);
            border-radius: 999px;
        }
        [data-testid="stProgress"] > div > div {
            background-color: #dce6e0;
            border-radius: 999px;
            overflow: hidden;
        }
        [data-testid="stDataFrame"],
        [data-testid="stTable"] {
            border: 2px solid var(--rss-line);
            border-radius: 0.75rem;
            background-color: #ffffff;
            overflow: hidden;
        }
        [role="radiogroup"] {
            gap: 0.5rem;
        }
        [role="radiogroup"] label {
            border-radius: 0.65rem;
        }
        hr {display: none !important;}
        [data-testid="stForm"] [role="radiogroup"] > label {
            align-items: flex-start;
            margin-bottom: 0.8rem;
            padding: 0.65rem 0;
        }
        .rss-plan-ready {
            position: relative;
            display: flex;
            align-items: center;
            gap: 0.7rem;
            overflow: hidden;
            margin: 0.4rem 0 0.85rem;
            padding: 0.75rem 1rem;
            border: 2px solid var(--rss-chalkboard);
            border-radius: 0.8rem;
            background-color: #edf9f2;
            color: var(--rss-ink);
            font-weight: 750;
            animation: rss-celebrate-in 320ms ease-out both;
        }
        .rss-plan-ready__check {
            display: grid;
            flex: 0 0 2rem;
            width: 2rem;
            height: 2rem;
            place-items: center;
            border-radius: 50%;
            background-color: var(--rss-chalkboard);
            color: #ffffff;
            animation: rss-check-pop 360ms 80ms ease-out both;
        }
        .rss-plan-ready::after {
            position: absolute;
            top: 0.35rem;
            right: 1.2rem;
            width: 0.42rem;
            height: 0.42rem;
            border-radius: 50%;
            background-color: var(--rss-pencil);
            box-shadow:
                1.1rem 0.45rem 0 var(--rss-crayon),
                2rem -0.05rem 0 var(--rss-notebook),
                2.8rem 0.65rem 0 var(--rss-chalkboard);
            content: "";
            animation: rss-confetti 520ms 100ms ease-out both;
        }
        @keyframes rss-card-in {
            from {
                opacity: 0;
                transform: translateY(0.35rem);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        @keyframes rss-step-in {
            from {transform: scale(0.97);}
            to {transform: scale(1);}
        }
        @keyframes rss-fields-in {
            from {
                opacity: 0;
                transform: translateY(0.2rem);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        @keyframes rss-celebrate-in {
            from {
                opacity: 0;
                transform: translateY(0.45rem);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        @keyframes rss-check-pop {
            from {
                opacity: 0;
                transform: scale(0.7) rotate(-8deg);
            }
            to {
                opacity: 1;
                transform: scale(1) rotate(0);
            }
        }
        @keyframes rss-confetti {
            from {
                opacity: 0;
                transform: translateY(-0.45rem) rotate(-8deg);
            }
            to {
                opacity: 1;
                transform: translateY(0) rotate(0);
            }
        }
        @media (max-width: 700px) {
            .block-container {
                margin-top: 0;
                margin-bottom: 0;
                padding: 1.2rem 1rem 3rem;
                border-right-width: 0;
                border-left-width: 0;
                border-radius: 0;
                box-shadow: none;
            }
            .rss-title {
                gap: 0.16em;
                font-size: clamp(2rem, 8.4vw, 2.8rem) !important;
            }
            .rss-stepper {
                gap: 0.2rem;
                padding: 0.25rem;
            }
            .rss-stepper__item {
                min-height: 2.65rem;
                padding: 0.35rem 0.2rem;
                font-size: 0.72rem;
            }
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
                gap: 0.85rem;
            }
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                flex: 1 1 100% !important;
                width: 100% !important;
            }
            [data-testid="stVerticalBlockBorderWrapper"] > div {
                padding: 0.8rem;
            }
        }
        @media (prefers-reduced-motion: reduce) {
            *,
            *::before,
            *::after {
                scroll-behavior: auto !important;
                animation-duration: 0.01ms !important;
                animation-delay: 0ms !important;
                transition-duration: 0.01ms !important;
            }
            .stButton > button:hover,
            .stDownloadButton > button:hover,
            [data-testid="stFormSubmitButton"] > button:hover {
                transform: none !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_app_title(st: Any) -> None:
    """Render the high-contrast three-color application identity."""

    st.markdown(
        (
            '<h1 class="rss-title" aria-label="Ready, Set, School">'
            '<span class="rss-title__ready">Ready,</span>'
            '<span class="rss-title__set">Set,</span>'
            '<span class="rss-title__school">School</span>'
            "</h1>"
        ),
        unsafe_allow_html=True,
    )
    st.caption(APP_TAGLINE)


def main() -> None:
    """Run the complete Streamlit screen flow."""

    import streamlit as st

    st.set_page_config(
        page_title=APP_NAME,
        page_icon="🎒",
        layout="wide",
    )
    preserve_navigation_state(st.session_state)
    _initialize_state(st)
    _apply_custom_css(st)
    screen = st.session_state["screen"]
    _render_app_title(st)
    progress_screen = (
        "lists"
        if screen == "working"
        and not st.session_state["organized_list_confirmed"]
        else screen
    )
    _screen_progress(
        st,
        progress_screen,
        st.session_state.get("progress_substep"),
    )
    _persistent_notice(st)
    {
        "intake": _render_intake,
        "lists": _render_lists,
        "working": _render_working,
        "sections": _render_sections,
        "requirement_merge": _render_requirement_merge,
        "review": _render_review,
        "approval": _render_approval,
        "summary": _render_summary,
    }[screen](st)


if __name__ == "__main__":
    main()
