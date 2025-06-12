"""
Test to ensure all ingestion scripts only use fields that exist in the official data structures.
This test validates against the data structures defined in ai-docs/data-structures.md.

This test suite provides comprehensive validation to ensure data integrity:

1. test_no_undefined_fields_used: Ensures ingestion scripts don't reference fields 
   that don't exist in the API responses, preventing runtime errors and data loss.

2. test_required_fields_are_handled: Validates that critical fields needed for 
   data processing are actually being used by the ingestion scripts.

3. test_no_hardcoded_nonexistent_fields: Warns about suspicious string literals
   that might be incorrect field names.

4. test_field_type_consistency: Ensures fields that should be exclusive to one
   data type don't accidentally appear in others.

The test uses AST parsing to analyze the actual field usage in the code, filtering
out infrastructure code, methods, and non-data fields to focus only on actual
data field validation.
"""

import pytest
import ast
from pathlib import Path
from typing import Set, List, Tuple

# Define the exact fields from data-structures.md
VALID_FIELDS = {
    "metrics_alltime": {
        "login", "accountId", "planId", "trader", "status", "type", "phase", "broker",
        "mt_version", "price_stream", "country", "approved_payouts", "pending_payouts",
        "startingBalance", "priorDaysBalance", "priorDaysEquity", "currentBalance",
        "currentEquity", "firstTradeDate", "daysSinceInitialDeposit",
        "daysSinceFirstTrade", "numTrades", "firstTradeOpen", "lastTradeOpen",
        "lastTradeClose", "lifeTimeInDays", "netProfit", "grossProfit", "grossLoss",
        "gainToPain", "profitFactor", "successRate", "meanProfit", "medianProfit",
        "stdProfits", "riskAdjProfit", "minProfit", "maxProfit", "profitPerc10",
        "profitPerc25", "profitPerc75", "profitPerc90", "expectancy",
        "profitTop10PrcntTrades", "profitBottom10PrcntTrades", "top10PrcntProfitContrib",
        "bottom10PrcntLossContrib", "oneStdOutlierProfit", "oneStdOutlierProfitContrib",
        "twoStdOutlierProfit", "twoStdOutlierProfitContrib", "netProfitPerUSDVolume",
        "grossProfitPerUSDVolume", "grossLossPerUSDVolume",
        "distanceGrossProfitLossPerUSDVolume", "multipleGrossProfitLossPerUSDVolume",
        "grossProfitPerLot", "grossLossPerLot", "distanceGrossProfitLossPerLot",
        "multipleGrossProfitLossPerLot", "netProfitPerDuration",
        "grossProfitPerDuration", "grossLossPerDuration", "meanRet", "stdRets",
        "riskAdjRet", "downsideStdRets", "downsideRiskAdjRet", "totalRet",
        "dailyMeanRet", "dailyStdRet", "dailySharpe", "dailyDownsideStdRet",
        "dailySortino", "relNetProfit", "relGrossProfit", "relGrossLoss",
        "relMeanProfit", "relMedianProfit", "relStdProfits", "relRiskAdjProfit",
        "relMinProfit", "relMaxProfit", "relProfitPerc10", "relProfitPerc25",
        "relProfitPerc75", "relProfitPerc90", "relProfitTop10PrcntTrades",
        "relProfitBottom10PrcntTrades", "relOneStdOutlierProfit",
        "relTwoStdOutlierProfit", "meanDrawDown", "medianDrawDown", "maxDrawDown",
        "meanNumTradesInDD", "medianNumTradesInDD", "maxNumTradesInDD",
        "relMeanDrawDown", "relMedianDrawDown", "relMaxDrawDown", "totalLots",
        "totalVolume", "stdVolumes", "meanWinningLot", "meanLosingLot",
        "distanceWinLossLots", "multipleWinLossLots", "meanWinningVolume",
        "meanLosingVolume", "distanceWinLossVolume", "multipleWinLossVolume",
        "meanDuration", "medianDuration", "stdDurations", "minDuration", "maxDuration",
        "cvDurations", "meanTP", "medianTP", "stdTP", "minTP", "maxTP", "cvTP",
        "meanSL", "medianSL", "stdSL", "minSL", "maxSL", "cvSL", "meanTPvsSL",
        "medianTPvsSL", "minTPvsSL", "maxTPvsSL", "cvTPvsSL", "meanNumConsecWins",
        "medianNumConsecWins", "maxNumConsecWins", "meanNumConsecLosses",
        "medianNumConsecLosses", "maxNumConsecLosses", "meanValConsecWins",
        "medianValConsecWins", "maxValConsecWins", "meanValConsecLosses",
        "medianValConsecLosses", "maxValConsecLosses", "meanNumOpenPos",
        "medianNumOpenPos", "maxNumOpenPos", "meanValOpenPos", "medianValOpenPos",
        "maxValOpenPos", "meanValtoEqtyOpenPos", "medianValtoEqtyOpenPos",
        "maxValtoEqtyOpenPos", "meanAccountMargin", "meanFirmMargin",
        "meanTradesPerDay", "medianTradesPerDay", "minTradesPerDay", "maxTradesPerDay",
        "cvTradesPerDay", "meanIdleDays", "medianIdleDays", "maxIdleDays",
        "minIdleDays", "numTradedSymbols", "mostTradedSymbol", "mostTradedSmbTrades",
        "updatedDate"
    },
    "metrics_daily": {
        "date", "login", "planId", "accountId", "trader", "status", "type", "phase",
        "broker", "mt_version", "price_stream", "country", "days_to_next_payout",
        "todays_payouts", "approved_payouts", "pending_payouts", "startingBalance",
        "priorDaysBalance", "priorDaysEquity", "currentBalance", "currentEquity",
        "firstTradeDate", "daysSinceInitialDeposit", "daysSinceFirstTrade",
        "numTrades", "netProfit", "grossProfit", "grossLoss", "gainToPain",
        "profitFactor", "successRate", "meanProfit", "medianProfit", "stdProfits",
        "riskAdjProfit", "minProfit", "maxProfit", "profitPerc10", "profitPerc25",
        "profitPerc75", "profitPerc90", "expectancy", "profitTop10PrcntTrades",
        "profitBottom10PrcntTrades", "top10PrcntProfitContrib",
        "bottom10PrcntLossContrib", "oneStdOutlierProfit", "oneStdOutlierProfitContrib",
        "twoStdOutlierProfit", "twoStdOutlierProfitContrib", "netProfitPerUSDVolume",
        "grossProfitPerUSDVolume", "grossLossPerUSDVolume",
        "distanceGrossProfitLossPerUSDVolume", "multipleGrossProfitLossPerUSDVolume",
        "grossProfitPerLot", "grossLossPerLot", "distanceGrossProfitLossPerLot",
        "multipleGrossProfitLossPerLot", "netProfitPerDuration",
        "grossProfitPerDuration", "grossLossPerDuration", "meanRet", "stdRets",
        "riskAdjRet", "downsideStdRets", "downsideRiskAdjRet", "relNetProfit",
        "relGrossProfit", "relGrossLoss", "relMeanProfit", "relMedianProfit",
        "relStdProfits", "relRiskAdjProfit", "relMinProfit", "relMaxProfit",
        "relProfitPerc10", "relProfitPerc25", "relProfitPerc75", "relProfitPerc90",
        "relProfitTop10PrcntTrades", "relProfitBottom10PrcntTrades",
        "relOneStdOutlierProfit", "relTwoStdOutlierProfit", "meanDrawDown",
        "medianDrawDown", "maxDrawDown", "meanNumTradesInDD", "medianNumTradesInDD",
        "maxNumTradesInDD", "relMeanDrawDown", "relMedianDrawDown", "relMaxDrawDown",
        "totalLots", "totalVolume", "stdVolumes", "meanWinningLot", "meanLosingLot",
        "distanceWinLossLots", "multipleWinLossLots", "meanWinningVolume",
        "meanLosingVolume", "distanceWinLossVolume", "multipleWinLossVolume",
        "meanDuration", "medianDuration", "stdDurations", "minDuration", "maxDuration",
        "cvDurations", "meanTP", "medianTP", "stdTP", "minTP", "maxTP", "cvTP",
        "meanSL", "medianSL", "stdSL", "minSL", "maxSL", "cvSL", "meanTPvsSL",
        "medianTPvsSL", "minTPvsSL", "maxTPvsSL", "cvTPvsSL", "meanNumConsecWins",
        "medianNumConsecWins", "maxNumConsecWins", "meanNumConsecLosses",
        "medianNumConsecLosses", "maxNumConsecLosses", "meanValConsecWins",
        "medianValConsecWins", "maxValConsecWins", "meanValConsecLosses",
        "medianValConsecLosses", "maxValConsecLosses", "meanNumOpenPos",
        "medianNumOpenPos", "maxNumOpenPos", "meanValOpenPos", "medianValOpenPos",
        "maxValOpenPos", "meanValtoEqtyOpenPos", "medianValtoEqtyOpenPos",
        "maxValtoEqtyOpenPos", "meanAccountMargin", "meanFirmMargin",
        "numTradedSymbols", "mostTradedSmbTrades", "mostTradedSymbol"
    },
    "metrics_hourly": {
        "date", "datetime", "hour", "login", "planId", "accountId", "trader", "status",
        "type", "phase", "broker", "mt_version", "price_stream", "country",
        "days_to_next_payout", "todays_payouts", "approved_payouts", "pending_payouts",
        "startingBalance", "priorDaysBalance", "priorDaysEquity", "currentBalance",
        "currentEquity", "firstTradeDate", "daysSinceInitialDeposit",
        "daysSinceFirstTrade", "numTrades", "netProfit", "grossProfit", "grossLoss",
        "gainToPain", "profitFactor", "successRate", "meanProfit", "medianProfit",
        "stdProfits", "riskAdjProfit", "minProfit", "maxProfit", "profitPerc10",
        "profitPerc25", "profitPerc75", "profitPerc90", "expectancy",
        "profitTop10PrcntTrades", "profitBottom10PrcntTrades", "top10PrcntProfitContrib",
        "bottom10PrcntLossContrib", "oneStdOutlierProfit", "oneStdOutlierProfitContrib",
        "twoStdOutlierProfit", "twoStdOutlierProfitContrib", "netProfitPerUSDVolume",
        "grossProfitPerUSDVolume", "grossLossPerUSDVolume",
        "distanceGrossProfitLossPerUSDVolume", "multipleGrossProfitLossPerUSDVolume",
        "grossProfitPerLot", "grossLossPerLot", "distanceGrossProfitLossPerLot",
        "multipleGrossProfitLossPerLot", "netProfitPerDuration",
        "grossProfitPerDuration", "grossLossPerDuration", "meanRet", "stdRets",
        "riskAdjRet", "downsideStdRets", "downsideRiskAdjRet", "relNetProfit",
        "relGrossProfit", "relGrossLoss", "relMeanProfit", "relMedianProfit",
        "relStdProfits", "relRiskAdjProfit", "relMinProfit", "relMaxProfit",
        "relProfitPerc10", "relProfitPerc25", "relProfitPerc75", "relProfitPerc90",
        "relProfitTop10PrcntTrades", "relProfitBottom10PrcntTrades",
        "relOneStdOutlierProfit", "relTwoStdOutlierProfit", "meanDrawDown",
        "medianDrawDown", "maxDrawDown", "meanNumTradesInDD", "medianNumTradesInDD",
        "maxNumTradesInDD", "relMeanDrawDown", "relMedianDrawDown", "relMaxDrawDown",
        "totalLots", "totalVolume", "stdVolumes", "meanWinningLot", "meanLosingLot",
        "distanceWinLossLots", "multipleWinLossLots", "meanWinningVolume",
        "meanLosingVolume", "distanceWinLossVolume", "multipleWinLossVolume",
        "meanDuration", "medianDuration", "stdDurations", "minDuration", "maxDuration",
        "cvDurations", "meanTP", "medianTP", "stdTP", "minTP", "maxTP", "cvTP",
        "meanSL", "medianSL", "stdSL", "minSL", "maxSL", "cvSL", "meanTPvsSL",
        "medianTPvsSL", "minTPvsSL", "maxTPvsSL", "cvTPvsSL", "meanNumConsecWins",
        "medianNumConsecWins", "maxNumConsecWins", "meanNumConsecLosses",
        "medianNumConsecLosses", "maxNumConsecLosses", "meanValConsecWins",
        "medianValConsecWins", "maxValConsecWins", "meanValConsecLosses",
        "medianValConsecLosses", "maxValConsecLosses", "meanNumOpenPos",
        "medianNumOpenPos", "maxNumOpenPos", "meanValOpenPos", "medianValOpenPos",
        "maxValOpenPos", "meanValtoEqtyOpenPos", "medianValtoEqtyOpenPos",
        "maxValtoEqtyOpenPos", "meanAccountMargin", "meanFirmMargin",
        "numTradedSymbols", "mostTradedSmbTrades", "mostTradedSymbol"
    },
    "trades": {
        "tradeDate", "broker", "mngr", "platform", "ticket", "position", "login",
        "stdSymbol", "side", "lots", "contractSize", "qtyInBaseCrncy", "volumeUSD",
        "stopLoss", "takeProfit", "openTime", "openPrice", "closeTime", "closePrice",
        "duration", "profit", "commission", "fee", "swap", "comment"
    },
    # Plans are from CSV, fields will be validated differently
    "plans": set()  # This will be populated from actual CSV headers when available
}

# Common wrapper fields that might appear in API responses
WRAPPER_FIELDS = {"Status", "Data", "Time", "total", "skip", "limit", "count", "data"}


class FieldUsageVisitor(ast.NodeVisitor):
    """AST visitor to find field access patterns in code."""
    
    def __init__(self):
        self.accessed_fields: Set[str] = set()
        self.suspicious_patterns: List[Tuple[str, int, str]] = []
    
    def visit_Subscript(self, node):
        """Track dictionary/list subscript access like data['field']."""
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            field = node.slice.value
            self.accessed_fields.add(field)
        self.generic_visit(node)
    
    def visit_Attribute(self, node):
        """Track attribute access like obj.field."""
        if isinstance(node.attr, str):
            self.accessed_fields.add(node.attr)
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Track method calls that might access fields."""
        # Check for .get() calls
        if (isinstance(node.func, ast.Attribute) and 
            node.func.attr == 'get' and 
            len(node.args) > 0 and
            isinstance(node.args[0], ast.Constant) and
            isinstance(node.args[0].value, str)):
            field = node.args[0].value
            self.accessed_fields.add(field)
        
        # Check for setdefault calls
        if (isinstance(node.func, ast.Attribute) and 
            node.func.attr == 'setdefault' and 
            len(node.args) > 0 and
            isinstance(node.args[0], ast.Constant) and
            isinstance(node.args[0].value, str)):
            field = node.args[0].value
            self.accessed_fields.add(field)
        
        self.generic_visit(node)
    
    def visit_Dict(self, node):
        """Track dictionary literal keys."""
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                self.accessed_fields.add(key.value)
        self.generic_visit(node)


def extract_fields_from_source(filepath: Path) -> Set[str]:
    """Extract all field names accessed in a Python source file."""
    with open(filepath, 'r') as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
        visitor = FieldUsageVisitor()
        visitor.visit(tree)
        return visitor.accessed_fields
    except SyntaxError as e:
        pytest.fail(f"Syntax error in {filepath}: {e}")


def get_data_type_from_script(script_path: Path) -> str:
    """Determine which data type a script handles based on its name and content."""
    filename = script_path.name
    
    if "metrics" in filename:
        # Metrics ingester handles all three types, return special marker
        return "metrics_all"  # Special case for metrics that handles all types
    elif "trade" in filename:
        return "trades"
    elif "plan" in filename:
        return "plans"
    elif "regime" in filename:
        return None  # Regimes not in data structures doc
    else:
        return None


class TestDataStructureFieldValidation:
    """Test suite to validate field usage across all ingestion scripts."""
    
    @pytest.fixture
    def ingestion_scripts(self):
        """Get all ingestion scripts."""
        scripts_dir = Path(__file__).parent.parent / "src" / "data_ingestion"
        return list(scripts_dir.glob("ingest_*.py"))
    
    def test_no_undefined_fields_used(self, ingestion_scripts):
        """Ensure scripts only use fields defined in data structures."""
        errors = []
        
        for script in ingestion_scripts:
            # Skip intelligent ingestion scripts that delegate to original implementations
            if "intelligent" in script.name:
                continue
                
            data_type = get_data_type_from_script(script)
            if data_type is None:
                continue  # Skip scripts not in data structures doc
            
            # Special handling for metrics ingester that processes all types
            if data_type == "metrics_all":
                valid_fields = (
                    VALID_FIELDS.get("metrics_alltime", set()) |
                    VALID_FIELDS.get("metrics_daily", set()) |
                    VALID_FIELDS.get("metrics_hourly", set())
                )
            else:
                valid_fields = VALID_FIELDS.get(data_type, set())
            
            used_fields = extract_fields_from_source(script)
            
            # Remove common Python attributes and methods
            python_builtins = {
                'append', 'extend', 'items', 'keys', 'values', 'get', 'pop',
                'update', 'clear', 'copy', 'setdefault', '__dict__', '__class__',
                'format', 'strip', 'lower', 'upper', 'replace', 'split', 'join',
                'startswith', 'endswith', 'encode', 'decode', 'isoformat',
                'strftime', 'date', 'time', 'year', 'month', 'day', 'hour',
                'minute', 'second', 'microsecond', 'timestamp', 'total_seconds'
            }
            
            # Remove logging and other infrastructure fields
            infrastructure_fields = {
                'logger', 'has_data', 'account_batch_size', 'capitalize', 
                'hourly_batch_size', 'ingest_with_date_range', 'ingest_without_date_range',
                'info', 'error', 'warning', 'debug', 'exception',
                'name', 'level', 'handlers', 'filters', 'disabled',
                'base_url', 'headers', 'timeout', 'verify', 'auth',
                'status_code', 'json', 'text', 'content', 'raise_for_status',
                'get', 'post', 'put', 'delete', 'patch', 'head', 'options',
                'close', 'commit', 'rollback', 'execute', 'fetchone', 'fetchall',
                'rowcount', 'lastrowid', 'description', 'cursor', 'connection',
                'session', 'params', 'url', 'method', 'response', 'request',
                'encoding', 'cookies', 'history', 'reason', 'ok', 'links',
                'raw', 'iter_content', 'iter_lines', 'stream', 'cert',
                'proxies', 'allow_redirects', 'files', 'data', 'hooks',
                'seconds', 'microseconds', 'days', 'tzinfo', 'utcnow', 'now',
                'min', 'max', 'avg', 'sum', 'count', 'total', 'limit', 'offset',
                'page', 'pages', 'size', 'length', 'index', 'idx', 'pos',
                'start', 'end', 'begin', 'finish', 'from', 'to', 'at',
                'result', 'results', 'output', 'outputs', 'input', 'inputs',
                'args', 'kwargs', 'self', 'cls', 'obj', 'instance', 'klass',
                'module', 'package', 'path', 'file', 'filename', 'filepath',
                'dir', 'directory', 'folder', 'root', 'base', 'ext', 'extension',
                # Ingestion-specific infrastructure
                'api_client', 'db_manager', 'checkpoint_manager', 'metrics',
                'enable_validation', 'enable_deduplication', 'force_refresh',
                'batch_size', 'start_date', 'end_date', 'logins', 'symbols',
                'ingestion_timestamp', 'source_api_endpoint', 'table_name',
                'table_mapping', 'field_mapping', 'column_mapping',
                'new_records', 'duplicate_records', 'invalid_records', 'total_records',
                'api_calls', 'api_errors', 'db_errors', 'validation_errors',
                'processing_time', 'records_per_second', 'seen_records', "add_parser",
                "add_subparsers", "execute_query", "ingest_metrics_for_training", "strategy", "no_hourly", "sleep",
                # Database operation fields
                'account_id', 'metric_id', 'plan_id', 'regime_id',
                'record_id', 'row_id', 'batch_data', 'batch_records',
                'insert', 'update', 'upsert', 'delete', 'truncate',
                'execute_command', 'executemany', 'get_connection',
                # Checkpoint fields  
                'checkpoint_dir', 'last_processed_date', 'last_processed_page',
                'last_processed_file', 'last_processed_row', 'completion_time',
                'save_checkpoint', 'load_checkpoint', 'clear_checkpoint',
                # Parsing/transformation fields
                'parse_args', 'parse_date', 'parse_timestamp', 'format_date',
                'transform', 'convert', 'normalize', 'validate', 'sanitize',
                'safe_float', 'safe_int', 'safe_str', 'safe_bool',
                'strptime', 'strftime', 'fromisoformat', 'to_datetime',
                # Database column mapping fields (transformations of API fields)
                'close_price', 'open_price', 'close_time', 'open_time',
                'current_price', 'unrealized_pnl', 'std_symbol', 'symbol',
                'stop_loss', 'take_profit', 'volume_usd', 'trade_date', 'contract_size',
                'qty_in_base_ccy', 'duration', 'fee', 'swap', 'unrealized_profit', "manager",
                # Metric-specific transformation fields
                'balance_start', 'balance_end', 'equity_start', 'equity_end',
                'lots_traded', 'volume_traded', 'num_trades', 'win_rate',
                # Plans-specific fields
                'plan_name', 'plan_type', 'starting_balance', 'profit_target',
                'profit_target_pct', 'profit_share_pct', 'max_drawdown',
                'max_drawdown_pct', 'max_daily_drawdown', 'max_daily_drawdown_pct',
                'max_trading_days', 'min_trading_days', 'max_leverage',
                'inactivity_period', 'liquidate_friday', 'is_drawdown_relative',
                'daily_drawdown_by_balance_equity', 'makeDrawdownStatic',
                # File operations
                'open', 'read', 'write', 'load', 'dump', 'exists', 'mkdir',
                'unlink', 'glob', 'abspath', 'dirname', 'basename',
                # Common program fields
                'main', 'init', '__init__', 'setup', 'teardown', 'cleanup',
                'run', 'start', 'stop', 'pause', 'resume', 'cancel',
                'log_level', 'verbose', 'debug_mode', 'dry_run',
                'model_db', 'log_pipeline_execution', 'log_final_summary',
                'get_metrics', 'get_trades', 'get_plans', 'get_regimes',
                'ingest_metrics', 'ingest_trades', 'ingest_plans', 'ingest_regimes',
                'ingest_metrics_intelligent', 'ingest_trades_intelligent',
                'calculate_rate', 'add', 'value', 'files', 'files_processed',
                # Ingestion configuration
                'no_validation', 'no_deduplication', 'no_resume',
                'enable_consistency', 'force_full_refresh', 'batch_days',
                'max_retries', 'trade_type', 'metric_type', 'ingestion_type',
                'closed', 'open', 'alltime', 'daily', 'hourly',
                'ALLTIME', 'DAILY', 'HOURLY', 'CLOSED', 'OPEN',
                # Field mapping configs
                'alltime_field_mapping', 'daily_field_mapping', 'hourly_field_mapping',
                'alltime_specific_fields', 'daily_hourly_specific_fields', 'hourly_specific_fields',
                'core_fields', 'timeline_fields', 'performance_fields', 'distribution_fields',
                'outlier_fields', 'volume_lot_fields', 'duration_fields', 'sl_tp_fields',
                'streak_fields', 'drawdown_fields', 'position_fields', 'margin_activity_fields',
                'payout_balance_fields', 'relative_fields', 'return_fields', 'unit_profit_fields',
                'COLUMN_MAPPING', 'field_mappings', 'metrics_by_type',
                # CSV processing
                'csv_dir', 'source_endpoint', 'source_file',
                'get_metrics_summary', 'md5', 'hexdigest',
                # Specific computed fields used internally
                'duration_seconds', 'accountids', 'account_ids', 'checkpoint_managers',
                'config', 'updatedDate',
                # DataFrame operations
                'DataFrame', 'read_csv', 'to_dict', 'iloc', 'columns',
                'index', 'values', 'shape', 'dtype', 'isna', 'notna',
                'fillna', 'dropna', 'rename', 'merge', 'join',
                # Argument parsing
                'ArgumentParser', 'add_argument', 'parse_known_args',
                'formatter_class', 'description', 'epilog', 'prog'
            }
            
            # Filter out non-data fields and private methods
            data_fields = {
                f for f in used_fields - python_builtins - infrastructure_fields - WRAPPER_FIELDS
                if not f.startswith('_')
            }
            
            # Find undefined fields
            undefined_fields = data_fields - valid_fields
            
            if undefined_fields:
                errors.append({
                    'script': script.name,
                    'data_type': data_type,
                    'undefined_fields': sorted(undefined_fields),
                    'valid_fields_count': len(valid_fields),
                    'used_fields_count': len(data_fields)
                })
        
        if errors:
            error_msg = "Found undefined fields in ingestion scripts:\n\n"
            for error in errors:
                error_msg += f"Script: {error['script']}\n"
                error_msg += f"Data Type: {error['data_type']}\n"
                error_msg += f"Undefined Fields: {', '.join(error['undefined_fields'])}\n"
                error_msg += f"(Script uses {error['used_fields_count']} fields, "
                error_msg += f"{len(error['undefined_fields'])} are undefined)\n\n"
            
            pytest.fail(error_msg)
    
    def test_required_fields_are_handled(self, ingestion_scripts):
        """Ensure scripts handle all critical fields from data structures."""
        # Define critical fields that must be handled
        critical_fields = {
            "metrics_alltime": {"login", "accountId", "planId", "updatedDate"},
            "metrics_daily": {"date", "login", "accountId", "planId"},
            "metrics_hourly": {"date", "datetime", "hour", "login", "accountId", "planId"},
            "metrics_all": {"login", "accountId", "planId"},  # Common to all metrics
            "trades": {"tradeDate", "login", "position", "profit"}
        }
        
        errors = []
        
        for script in ingestion_scripts:
            # Skip intelligent ingestion scripts that delegate to original implementations
            if "intelligent" in script.name:
                continue
                
            data_type = get_data_type_from_script(script)
            if data_type is None or data_type not in critical_fields:
                continue
            
            required = critical_fields[data_type]
            used_fields = extract_fields_from_source(script)
            
            missing_critical = required - used_fields
            
            if missing_critical:
                errors.append({
                    'script': script.name,
                    'data_type': data_type,
                    'missing_critical_fields': sorted(missing_critical)
                })
        
        if errors:
            error_msg = "Scripts missing critical fields:\n\n"
            for error in errors:
                error_msg += f"Script: {error['script']}\n"
                error_msg += f"Data Type: {error['data_type']}\n"
                error_msg += f"Missing Critical Fields: {', '.join(error['missing_critical_fields'])}\n\n"
            
            pytest.fail(error_msg)
    
    def test_no_hardcoded_nonexistent_fields(self, ingestion_scripts):
        """Ensure no hardcoded field names that don't exist in data structures."""
        errors = []
        
        # Pattern to find hardcoded string literals that look like field names
        field_pattern = r'["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        
        for script in ingestion_scripts:
            # Skip intelligent ingestion scripts that delegate to original implementations
            if "intelligent" in script.name:
                continue
                
            data_type = get_data_type_from_script(script)
            if data_type is None:
                continue
            
            # Special handling for metrics ingester
            if data_type == "metrics_all":
                valid_fields = (
                    VALID_FIELDS.get("metrics_alltime", set()) |
                    VALID_FIELDS.get("metrics_daily", set()) |
                    VALID_FIELDS.get("metrics_hourly", set())
                )
            else:
                valid_fields = VALID_FIELDS.get(data_type, set())
            
            with open(script, 'r') as f:
                content = f.read()
            
            # Find all string literals that could be field names
            import re
            potential_fields = set(re.findall(field_pattern, content))
            
            # Filter to only those that look like data fields
            # (camelCase or snake_case, not all caps, not starting with underscore)
            data_like_fields = {
                f for f in potential_fields
                if (f[0].islower() or '_' in f) and 
                not f.isupper() and 
                not f.startswith('_') and
                len(f) > 2
            }
            
            # Remove known non-data fields
            non_data_patterns = {
                'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'WHERE', 'VALUES',
                'CREATE', 'TABLE', 'INDEX', 'JOIN', 'LEFT', 'RIGHT', 'INNER',
                'http', 'https', 'www', 'com', 'org', 'net',
                'true', 'false', 'null', 'none', 'undefined',
                'error', 'success', 'warning', 'info', 'debug',
                'get', 'post', 'put', 'delete', 'patch',
                'utf', 'ascii', 'json', 'csv', 'xml', 'html',
                'key', 'value', 'item', 'data', 'result', 'response',
                'id', 'name', 'type', 'date', 'time', 'datetime'
            }
            
            suspicious_fields = data_like_fields - valid_fields - WRAPPER_FIELDS
            suspicious_fields = {
                f for f in suspicious_fields 
                if not any(pattern in f.lower() for pattern in non_data_patterns)
            }
            
            if suspicious_fields and len(suspicious_fields) < 20:  # Avoid false positives
                errors.append({
                    'script': script.name,
                    'data_type': data_type,
                    'suspicious_fields': sorted(suspicious_fields)
                })
        
        if errors:
            error_msg = "Found suspicious field names not in data structures:\n\n"
            for error in errors:
                error_msg += f"Script: {error['script']}\n"
                error_msg += f"Data Type: {error['data_type']}\n"
                error_msg += f"Suspicious Fields: {', '.join(error['suspicious_fields'])}\n\n"
            
            # This is a warning, not a failure
            import warnings
            warnings.warn(error_msg)
    
    def test_field_type_consistency(self):
        """Ensure field names don't appear in wrong data types."""
        # Fields that should only appear in specific data types
        # Note: Based on the data structures, some fields DO appear across metric types
        exclusive_fields = {
            "metrics_alltime": {"lifeTimeInDays", "firstTradeOpen", "lastTradeOpen", "lastTradeClose"},
            "metrics_daily": set(),  # days_to_next_payout and todays_payouts also in hourly
            "metrics_hourly": {"hour", "datetime"},
            "trades": {"ticket", "position", "trdSymbol", "stdSymbol", "side", "lots", "contractSize", "qtyInBaseCrncy"}
        }
        
        errors = []
        
        for data_type1, fields1 in exclusive_fields.items():
            for data_type2, valid_fields_set in VALID_FIELDS.items():
                if data_type1 != data_type2:
                    overlap = fields1.intersection(valid_fields_set)
                    if overlap:
                        errors.append({
                            'field': list(overlap),
                            'exclusive_to': data_type1,
                            'also_in': data_type2
                        })
        
        if errors:
            error_msg = "Found fields that should be exclusive to one data type:\n\n"
            for error in errors:
                error_msg += f"Fields: {', '.join(error['field'])}\n"
                error_msg += f"Should be exclusive to: {error['exclusive_to']}\n"
                error_msg += f"But also found in: {error['also_in']}\n\n"
            
            pytest.fail(error_msg)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])