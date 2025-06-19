#!/usr/bin/env python
"""
Utilities for data type conversion and memory optimization.

This module provides functions to safely convert between data types,
particularly for reducing memory usage by converting float64 to float32.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

MAX_REL_ERROR = 1e-6


def convert_to_float32(df: pd.DataFrame, exclude_columns: List[str] = None) -> pd.DataFrame:
    """
    Convert float64 columns to float32 to reduce memory usage.
    
    Args:
        df: DataFrame to convert
        exclude_columns: List of columns to exclude from conversion (e.g., IDs)
        
    Returns:
        DataFrame with float32 columns
    """
    if exclude_columns is None:
        exclude_columns = []
    
    # Get float64 columns
    float64_cols = df.select_dtypes(include=['float64']).columns.tolist()
    
    # Remove excluded columns
    float64_cols = [col for col in float64_cols if col not in exclude_columns]
    
    if not float64_cols:
        logger.info("No float64 columns to convert")
        return df
    
    # Convert columns
    logger.info(f"Converting {len(float64_cols)} float64 columns to float32...")
    
    # Create a copy to avoid modifying the original
    df_converted = df.copy()
    
    for col in float64_cols:
        try:
            # Check for values that might lose precision
            col_data = df[col].dropna()
            if len(col_data) > 0:
                min_val = col_data.min()
                max_val = col_data.max()
                
                # Float32 range: ±3.4e38
                if abs(min_val) > 3.4e38 or abs(max_val) > 3.4e38:
                    logger.warning(f"Column '{col}' has values outside float32 range, skipping conversion")
                    continue
                
                # Optional: precision-loss guard – ensure relative error < MAX_REL_ERROR
                converted = col_data.astype(np.float32).astype(np.float64)
                # Avoid division by zero by clipping denominator to 1
                rel_err = ((col_data - converted).abs() / col_data.abs().clip(lower=1)).max()
                if rel_err > MAX_REL_ERROR:
                    logger.warning(
                        f"Column '{col}' down-cast would introduce max relative error {rel_err:.2e} > {MAX_REL_ERROR:.1e}; keeping float64"
                    )
                    continue
                
            # Passed both range and precision checks → convert to float32
            df_converted[col] = df[col].astype(np.float32)
            
        except Exception as e:
            logger.warning(f"Could not convert column '{col}' to float32: {e}")
    
    return df_converted


def get_memory_usage(df: pd.DataFrame) -> Dict[str, float]:
    """
    Get detailed memory usage statistics for a DataFrame.
    
    Args:
        df: DataFrame to analyze
        
    Returns:
        Dictionary with memory statistics in MB
    """
    # Get memory usage by dtype
    memory_by_dtype = {}
    
    for dtype in df.dtypes.unique():
        cols = df.select_dtypes(include=[dtype]).columns
        if len(cols) > 0:
            memory_bytes = df[cols].memory_usage(deep=True).sum()
            memory_by_dtype[str(dtype)] = memory_bytes / (1024**2)  # Convert to MB
    
    # Total memory
    total_memory = df.memory_usage(deep=True).sum() / (1024**2)
    
    return {
        'total_mb': total_memory,
        'by_dtype': memory_by_dtype,
        'shape': df.shape,
        'columns': len(df.columns)
    }

# ---------------------------------------------------------------------------
# Pretty-print helper
# ---------------------------------------------------------------------------

def fmt_memory_usage(stats: Dict[str, float]) -> str:
    """Return a concise human-readable string for the *stats* dict produced by
    ``get_memory_usage``.

    Example output:
        "1311.49 MB | rows: 29 852, cols: 5 802 (float64: 1293 MB, category: 3 MB)"
    """

    total = stats.get('total_mb', 0)
    rows, cols = stats.get('shape', (0, 0))

    # Show top two dtypes by memory
    by_dtype = stats.get('by_dtype', {})
    top = sorted(by_dtype.items(), key=lambda x: x[1], reverse=True)[:2]
    dtype_str = ', '.join(f"{dt}: {mb:.0f} MB" for dt, mb in top)

    return f"{total:.2f} MB | rows: {rows:,}, cols: {cols:,} ({dtype_str})"
