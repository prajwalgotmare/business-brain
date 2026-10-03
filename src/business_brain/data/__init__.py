"""Canonical data contracts and deterministic demo-data builders."""

from business_brain.data.commerce_generator import build_commerce_inventory_dataset
from business_brain.data.commerce_models import CommerceInventoryDataset
from business_brain.data.finance_generator import build_finance_dataset
from business_brain.data.finance_models import FinanceDataset
from business_brain.data.logistics_generator import build_logistics_dataset
from business_brain.data.logistics_models import LogisticsDataset
from business_brain.data.models import ReferenceCatalog
from business_brain.data.quality_generator import build_data_quality_manifest
from business_brain.data.quality_models import DataQualityManifest
from business_brain.data.reference_catalog import build_reference_catalog
from business_brain.data.scenario_generator import build_ground_truth_manifest
from business_brain.data.scenario_models import GroundTruthManifest

__all__ = [
    "CommerceInventoryDataset",
    "DataQualityManifest",
    "FinanceDataset",
    "GroundTruthManifest",
    "LogisticsDataset",
    "ReferenceCatalog",
    "build_commerce_inventory_dataset",
    "build_data_quality_manifest",
    "build_finance_dataset",
    "build_ground_truth_manifest",
    "build_logistics_dataset",
    "build_reference_catalog",
]
