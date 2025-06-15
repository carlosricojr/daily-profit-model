-- Migration: Handle NULL account_ids in metrics tables
-- Description: Creates a trigger function to automatically generate account_id from md5(login, platform, broker)
-- when NULL account_id is inserted into raw_metrics tables

-- Create the trigger function
CREATE OR REPLACE FUNCTION prop_trading_model.generate_account_id_if_null()
RETURNS TRIGGER AS $$
BEGIN
    -- Only generate account_id if it's NULL AND all required fields are present
    IF NEW.account_id IS NULL AND 
       NEW.login IS NOT NULL AND 
       NEW.platform IS NOT NULL AND 
       NEW.broker IS NOT NULL THEN
        -- Generate md5 hash from login|platform|broker
        -- Cast integers to text for concatenation (required by || operator)
        NEW.account_id := md5(NEW.login || '|' || NEW.platform::text || '|' || NEW.broker::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for raw_metrics_alltime
CREATE TRIGGER tr_generate_account_id_alltime
    BEFORE INSERT ON prop_trading_model.raw_metrics_alltime
    FOR EACH ROW
    EXECUTE FUNCTION prop_trading_model.generate_account_id_if_null();

-- Create triggers for raw_metrics_daily and its partitions
CREATE TRIGGER tr_generate_account_id_daily
    BEFORE INSERT ON prop_trading_model.raw_metrics_daily
    FOR EACH ROW
    EXECUTE FUNCTION prop_trading_model.generate_account_id_if_null();

-- Create triggers for raw_metrics_hourly and its partitions
CREATE TRIGGER tr_generate_account_id_hourly
    BEFORE INSERT ON prop_trading_model.raw_metrics_hourly
    FOR EACH ROW
    EXECUTE FUNCTION prop_trading_model.generate_account_id_if_null();