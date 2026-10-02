"""Deterministic master-data catalog for Aura Brands and Apex Retail."""

from decimal import ROUND_HALF_UP, Decimal

from business_brain.data.models import (
    Carrier,
    Product,
    ReferenceCatalog,
    Region,
    ServiceLevel,
    Supplier,
    Tenant,
    Warehouse,
)

REFERENCE_DATA_SEED = 20261003

_AURA_PRODUCTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "skincare",
        (
            "Hydrating Face Cleanser",
            "Vitamin C Serum",
            "Daily Moisture Cream",
            "Mineral Sunscreen",
            "Gentle Exfoliating Toner",
            "Night Repair Oil",
            "Clay Renewal Mask",
            "Cooling Eye Gel",
            "Barrier Support Balm",
            "Micellar Cleansing Water",
        ),
    ),
    (
        "home_care",
        (
            "Citrus Surface Cleaner",
            "Lavender Laundry Liquid",
            "Plant Based Dish Wash",
            "Fabric Refresh Spray",
            "Concentrated Floor Cleaner",
            "Glass Cleaning Mist",
            "Kitchen Degreaser",
            "Bathroom Cleaning Foam",
            "Reusable Cleaning Cloths",
            "Odor Neutralizing Spray",
        ),
    ),
    (
        "wellness",
        (
            "Daily Greens Blend",
            "Electrolyte Hydration Mix",
            "Sleep Support Tea",
            "Plant Protein Vanilla",
            "Plant Protein Cacao",
            "Ginger Wellness Shots",
            "Berry Fiber Blend",
            "Calm Herbal Infusion",
            "Morning Matcha Blend",
            "Recovery Mineral Mix",
        ),
    ),
    (
        "personal_care",
        (
            "Rosemary Shampoo",
            "Nourishing Conditioner",
            "Coconut Body Wash",
            "Shea Body Lotion",
            "Natural Deodorant",
            "Peppermint Hand Cream",
            "Repair Hair Mask",
            "Sea Salt Body Scrub",
            "Aloe Hand Wash",
            "Travel Care Set",
        ),
    ),
    (
        "travel_accessories",
        (
            "Insulated Travel Bottle",
            "Compact Toiletry Case",
            "Reusable Travel Pouches",
            "Canvas Weekender Bag",
            "Memory Foam Eye Mask",
            "Packing Cube Set",
            "Silicone Bottle Set",
            "Travel Laundry Bag",
            "Foldable Shopping Tote",
            "Portable Cutlery Set",
        ),
    ),
)

_CATEGORY_CODES = {
    "skincare": "SKN",
    "home_care": "HOM",
    "wellness": "WEL",
    "personal_care": "PER",
    "travel_accessories": "TRV",
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _aura_products() -> list[Product]:
    products: list[Product] = []
    sequence = 1
    for category_index, (category, names) in enumerate(_AURA_PRODUCTS):
        for item_index, name in enumerate(names):
            list_price = _money(
                Decimal("13.99")
                + Decimal(category_index * 4)
                + Decimal(item_index) * Decimal("2.75")
            )
            standard_cost = _money(
                list_price * Decimal("0.41") + Decimal(category_index) * Decimal("0.35")
            )
            reorder_point = 48 + ((sequence * 11) % 55)
            safety_stock = max(18, reorder_point // 2)
            products.append(
                Product(
                    product_id=f"prd_aur_{sequence:03d}",
                    tenant_id="tenant_aura",
                    sku=f"AUR-{_CATEGORY_CODES[category]}-{sequence:03d}",
                    product_name=f"Aura {name}",
                    category=category,
                    unit_of_measure="EA",
                    list_price=list_price,
                    standard_cost=standard_cost,
                    currency_code="USD",
                    reorder_point=reorder_point,
                    safety_stock=safety_stock,
                )
            )
            sequence += 1
    return products


def _apex_products() -> list[Product]:
    names = (
        "Apex Stainless Bottle",
        "Apex Trail Backpack",
        "Apex Packing Cube Set",
        "Apex Desk Organizer",
        "Apex Cable Pouch",
        "Apex Lunch Container",
        "Apex Travel Towel",
        "Apex Utility Tote",
    )
    products: list[Product] = []
    for sequence, name in enumerate(names, start=1):
        list_price = _money(Decimal("19.50") + Decimal(sequence) * Decimal("3.25"))
        products.append(
            Product(
                product_id=f"prd_apx_{sequence:03d}",
                tenant_id="tenant_apex",
                sku=f"APX-GEN-{sequence:03d}",
                product_name=name,
                category="general_merchandise",
                unit_of_measure="EA",
                list_price=list_price,
                standard_cost=_money(list_price * Decimal("0.46")),
                currency_code="USD",
                reorder_point=35 + sequence * 3,
                safety_stock=18 + sequence,
            )
        )
    return products


def build_reference_catalog() -> ReferenceCatalog:
    """Return the stable cross-tenant reference catalog used by all later generators."""

    return ReferenceCatalog(
        generation_seed=REFERENCE_DATA_SEED,
        tenants=[
            Tenant(
                tenant_id="tenant_aura",
                tenant_name="Aura Brands",
                default_currency_code="USD",
                timezone="America/Chicago",
            ),
            Tenant(
                tenant_id="tenant_apex",
                tenant_name="Apex Retail",
                default_currency_code="USD",
                timezone="America/New_York",
            ),
        ],
        regions=[
            Region(
                region_id="reg_aur_east",
                tenant_id="tenant_aura",
                region_name="East",
                country_code="US",
            ),
            Region(
                region_id="reg_aur_central",
                tenant_id="tenant_aura",
                region_name="Central",
                country_code="US",
            ),
            Region(
                region_id="reg_aur_west",
                tenant_id="tenant_aura",
                region_name="West",
                country_code="US",
            ),
            Region(
                region_id="reg_apx_east",
                tenant_id="tenant_apex",
                region_name="East",
                country_code="US",
            ),
            Region(
                region_id="reg_apx_west",
                tenant_id="tenant_apex",
                region_name="West",
                country_code="US",
            ),
        ],
        products=[*_aura_products(), *_apex_products()],
        warehouses=[
            Warehouse(
                warehouse_id="wh_aur_east",
                tenant_id="tenant_aura",
                region_id="reg_aur_east",
                warehouse_name="Aura East Fulfillment Center",
                country_code="US",
                timezone="America/New_York",
            ),
            Warehouse(
                warehouse_id="wh_aur_central",
                tenant_id="tenant_aura",
                region_id="reg_aur_central",
                warehouse_name="Aura Central Distribution Center",
                country_code="US",
                timezone="America/Chicago",
            ),
            Warehouse(
                warehouse_id="wh_aur_west",
                tenant_id="tenant_aura",
                region_id="reg_aur_west",
                warehouse_name="Aura West Fulfillment Center",
                country_code="US",
                timezone="America/Los_Angeles",
            ),
            Warehouse(
                warehouse_id="wh_apx_east",
                tenant_id="tenant_apex",
                region_id="reg_apx_east",
                warehouse_name="Apex East Warehouse",
                country_code="US",
                timezone="America/New_York",
            ),
            Warehouse(
                warehouse_id="wh_apx_west",
                tenant_id="tenant_apex",
                region_id="reg_apx_west",
                warehouse_name="Apex West Warehouse",
                country_code="US",
                timezone="America/Los_Angeles",
            ),
        ],
        suppliers=[
            Supplier(
                supplier_id="sup_aur_packaging",
                tenant_id="tenant_aura",
                supplier_name="Evergreen Packaging Works",
                payment_terms_days=60,
                lead_time_days=21,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_aur_skincare",
                tenant_id="tenant_aura",
                supplier_name="Lumina Personal Care Labs",
                payment_terms_days=30,
                lead_time_days=28,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_aur_home",
                tenant_id="tenant_aura",
                supplier_name="ClearHome Manufacturing",
                payment_terms_days=45,
                lead_time_days=18,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_aur_wellness",
                tenant_id="tenant_aura",
                supplier_name="Northfield Wellness Foods",
                payment_terms_days=30,
                lead_time_days=24,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_aur_accessories",
                tenant_id="tenant_aura",
                supplier_name="Harbor Travel Goods",
                payment_terms_days=60,
                lead_time_days=35,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_apx_general",
                tenant_id="tenant_apex",
                supplier_name="Apex Demo Wholesale Supply",
                payment_terms_days=30,
                lead_time_days=17,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_apx_packaging",
                tenant_id="tenant_apex",
                supplier_name="Summit Box and Paper",
                payment_terms_days=45,
                lead_time_days=14,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_aur_fedex_demo",
                tenant_id="tenant_aura",
                supplier_name="FedEx Demo Carrier Billing",
                payment_terms_days=30,
                lead_time_days=2,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_aur_northstar",
                tenant_id="tenant_aura",
                supplier_name="NorthStar Parcel Billing",
                payment_terms_days=30,
                lead_time_days=4,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_aur_blueline",
                tenant_id="tenant_aura",
                supplier_name="BlueLine Regional Freight Billing",
                payment_terms_days=30,
                lead_time_days=5,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_apx_summit",
                tenant_id="tenant_apex",
                supplier_name="Summit Parcel Network Billing",
                payment_terms_days=30,
                lead_time_days=4,
                currency_code="USD",
            ),
            Supplier(
                supplier_id="sup_apx_rapid",
                tenant_id="tenant_apex",
                supplier_name="Apex Rapid Delivery Billing",
                payment_terms_days=30,
                lead_time_days=2,
                currency_code="USD",
            ),
        ],
        carriers=[
            Carrier(
                carrier_id="car_aur_fedex_demo",
                tenant_id="tenant_aura",
                carrier_name="FedEx Demo Carrier",
                service_level=ServiceLevel.EXPEDITED,
                sla_delivery_days=2,
            ),
            Carrier(
                carrier_id="car_aur_northstar",
                tenant_id="tenant_aura",
                carrier_name="NorthStar Parcel",
                service_level=ServiceLevel.STANDARD,
                sla_delivery_days=4,
            ),
            Carrier(
                carrier_id="car_aur_blueline",
                tenant_id="tenant_aura",
                carrier_name="BlueLine Regional Freight",
                service_level=ServiceLevel.STANDARD,
                sla_delivery_days=5,
            ),
            Carrier(
                carrier_id="car_apx_summit",
                tenant_id="tenant_apex",
                carrier_name="Summit Parcel Network",
                service_level=ServiceLevel.STANDARD,
                sla_delivery_days=4,
            ),
            Carrier(
                carrier_id="car_apx_rapid",
                tenant_id="tenant_apex",
                carrier_name="Apex Rapid Delivery",
                service_level=ServiceLevel.EXPEDITED,
                sla_delivery_days=2,
            ),
        ],
    )
