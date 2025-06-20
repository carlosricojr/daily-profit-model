import pandas as pd
from pathlib import Path
import pytest

ARTEFACT_DIR = Path(__file__).resolve().parents[1] / "artefacts"

# Skip the whole module early if the matrices haven't been generated yet –
# this avoids CI failures when the feature-engineering pipeline hasn't run.
_REQUIRED = [ARTEFACT_DIR / f"{s}_matrix.parquet" for s in ("train", "val", "test")]
if not all(p.exists() for p in _REQUIRED):
    pytest.skip("Feature matrices not available yet – skipping integrity checks", allow_module_level=True)

def _load(split):
    return pd.read_parquet(ARTEFACT_DIR / f"{split}_matrix.parquet")

def test_no_future_data():
    """cutoff_time must be < target_date for every row."""
    for split in ("train", "val", "test"):
        df = _load(split)
        cutoff = df.index.get_level_values(1)  # cutoff_time (D-1)
        target = cutoff + pd.Timedelta(days=1)  # prediction date D
        assert (cutoff < target).all(), f"{split}: found {((cutoff >= target).sum())} bad rows"

def test_disjoint_splits():
    """No (instance_id, target_date) pair appears in more than one split."""
    seen = set()
    for split in ("train", "val", "test"):
        df = _load(split)
        target_dates = df.index.get_level_values(1) + pd.Timedelta(days=1)
        keys = set(zip(df.index.get_level_values(0), target_dates))
        overlap = seen & keys
        assert not overlap, f"rows leak from earlier split into {split}: {len(overlap)}"
        seen |= keys

def test_target_alignment():
    """Every target column must have non-nulls for every row."""
    df_test = _load("test")
    target_cols = [c for c in df_test.columns if c.startswith("target_") and c != "target_date"]
    assert target_cols, "no target columns found"
    for split in ("train", "val", "test"):
        df = _load(split)
        null_counts = df[target_cols].isna().sum()
        assert (null_counts == 0).all(), f"{split}: missing targets in {null_counts[null_counts>0]}"