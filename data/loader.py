"""Load the seeded D-3 catalog into the entities defined by BRD Section 8."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Store:
    """A fictional retailer and its fulfillment terms (BRD Section 8)."""

    store_id: str
    name: str
    distance_miles: float
    pickup_fee: int
    pickup_minimum: int
    delivery_fee: int
    delivery_minimum: int
    tax_applies: bool
    pickup_available: bool = True


@dataclass(frozen=True)
class Offer:
    """One purchasable product at one store (BRD Sections 5 and 8)."""

    sku: str
    store_id: str
    brand: str
    title: str
    category: str
    pack_size: int
    unit_price: int
    pack_price: int
    stock_qty: int
    is_returnable: bool
    attributes: dict[str, Any]


def _read_json(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        contents: Any = json.load(source)

    if not isinstance(contents, list) or not all(
        isinstance(row, dict) for row in contents
    ):
        raise ValueError(f"{path} must contain a JSON array of objects")

    return contents


def load_stores(path: str | Path | None = None) -> list[Store]:
    """Load the four fictional stores selected by decision D-3."""

    source_path = Path(path) if path is not None else DATA_DIR / "stores.json"
    rows = _read_json(source_path)
    return [Store(**row) for row in rows]


def load_catalog(path: str | Path | None = None) -> list[Offer]:
    """Load the seeded offers that form the FR-17 candidate pool."""

    source_path = Path(path) if path is not None else DATA_DIR / "catalog.json"
    rows = _read_json(source_path)
    return [Offer(**row) for row in rows]
