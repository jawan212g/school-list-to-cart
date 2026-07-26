"""Streamlit interface for the school list-to-cart application."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from agent.aggregate import UnitNeed
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
    evaluate_budget_actions,
)
from agent.decisions import Decision, DecisionLog
from agent.extract import (
    MODEL_NAME,
    create_model_client,
    extract_document,
    get_api_key_diagnostic,
)
from agent.gate import ApprovalBatch, ApprovalInterrupt
from agent.match import MatchResult
from agent.optimize import (
    CartLine,
    CartPlan,
    OptimizationConfig,
    OptimizationResult,
    optimize_cart,
)
from agent.pipeline import (
    ListInput,
    PipelineResult,
    PipelineSession,
    run_pipeline,
)
from agent.rules import (
    DEFAULT_TAX_BASIS_POINTS,
    MAX_CHILDREN_PER_SESSION,
    MAX_UPLOAD_BYTES,
    MINIMUM_BUDGET_CENTS,
    MODEL_MAX_CONCURRENCY,
    NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS,
    SUBSTITUTION_NONE,
)
from agent.schema import (
    ExtractionEnvelope,
    validate_extraction_envelope,
)
from agent.store_scope import (
    FulfillmentPreference,
    pickup_trip_is_within_radius,
    store_supports_fulfillment,
)
from data.loader import Offer, Store, load_catalog, load_stores


LOGGER = logging.getLogger(__name__)
CENTS_PER_DOLLAR = 100
BASIS_POINTS_PER_PERCENT = 100
MAX_TAX_PERCENT = Decimal("25")
MAX_STORE_RADIUS_MILES = 25.0
MAX_CLASSROOM_STUDENTS = 100
DEFAULT_BUDGET_TEXT = "150.00"
DEFAULT_RADIUS_MILES = 10.0
DEVELOPMENT_DEBUG_ENV = "SCHOOL_CART_DEBUG"
DEBUG_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})
SUPPORTED_UPLOADS: Mapping[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".txt": "text/plain",
}
SCREEN_ORDER = ("intake", "lists", "working", "approval", "summary")
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
    "binders": "Binder",
    "colored_pencils": "Colored pencils",
    "composition_notebooks": "Composition notebook",
    "crayons": "Crayons",
    "dividers": "Dividers",
    "glue_sticks": "Glue sticks",
    "headphones": "Headphones",
    "highlighters": "Highlighters",
    "notebook_paper": "Notebook paper",
    "pencil_boxes": "Pencil box",
    "pencils": "Pencils",
    "pens": "Pens",
    "rulers": "Ruler",
    "scissors": "Scissors",
    "tissues": "Tissues",
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


def money_to_cents(value: str) -> int:
    """Parse a positive display amount into integer cents (E-37)."""

    cleaned = value.strip().replace("$", "").replace(",", "")
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


def detect_list_identity_warnings(
    extractions: Mapping[str, object],
    children: Sequence[Mapping[str, Any]],
) -> tuple[ListIdentityWarning, ...]:
    """Compare extracted list grades with intake grades before cart build."""

    warnings: list[ListIdentityWarning] = []
    for child in children:
        child_id = str(child["child_id"])
        extracted_value = extractions.get(child_id)
        if extracted_value is None:
            continue
        extraction = validate_extraction_envelope(extracted_value)
        if not extraction.stated_grades:
            continue
        entered_grade = str(child["grade"])
        if any(
            _grade_statement_matches(entered_grade, stated_grade)
            for stated_grade in extraction.stated_grades
        ):
            continue
        stated_text = _join_names(
            tuple(
                _grade_display(grade)
                for grade in extraction.stated_grades
            )
        )
        entered_text = _grade_display(entered_grade)
        warnings.append(
            ListIdentityWarning(
                child_label=str(child["label"]),
                entered_grade=entered_grade,
                stated_grades=extraction.stated_grades,
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
                "Simulated distance": f"{store.distance_miles:.1f} miles",
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


def probe_openai_connection(client: Any | None = None) -> tuple[bool, str]:
    """Make one minimal model-availability call for deployment diagnostics."""

    try:
        active_client = client or create_model_client()
        active_client.models.retrieve(MODEL_NAME)
    except Exception as error:
        LOGGER.exception(
            "OpenAI development diagnostic failed: %r",
            error,
        )
        return False, _exact_exception_message(error)
    return (
        True,
        f"OpenAI connection succeeded and {MODEL_NAME} is available.",
    )


def validate_uploaded_document(
    filename: str,
    data: bytes,
) -> str:
    """Validate extension, size, and signature before extraction (FR-06, E-35)."""

    suffix = Path(filename).suffix.casefold()
    mime_type = SUPPORTED_UPLOADS.get(suffix)
    if mime_type is None:
        raise ValueError("Use a PDF, JPG, PNG, or TXT file.")
    if len(data) > MAX_UPLOAD_BYTES:
        maximum_mb = MAX_UPLOAD_BYTES // 1_000_000
        raise ValueError(f"File exceeds the {maximum_mb} MB size limit.")
    if not data:
        raise ValueError("The uploaded file is empty.")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("This file is not a valid PDF.")
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
) -> tuple[Offer, ...]:
    return tuple(
        replace(offer, stock_qty=0)
        if offer.sku in stockout_skus
        else offer
        for offer in load_catalog()
    )


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
    return re.sub(
        r"(-?\d+) cents\b",
        lambda match: format_money(int(match.group(1))),
        visible,
    )


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
        return "the selected entries"
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

    return child_labels.get(child_id, "Unknown entry")


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
            "Current complete-cart landed cost: "
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
            "Current complete-cart landed cost: "
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
        return "Budget — the complete required cart costs more"
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
            "The complete required cart is over budget by "
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
                for candidate in presentation.options
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
        "SCHOOL SUPPLY CART",
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
    lines.extend([
        "Simulated catalog; fictional stores; no payment was collected.",
        "",
        f"ITEM SUBTOTAL: {format_money(item_subtotal)}",
        f"TAX: {format_money(tax)}",
        f"FULFILLMENT FEES: {format_money(fees)}",
        f"LANDED COST: {format_money(optimization.landed_cost)}",
        "",
    ])
    if self_sourced_decisions:
        lines.extend(
            [
                (
                    "STATUS: INCOMPLETE — one or more required items will be "
                    "sourced separately by the parent."
                ),
                "",
                "ITEMS YOU CHOSE TO SOURCE YOURSELF",
            ]
        )
        lines.extend(
            (
                f"  {selection.item_name} | "
                f"{_join_names(selection.affected_children)} | "
                "UNFULFILLED BY PARENT CHOICE"
            )
            for selection in self_sourced_decisions
        )
        lines.append("")
    else:
        lines.extend(["STATUS: COMPLETE", ""])
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
        "child_count": 1,
        "intake": None,
        "list_inputs": (),
        "extracted_lists": {},
        "extraction_errors": {},
        "extraction_cache_ready": False,
        "list_identity_confirmed": False,
        "result": None,
        "approval_outcomes": {},
        "approval_presentations_cache": None,
        "approval_generation": 0,
        "approved_optimization": None,
        "budget_action_ids": (),
        "parent_decisions": (),
        "include_addons": False,
        "checkout_confirmation": None,
        "stockout_skus": frozenset(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_session_data(st: Any) -> None:
    """Remove every in-memory session value; nothing is persisted (BRD 11.3)."""

    st.session_state.clear()


def _persistent_notice(st: Any) -> None:
    st.info(
        "This prototype uses a simulated catalog and fictional stores. "
        "Store distances are simulated from a notional home location; no "
        "address is collected and no geocoding occurs. The radius applies to "
        "pickup trips only, never delivery. Checkout is simulated, and no "
        "payment information is collected."
    )
    st.caption(
        "Tax uses the rate you enter. State-specific tax rules and tax "
        "holidays are not modeled."
    )


def _screen_progress(st: Any, screen: str) -> None:
    labels = {
        "intake": "1 · Setup",
        "lists": "2 · Lists",
        "working": "3 · Working",
        "approval": "4 · Approval",
        "summary": "5 · Summary",
    }
    current = SCREEN_ORDER.index(screen) + 1
    st.progress(current / len(SCREEN_ORDER))
    st.caption(labels[screen])


def _render_development_diagnostic(st: Any) -> None:
    with st.expander("Development use: OpenAI connection diagnostic"):
        diagnostic = get_api_key_diagnostic()
        st.write(
            escape_streamlit_dollars(
                f"API key found: {'Yes' if diagnostic.found else 'No'}"
            )
        )
        st.write(
            escape_streamlit_dollars(
                f"Credential source: {diagnostic.source or 'None'}"
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
                f"Configured model: {MODEL_NAME}"
            )
        )
        st.caption(
            "The preview contains only the first 8 and last 4 characters. "
            "The full key is never displayed."
        )
        if st.button(
            "Test OpenAI connection",
            key="development_openai_connection_test",
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


def _render_intake(st: Any) -> None:
    st.header("Set up this shopping session")
    if development_diagnostics_enabled(st):
        _render_development_diagnostic(st)
    st.write(
        "Use labels such as “Grade 2” instead of full child names. "
        "Nothing is saved after this session."
    )
    child_count = int(
        st.number_input(
            "How many children or classroom groups?",
            min_value=1,
            max_value=MAX_CHILDREN_PER_SESSION,
            value=int(st.session_state["child_count"]),
            step=1,
            help=(
                f"Sessions are capped at {MAX_CHILDREN_PER_SESSION} entries "
                "to keep the live workflow reliable."
            ),
        )
    )
    st.session_state["child_count"] = child_count

    children: list[dict[str, Any]] = []
    for index in range(child_count):
        child_id = f"child-{index + 1}"
        with st.container(border=True):
            st.subheader(
                escape_streamlit_dollars(f"Entry {index + 1}")
            )
            left, right = st.columns(2)
            label = left.text_input(
                "Label",
                value=f"Child {index + 1}",
                key=f"child_label_{index}",
                placeholder="Example: Grade 2",
            )
            grade = right.text_input(
                "Grade",
                value="",
                key=f"child_grade_{index}",
                placeholder="Example: 2",
            )
            entity_type = st.radio(
                "Who is this list for?",
                ("One student", "A classroom group"),
                horizontal=True,
                key=f"entity_type_{index}",
            )
            student_count = 1
            if entity_type == "A classroom group":
                student_count = int(
                    st.number_input(
                        "Students in this classroom",
                        min_value=1,
                        max_value=MAX_CLASSROOM_STUDENTS,
                        value=20,
                        step=1,
                        key=f"student_count_{index}",
                    )
                )
            children.append(
                {
                    "child_id": child_id,
                    "label": label.strip(),
                    "grade": grade.strip(),
                    "student_count": student_count,
                    "entity_type": (
                        "classroom"
                        if entity_type == "A classroom group"
                        else "student"
                    ),
                }
            )

    st.subheader("Budget")
    budget_mode_label = st.radio(
        "How should the budget be entered?",
        ("One combined budget", "A budget for each entry"),
        horizontal=True,
    )
    budget_mode = (
        "combined"
        if budget_mode_label == "One combined budget"
        else "per_child"
    )
    budget_texts: dict[str, str] = {}
    if budget_mode == "combined":
        combined_budget = st.text_input(
            r"Combined budget (\$)",
            value=DEFAULT_BUDGET_TEXT,
            help=(
                "This is a text field so a tight demo budget such as 75 "
                "can be entered directly."
            ),
        )
    else:
        combined_budget = ""
        columns = st.columns(2)
        for index, child in enumerate(children):
            budget_texts[child["child_id"]] = columns[index % 2].text_input(
                escape_streamlit_dollars(
                    (
                        f"{child['label'] or f'Entry {index + 1}'} "
                        r"budget (\$)"
                    )
                ),
                value="75.00",
                key=f"budget_{index}",
            )

    st.subheader("Shopping preferences")
    mode_label = st.selectbox(
        "Shopping mode",
        tuple(SHOPPING_MODES),
    )
    shopping_mode = SHOPPING_MODES[mode_label]
    stores = load_stores()
    allowed_stores: frozenset[str] | None = None
    max_stores: int | None = None
    if shopping_mode == "custom":
        selected_names = st.multiselect(
            "Stores to consider",
            tuple(store.name for store in stores),
            default=tuple(store.name for store in stores),
        )
        store_ids_by_name = {
            store.name: store.store_id for store in stores
        }
        allowed_stores = frozenset(
            store_ids_by_name[name] for name in selected_names
        )
        max_stores = int(
            st.number_input(
                "Maximum stores",
                min_value=1,
                max_value=len(stores),
                value=2,
                step=1,
            )
        )
    radius = float(
        st.number_input(
            "Pickup-trip radius (simulated miles)",
            min_value=0.0,
            max_value=MAX_STORE_RADIUS_MILES,
            value=DEFAULT_RADIUS_MILES,
            step=0.5,
            help=(
                "This limits trips to pickup locations. It does not limit "
                "stores that can deliver."
            ),
        )
    )
    fulfillment_label = st.selectbox(
        "Fulfillment preference",
        tuple(FULFILLMENT_OPTIONS),
    )
    fulfillment_preference = FULFILLMENT_OPTIONS[fulfillment_label]
    st.caption(
        "These are fixed, simulated distances from a notional home location. "
        "They are not calculated from an address. Delivery remains available "
        "outside the pickup-trip radius."
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
    tax_rate_text = st.text_input(
        "Sales tax rate (%)",
        value=f"{DEFAULT_TAX_BASIS_POINTS / BASIS_POINTS_PER_PERCENT:.1f}",
    )

    if st.button("Continue to supply lists", type="primary"):
        errors: list[str] = []
        if any(not child["label"] for child in children):
            errors.append("Every entry needs a short label.")
        if any(not child["grade"] for child in children):
            errors.append("Every entry needs a grade.")
        try:
            if budget_mode == "combined":
                budget_total = money_to_cents(combined_budget)
                budget_allocations: dict[str, int] = {}
            else:
                budget_allocations = {
                    child_id: money_to_cents(value)
                    for child_id, value in budget_texts.items()
                }
                budget_total = sum(budget_allocations.values())
        except ValueError as error:
            errors.append(str(error))
            budget_total = 0
            budget_allocations = {}
        try:
            tax_basis_points = tax_percent_to_basis_points(tax_rate_text)
        except ValueError as error:
            errors.append(str(error))
            tax_basis_points = DEFAULT_TAX_BASIS_POINTS
        if shopping_mode == "custom" and not allowed_stores:
            errors.append("Choose at least one store in custom mode.")
        if errors:
            for error in errors:
                st.error(escape_streamlit_dollars(error))
            return
        st.session_state["intake"] = {
            "session_id": str(uuid4()),
            "children": tuple(children),
            "budget_total": budget_total,
            "budget_mode": budget_mode,
            "budget_allocations": budget_allocations,
            "shopping_mode": shopping_mode,
            "store_radius_miles": radius,
            "allowed_stores": allowed_stores,
            "max_stores": max_stores,
            "fulfillment_pref": fulfillment_preference,
            "tax_basis_points": tax_basis_points,
        }
        st.session_state["result"] = None
        st.session_state["list_identity_confirmed"] = False
        st.session_state["approval_outcomes"] = {}
        st.session_state["parent_decisions"] = ()
        st.session_state["checkout_confirmation"] = None
        st.session_state["screen"] = "lists"
        st.rerun()


def _build_list_inputs(
    st: Any,
    children: Sequence[Mapping[str, Any]],
) -> tuple[ListInput, ...]:
    inputs: list[ListInput] = []
    errors: list[str] = []
    for index, child in enumerate(children):
        mode = st.session_state.get(f"list_mode_{index}", "Paste text")
        if mode == "Upload a file":
            upload = st.session_state.get(f"list_upload_{index}")
            if upload is None:
                errors.append(f"{child['label']}: choose a file.")
                continue
            data = upload.getvalue()
            try:
                mime_type = validate_uploaded_document(upload.name, data)
            except ValueError as error:
                errors.append(f"{child['label']}: {error}")
                continue
            inputs.append(
                ListInput(
                    child_id=str(child["child_id"]),
                    source=data,
                    mime_type=mime_type,
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
                )
            )
    if errors:
        raise ValueError("\n".join(errors))
    return tuple(inputs)


def _render_lists(st: Any) -> None:
    intake = st.session_state["intake"]
    if intake is None:
        st.session_state["screen"] = "intake"
        st.rerun()
    children = intake["children"]
    st.header("Add one list for each entry")
    st.write(
        "Upload PDF, JPG, PNG, or TXT, or paste the list directly. "
        "Each file is validated before processing."
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
        if st.button("Rebuild using the saved lists"):
            st.session_state["result"] = None
            st.session_state["list_identity_confirmed"] = False
            st.session_state["screen"] = "working"
            st.rerun()
    for index, child in enumerate(children):
        with st.container(border=True):
            st.subheader(
                escape_streamlit_dollars(
                    f"{child['label']} · Grade {child['grade']}"
                )
            )
            st.radio(
                "List source",
                ("Paste text", "Upload a file"),
                horizontal=True,
                key=f"list_mode_{index}",
            )
            if st.session_state[f"list_mode_{index}"] == "Upload a file":
                st.file_uploader(
                    "Supply list",
                    type=("pdf", "jpg", "jpeg", "png", "txt"),
                    key=f"list_upload_{index}",
                )
                st.caption(
                    f"Maximum size: {MAX_UPLOAD_BYTES // 1_000_000} MB."
                )
            else:
                st.text_area(
                    "Paste the complete list",
                    height=220,
                    key=f"list_paste_{index}",
                    placeholder="Paste required items and optional sections…",
                )
    left, right = st.columns([1, 2])
    if left.button("Back"):
        st.session_state["screen"] = "intake"
        st.rerun()
    if right.button("Build my cart", type="primary"):
        try:
            list_inputs = _build_list_inputs(st, children)
        except ValueError as error:
            for message in str(error).splitlines():
                st.error(escape_streamlit_dollars(message))
            return
        st.session_state["list_inputs"] = list_inputs
        st.session_state["extracted_lists"] = {}
        st.session_state["extraction_errors"] = {}
        st.session_state["extraction_cache_ready"] = False
        st.session_state["list_identity_confirmed"] = False
        st.session_state["result"] = None
        st.session_state["screen"] = "working"
        st.rerun()


def _pipeline_session(intake: Mapping[str, Any]) -> PipelineSession:
    children = intake["children"]
    return PipelineSession(
        session_id=str(intake["session_id"]),
        children=tuple(child["child_id"] for child in children),
        budget_total=int(intake["budget_total"]),
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


def _extract_list_inputs(
    list_inputs: Sequence[ListInput],
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

    def extract_one(list_input: ListInput) -> ExtractionEnvelope:
        return validate_extraction_envelope(
            extract_document(
                list_input.source,
                child_id=list_input.child_id,
                mime_type=list_input.mime_type,
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
                    f"Read {done_count} of {len(list_inputs)} lists",
                )
            try:
                completed[list_input.child_id] = future.result()
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
    progress_callback: (
        Callable[[str, int, int, str], None] | None
    ) = None,
) -> PipelineResult:
    """Run later pipeline stages without making a second extraction call."""

    def cached_extractor(
        source: str | Path | bytes,
        *,
        child_id: str,
        mime_type: str | None,
        client: object | None,
    ) -> ExtractionEnvelope:
        del source, mime_type, client
        error = extraction_errors.get(child_id)
        if error is not None:
            raise error
        return extractions[child_id]

    return run_pipeline(
        session,
        list_inputs,
        offers=offers,
        extractor=cached_extractor,
        progress_callback=progress_callback,
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
        left, right = st.columns(2)
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
        st.rerun()
    if return_to_lists:
        st.session_state["screen"] = "lists"
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
    st.session_state["result"] = result
    if not result.extractions:
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
            st.session_state["screen"] = "lists"
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
    st.rerun()


def _render_working(st: Any) -> None:
    intake = st.session_state["intake"]
    list_inputs = st.session_state["list_inputs"]
    if intake is None or not list_inputs:
        st.error("Session setup or supply lists are missing.")
        if st.button("Return to lists"):
            st.session_state["screen"] = "lists"
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

    if not st.session_state["extraction_cache_ready"]:
        st.header("Reading the supply lists")
        with st.status("Extracting list details…", expanded=True) as status:
            def extraction_progress(
                stage: str,
                completed: int,
                total: int,
                detail: str,
            ) -> None:
                del stage, completed, total
                status.update(label=detail)

            extractions, extraction_errors = _extract_list_inputs(
                list_inputs,
                progress_callback=extraction_progress,
            )
            st.session_state["extracted_lists"] = extractions
            st.session_state["extraction_errors"] = extraction_errors
            st.session_state["extraction_cache_ready"] = True
            status.update(
                label="List extraction complete",
                state="complete",
            )

    extractions = st.session_state["extracted_lists"]
    extraction_errors = st.session_state["extraction_errors"]
    identity_warnings = detect_list_identity_warnings(
        extractions,
        intake["children"],
    )
    if (
        identity_warnings
        and not st.session_state["list_identity_confirmed"]
    ):
        _render_list_identity_warnings(st, identity_warnings)
        return

    st.header("Building the cart")
    with st.status("Planning the cart…", expanded=True) as status:
        last_detail = [""]

        def cart_progress(
            stage: str,
            completed: int,
            total: int,
            detail: str,
        ) -> None:
            del stage, completed, total
            if detail != last_detail[0]:
                status.update(label=detail)
                last_detail[0] = detail

        offers = _active_catalog_offers(
            frozenset(st.session_state["stockout_skus"])
        )
        try:
            result = _run_pipeline_from_cached_extractions(
                _pipeline_session(intake),
                list_inputs,
                extractions,
                extraction_errors,
                offers=offers,
                progress_callback=cart_progress,
            )
        except Exception as error:
            status.update(label="Cart build stopped", state="error")
            st.error(
                escape_streamlit_dollars(
                    "The cart could not be built. Your setup and lists are "
                    "still available. Technical detail: "
                    f"{type(error).__name__}: {error}"
                )
            )
            if st.button("Return to lists"):
                st.session_state["screen"] = "lists"
                st.rerun()
            return
        status.update(label="Cart proposal ready", state="complete")
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
        frozenset(st.session_state["stockout_skus"])
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


def _render_approval(st: Any) -> None:
    """Render cached decisions with a live, delta-only budget builder."""

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
        frozenset(st.session_state["stockout_skus"])
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
    presentations: tuple[ApprovalDisplayDecision, ...] = tuple(cache)
    generation = int(st.session_state["approval_generation"])
    offers_by_sku = {offer.sku: offer for offer in offers}

    st.header("Review the decisions")
    st.write(
        "Everything needing your input is collected here. "
        "The recommended choice is selected by default."
    )
    selections: dict[str, ApprovalDisplayOption] = {}
    budget_selected_ids: tuple[str, ...] = ()
    budget_evaluation: BudgetSelectionEvaluation | None = None
    budget_selection_error: str | None = None

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

            if (
                interrupt.kind == "budget_exceeded"
                and result.budget_analysis is not None
            ):
                st.markdown("#### Tier 1 — choose a whole plan")
                strategy_key = (
                    f"budget_strategy_{generation}_{interrupt.interrupt_id}"
                )
                strategy = st.radio(
                    "Choose one strategy",
                    presentation.options,
                    index=approval_default_index(presentation.options),
                    format_func=approval_option_label,
                    captions=tuple(
                        approval_option_caption(option)
                        for option in presentation.options
                    ),
                    key=strategy_key,
                )
                selections[interrupt.interrupt_id] = strategy
                last_strategy_key = f"{strategy_key}_last"
                last_strategy = st.session_state.get(last_strategy_key)
                custom_strategy = strategy.alternative_id.endswith("-custom")
                if last_strategy != strategy.alternative_id:
                    if not custom_strategy:
                        selected_set = frozenset(strategy.budget_action_ids)
                        for action in result.budget_analysis.actions:
                            checkbox_key = (
                                f"budget_action_{generation}_{action.action_id}"
                            )
                            st.session_state[checkbox_key] = (
                                action.action_id in selected_set
                            )
                    st.session_state[last_strategy_key] = (
                        strategy.alternative_id
                    )
                custom_option = next(
                    option
                    for option in presentation.options
                    if option.alternative_id.endswith("-custom")
                )

                def mark_budget_as_custom() -> None:
                    st.session_state[strategy_key] = custom_option
                    st.session_state[last_strategy_key] = (
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
                        st.checkbox(
                            escape_streamlit_dollars(
                                _budget_action_label(
                                    action,
                                    offers_by_sku,
                                    child_labels,
                                )
                            ),
                            key=checkbox_key,
                            on_change=mark_budget_as_custom,
                        )
                        st.caption(
                            escape_streamlit_dollars(
                                _budget_action_caption(action)
                            )
                        )

                st.write("Required items you could source yourself")
                for action in result.budget_analysis.omission_actions:
                    checkbox_key = (
                        f"budget_action_{generation}_{action.action_id}"
                    )
                    st.checkbox(
                        escape_streamlit_dollars(
                            _budget_action_label(
                                action,
                                offers_by_sku,
                                child_labels,
                            )
                        ),
                        key=checkbox_key,
                        on_change=mark_budget_as_custom,
                    )
                    st.caption(
                        escape_streamlit_dollars(
                            _budget_action_caption(action)
                        )
                    )

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
                    st.error(
                        escape_streamlit_dollars(budget_selection_error)
                    )
                else:
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

            st.info(
                escape_streamlit_dollars(
                    f"Recommendation: {presentation.recommendation}"
                )
            )
            selections[interrupt.interrupt_id] = st.radio(
                "Choose one",
                presentation.options,
                index=approval_default_index(presentation.options),
                format_func=approval_option_label,
                captions=tuple(
                    approval_option_caption(option)
                    for option in presentation.options
                ),
                key=(
                    f"approval_{generation}_{interrupt.interrupt_id}"
                ),
            )

    submitted = st.button(
        "Save decisions and continue",
        type="primary",
        use_container_width=True,
        disabled=budget_selection_error is not None,
    )
    if not submitted:
        return

    outcomes = dict(st.session_state["approval_outcomes"])
    response_log = DecisionLog(f"{result.session.session_id}-parent")
    for presentation in presentations:
        interrupt = presentation.interrupt
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

    st.session_state["approval_outcomes"] = outcomes
    st.session_state["budget_action_ids"] = budget_selected_ids
    st.session_state["approved_optimization"] = approved_optimization
    st.session_state["parent_decisions"] = (
        tuple(st.session_state["parent_decisions"]) + response_log.entries
    )
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
    if (
        cached_approved is not None
        and not st.session_state["include_addons"]
    ):
        return cached_approved, result.matches

    proposal = result.addon_proposal
    if (
        st.session_state["include_addons"]
        and proposal.eligible
        and proposal.optimization is not None
        and proposal.matches is not None
    ):
        optimization = proposal.optimization
        matches = proposal.matches
        unit_needs = proposal.purchase_needs
    else:
        optimization = result.proposed_cart
        matches = result.matches
        unit_needs = result.purchase_needs
    return (
        _apply_approval_outcomes(
            optimization,
            matches,
            unit_needs,
            presentations,
            st.session_state["approval_outcomes"],
            offers,
            stores,
            _optimization_config(result),
            budget_analysis=result.budget_analysis,
            budget_action_ids=st.session_state["budget_action_ids"],
        ),
        matches,
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
    st.subheader("Where to shop")
    for plan in _plans(optimization):
        for order in plan.store_orders:
            store = stores_by_id.get(order.store_id)
            store_name = store.name if store else "Unknown store"
            with st.expander(
                escape_streamlit_dollars(
                    (
                        f"{store_name} · "
                        f"{order.fulfillment_method.title()} · "
                        "Landed cost "
                        f"{format_streamlit_money(order.landed_cost)}"
                    )
                ),
                expanded=True,
            ):
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
    st.subheader("Per-child attribution")
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
            "Entry": child["label"],
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
    st.subheader("Substitutions and package choices")
    stores_by_id = {store.store_id: store for store in stores}
    rows = []
    for plan in _plans(optimization):
        for line in plan.lines:
            if line.substitution_type == SUBSTITUTION_NONE:
                continue
            candidate = matches.candidate(
                line.source_requirement_ids,
                line.sku,
            )
            reasons = (
                candidate.substitution_reasons
                if candidate is not None
                else ()
            )
            store = stores_by_id.get(line.store_id)
            rows.append(
                {
                    "Product": _product_name(line, matches),
                    "Store": (
                        store.name if store is not None else "Unknown store"
                    ),
                    "Review": SUBSTITUTION_SEVERITY_LABELS.get(
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
    if rows:
        st.table(escape_streamlit_data(rows))
    else:
        st.write("No substitutions were made.")


def _render_addons(
    st: Any,
    result: PipelineResult,
    child_labels: Mapping[str, str],
) -> None:
    proposal = result.addon_proposal
    if not proposal.eligible:
        st.session_state["include_addons"] = False
        return
    st.subheader("Optional classroom add-ons")
    st.success(
        "The required-item cart is at or below 90% of the budget, so these "
        "wish-list items can be considered."
    )
    st.table(
        escape_streamlit_data([
            {
                "For": _child_display_label(
                    item.child_id,
                    child_labels,
                ),
                "Type": item.requirement_type.title(),
                "List item": item.raw_text,
            }
            for item in proposal.items
        ])
    )
    if proposal.resulting_landed_cost_cents is not None:
        left, right = st.columns(2)
        left.metric(
            "Resulting landed cost",
            format_streamlit_money(
                proposal.resulting_landed_cost_cents
            ),
        )
        right.metric(
            "Added landed cost",
            format_streamlit_money(
                proposal.incremental_landed_cost_cents or 0
            ),
        )
    blockers = []
    if proposal.review_requirement_ids:
        blockers.append("one or more add-ons needs review")
    if proposal.gap_items:
        blockers.append("some add-ons are unavailable")
    if blockers:
        st.warning(
            "This add-on cannot be included yet because "
            + " and ".join(blockers)
            + "."
        )
        st.session_state["include_addons"] = False
        return
    st.checkbox(
        "Include these optional items in the simulated order",
        key="include_addons",
        help=(
            "The required-item recommendation stays unchanged unless you "
            "select this option."
        ),
    )


def _render_approvals_summary(
    st: Any,
    presentations: Sequence[ApprovalDisplayDecision],
) -> None:
    st.subheader("Approval outcomes")
    outcomes = st.session_state["approval_outcomes"]
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
                    alternative.label if alternative else "Pending"
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
    st.subheader("Items you chose to source yourself")
    st.warning(
        "This shopping plan is incomplete. The required items below are not "
        "included in the store cart."
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


def _approval_outcome_labels(
    presentations: Sequence[ApprovalDisplayDecision],
    outcomes: Mapping[str, str],
) -> dict[str, str]:
    labels: dict[str, str] = {}
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
            selected.label if selected is not None else "Pending"
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
        frozenset(st.session_state["stockout_skus"])
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
    optimization, matches = _effective_cart(
        st,
        result,
        approval_presentations,
        offers,
        stores,
    )
    st.header("Your proposed shopping plan")
    _render_budget_status(
        st,
        optimization,
        int(intake["budget_total"]),
    )
    if result.extraction_failures:
        st.warning(
            "The cart was built from the lists that succeeded. "
            "These entries could not be extracted:"
        )
        for child_id, reason in result.extraction_failures.items():
            st.write(
                escape_streamlit_dollars(
                    f"- {_child_display_label(child_id, child_labels)}: "
                    f"{reason}"
                )
            )

    _render_self_sourced_items(st, self_sourced_decisions)
    _render_cost_summary(st, optimization)
    _render_addons(st, result, child_labels)
    _render_store_breakdown(
        st,
        optimization,
        matches,
        stores,
        child_labels,
    )
    _render_per_child(
        st,
        optimization,
        children,
        intake["budget_allocations"],
    )
    _render_substitutions(st, optimization, matches, stores)
    _render_approvals_summary(st, approval_presentations)

    st.subheader("Demonstrate live re-planning")
    with st.container(border=True):
        st.write(
            "Choose a product from this cart and mark it out of stock. The "
            "agent will rebuild the plan from the cached lists using the "
            "remaining catalog inventory."
        )
        selected_skus = tuple(
            dict.fromkeys(
                line.sku
                for plan in _plans(optimization)
                for line in plan.lines
            )
        )
        if selected_skus:
            stockout_sku = st.selectbox(
                "Product to mark out of stock",
                selected_skus,
                format_func=lambda sku: escape_streamlit_dollars(
                    _catalog_product_label(sku, offers, stores)
                ),
            )
            if st.button(
                "Mark out of stock and re-plan",
                type="primary",
            ):
                st.session_state["stockout_skus"] = (
                    frozenset(st.session_state["stockout_skus"])
                    | {stockout_sku}
                )
                st.session_state["checkout_confirmation"] = None
                st.session_state["result"] = None
                st.session_state["screen"] = "working"
                st.rerun()
        else:
            st.info("There are no selected cart products to mark out of stock.")

    display_only = result.normalization.display_only_requirements
    if display_only:
        with st.expander("List notes that are not shopping items"):
            for requirement in display_only:
                st.write(
                    escape_streamlit_dollars(
                        "- "
                        f"{_child_display_label(requirement.source.child_id, child_labels)}: "
                        f"{requirement.source.raw_text}"
                    )
                )

    parent_decisions = tuple(st.session_state["parent_decisions"])
    with st.expander("Full decision log"):
        st.table(
            escape_streamlit_data([
                {
                    "Time": decision.timestamp.isoformat(
                        timespec="seconds"
                    ),
                    "Actor": decision.actor.title(),
                    "Type": decision.type.replace("_", " ").title(),
                    "Rationale": _humanize_internal_text(
                        decision.rationale,
                        offers,
                        stores,
                    ),
                }
                for decision in _decision_log(result, parent_decisions)
            ])
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
        ),
        self_sourced_decisions,
        parent_decisions,
    )
    st.download_button(
        "Download text shopping list",
        data=summary_text,
        file_name="school-supply-cart.txt",
        mime="text/plain",
    )

    st.subheader("Simulated checkout")
    checkout_label = "Place simulated order"
    if self_sourced_decisions:
        st.warning(
            "This checkout covers only the store-supplied items. Your overall "
            "school-supply plan remains incomplete until you source the listed "
            "required items yourself."
        )
        checkout_label = "Place partial simulated order"
    else:
        st.caption(
            "This creates an order confirmation only. No retailer account or "
            "payment information is used."
        )
    if st.button(checkout_label, type="primary"):
        confirmation = {
            "confirmation_id": (
                "SIM-" + result.session.session_id.split("-")[0].upper()
            ),
            "created_at": datetime.now(timezone.utc),
            "landed_cost": optimization.landed_cost,
            "is_partial": bool(self_sourced_decisions),
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

    left, right = st.columns(2)
    if left.button("Change shopping settings"):
        st.session_state["result"] = None
        st.session_state["checkout_confirmation"] = None
        st.session_state["screen"] = "intake"
        st.rerun()
    if right.button("Start a new session"):
        clear_session_data(st)
        st.rerun()


def main() -> None:
    """Run the complete Streamlit screen flow."""

    import streamlit as st

    st.set_page_config(
        page_title="School Supply Cart",
        page_icon="🛒",
        layout="wide",
    )
    st.markdown(
        """
        <style>
        .block-container {max-width: 1120px; padding-top: 1.5rem;}
        h1, h2, h3 {letter-spacing: -0.02em;}
        [data-testid="stMetric"] {
            border: 1px solid #e5e7eb;
            border-radius: 0.75rem;
            padding: 0.8rem;
            background: #ffffff;
        }
        [data-testid="stForm"] [role="radiogroup"] > label {
            align-items: flex-start;
            margin-bottom: 0.7rem;
            padding: 0.55rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _initialize_state(st)
    st.title("School Supply Cart")
    st.caption(
        "Turn one or more school lists into one clear, budget-aware plan."
    )
    _persistent_notice(st)
    screen = st.session_state["screen"]
    _screen_progress(st, screen)
    {
        "intake": _render_intake,
        "lists": _render_lists,
        "working": _render_working,
        "approval": _render_approval,
        "summary": _render_summary,
    }[screen](st)


if __name__ == "__main__":
    main()
