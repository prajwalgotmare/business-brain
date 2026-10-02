"""Canonical data contracts and deterministic demo-data builders."""

from business_brain.data.commerce_generator import build_commerce_inventory_dataset
from business_brain.data.commerce_models import CommerceInventoryDataset
from business_brain.data.logistics_generator import build_logistics_dataset
from business_brain.data.logistics_models import LogisticsDataset
from business_brain.data.models import ReferenceCatalog
from business_brain.data.reference_catalog import build_reference_catalog

__all__ = [
    "CommerceInventoryDataset",
    "LogisticsDataset",
    "ReferenceCatalog",
    "build_commerce_inventory_dataset",
    "build_logistics_dataset",
    "build_reference_catalog",
]
