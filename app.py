"""Streamlit interface for the school list-to-cart application."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.decisions import Decision, DecisionLog
from agent.extract import (
    MODEL_NAME,
    create_model_client,
    get_api_key_diagnostic,
)
from agent.gate import ApprovalBatch, ApprovalInterrupt
from agent.match import MatchResult
from agent.optimize import CartPlan, OptimizationResult
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
    SUBSTITUTION_NONE,
)
from agent.store_scope import (
    FulfillmentPreference,
    pickup_trip_is_within_radius,
    store_supports_fulfillment,
)
from data.loader import Store, load_catalog, load_stores


LOGGER = logging.getLogger(__name__)
CENTS_PER_DOLLAR = 100
BASIS_POINTS_PER_PERCENT = 100
MAX_TAX_PERCENT = Decimal("25")
MAX_STORE_RADIUS_MILES = 25.0
MAX_CLASSROOM_STUDENTS = 100
DEFAULT_BUDGET_TEXT = "150.00"
DEFAULT_RADIUS_MILES = 10.0
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
    """Format integer cents at the interface boundary."""

    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return (
        f"{sign}${absolute // CENTS_PER_DOLLAR:,}."
        f"{absolute % CENTS_PER_DOLLAR:02d}"
    )


def format_cost_delta(cents: int) -> str:
    """Format one approval alternative's landed-cost change."""

    if cents == 0:
        return "no cost change"
    direction = "adds" if cents > 0 else "saves"
    return f"{direction} {format_money(abs(cents))}"


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
    parent_decisions: Sequence[Decision],
) -> str:
    """Build the manual-shopping export artifact (FR-34, FR-36)."""

    stores_by_id = {store.store_id: store for store in stores}
    item_subtotal, tax, fees = _combined_costs(optimization)
    lines = [
        "SCHOOL SUPPLY CART",
        "Simulated catalog; fictional stores; no payment was collected.",
        "",
        f"ITEM SUBTOTAL: {format_money(item_subtotal)}",
        f"TAX: {format_money(tax)}",
        f"FULFILLMENT FEES: {format_money(fees)}",
        f"LANDED COST: {format_money(optimization.landed_cost)}",
        "",
    ]
    for plan in _plans(optimization):
        for order in plan.store_orders:
            store_name = stores_by_id.get(order.store_id)
            lines.append(
                (
                    f"{store_name.name if store_name else order.store_id} "
                    f"— {order.fulfillment_method.title()}"
                )
            )
            for cart_line in order.lines:
                allocations = ", ".join(
                    f"{child_labels.get(child_id, child_id)}: {units}"
                    for child_id, units in cart_line.allocated_to.items()
                )
                lines.append(
                    (
                        f"  {cart_line.canonical_item} | {cart_line.sku} | "
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
            f"{decision.type} | {decision.rationale}"
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
        "result": None,
        "approval_outcomes": {},
        "parent_decisions": (),
        "include_addons": False,
        "checkout_confirmation": None,
        "stockout_skus": frozenset(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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
            f"API key found: {'Yes' if diagnostic.found else 'No'}"
        )
        st.write(f"Credential source: {diagnostic.source or 'None'}")
        st.write(
            "Key preview: "
            f"{diagnostic.masked_key or 'Not available'}"
        )
        st.write(f"Configured model: {MODEL_NAME}")
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
                st.success(message)
            else:
                st.error(message)
                st.caption(
                    "The complete exception and traceback were written to "
                    "the Streamlit application logs."
                )


def _render_intake(st: Any) -> None:
    st.header("Set up this shopping session")
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
            st.subheader(f"Entry {index + 1}")
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
            "Combined budget ($)",
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
                f"{child['label'] or f'Entry {index + 1}'} budget ($)",
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
        store_radius_rows(
            stores,
            radius,
            fulfillment_preference,
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
                st.error(error)
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
            st.session_state["screen"] = "working"
            st.rerun()
    for index, child in enumerate(children):
        with st.container(border=True):
            st.subheader(f"{child['label']} · Grade {child['grade']}")
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
                st.error(message)
            return
        st.session_state["list_inputs"] = list_inputs
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


def _render_working(st: Any) -> None:
    st.header("Building the cart")
    st.write("This usually takes one to three minutes for multiple lists.")
    intake = st.session_state["intake"]
    list_inputs = st.session_state["list_inputs"]
    if intake is None or not list_inputs:
        st.error("Session setup or supply lists are missing.")
        if st.button("Return to lists"):
            st.session_state["screen"] = "lists"
            st.rerun()
        return
    with st.status("Reading and planning…", expanded=True) as status:
        st.write("Reading and validating each list")
        st.write("Normalizing quantities and combining shared needs")
        st.write("Matching products from the simulated catalog")
        st.write("Optimizing packages, stores, tax, and fulfillment")
        st.write("Checking the approval gate and optional add-ons")
        offers = tuple(load_catalog())
        stockout_skus = st.session_state["stockout_skus"]
        if stockout_skus:
            offers = tuple(
                replace(offer, stock_qty=0)
                if offer.sku in stockout_skus
                else offer
                for offer in offers
            )
        try:
            result = run_pipeline(
                _pipeline_session(intake),
                list_inputs,
                offers=offers,
            )
        except Exception as error:
            status.update(label="Cart build stopped", state="error")
            st.error(
                "The cart could not be built. Your setup and lists are still "
                f"available. Technical detail: {type(error).__name__}: {error}"
            )
            if st.button("Return to lists"):
                st.session_state["screen"] = "lists"
                st.rerun()
            return
        if not result.extractions:
            status.update(label="No lists could be extracted", state="error")
            st.error(
                "Every list failed extraction. Return to the lists screen and "
                "check the files or pasted text."
            )
            for child_id, reason in result.extraction_failures.items():
                st.warning(f"{child_id}: {reason}")
            if st.button("Return to lists"):
                st.session_state["screen"] = "lists"
                st.rerun()
            return
        status.update(label="Cart proposal ready", state="complete")
    st.session_state["result"] = result
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


def _render_approval(st: Any) -> None:
    result: PipelineResult | None = st.session_state["result"]
    if result is None:
        st.session_state["screen"] = "working"
        st.rerun()
    interrupts = _all_interrupts(result.approval_batch)
    st.header("Review the decisions")
    st.write(
        "Everything needing your input is collected here. "
        "The recommended choice appears first."
    )
    selections: dict[str, Any] = {}
    for index, interrupt in enumerate(interrupts):
        with st.container(border=True):
            st.subheader(
                f"{index + 1}. {interrupt.kind.replace('_', ' ').title()}"
            )
            st.write(interrupt.message)
            st.info(f"Recommendation: {interrupt.recommendation}")
            alternatives = interrupt.alternatives
            existing = st.session_state["approval_outcomes"].get(
                interrupt.interrupt_id
            )
            default_index = next(
                (
                    alternative_index
                    for alternative_index, alternative in enumerate(
                        alternatives
                    )
                    if alternative.alternative_id == existing
                ),
                0,
            )
            selections[interrupt.interrupt_id] = st.radio(
                "Choose one",
                alternatives,
                index=default_index,
                format_func=lambda alternative: (
                    f"{alternative.label} "
                    f"({format_cost_delta(alternative.cost_delta_cents)})"
                ),
                key=f"approval_{interrupt.interrupt_id}",
            )
    if st.button("Save decisions and continue", type="primary"):
        outcomes = dict(st.session_state["approval_outcomes"])
        response_log = DecisionLog(
            f"{result.session.session_id}-parent"
        )
        for interrupt in interrupts:
            alternative = selections[interrupt.interrupt_id]
            outcomes[interrupt.interrupt_id] = alternative.alternative_id
            response_log.record_approval_response(
                (
                    f"{interrupt.kind.replace('_', ' ')}: "
                    f"{alternative.label} "
                    f"({format_cost_delta(alternative.cost_delta_cents)})."
                ),
                affected_lines=interrupt.affected_lines,
            )
        st.session_state["approval_outcomes"] = outcomes
        st.session_state["parent_decisions"] = (
            tuple(st.session_state["parent_decisions"])
            + response_log.entries
        )
        st.session_state["screen"] = "summary"
        st.rerun()


def _effective_cart(
    st: Any,
    result: PipelineResult,
) -> tuple[OptimizationResult, MatchResult]:
    proposal = result.addon_proposal
    if (
        st.session_state["include_addons"]
        and proposal.eligible
        and proposal.optimization is not None
        and proposal.matches is not None
    ):
        return proposal.optimization, proposal.matches
    return result.proposed_cart, result.matches


def _render_cost_summary(
    st: Any,
    optimization: OptimizationResult,
    budget_cents: int,
) -> None:
    item_subtotal, tax, fees = _combined_costs(optimization)
    columns = st.columns(4)
    columns[0].metric("Item subtotal", format_money(item_subtotal))
    columns[1].metric("Tax", format_money(tax))
    columns[2].metric("Fulfillment fees", format_money(fees))
    columns[3].metric("Landed cost", format_money(optimization.landed_cost))
    variance = budget_cents - optimization.landed_cost
    if variance >= 0:
        st.success(f"Budget remaining: {format_money(variance)}")
    else:
        st.error(f"Budget shortfall: {format_money(abs(variance))}")


def _render_store_breakdown(
    st: Any,
    optimization: OptimizationResult,
    stores: Sequence[Store],
    child_labels: Mapping[str, str],
) -> None:
    stores_by_id = {store.store_id: store for store in stores}
    st.subheader("Where to shop")
    for plan in _plans(optimization):
        for order in plan.store_orders:
            store = stores_by_id.get(order.store_id)
            store_name = store.name if store else order.store_id
            with st.expander(
                (
                    f"{store_name} · {order.fulfillment_method.title()} · "
                    f"Landed cost {format_money(order.landed_cost)}"
                ),
                expanded=True,
            ):
                rows = []
                for line in order.lines:
                    allocations = ", ".join(
                        f"{child_labels.get(child_id, child_id)}: {units}"
                        for child_id, units in line.allocated_to.items()
                    )
                    rows.append(
                        {
                            "Item": line.canonical_item.replace("_", " ").title(),
                            "SKU": line.sku,
                            "Packs": line.packs_purchased,
                            "Needed": line.units_needed,
                            "Bought": line.units_purchased,
                            "For": allocations,
                            "Line cost": format_money(line.line_cost),
                        }
                    )
                st.table(rows)
                a, b, c, d = st.columns(4)
                a.metric("Item subtotal", format_money(order.item_subtotal))
                b.metric("Tax", format_money(order.tax))
                c.metric(
                    "Fulfillment fee",
                    format_money(order.fulfillment_fee),
                )
                d.metric("Landed cost", format_money(order.landed_cost))


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
            "Item subtotal": format_money(item_costs.get(child_id, 0)),
            "Landed cost": format_money(landed_costs.get(child_id, 0)),
        }
        if child_id in allocations:
            variance = allocations[child_id] - landed_costs.get(child_id, 0)
            row["Budget variance"] = format_money(variance)
        rows.append(row)
    st.table(rows)


def _render_substitutions(
    st: Any,
    optimization: OptimizationResult,
    matches: MatchResult,
) -> None:
    st.subheader("Substitutions and package choices")
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
            rows.append(
                {
                    "Item": line.canonical_item.replace("_", " ").title(),
                    "SKU": line.sku,
                    "Severity": line.substitution_type,
                    "Reason": ", ".join(reasons) or "package-size overage",
                }
            )
    if rows:
        st.table(rows)
    else:
        st.write("No substitutions were made.")


def _render_addons(st: Any, result: PipelineResult) -> None:
    proposal = result.addon_proposal
    st.subheader("Optional classroom add-ons")
    if not proposal.items:
        st.write("No donation or optional items were found.")
        return
    if not proposal.eligible:
        st.caption(proposal.reason)
        return
    st.success(
        "The required-item cart is at or below 90% of the budget, so these "
        "wish-list items can be considered."
    )
    st.table(
        [
            {
                "For": item.child_id,
                "Type": item.requirement_type.title(),
                "List item": item.raw_text,
            }
            for item in proposal.items
        ]
    )
    if proposal.resulting_landed_cost_cents is not None:
        left, right = st.columns(2)
        left.metric(
            "Resulting landed cost",
            format_money(proposal.resulting_landed_cost_cents),
        )
        right.metric(
            "Added landed cost",
            format_money(proposal.incremental_landed_cost_cents or 0),
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


def _render_approvals_summary(st: Any, result: PipelineResult) -> None:
    st.subheader("Approval outcomes")
    outcomes = st.session_state["approval_outcomes"]
    interrupts = _all_interrupts(result.approval_batch)
    if not interrupts:
        st.write("No approvals were required.")
        return
    rows = []
    for interrupt in interrupts:
        selected_id = outcomes.get(interrupt.interrupt_id)
        alternative = next(
            (
                option
                for option in interrupt.alternatives
                if option.alternative_id == selected_id
            ),
            None,
        )
        rows.append(
            {
                "Decision": interrupt.kind.replace("_", " ").title(),
                "Issue": interrupt.message,
                "Outcome": (
                    alternative.label if alternative else "Pending"
                ),
            }
        )
    st.table(rows)


def _approval_outcome_labels(
    result: PipelineResult,
    outcomes: Mapping[str, str],
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for interrupt in _all_interrupts(result.approval_batch):
        selected_id = outcomes.get(interrupt.interrupt_id)
        selected = next(
            (
                alternative
                for alternative in interrupt.alternatives
                if alternative.alternative_id == selected_id
            ),
            None,
        )
        labels[interrupt.interrupt_id] = (
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
    st.header("Your proposed shopping plan")
    if result.extraction_failures:
        st.warning(
            "The cart was built from the lists that succeeded. "
            "These entries could not be extracted:"
        )
        for child_id, reason in result.extraction_failures.items():
            st.write(f"- {child_labels.get(child_id, child_id)}: {reason}")

    _render_addons(st, result)
    optimization, matches = _effective_cart(st, result)
    _render_cost_summary(st, optimization, int(intake["budget_total"]))
    _render_store_breakdown(st, optimization, stores, child_labels)
    _render_per_child(
        st,
        optimization,
        children,
        intake["budget_allocations"],
    )
    _render_substitutions(st, optimization, matches)
    _render_approvals_summary(st, result)

    display_only = result.normalization.display_only_requirements
    if display_only:
        with st.expander("List notes that are not shopping items"):
            for requirement in display_only:
                st.write(
                    f"- {child_labels.get(requirement.source.child_id, requirement.source.child_id)}: "
                    f"{requirement.source.raw_text}"
                )

    parent_decisions = tuple(st.session_state["parent_decisions"])
    with st.expander("Full decision log"):
        st.table(
            [
                {
                    "Time": decision.timestamp.isoformat(
                        timespec="seconds"
                    ),
                    "Actor": decision.actor.title(),
                    "Type": decision.type.replace("_", " ").title(),
                    "Rationale": decision.rationale,
                }
                for decision in _decision_log(result, parent_decisions)
            ]
        )

    summary_text = build_text_summary(
        result,
        optimization,
        matches,
        stores,
        child_labels,
        _approval_outcome_labels(
            result,
            st.session_state["approval_outcomes"],
        ),
        parent_decisions,
    )
    st.download_button(
        "Download text shopping list",
        data=summary_text,
        file_name="school-supply-cart.txt",
        mime="text/plain",
    )

    with st.expander("Demonstrate a stockout and re-plan"):
        selected_skus = tuple(
            dict.fromkeys(
                line.sku
                for plan in _plans(optimization)
                for line in plan.lines
            )
        )
        stockout_sku = st.selectbox(
            "Mark one selected SKU out of stock",
            selected_skus,
        )
        if st.button("Inject stockout and rebuild"):
            st.session_state["stockout_skus"] = (
                frozenset(st.session_state["stockout_skus"])
                | {stockout_sku}
            )
            st.session_state["checkout_confirmation"] = None
            st.session_state["result"] = None
            st.session_state["screen"] = "working"
            st.rerun()

    st.subheader("Simulated checkout")
    st.caption(
        "This creates an order confirmation only. No retailer account or "
        "payment information is used."
    )
    if st.button("Place simulated order", type="primary"):
        confirmation = {
            "confirmation_id": (
                "SIM-" + result.session.session_id.split("-")[0].upper()
            ),
            "created_at": datetime.now(timezone.utc),
            "landed_cost": optimization.landed_cost,
        }
        st.session_state["checkout_confirmation"] = confirmation
    confirmation = st.session_state["checkout_confirmation"]
    if confirmation:
        st.success(
            f"Order {confirmation['confirmation_id']} confirmed at "
            f"{confirmation['created_at'].strftime('%Y-%m-%d %H:%M UTC')}. "
            f"Landed cost: {format_money(confirmation['landed_cost'])}."
        )

    left, right = st.columns(2)
    if left.button("Change shopping settings"):
        st.session_state["result"] = None
        st.session_state["checkout_confirmation"] = None
        st.session_state["screen"] = "intake"
        st.rerun()
    if right.button("Start a new session"):
        st.session_state.clear()
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
