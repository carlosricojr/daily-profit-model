-- Fix model_training_input table to use integer for is_drawdown_relative
-- This ensures compatibility with ML frameworks that expect numeric features

ALTER TABLE prop_trading_model.model_training_input 
ALTER COLUMN is_drawdown_relative TYPE INTEGER USING CASE WHEN is_drawdown_relative THEN 1 ELSE 0 END;

-- Add default value
ALTER TABLE prop_trading_model.model_training_input 
ALTER COLUMN is_drawdown_relative SET DEFAULT 0;

-- Update comment
COMMENT ON COLUMN prop_trading_model.model_training_input.is_drawdown_relative IS '0/1 integer instead of boolean for ML compatibility';