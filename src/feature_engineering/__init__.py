"""
Feature engineering module for daily profit prediction model.

This module provides unified feature engineering capabilities with:
- Optimized bulk query processing
- Comprehensive risk metrics
- Lookahead bias validation
- Quality monitoring
- Performance tracking
"""

# Import from the unified module
from .feature_engineering import (
    # Core classes
    UnifiedFeatureEngineer,
    LookaheadBiasValidator,
    FeatureQualityMonitor,
    
    # Backward compatibility classes
    OptimizedFeatureEngineer,
    IntegratedProductionFeatureEngineer,
    EnhancedFeatureEngineerV2,
    
    # Main entry points
    engineer_features_unified,
    engineer_features_optimized,
    engineer_features_enhanced_v2,
    
    # Configuration
    FEATURE_VERSION,
    PRODUCTION_CONFIG,
)

# Re-export for backward compatibility with existing imports
from .feature_engineering import (
    OptimizedFeatureEngineer as OriginalOptimizedFeatureEngineer,
    IntegratedProductionFeatureEngineer as OriginalIntegratedProductionFeatureEngineer,
)

__all__ = [
    "UnifiedFeatureEngineer",
    "LookaheadBiasValidator",
    "FeatureQualityMonitor",
    "OptimizedFeatureEngineer",
    "IntegratedProductionFeatureEngineer",
    "EnhancedFeatureEngineerV2",
    "engineer_features_unified",
    "engineer_features_optimized",
    "engineer_features_enhanced_v2",
    "FEATURE_VERSION",
    "PRODUCTION_CONFIG",
]