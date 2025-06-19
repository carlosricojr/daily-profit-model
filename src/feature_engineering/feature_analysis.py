#!/usr/bin/env python
"""Multi-target feature analysis and selection using the 80/20 principle.

This module implements streamlined feature selection for multiple prediction targets,
creating model-ready datasets with the most predictive features for each target.

Key simplifications:
- Only 2 feature selection methods: Mutual Information and LightGBM importance
- Automatic multi-target processing
- Direct output of model-ready datasets
- Simple JSON metadata for reproducibility
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
import json
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

from sklearn.feature_selection import mutual_info_regression
import lightgbm as lgb

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MultiTargetFeatureSelector:
    """Simplified feature selector for multiple prediction targets."""
    
    def __init__(self, top_features: int = 100):
        """Initialize the feature selector.
        
        Args:
            top_features: Number of top features to select per target
        """
        self.top_features = top_features
        self.feature_scores = {}
        self.selected_features = {}
        
    def analyze_all_targets(self, train_path: str, output_dir: str = "artefacts/model_inputs"):
        """Analyze features for all available targets and create model inputs.
        
        Args:
            train_path: Path to training data parquet file
            output_dir: Base directory for model input outputs
        """
        logger.info(f"Loading training data from {train_path}")
        df = pd.read_parquet(train_path)
        
        # Identify target columns
        target_cols = [col for col in df.columns if col.startswith("target_")]
        # Filter to numeric targets only (exclude categorical like most_traded_symbol)
        numeric_targets = []
        for col in target_cols:
            if df[col].dtype in [np.float64, np.float32, np.int64, np.int32]:
                numeric_targets.append(col)
        
        logger.info(f"Found {len(numeric_targets)} numeric targets: {numeric_targets}")
        
        # Get feature columns (exclude targets and non-numeric)
        feature_cols = [col for col in df.columns if not col.startswith("target_")]
        numeric_features = []
        for col in feature_cols:
            if df[col].dtype in [np.float64, np.float32, np.int64, np.int32]:
                numeric_features.append(col)
        
        logger.info(f"Found {len(numeric_features)} numeric features")
        
        # Analyze each target
        for target in numeric_targets:
            logger.info(f"\nAnalyzing features for {target}")
            self._analyze_target(df, target, numeric_features)
        
        # Create model input datasets
        self._create_model_inputs(train_path, output_dir)
        
        # Save metadata
        self._save_metadata(output_dir)
        
    def _analyze_target(self, df: pd.DataFrame, target_col: str, feature_cols: List[str]):
        """Analyze features for a single target using MI and LightGBM.
        
        Args:
            df: Full dataframe
            target_col: Target column name
            feature_cols: List of feature column names
        """
        # Filter to rows with non-null target
        mask = df[target_col].notna()
        X = df.loc[mask, feature_cols].fillna(0)
        y = df.loc[mask, target_col]
        
        if len(y) < 100:
            logger.warning(f"Skipping {target_col} - only {len(y)} non-null samples")
            return
        
        logger.info(f"  {len(y)} samples, target mean: {y.mean():.2f}, std: {y.std():.2f}")
        
        # 1. Mutual Information
        logger.info("  Calculating mutual information...")
        mi_scores = mutual_info_regression(X, y, random_state=42, n_neighbors=5)
        mi_df = pd.DataFrame({
            'feature': feature_cols,
            'mi_score': mi_scores
        }).sort_values('mi_score', ascending=False)
        
        # 2. LightGBM Feature Importance
        logger.info("  Calculating LightGBM importance...")
        
        # Simple model parameters
        params = {
            'objective': 'regression',
            'metric': 'mae',
            'num_leaves': 31,
            'learning_rate': 0.1,
            'feature_fraction': 0.8,
            'verbosity': -1,
            'random_state': 42
        }
        
        train_data = lgb.Dataset(X, label=y)
        model = lgb.train(
            params,
            train_data,
            num_boost_round=100,
            callbacks=[lgb.log_evaluation(0)]
        )
        
        # Get feature importance
        importance = pd.DataFrame({
            'feature': feature_cols,
            'lgb_importance': model.feature_importance(importance_type='gain')
        }).sort_values('lgb_importance', ascending=False)
        
        # Combine scores (simple average of ranks)
        mi_df['mi_rank'] = range(1, len(mi_df) + 1)
        importance['lgb_rank'] = range(1, len(importance) + 1)
        
        combined = mi_df.merge(importance[['feature', 'lgb_rank']], on='feature')
        combined['avg_rank'] = (combined['mi_rank'] + combined['lgb_rank']) / 2
        combined = combined.sort_values('avg_rank')
        
        # Store results
        target_name = target_col.replace('target_', '')
        self.feature_scores[target_name] = combined
        self.selected_features[target_name] = combined.head(self.top_features)['feature'].tolist()
        
        logger.info(f"  Top 5 features: {self.selected_features[target_name][:5]}")
        
    def _create_model_inputs(self, train_path: str, output_dir: str):
        """Create model-ready datasets with selected features for each target.
        
        Args:
            train_path: Path to original training data
            output_dir: Base directory for outputs
        """
        output_path = Path(output_dir)
        
        # Load all data splits
        data_splits = {}
        for split in ['train', 'val', 'test']:
            file_path = Path(train_path).parent / f"{split}_matrix.parquet"
            if file_path.exists():
                data_splits[split] = pd.read_parquet(file_path)
                logger.info(f"Loaded {split} data: {data_splits[split].shape}")
        
        # Create datasets for each target
        for target_name, features in self.selected_features.items():
            target_col = f"target_{target_name}"
            target_dir = output_path / target_name
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Save each split with selected features + target
            for split_name, df in data_splits.items():
                # Get available features (some might be missing in test/val)
                available_features = [f for f in features if f in df.columns]
                
                if target_col in df.columns:
                    # Create dataset with features + target
                    columns = available_features + [target_col]
                    # Also include binary classification targets if this is net_profit
                    if target_name == 'net_profit':
                        for binary_col in ['target_is_profitable', 'target_is_highly_profitable']:
                            if binary_col in df.columns:
                                columns.append(binary_col)
                    
                    model_df = df[columns].copy()
                    
                    # Save to parquet
                    output_file = target_dir / f"{split_name}_matrix.parquet"
                    model_df.to_parquet(output_file)
                    
                    logger.info(f"Saved {target_name}/{split_name}: {model_df.shape} -> {output_file}")
                    
                    # Log basic stats
                    if split_name == 'train':
                        null_pct = (model_df[target_col].isna().sum() / len(model_df)) * 100
                        logger.info(f"  Target null %: {null_pct:.1f}%")
    
    def _save_metadata(self, output_dir: str):
        """Save feature selection metadata as JSON.
        
        Args:
            output_dir: Base directory for outputs
        """
        output_path = Path(output_dir)
        
        # Create summary metadata
        metadata = {
            'feature_selection_params': {
                'top_features': self.top_features,
                'methods': ['mutual_information', 'lightgbm_importance']
            },
            'targets': {}
        }
        
        # Add per-target information
        for target_name, features in self.selected_features.items():
            scores_df = self.feature_scores[target_name]
            
            metadata['targets'][target_name] = {
                'num_features': len(features),
                'selected_features': features,
                'top_10_features': features[:10],
                'feature_scores': scores_df.head(10)[['feature', 'mi_score', 'lgb_importance', 'avg_rank']].to_dict('records')
            }
        
        # Save metadata
        metadata_file = output_path / 'feature_selection_metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"\nSaved metadata to {metadata_file}")
        
        # Create simple summary report
        report_lines = ["Feature Selection Summary", "=" * 50, ""]
        
        for target_name, features in self.selected_features.items():
            report_lines.append(f"\n{target_name.upper()} ({len(features)} features)")
            report_lines.append("-" * 30)
            report_lines.append(f"Top 10: {', '.join(features[:10])}")
        
        report_file = output_path / 'feature_selection_summary.txt'
        with open(report_file, 'w') as f:
            f.write('\n'.join(report_lines))
        
        logger.info(f"Saved summary to {report_file}")


def main():
    """Run multi-target feature analysis."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-target feature selection")
    parser.add_argument("--train-path", type=str, default="artefacts/train_matrix.parquet",
                       help="Path to training data")
    parser.add_argument("--top-features", type=int, default=100,
                       help="Number of top features to select per target")
    parser.add_argument("--output-dir", type=str, default="artefacts/model_inputs",
                       help="Output directory for model inputs")
    
    args = parser.parse_args()
    
    # Run feature selection
    selector = MultiTargetFeatureSelector(top_features=args.top_features)
    selector.analyze_all_targets(args.train_path, args.output_dir)
    
    logger.info("\nFeature selection complete!")


if __name__ == "__main__":
    main()