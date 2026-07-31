"""Structural tests for bounded, concurrent model-facing work."""

import json
import logging
from threading import Barrier, Lock

import pytest

from agent.aggregate import UnitNeed
from agent.match import (
    MATCH_DATA_END,
    MATCH_DATA_START,
    OpenAISuitabilityJudge,
    StructuredSuitabilityJudge,
    SuitabilityCase,
    SuitabilityDecision,
    SuitabilityEnvelope,
)
from agent.pipeline import ListInput, PipelineSession, run_pipeline
from agent.rules import (
    MATCHING_MODEL_TIMEOUT_SECONDS,
    MODEL_CALL_MAX_RETRIES,
)
from agent.schema import ExtractionEnvelope, Requirement
from data.loader import Offer, Store


def _store() -> Store:
    return Store(
        store_id="STORE",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )


def _offer(sku: str, category: str) -> Offer:
    return Offer(
        sku=sku,
        store_id="STORE",
        brand="Test",
        title=sku,
        category=category,
        pack_size=1,
        unit_price=100,
        pack_price=100,
        stock_qty=10,
        is_returnable=True,
        attributes={},
    )


def _need(index: int, category: str) -> UnitNeed:
    return UnitNeed(
        canonical_item=category,
        quantity=1,
        brand_lock=None,
        unit_type="each",
        exclusions=(),
        is_required=True,
        attributes={},
        allocated_to={f"child-{index}": 1},
        source_requirement_ids=(f"req-{index}",),
    )


def test_two_list_extractions_run_concurrently() -> None:
    """FR-06: two independent list reads overlap instead of running serially."""

    barrier = Barrier(2)

    def extractor(
        source: object,
        *,
        child_id: str,
        mime_type: str | None,
        client: object | None,
    ) -> ExtractionEnvelope:
        del source, mime_type, client
        barrier.wait(timeout=1)
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="display-note",
                    child_id=child_id,
                    raw_text="Label all supplies",
                    canonical_item="non_purchasable",
                    quantity=1,
                    is_required=False,
                    is_purchasable=False,
                    requirement_type="optional",
                    extraction_confidence=1.0,
                ),
            )
        )

    progress_events: list[tuple[str, int, int]] = []
    result = run_pipeline(
        PipelineSession(
            session_id="parallel-extraction",
            children=("one", "two"),
            budget_total=1_000,
        ),
        (
            ListInput("one", "first list"),
            ListInput("two", "second list"),
        ),
        stores=(_store(),),
        offers=(),
        extractor=extractor,
        suitability_judge=StructuredSuitabilityJudge(),
        progress_callback=lambda stage, done, total, detail: (
            progress_events.append((stage, done, total))
        ),
    )

    assert tuple(result.extractions) == ("one", "two")
    assert ("extraction", 2, 2) in progress_events
    assert any(stage == "optimization" for stage, _, _ in progress_events)


class _ConcurrentResponses:
    def __init__(self) -> None:
        self.barrier = Barrier(4)
        self.lock = Lock()
        self.active = 0
        self.maximum_active = 0

    def parse(self, **kwargs: object) -> object:
        input_text = str(kwargs["input"])
        serialized = input_text.removeprefix(
            f"{MATCH_DATA_START}\n"
        ).removesuffix(f"\n{MATCH_DATA_END}")
        payload = json.loads(serialized)
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        self.barrier.wait(timeout=1)
        decisions = tuple(
            SuitabilityDecision(
                need_key=row["need_key"],
                sku=row["sku"],
                suitable=True,
                confidence=0.95,
                reason="Concurrent fixed judgment.",
            )
            for row in payload
        )
        with self.lock:
            self.active -= 1
        return type(
            "Response",
            (),
            {"output_parsed": SuitabilityEnvelope(decisions=decisions)},
        )()


class _ConcurrentClient:
    def __init__(self) -> None:
        self.responses = _ConcurrentResponses()
        self.options: list[dict[str, object]] = []

    def with_options(self, **kwargs: object) -> "_ConcurrentClient":
        self.options.append(kwargs)
        return self


class _TimeoutResponses:
    def parse(self, **kwargs: object) -> object:
        del kwargs
        raise TimeoutError("matching batch exceeded its request limit")


class _TimeoutClient:
    def __init__(self) -> None:
        self.responses = _TimeoutResponses()
        self.options: list[dict[str, object]] = []

    def with_options(self, **kwargs: object) -> "_TimeoutClient":
        self.options.append(kwargs)
        return self


def test_matching_batches_overlap_and_apply_timeout_retry() -> None:
    """FR-17: model batches overlap and every call is bounded and retryable."""

    categories = ("pencils", "pens", "rulers", "erasers")
    client = _ConcurrentClient()
    progress: list[tuple[str, int, int, str]] = []
    judge = OpenAISuitabilityJudge(  # type: ignore[arg-type]
        client,
        progress_callback=lambda *event: progress.append(event),
    )
    decisions = judge.judge(
        tuple(
            SuitabilityCase(
                need_key=f"req-{index}",
                unit_need=_need(index, category),
                offer=_offer(f"SKU-{index}", category),
            )
            for index, category in enumerate(categories)
        )
    )

    assert len(decisions) == 4
    assert client.responses.maximum_active == 4
    assert len(client.options) == 4
    assert all(
        options == {
            "timeout": MATCHING_MODEL_TIMEOUT_SECONDS,
            "max_retries": MODEL_CALL_MAX_RETRIES,
        }
        for options in client.options
    )
    assert progress[0] == (
        "matching",
        0,
        4,
        "Matching 0 of 4 item types",
    )
    assert all(total == 4 for _, _, total, _ in progress)
    assert MATCHING_MODEL_TIMEOUT_SECONDS == 90.0


def test_matching_batch_failure_logs_elapsed_time_and_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A matching transport failure leaves timing evidence in service logs."""

    client = _TimeoutClient()
    judge = OpenAISuitabilityJudge(client)  # type: ignore[arg-type]

    with caplog.at_level(logging.ERROR, logger="agent.match"):
        with pytest.raises(TimeoutError, match="request limit"):
            judge.judge(
                (
                    SuitabilityCase(
                        need_key="req-timeout",
                        unit_need=_need(1, "pencils"),
                        offer=_offer("SKU-TIMEOUT", "pencils"),
                    ),
                )
            )

    assert "Semantic matching batch failed after" in caplog.text
    assert "against a 90.0-second request limit" in caplog.text
    assert "needs=1" in caplog.text
