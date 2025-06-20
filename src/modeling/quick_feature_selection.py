#!/usr/bin/env python
"""Quick feature selection using only LightGBM importance (faster than mutual information)."""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
import json
import lightgbm as lgb
import gc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def select_top_features_lgb(X, y, n_features=1200):
    """Select top features using LightGBM feature importance."""
    
    # Use a subset for faster training
    if len(X) > 100000:
        sample_idx = np.random.choice(len(X), 100000, replace=False)
        X_sample = X.iloc[sample_idx]
        y_sample = y.iloc[sample_idx]
    else:
        X_sample = X
        y_sample = y
    
    # Train a quick LightGBM model
    params = {
        'objective': 'regression' if y.dtype in [np.float32, np.float64] else 'binary',
        'metric': 'mae' if y.dtype in [np.float32, np.float64] else 'auc',
        'num_leaves': 31,
        'learning_rate': 0.1,
        'feature_fraction': 0.8,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'verbose': -1,
        'num_threads': 4,
        'force_col_wise': True
    }
    
    train_data = lgb.Dataset(X_sample, label=y_sample)
    model = lgb.train(params, train_data, num_boost_round=100)
    
    # Get feature importance
    importance = pd.DataFrame({
        'feature': X.columns,
        'importance': model.feature_importance(importance_type='gain')
    }).sort_values('importance', ascending=False)
    
    top_features = importance.head(n_features)['feature'].tolist()
    return top_features, importance

def main():
    """Run quick feature selection."""
    
    # Configuration
    TOP_FEATURES = 1200  # 20% of ~5700 features
    PRIORITY_TARGETS = ['net_profit', 'is_profitable', 'num_trades', 'success_rate', 'risk_adj_ret']
    
    logger.info(f"Loading cleaned training data...")
    train_df = pd.read_parquet('artefacts/clean/train_matrix.parquet')
    logger.info(f"Loaded shape: {train_df.shape}")
    
    # Get feature columns
    feature_cols = [col for col in train_df.columns if not col.startswith('target_')]
    logger.info(f"Found {len(feature_cols)} features")
    
    # Create output directory
    output_dir = Path('artefacts/model_inputs')
    output_dir.mkdir(exist_ok=True)
    
    # Track all selected features across targets
    all_selected_features = set()
    feature_importance_by_target = {}
    
    # Process each priority target
    for target in PRIORITY_TARGETS:
        target_col = f'target_{target}'
        if target_col not in train_df.columns:
            logger.warning(f"Target {target_col} not found, skipping")
            continue
            
        logger.info(f"\nProcessing {target}...")
        
        # Get non-null data for this target
        mask = train_df[target_col].notna()
        X = train_df.loc[mask, feature_cols]
        y = train_df.loc[mask, target_col]
        
        logger.info(f"  {len(y)} non-null samples")
        
        # Select features
        top_features, importance = select_top_features_lgb(X, y, TOP_FEATURES)
        all_selected_features.update(top_features)
        feature_importance_by_target[target] = importance.head(50).to_dict('records')
        
        logger.info(f"  Selected {len(top_features)} features")
        logger.info(f"  Top 5: {top_features[:5]}")
        
        # Create target-specific dataset
        target_dir = output_dir / target
        target_dir.mkdir(exist_ok=True)
        
        # Save data for each split
        for split in ['train', 'val', 'test']:
            split_path = Path(f'artefacts/clean/{split}_matrix.parquet')
            if not split_path.exists():
                logger.warning(f"  {split} file not found")
                continue
                
            # Load split data
            split_df = pd.read_parquet(split_path, columns=top_features + [target_col])
            
            # Also include binary targets for net_profit
            if target == 'net_profit':
                for binary_col in ['target_is_profitable', 'target_is_highly_profitable']:
                    if binary_col in pd.read_parquet(split_path, columns=[]).columns:
                        split_df[binary_col] = pd.read_parquet(split_path, columns=[binary_col])
            
            # Save
            output_path = target_dir / f'{split}_matrix.parquet'
            split_df.to_parquet(output_path)
            logger.info(f"  Saved {split}: {split_df.shape} -> {output_path}")
        
        # Clean up
        del X, y
        gc.collect()
    
    # Save metadata
    logger.info(f"\nTotal unique features selected: {len(all_selected_features)}")
    
    metadata = {
        'feature_selection': {
            'method': 'lightgbm_importance',
            'top_features_per_target': TOP_FEATURES,
            'total_unique_features': len(all_selected_features),
            'targets_processed': list(feature_importance_by_target.keys())
        },
        'feature_importance': feature_importance_by_target
    }
    
    with open(output_dir / 'feature_selection_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Saved metadata to {output_dir / 'feature_selection_metadata.json'}")
    logger.info("\nFeature selection complete!")

if __name__ == "__main__":
    main()