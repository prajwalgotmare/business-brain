"""Stable identifiers and values for the six evaluation scenarios."""

from decimal import Decimal

STOCKOUT_PRODUCT_ID = "prd_aur_006"
STOCKOUT_WAREHOUSE_ID = "wh_aur_west"
STOCKOUT_TARGET_ON_HAND = 3
MARGIN_RETURN_ORDER_IDS = {
    "ord_aur_00012",
    "ord_aur_00254",
    "ord_aur_00473",
}
OVERBILLING_SHIPMENT_ID = "shp_aur_000021"
OVERBILLING_AMOUNT = Decimal("18.00")
OVERDUE_INVOICE_ID = "vin_aur_00010"
APPROVAL_PURCHASE_ORDER_ID = "po_aur_approval_00001"
PACKAGING_SUPPLIER_ID = "sup_aur_packaging"
