#!/usr/bin/env python
"""
Utilities for data type conversion and memory optimization.

This module provides functions to safely convert between data types,
particularly for reducing memory usage by converting float64 to float32.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def optimize_dtypes(df: pd.DataFrame, exclude_from_categorical: Optional[List[str]] = None) -> pd.DataFrame:
    if exclude_from_categorical is None:
        exclude_from_categorical = []
    
    # First, convert any datetime columns that are stored as objects
    datetime_cols = []
    for col in df.columns:
        if col in ['date', 'datetime', 'first_trade_date', 'ingestion_timestamp'] or 'date' in col.lower():
            try:
                df[col] = pd.to_datetime(df[col])
                datetime_cols.append(col)
                print(f"Converted {col} to datetime type")
            except:
                pass
    
    # Downcast integer columns
    int_cols = df.select_dtypes(include=['int64', 'int32', 'int16', 'int8']).columns
    if len(int_cols) > 0:
        original_memory_int = df[int_cols].memory_usage(deep=True).sum() / (1024**2)  # Memory in MB
        df[int_cols] = df[int_cols].apply(pd.to_numeric, downcast='integer')
        new_memory_int = df[int_cols].memory_usage(deep=True).sum() / (1024**2)  # Memory in MB
        memory_saved_int = original_memory_int - new_memory_int
        if memory_saved_int > 0:
            print(f"Downcasted integer columns to save {memory_saved_int:.2f} MB memory")

    # Downcast float columns
    float_cols = df.select_dtypes(include=['float64', 'float32', 'float16']).columns
    if len(float_cols) > 0:
        original_memory_float = df[float_cols].memory_usage(deep=True).sum() / (1024**2)  # Memory in MB
        df[float_cols] = df[float_cols].apply(pd.to_numeric, downcast='float')
        new_memory_float = df[float_cols].memory_usage(deep=True).sum() / (1024**2)  # Memory in MB
        memory_saved_float = original_memory_float - new_memory_float
        if memory_saved_float > 0:
            print(f"Downcasted float columns to save {memory_saved_float:.2f} MB memory")

    # Convert object columns with low cardinality to category
    for col in df.select_dtypes(include=['object']).columns:
        # Skip columns that are known datetime columns
        if col in datetime_cols or 'date' in col.lower() or 'time' in col.lower():
            continue

        if col in exclude_from_categorical:
            print(f"INFO: Skipping categorical conversion for excluded column: {col}")
            continue   

        if df[col].nunique() / len(df) < 0.5:  # Low cardinality
            original_memory = df[col].memory_usage(deep=True) / (1024**2)  # Memory in MB
            df[col] = df[col].astype("category")
            new_memory = df[col].memory_usage(deep=True) / (1024**2)  # Memory in MB
            memory_saved = original_memory - new_memory
            if memory_saved > 0:
                print(f"Converted {col} to category to save {memory_saved:.2f} MB memory")

    return df


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
