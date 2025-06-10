"""
Comprehensive tests for enhanced metrics ingestion with risk factors.
"""

import pytest
from datetime import datetime, timedelta, date
from unittest.mock import Mock, patch, MagicMock
import json

from src.data_ingestion.ingest_metrics_v2 import MetricsIngesterV2, MetricType


class TestMetricsIngesterV2:
    """Test suite for enhanced metrics ingestion."""

    @pytest.fixture
    def ingester(self):
        """Create a test instance of MetricsIngesterV2."""
        with patch("src.data_ingestion.ingest_metrics_v2.get_db_manager"):
            with patch("src.data_ingestion.ingest_metrics_v2.RiskAnalyticsAPIClient"):
                return MetricsIngesterV2(
                    checkpoint_dir="/tmp/test_checkpoints",
                    enable_validation=True,
                    enable_deduplication=True,
                )

    @pytest.fixture
    def sample_alltime_metric(self):
        """Sample all-time metric with comprehensive risk factors."""
        return {
            "login": "142036",
            "accountId": "953785",
            "planId": 5198,
            "trader": "C521030",
            "status": 1,
            "type": 8,
            "phase": 4,
            "broker": 5,
            "mt_version": 5,
            "price_stream": 1,
            "country": "CA",
            "approved_payouts": 34372.5075,
            "pending_payouts": 3920,
            "startingBalance": 200000,
            "priorDaysBalance": 206880,
            "priorDaysEquity": 206880,
            "currentBalance": 206880,
            "currentEquity": 206880,
            "firstTradeDate": "2025-02-13T00:00:00.000Z",
            "daysSinceInitialDeposit": 118,
            "daysSinceFirstTrade": 116,
            "numTrades": 788,
            "firstTradeOpen": "2025-02-13T07:55:47.000Z",
            "lastTradeOpen": "2025-06-04T04:15:43.000Z",
            "lastTradeClose": "2025-06-04T04:32:20.000Z",
            "lifeTimeInDays": 110.858715277778,
            "netProfit": 60380.06,
            "grossProfit": 290229.84,
            "grossLoss": -229849.78,
            "gainToPain": 0.262693573167657,
            "profitFactor": 1.26269357316766,
            "successRate": 52.0304568527919,
            "meanProfit": 76.6244416243655,
            "medianProfit": 22.5,
            "stdProfits": 947.162248664395,
            "riskAdjProfit": 0.0808989607983369,
            "minProfit": -3562.5,
            "maxProfit": 8511,
            "profitPerc10": -867.5,
            "profitPerc25": -522.5,
            "profitPerc75": 482.765,
            "profitPerc90": 1065,
            "expectancy": 7662.44416243654,
            "profitTop10PrcntTrades": 158554.07,
            "profitBottom10PrcntTrades": -103578.26,
            "meanRet": 0.540203059070809,
            "stdRets": 4.32609797579687,
            "riskAdjRet": 0.124870740813794,
            "downsideStdRets": 1.32745463618453,
            "downsideRiskAdjRet": 0.406946530861124,
            "totalRet": 28.9007953199717,
            "dailyMeanRet": 0.239430696768549,
            "dailyStdRet": 1.43687320245324,
            "dailySharpe": 0.166633142270144,
            "dailyDownsideStdRet": 1.11777410761318,
            "dailySortino": 0.214203115940674,
            "relNetProfit": 30.19003,
            "relGrossProfit": 145.11492,
            "relGrossLoss": -114.92489,
            "meanDrawDown": -4119.54125,
            "medianDrawDown": -2109.5,
            "maxDrawDown": -22220,
            "meanNumTradesInDD": 28.125,
            "medianNumTradesInDD": 8.5,
            "maxNumTradesInDD": 272,
            "totalLots": 1911.81,
            "totalVolume": 513468784.374145,
            "meanWinningLot": 2.33168292682927,
            "meanLosingLot": 2.52862433862434,
            "meanDuration": 0.496435420191765,
            "medianDuration": 0.27,
            "stdDurations": 0.772431742015988,
            "cvDurations": 155.59561437369,
            "meanTP": 0.285172251555024,
            "meanSL": 0.137834456065543,
            "meanTPvsSL": 206.894748740778,
            "meanNumConsecWins": 4.27083333333333,
            "maxNumConsecWins": 22,
            "meanNumConsecLosses": 3.9375,
            "maxNumConsecLosses": 14,
            "meanNumOpenPos": 1.35913705583756,
            "maxNumOpenPos": 4,
            "meanAccountMargin": 30444.5906049718,
            "meanFirmMargin": 1217.78362419887,
            "meanTradesPerDay": 11.7611940298507,
            "medianTradesPerDay": 8,
            "maxTradesPerDay": 67,
            "numTradedSymbols": 5,
            "mostTradedSymbol": "XAUUSD",
            "mostTradedSmbTrades": 702,
            "updatedDate": "2025-06-09T00:00:00.000Z"
        }

    @pytest.fixture
    def sample_daily_metric(self):
        """Sample daily metric with comprehensive risk factors."""
        return {
            "date": "2025-02-13T00:00:00.000Z",
            "login": "142036",
            "planId": 5036,
            "accountId": "953785",
            "trader": "C521030",
            "status": 1,
            "type": 7,
            "phase": 4,
            "broker": 5,
            "mt_version": 5,
            "price_stream": 1,
            "country": "CA",
            "days_to_next_payout": 3,
            "todays_payouts": 0,
            "approved_payouts": 0,
            "pending_payouts": 0,
            "startingBalance": 200000,
            "priorDaysBalance": 200000,
            "priorDaysEquity": 200000,
            "currentBalance": 201786.32,
            "currentEquity": 201786.32,
            "numTrades": 15,
            "netProfit": 1933.82,
            "grossProfit": 3863.75,
            "grossLoss": -1929.93,
            "gainToPain": 1.00201561714674,
            "profitFactor": 2.00201561714674,
            "successRate": 60,
            "meanProfit": 128.921333333333,
            "medianProfit": 117.05,
            "stdProfits": 477.853513605256,
            "riskAdjProfit": 0.269792582167413,
            "minProfit": -594.96,
            "maxProfit": 1386,
            "profitPerc10": -556.35,
            "profitPerc25": -195.27,
            "profitPerc75": 408,
            "profitPerc90": 499.42,
            "dailySharpe": 0.166633142270144,
            "dailySortino": 0.214203115940674,
            "totalLots": 45.5,
            "totalVolume": 7600969.28323,
            "meanDuration": 0.560611111111111,
            "meanTP": 0.254587693008415,
            "meanSL": 0.130931759335018,
            "meanTPvsSL": 194.44303987163,
            "meanNumConsecWins": 3,
            "maxNumConsecWins": 5,
            "meanNumConsecLosses": 3,
            "maxNumConsecLosses": 5,
            "meanNumOpenPos": 1.8,
            "maxNumOpenPos": 3,
            "meanAccountMargin": 24308.7667768912,
            "meanFirmMargin": 972.350671075648,
            "numTradedSymbols": 2,
            "mostTradedSmbTrades": 10,
            "mostTradedSymbol": "GBPJPY"
        }

    def test_field_mapping_initialization(self, ingester):
        """Test that all field mappings are properly initialized."""
        # Check that all field mapping dictionaries exist
        assert hasattr(ingester, 'core_fields')
        assert hasattr(ingester, 'performance_fields')
        assert hasattr(ingester, 'distribution_fields')
        assert hasattr(ingester, 'return_fields')
        assert hasattr(ingester, 'drawdown_fields')
        
        # Check some critical mappings
        assert ingester.performance_fields['gainToPain'] == 'gain_to_pain'
        assert ingester.return_fields['dailySharpe'] == 'daily_sharpe'
        assert ingester.distribution_fields['profitPerc90'] == 'profit_perc_90'

    def test_transform_alltime_metric(self, ingester, sample_alltime_metric):
        """Test transformation of all-time metric with all new fields."""
        result = ingester._transform_alltime_metric(sample_alltime_metric)
        
        # Check core fields
        assert result['account_id'] == '953785'
        assert result['login'] == '142036'
        assert result['plan_id'] == '5198'
        assert result['trader_id'] == 'C521030'
        
        # Check risk metrics
        assert result['gain_to_pain'] == pytest.approx(0.262693573167657)
        assert result['risk_adj_profit'] == pytest.approx(0.0808989607983369)
        assert result['daily_sharpe'] == pytest.approx(0.166633142270144)
        assert result['daily_sortino'] == pytest.approx(0.214203115940674)
        
        # Check distribution metrics
        assert result['min_profit'] == -3562.5
        assert result['max_profit'] == 8511
        assert result['profit_perc_10'] == -867.5
        assert result['profit_perc_90'] == 1065
        
        # Check behavioral metrics
        assert result['mean_num_consec_wins'] == pytest.approx(4.27083333333333)
        assert result['max_num_consec_wins'] == 22
        assert result['mean_tp_vs_sl'] == pytest.approx(206.894748740778)
        
        # Check efficiency metrics
        assert result['mean_duration'] == pytest.approx(0.496435420191765)
        assert result['cv_durations'] == pytest.approx(155.59561437369)
        
        # Check that all expected fields are present
        expected_fields = [
            'net_profit', 'gross_profit', 'gross_loss', 'gain_to_pain',
            'daily_sharpe', 'daily_sortino', 'mean_profit', 'median_profit',
            'profit_perc_10', 'profit_perc_25', 'profit_perc_75', 'profit_perc_90',
            'mean_num_consec_wins', 'max_num_consec_wins', 'mean_tp_vs_sl',
            'total_lots', 'total_volume', 'mean_duration', 'cv_durations'
        ]
        
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_transform_daily_metric(self, ingester, sample_daily_metric):
        """Test transformation of daily metric with all new fields."""
        result = ingester._transform_daily_metric(sample_daily_metric)
        
        # Check date parsing
        assert result['date'] == date(2025, 2, 13)
        
        # Check daily-specific fields
        assert result['days_to_next_payout'] == 3
        assert result['todays_payouts'] == 0
        
        # Check balance fields
        assert result['balance_start'] == 200000  # priorDaysBalance
        assert result['balance_end'] == 201786.32  # currentBalance
        assert result['equity_start'] == 200000  # priorDaysEquity
        assert result['equity_end'] == 201786.32  # currentEquity
        
        # Check risk metrics
        assert result['gain_to_pain'] == pytest.approx(1.00201561714674)
        assert result['daily_sharpe'] == pytest.approx(0.166633142270144)
        
        # Check all standard daily fields are present
        assert result['net_profit'] == 1933.82
        assert result['total_trades'] == 15
        assert result['mean_duration'] == pytest.approx(0.560611111111111)

    def test_parse_date_formats(self, ingester):
        """Test parsing of various date formats."""
        # ISO format with time
        assert ingester._parse_date("2025-06-09T00:00:00.000Z") == date(2025, 6, 9)
        
        # Simple date format
        assert ingester._parse_date("2025-06-09") == date(2025, 6, 9)
        
        # Invalid format
        assert ingester._parse_date("invalid") is None
        
        # None input
        assert ingester._parse_date(None) is None

    def test_parse_timestamp_formats(self, ingester):
        """Test parsing of various timestamp formats."""
        # ISO format with milliseconds
        result = ingester._parse_timestamp("2025-02-13T07:55:47.000Z")
        assert result == datetime(2025, 2, 13, 7, 55, 47)
        
        # ISO format without milliseconds
        result = ingester._parse_timestamp("2025-02-13T07:55:47Z")
        assert result == datetime(2025, 2, 13, 7, 55, 47)
        
        # Invalid format
        assert ingester._parse_timestamp("invalid") is None

    def test_safe_conversions(self, ingester):
        """Test safe type conversions."""
        # Safe float
        assert ingester._safe_float(123.45) == 123.45
        assert ingester._safe_float("123.45") == 123.45
        assert ingester._safe_float(None) is None
        assert ingester._safe_float("invalid") is None
        
        # Safe int
        assert ingester._safe_int(123) == 123
        assert ingester._safe_int("123") == 123
        assert ingester._safe_int(123.9) == 123
        assert ingester._safe_int(None) is None
        assert ingester._safe_int("invalid") is None

    def test_comprehensive_field_coverage(self, ingester, sample_alltime_metric):
        """Test that all fields from the API are properly mapped."""
        result = ingester._transform_alltime_metric(sample_alltime_metric)
        
        # List of critical fields that must be present
        critical_fields = {
            # Risk metrics
            'gain_to_pain', 'risk_adj_profit', 'daily_sharpe', 'daily_sortino',
            'risk_adj_ret', 'downside_risk_adj_ret',
            
            # Distribution metrics
            'min_profit', 'max_profit', 'profit_perc_10', 'profit_perc_25',
            'profit_perc_75', 'profit_perc_90',
            
            # Efficiency metrics
            'mean_duration', 'cv_durations', 'mean_tp', 'mean_sl', 'mean_tp_vs_sl',
            
            # Behavioral metrics
            'mean_num_consec_wins', 'max_num_consec_wins',
            'mean_num_consec_losses', 'max_num_consec_losses',
            
            # Volume metrics
            'total_lots', 'total_volume', 'mean_winning_lot', 'mean_losing_lot',
            
            # Activity metrics
            'mean_trades_per_day', 'num_traded_symbols', 'most_traded_symbol'
        }
        
        missing_fields = critical_fields - set(result.keys())
        assert not missing_fields, f"Missing critical fields: {missing_fields}"

    @patch('src.data_ingestion.ingest_metrics_v2.get_db_manager')
    def test_bulk_processing_with_risk_metrics(self, mock_db_manager):
        """Test bulk processing handles all new risk metrics correctly."""
        # This would be an integration test in practice
        # Here we just verify the structure is correct
        ingester = MetricsIngesterV2()
        
        # Verify extended field mappings
        assert len(ingester.alltime_field_mapping) > 80  # Should have 100+ fields
        assert 'gainToPain' in ingester.alltime_field_mapping
        assert 'dailySharpe' in ingester.alltime_field_mapping
        assert 'meanNumConsecWins' in ingester.alltime_field_mapping


if __name__ == "__main__":
    pytest.main([__file__, "-v"])