"""Shared fulfillment-aware store scope rules."""

from __future__ import annotations

from typing import Literal

from data.loader import Store


FulfillmentPreference = Literal["pickup", "delivery", "either"]


def pickup_trip_is_within_radius(
    store: Store,
    store_radius_miles: float | None,
) -> bool:
    """Return whether a pickup trip is available within the FR-04 radius."""

    return store.pickup_available and (
        store_radius_miles is None
        or store.distance_miles <= store_radius_miles
    )


def store_supports_fulfillment(
    store: Store,
    store_radius_miles: float | None,
    fulfillment_preference: FulfillmentPreference,
) -> bool:
    """Apply radius only to fulfillment methods that require a trip (FR-04)."""

    if fulfillment_preference == "pickup":
        return pickup_trip_is_within_radius(store, store_radius_miles)
    if fulfillment_preference in {"delivery", "either"}:
        return True
    raise ValueError(
        f"Unsupported fulfillment preference: {fulfillment_preference}"
    )
