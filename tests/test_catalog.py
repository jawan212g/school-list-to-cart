"""Consistency checks for the seeded catalog build block."""

from collections import defaultdict

from data.loader import load_catalog, load_stores


def test_seeded_catalog_loads() -> None:
    """The expanded catalog contains four stores and broad real-list coverage."""

    stores = load_stores()
    offers = load_catalog()

    assert len(stores) == 4
    assert 150 <= len(offers) <= 175
    assert len({offer.category for offer in offers}) == 35
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


def test_catalog_attribute_evidence_and_exact_school_sizes() -> None:
    """Matching data records checkable evidence and common exact sizes."""

    offers = load_catalog()
    by_sku = {offer.sku: offer for offer in offers}

    assert by_sku["VD-PEN-TIC-024"].attributes["pre_sharpened"] is True
    assert by_sku["VD-PBX-VB-001"].attributes["length_inches"] == 8
    assert by_sku["VD-GLU-VB-006"].attributes["size_label"] == "large"
    assert any(
        offer.category == "binders"
        and offer.attributes.get("capacity_inches") == 1.5
        for offer in offers
    )
    assert any(
        offer.category == "dividers"
        and offer.attributes.get("tabs_per_set") == 5
        for offer in offers
    )


def test_catalog_covers_categories_observed_in_real_district_lists() -> None:
    """New visual-list categories have stocked choices without losing old ones."""

    offers = tuple(
        offer for offer in load_catalog() if offer.stock_qty > 0
    )
    categories = {offer.category for offer in offers}
    requested = {
        "play_dough",
        "modeling_compound",
        "watercolor_paints",
        "dry_erase_markers",
        "permanent_markers",
        "sticky_notes",
        "index_cards",
        "hand_sanitizer",
        "baby_wipes",
        "water_bottles",
        "pencil_sharpeners",
        "pencil_pouches",
        "spiral_notebooks",
        "dividers",
        "folders",
        "binders",
        "erasers",
    }

    assert requested <= categories
    assert {
        offer.attributes.get("style")
        for offer in offers
        if offer.category == "erasers"
    } >= {"block", "cap", "kneaded"}
    assert {
        offer.attributes.get("capacity_inches")
        for offer in offers
        if offer.category == "binders"
    } >= {1, 1.5, 2}
    assert any(
        offer.category == "folders"
        and offer.attributes.get("material") == "plastic"
        for offer in offers
    )


def test_edited_constraints_retain_satisfying_and_nonmatching_choices() -> None:
    """Catalog edits must not make large, size, or sharpened checks trivial."""

    stocked = tuple(
        offer for offer in load_catalog() if offer.stock_qty > 0
    )
    glue_sticks = tuple(
        offer for offer in stocked if offer.category == "glue_sticks"
    )
    large_glue = tuple(
        offer
        for offer in glue_sticks
        if offer.attributes.get("size_label") == "large"
    )
    small_glue = tuple(
        offer
        for offer in glue_sticks
        if offer.attributes.get("size_label") == "standard"
    )
    pencil_boxes = tuple(
        offer for offer in stocked if offer.category == "pencil_boxes"
    )
    ticonderoga = tuple(
        offer
        for offer in stocked
        if offer.category == "pencils"
        and offer.brand == "Ticonderoga"
    )

    assert {offer.sku for offer in large_glue}.isdisjoint(
        offer.sku for offer in small_glue
    )
    assert min(offer.pack_price for offer in large_glue) > min(
        offer.pack_price for offer in small_glue
    )
    assert any(
        offer.attributes.get("length_inches") == 8
        for offer in pencil_boxes
    )
    assert any(
        offer.attributes.get("length_inches") != 8
        for offer in pencil_boxes
    )
    assert any(
        offer.attributes.get("pre_sharpened") is True
        for offer in ticonderoga
    )
    assert any(
        offer.attributes.get("pre_sharpened") is False
        for offer in ticonderoga
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
