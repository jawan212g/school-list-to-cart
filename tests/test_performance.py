"""Structural tests for bounded, concurrent model-facing work."""

import json
from threading import Barrier, Lock

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
    MODEL_CALL_MAX_RETRIES,
    MODEL_CALL_TIMEOUT_SECONDS,
)
from agent.schema import ExtractionEnvelope
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
        del source, child_id, mime_type, client
        barrier.wait(timeout=1)
        return ExtractionEnvelope(requirements=())

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


def test_matching_batches_overlap_and_apply_timeout_retry() -> None:
    """FR-17: model batches overlap and every call is bounded and retryable."""

    categories = ("pencils", "pens", "rulers", "erasers")
    client = _ConcurrentClient()
    judge = OpenAISuitabilityJudge(client)  # type: ignore[arg-type]
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
            "timeout": MODEL_CALL_TIMEOUT_SECONDS,
            "max_retries": MODEL_CALL_MAX_RETRIES,
        }
        for options in client.options
    )
