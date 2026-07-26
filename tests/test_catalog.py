"""Consistency checks for the seeded catalog build block."""

from collections import defaultdict

from data.loader import load_catalog, load_stores


def test_seeded_catalog_loads() -> None:
    """The catalog contains the four stores and roughly 120 offers."""

    stores = load_stores()
    offers = load_catalog()

    assert len(stores) == 4
    assert 110 <= len(offers) <= 130
    assert len({offer.category for offer in offers}) == 25
    assert all(isinstance(offer.pack_price, int) for offer in offers)
    assert all(isinstance(offer.unit_price, int) for offer in offers)


def test_every_offer_references_a_valid_store() -> None:
    """No offer is orphaned from the seeded store table."""

    store_ids = {store.store_id for store in load_stores()}

    assert all(offer.store_id in store_ids for offer in load_catalog())


def test_single_source_items_create_real_availability_constraints() -> None:
    """At least two canonical items can be sourced from only one store."""

    stocked_at: dict[str, set[str]] = defaultdict(set)
    for offer in load_catalog():
        if offer.stock_qty > 0:
            stocked_at[offer.category].add(offer.store_id)

    single_source_items = {
        category
        for category, store_ids in stocked_at.items()
        if len(store_ids) == 1
    }

    assert len(single_source_items) >= 2


def test_at_least_three_larger_packs_are_worse_value() -> None:
    """Pack-size choice cannot safely assume that bigger is always cheaper."""

    groups: dict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
    for offer in load_catalog():
        if offer.stock_qty > 0:
            key = (offer.store_id, offer.category, offer.brand)
            groups[key].append((offer.pack_size, offer.pack_price))

    non_monotonic_groups: set[tuple[str, str, str]] = set()
    for group, sizes_and_prices in groups.items():
        for small_size, small_price in sizes_and_prices:
            for large_size, large_price in sizes_and_prices:
                if (
                    large_size > small_size
                    and large_price * small_size > small_price * large_size
                ):
                    non_monotonic_groups.add(group)
                    break

    assert len(non_monotonic_groups) >= 3


def test_catalog_contains_required_pack_and_brand_choices() -> None:
    """Pencils and brand-sensitive art supplies include meaningful choices."""

    offers = load_catalog()
    pencil_sizes = {
        offer.pack_size
        for offer in offers
        if offer.category == "pencils" and offer.stock_qty > 0
    }
    brands_by_category = {
        category: {
            offer.brand
            for offer in offers
            if offer.category == category and offer.stock_qty > 0
        }
        for category in ("pencils", "crayons", "colored_pencils")
    }

    assert {8, 12, 24, 48} <= pencil_sizes
    assert {"Value Basics", "Ticonderoga"} <= brands_by_category["pencils"]
    assert {"Value Basics", "Crayola"} <= brands_by_category["crayons"]
    assert {"Value Basics", "Crayola"} <= brands_by_category["colored_pencils"]


def test_catalog_attribute_evidence_and_known_size_gaps() -> None:
    """Matching data records checkable evidence without inventing exact sizes."""

    offers = load_catalog()
    by_sku = {offer.sku: offer for offer in offers}

    assert by_sku["VD-PEN-TIC-024"].attributes["pre_sharpened"] is True
    assert by_sku["VD-PBX-VB-001"].attributes["length_inches"] == 8
    assert by_sku["VD-GLU-VB-006"].attributes["size_label"] == "large"
    assert not any(
        offer.category == "binders"
        and offer.attributes.get("capacity_inches") == 1.5
        for offer in offers
    )
    assert not any(
        offer.category == "dividers"
        and offer.attributes.get("tabs_per_set") == 5
        for offer in offers
    )


def test_catalog_includes_stockouts_and_high_value_nonreturnable_item() -> None:
    """The approval and availability paths have seeded data to exercise."""

    offers = load_catalog()

    assert any(offer.stock_qty == 0 for offer in offers)
    assert any(
        not offer.is_returnable and offer.pack_price > 1500
        for offer in offers
    )


def test_store_profiles_encode_distinct_tradeoffs() -> None:
    """The four D-3 stores differ in selection, location, and fulfillment."""

    stores = {store.store_id: store for store in load_stores()}
    stocked_categories: dict[str, set[str]] = defaultdict(set)
    for offer in load_catalog():
        if offer.stock_qty > 0:
            stocked_categories[offer.store_id].add(offer.category)

    pickup_stores = [
        store for store in stores.values() if store.pickup_available
    ]

    assert stores["NEIGHBOR_MART"].pickup_fee == 0
    assert not stores["SUPPLY_CLOUD"].pickup_available
    assert stores["VALUE_DEPOT"].distance_miles == max(
        store.distance_miles for store in pickup_stores
    )
    assert stores["SCHOLARS_CORNER"].distance_miles == min(
        store.distance_miles for store in pickup_stores
    )
    assert (
        len(stocked_categories["SUPPLY_CLOUD"])
        > len(stocked_categories["VALUE_DEPOT"])
        > len(stocked_categories["NEIGHBOR_MART"])
        > len(stocked_categories["SCHOLARS_CORNER"])
    )
