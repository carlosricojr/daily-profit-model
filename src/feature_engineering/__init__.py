"""
Feature engineering module for daily profit prediction model.

This module provides featuretools-based feature engineering capabilities.
"""

# Version tracking
__version__ = "2.0.0"

# Import key functions for external access
from .utils import prepare_dataframe, make_daily_id, make_hash_id, split_date_range_into_chunks
from .ft_build_feature_matrix import main