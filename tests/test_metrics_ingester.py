"""
Comprehensive tests for enhanced metrics ingestion with risk factors.
"""

import pytest
from datetime import datetime, date
from unittest.mock import patch

from src.data_ingestion.ingest_metrics import MetricsIngester


class TestMetricsIngester:
    """Test suite for enhanced metrics ingestion."""

    @pytest.fixture
    def ingester(self):
        """Create a test instance of MetricsIngester."""
        with patch("src.data_ingestion.base_ingester.get_db_manager"):
            with patch("src.utils.api_client.RiskAnalyticsAPIClient"):
                return MetricsIngester(
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
            "top10PrcntProfitContrib": 54.6305197287777,
            "bottom10PrcntLossContrib": 45.0634584031362,
            "oneStdOutlierProfit": 61953.6,
            "oneStdOutlierProfitContrib": 102.606059020147,
            "twoStdOutlierProfit": 70176.21,
            "twoStdOutlierProfitContrib": 116.2241475083,
            "netProfitPerUSDVolume": 0.000117592464892672,
            "grossProfitPerUSDVolume": 0.00112415772633813,
            "grossLossPerUSDVolume": -0.000900335729449451,
            "distanceGrossProfitLossPerUSDVolume": 0.000223821996888682,
            "multipleGrossProfitLossPerUSDVolume": 1.24859837232667,
            "grossProfitPerLot": 303.590874381531,
            "grossLossPerLot": -240.473917683246,
            "distanceGrossProfitLossPerLot": 63.1169566982854,
            "multipleGrossProfitLossPerLot": 1.26246903325883,
            "netProfitPerDuration": 154.349263786953,
            "grossProfitPerDuration": 1210.09352730457,
            "grossLossPerDuration": -1518.66110439176,
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
            "relMeanProfit": 0.0383122208121827,
            "relMedianProfit": 0.01125,
            "relStdProfits": 0.473581124332197,
            "relRiskAdjProfit": 0.000040449480399168,
            "relMinProfit": -1.78125,
            "relMaxProfit": 4.2555,
            "relProfitPerc10": -0.43375,
            "relProfitPerc25": -0.26125,
            "relProfitPerc75": 0.2413825,
            "relProfitPerc90": 0.5325,
            "relProfitTop10PrcntTrades": 79.277035,
            "relProfitBottom10PrcntTrades": -51.78913,
            "relOneStdOutlierProfit": 30.9768,
            "relTwoStdOutlierProfit": 35.088105,
            "meanDrawDown": -4119.54125,
            "medianDrawDown": -2109.5,
            "maxDrawDown": -22220,
            "meanNumTradesInDD": 28.125,
            "medianNumTradesInDD": 8.5,
            "maxNumTradesInDD": 272,
            "relMeanDrawDown": -2.059770625,
            "relMedianDrawDown": -1.05475,
            "relMaxDrawDown": -11.11,
            "totalLots": 1911.81,
            "totalVolume": 513468784.374145,
            "stdVolumes": 256455.092477096,
            "meanWinningLot": 2.33168292682927,
            "meanLosingLot": 2.52862433862434,
            "distanceWinLossLots": -0.19694141179507,
            "multipleWinLossLots": 0.922115195686911,
            "meanWinningVolume": 629696.031038676,
            "meanLosingVolume": 675379.395894941,
            "distanceWinLossVolume": -45683.3648562641,
            "multipleWinLossVolume": 0.932358959817349,
            "meanDuration": 0.496435420191765,
            "medianDuration": 0.27,
            "stdDurations": 0.772431742015988,
            "minDuration": 0.00666666666666667,
            "maxDuration": 7.73666666666667,
            "cvDurations": 155.59561437369,
            "meanTP": 0.285172251555024,
            "medianTP": 0.249051423141666,
            "stdTP": 0.237364596506122,
            "minTP": 0.0443937695420393,
            "maxTP": 2.36676184818228,
            "cvTP": 83.2355165033727,
            "meanSL": 0.137834456065543,
            "medianSL": 0.102124900616585,
            "stdSL": 0.305658672109091,
            "minSL": 0,
            "maxSL": 3.16346742318951,
            "cvSL": 221.757810662193,
            "meanTPvsSL": 206.894748740778,
            "medianTPvsSL": 243.86943990937,
            "minTPvsSL": 100,
            "maxTPvsSL": 74.8154329275826,
            "cvTPvsSL": 37.5344238179581,
            "meanNumConsecWins": 4.27083333333333,
            "medianNumConsecWins": 3,
            "maxNumConsecWins": 22,
            "meanNumConsecLosses": 3.9375,
            "medianNumConsecLosses": 3,
            "maxNumConsecLosses": 14,
            "meanValConsecWins": 3023.2275,
            "medianValConsecWins": 1619,
            "maxValConsecWins": 14601.15,
            "meanValConsecLosses": -2394.26854166667,
            "medianValConsecLosses": -1782.75,
            "maxValConsecLosses": -10308.5,
            "meanNumOpenPos": 1.35913705583756,
            "medianNumOpenPos": 1,
            "maxNumOpenPos": 4,
            "meanValOpenPos": 875770.394475777,
            "medianValOpenPos": 762205,
            "maxValOpenPos": 3231285,
            "meanValtoEqtyOpenPos": 378.628935822743,
            "medianValtoEqtyOpenPos": 341.507867496481,
            "maxValtoEqtyOpenPos": 1512.95392925506,
            "meanAccountMargin": 30444.5906049718,
            "meanFirmMargin": 1217.78362419887,
            "meanTradesPerDay": 11.7611940298507,
            "medianTradesPerDay": 8,
            "minTradesPerDay": 1,
            "maxTradesPerDay": 67,
            "cvTradesPerDay": 104.507676592427,
            "meanIdleDays": 2.25,
            "medianIdleDays": 2,
            "maxIdleDays": 5,
            "minIdleDays": 1,
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
            "firstTradeDate": "2025-02-13T00:00:00.000Z",
            "daysSinceInitialDeposit": 2,
            "daysSinceFirstTrade": 1,
            "numTrades": 15,
            "netProfit": 1933.8200000000002,
            "grossProfit": 3863.75,
            "grossLoss": -1929.9299999999998,
            "gainToPain": 1.002015617146736,
            "profitFactor": 2.002015617146736,
            "successRate": 60,
            "meanProfit": 128.92133333333334,
            "medianProfit": 117.05,
            "stdProfits": 477.85351360525635,
            "riskAdjProfit": 0.2697925821674134,
            "minProfit": -594.96,
            "maxProfit": 1386,
            "profitPerc10": -556.35,
            "profitPerc25": -195.27,
            "profitPerc75": 408,
            "profitPerc90": 499.42,
            "expectancy": 12892.133333333333,
            "profitTop10PrcntTrades": 1386,
            "profitBottom10PrcntTrades": -594.96,
            "top10PrcntProfitContrib": 35.87188612099644,
            "bottom10PrcntLossContrib": 30.82806112138783,
            "oneStdOutlierProfit": 234.68999999999994,
            "oneStdOutlierProfitContrib": 12.136082986006967,
            "twoStdOutlierProfit": 1386,
            "twoStdOutlierProfitContrib": 71.67161369724172,
            "netProfitPerUSDVolume": 0.00025441755228067855,
            "grossProfitPerUSDVolume": 0.0008517108300391275,
            "grossLossPerUSDVolume": -0.0006297675288139097,
            "distanceGrossProfitLossPerUSDVolume": 0.00022194330122521778,
            "multipleGrossProfitLossPerUSDVolume": 1.352420998337626,
            "grossProfitPerLot": 154.55,
            "grossLossPerLot": -94.14292682926829,
            "distanceGrossProfitLossPerLot": 60.40707317073172,
            "multipleGrossProfitLossPerLot": 1.6416528060603235,
            "netProfitPerDuration": 229.96571202061247,
            "grossProfitPerDuration": 754.025044722719,
            "grossLossPerDuration": -587.4977168949771,
            "meanRet": 0.01811326950904731,
            "stdRets": 0.08346189885685884,
            "riskAdjRet": 0.21702441182308152,
            "downsideStdRets": 0.05238118174091061,
            "downsideRiskAdjRet": 0.34579726739728234,
            "relNetProfit": 0.9669100000000002,
            "relGrossProfit": 1.931875,
            "relGrossLoss": -0.964965,
            "relMeanProfit": 0.06446066666666667,
            "relMedianProfit": 0.058524999999999994,
            "relStdProfits": 0.23892675680262818,
            "relRiskAdjProfit": 0.0001348962910837067,
            "relMinProfit": -0.29748,
            "relMaxProfit": 0.6930000000000001,
            "relProfitPerc10": -0.278175,
            "relProfitPerc25": -0.09763500000000001,
            "relProfitPerc75": 0.20400000000000001,
            "relProfitPerc90": 0.24971,
            "relProfitTop10PrcntTrades": 0.6930000000000001,
            "relProfitBottom10PrcntTrades": -0.29748,
            "relOneStdOutlierProfit": 0.11734499999999998,
            "relTwoStdOutlierProfit": 0.6930000000000001,
            "meanDrawDown": -964.9649999999999,
            "medianDrawDown": -964.9649999999999,
            "maxDrawDown": -1743.9299999999998,
            "meanNumTradesInDD": 5.5,
            "medianNumTradesInDD": 5.5,
            "maxNumTradesInDD": 10,
            "relMeanDrawDown": -0.4824825,
            "relMedianDrawDown": -0.4824825,
            "relMaxDrawDown": -0.8719649999999999,
            "totalLots": 45.5,
            "totalVolume": 7600969.28323,
            "stdVolumes": 154636.0642277665,
            "meanWinningLot": 2.7777777777777777,
            "meanLosingLot": 3.4166666666666665,
            "distanceWinLossLots": -0.6388888888888888,
            "multipleWinLossLots": 0.8130081300813008,
            "meanWinningVolume": 504050.83558211115,
            "meanLosingVolume": 510751.9604985,
            "distanceWinLossVolume": -6701.124916388828,
            "multipleWinLossVolume": 0.9868798841029441,
            "meanDuration": 0.5606111111111111,
            "medianDuration": 0.24888888888888888,
            "stdDurations": 0.4488635306368768,
            "minDuration": 0.11722222222222223,
            "maxDuration": 1.3066666666666666,
            "cvDurations": 80.06682738543041,
            "meanTP": 0.2545876930084151,
            "medianTP": 0.24739786320349122,
            "stdTP": 0.03955151078766531,
            "minTP": 0.2008321661036483,
            "maxTP": 0.3203004773207452,
            "cvTP": 15.53551560968738,
            "meanSL": 0.13093175933501788,
            "medianSL": 0.13093175933501788,
            "stdSL": 0.004406586529637213,
            "minSL": 0.12652517280538067,
            "maxSL": 0.1353383458646551,
            "cvSL": 3.365559702258324,
            "meanTPvsSL": 194.44303987162974,
            "medianTPvsSL": 188.95175964944383,
            "minTPvsSL": 158.72901941226007,
            "maxTPvsSL": 236.66646379811766,
            "cvTPvsSL": 461.60273428704573,
            "meanNumConsecWins": 3,
            "medianNumConsecWins": 3,
            "maxNumConsecWins": 5,
            "meanNumConsecLosses": 3,
            "medianNumConsecLosses": 3,
            "maxNumConsecLosses": 5,
            "meanValConsecWins": 1287.9166666666667,
            "medianValConsecWins": 1386,
            "maxValConsecWins": 1544.25,
            "meanValConsecLosses": -964.9649999999999,
            "medianValConsecLosses": -964.9649999999999,
            "maxValConsecLosses": -1743.9299999999998,
            "meanNumOpenPos": 1.8,
            "medianNumOpenPos": 2,
            "maxNumOpenPos": 3,
            "meanValOpenPos": 1156196.0052442665,
            "medianValOpenPos": 1309249.5253599996,
            "maxValOpenPos": 1746304.5908679995,
            "meanValtoEqtyOpenPos": 578.0980026221332,
            "medianValtoEqtyOpenPos": 654.6247626799999,
            "maxValtoEqtyOpenPos": 873.1522954339997,
            "meanAccountMargin": 24308.766776891196,
            "meanFirmMargin": 972.3506710756477,
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
        assert result['login'] == '142036'
        assert result['account_id'] == '953785'
        assert result['plan_id'] == 5036
        assert result['trader_id'] == 'C521030'

        assert result['status'] == 1
        assert result['type'] == 7
        assert result['phase'] == 4
        assert result['broker'] == 5
        assert result['mt_version'] == 5
        assert result['price_stream'] == 1
        assert result['country'] == 'CA'

        assert result['days_to_next_payout'] == 3
        assert result['todays_payouts'] == 0
        assert result['approved_payouts'] == 0
        assert result['pending_payouts'] == 0
        assert result['starting_balance'] == 200000
        assert result['prior_days_balance'] == 200000
        assert result['prior_days_equity'] == 200000
        assert result['current_balance'] == 201786.32
        assert result['current_equity'] == 201786.32
        assert result['first_trade_date'] == date(2025, 2, 13)
        assert result['days_since_initial_deposit'] == 2
        assert result['days_since_first_trade'] == 1
        assert result['num_trades'] == 15
        assert result['net_profit'] == 1933.82
        assert result['gross_profit'] == 3863.75
        assert result['gross_loss'] == -1929.93
        assert result['mean_profit'] == 128.92133333333334
        assert result['median_profit'] == 117.05
        assert result['std_profits'] == 477.85351360525635
        assert result['risk_adj_profit'] == 0.2697925821674134
        assert result['min_profit'] == -594.96
        assert result['max_profit'] == 1386
        assert result['profit_perc_10'] == -556.35
        assert result['profit_perc_25'] == -195.27
        assert result['profit_perc_75'] == 408
        assert result['profit_perc_90'] == 499.42
        assert result['expectancy'] == 12892.133333333333
        assert result['profit_top_10_prcnt_trades'] == 1386
        assert result['profit_bottom_10_prcnt_trades'] == -594.96
        assert result['top_10_prcnt_profit_contrib'] == 35.87188612099644
        assert result['bottom_10_prcnt_loss_contrib'] == 30.82806112138783
        assert result['one_std_outlier_profit'] == 234.69
        assert result['one_std_outlier_profit_contrib'] == 12.136082986006967
        assert result['two_std_outlier_profit'] == 1386
        assert result['two_std_outlier_profit_contrib'] == 71.67161369724172
        assert result['net_profit_per_usd_volume'] == 0.00025441755228067855
        assert result['gross_profit_per_usd_volume'] == 0.0008517108300391275
        assert result['gross_loss_per_usd_volume'] == -0.0006297675288139097
        assert result['distance_gross_profit_loss_per_usd_volume'] == 0.00022194330122521778
        assert result['multiple_gross_profit_loss_per_usd_volume'] == 1.352420998337626
        assert result['gross_profit_per_lot'] == 154.55
        assert result['gross_loss_per_lot'] == -94.14292682926829
        assert result['distance_gross_profit_loss_per_lot'] == 60.40707317073172
        assert result['multiple_gross_profit_loss_per_lot'] == 1.6416528060603235
        assert result['net_profit_per_duration'] == 229.96571202061247
        assert result['gross_profit_per_duration'] == 754.025044722719
        assert result['gross_loss_per_duration'] == -587.4977168949771
        assert result['mean_ret'] == 0.01811326950904731
        assert result['std_rets'] == 0.08346189885685884
        assert result['risk_adj_ret'] == 0.21702441182308152
        assert result['downside_std_rets'] == 0.05238118174091061
        assert result['downside_risk_adj_ret'] == 0.34579726739728234
        assert result['rel_net_profit'] == 0.9669100000000002
        assert result['rel_gross_profit'] == 1.931875
        assert result['rel_gross_loss'] == -0.964965
        assert result['rel_mean_profit'] == 0.06446066666666667
        assert result['rel_median_profit'] == 0.058524999999999994
        assert result['rel_std_profits'] == 0.23892675680262818
        assert result['rel_risk_adj_profit'] == 0.0001348962910837067
        assert result['rel_min_profit'] == -0.29748
        assert result['rel_max_profit'] == 0.6930000000000001
        assert result['rel_profit_perc_10'] == -0.278175
        assert result['rel_profit_perc_25'] == -0.09763500000000001
        assert result['rel_profit_perc_75'] == 0.20400000000000001
        assert result['rel_profit_perc_90'] == 0.24971
        assert result['rel_profit_top_10_prcnt_trades'] == 0.6930000000000001
        assert result['rel_profit_bottom_10_prcnt_trades'] == -0.29748
        assert result['rel_one_std_outlier_profit'] == 0.11734499999999998
        assert result['rel_two_std_outlier_profit'] == 0.6930000000000001
        assert result['mean_draw_down'] == -964.9649999999999
        assert result['median_draw_down'] == -964.9649999999999
        assert result['max_draw_down'] == -1743.9299999999998
        assert result['mean_num_trades_in_dd'] == 5.5
        assert result['median_num_trades_in_dd'] == 5.5
        assert result['max_num_trades_in_dd'] == 10
        assert result['rel_mean_draw_down'] == -0.4824825
        assert result['rel_median_draw_down'] == -0.4824825
        assert result['rel_max_draw_down'] == -0.8719649999999999
        assert result['total_lots'] == 45.5
        assert result['total_volume'] == 7600969.28323
        assert result['std_volumes'] == 154636.0642277665
        assert result['mean_winning_lot'] == 2.7777777777777777
        assert result['mean_losing_lot'] == 3.4166666666666665
        assert result['distance_win_loss_lots'] == -0.6388888888888888
        assert result['multiple_win_loss_lots'] == 0.8130081300813008
        assert result['mean_winning_volume'] == 504050.83558211115
        assert result['mean_losing_volume'] == 510751.9604985
        assert result['distance_win_loss_volume'] == -6701.124916388828
        assert result['multiple_win_loss_volume'] == 0.9868798841029441
        assert result['mean_duration'] == 0.5606111111111111
        assert result['median_duration'] == 0.24888888888888888
        assert result['std_durations'] == 0.4488635306368768
        assert result['min_duration'] == 0.11722222222222223
        assert result['max_duration'] == 1.3066666666666666
        assert result['cv_durations'] == 80.06682738543041
        assert result['mean_tp'] == 0.2545876930084151
        assert result['median_tp'] == 0.24739786320349122
        assert result['std_tp'] == 0.03955151078766531
        assert result['min_tp'] == 0.2008321661036483
        assert result['max_tp'] == 0.3203004773207452
        assert result['cv_tp'] == 15.53551560968738
        assert result['mean_sl'] == 0.13093175933501788
        assert result['median_sl'] == 0.13093175933501788
        assert result['std_sl'] == 0.004406586529637213
        assert result['min_sl'] == 0.12652517280538067
        assert result['max_sl'] == 0.1353383458646551
        assert result['cv_sl'] == 3.365559702258324
        assert result['mean_tp_vs_sl'] == 194.44303987162974
        assert result['median_tp_vs_sl'] == 188.95175964944383
        assert result['min_tp_vs_sl'] == 158.72901941226007
        assert result['max_tp_vs_sl'] == 236.66646379811766
        assert result['cv_tp_vs_sl'] == 461.60273428704573
        assert result['mean_num_consec_wins'] == 3
        assert result['median_num_consec_wins'] == 3
        assert result['max_num_consec_wins'] == 5
        assert result['mean_num_consec_losses'] == 3
        assert result['median_num_consec_losses'] == 3
        assert result['max_num_consec_losses'] == 5
        assert result['mean_val_consec_wins'] == 1287.9166666666667
        assert result['median_val_consec_wins'] == 1386
        assert result['max_val_consec_wins'] == 1544.25
        assert result['mean_val_consec_losses'] == -964.9649999999999
        assert result['median_val_consec_losses'] == -964.9649999999999
        assert result['max_val_consec_losses'] == -1743.9299999999998
        assert result['mean_num_open_pos'] == 1.8
        assert result['median_num_open_pos'] == 2
        assert result['max_num_open_pos'] == 3
        assert result['mean_val_open_pos'] == 1156196.0052442665
        assert result['median_val_open_pos'] == 1309249.5253599996
        assert result['max_val_open_pos'] == 1746304.5908679995
        assert result['mean_valtoeqty_open_pos'] == 578.0980026221332
        assert result['median_valtoeqty_open_pos'] == 654.6247626799999
        assert result['max_valtoeqty_open_pos'] == 873.1522954339997
        assert result['mean_account_margin'] == 24308.766776891196
        assert result['mean_firm_margin'] == 972.3506710756477
        assert result['num_traded_symbols'] == 2
        assert result['most_traded_smb_trades'] == 10
        assert result['most_traded_symbol'] == 'GBPJPY'
        
        # Check that all expected fields are present
        expected_fields = [
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
        assert result['num_trades'] == 15
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

    @patch('src.data_ingestion.base_ingester.get_db_manager')
    @patch('src.utils.api_client.RiskAnalyticsAPIClient')
    def test_bulk_processing_with_risk_metrics(self, mock_api_client, mock_db_manager):
        """Test bulk processing handles all new risk metrics correctly."""
        # This would be an integration test in practice
        # Here we just verify the structure is correct
        ingester = MetricsIngester()
        
        # Verify extended field mappings
        assert len(ingester.alltime_field_mapping) > 80  # Should have 100+ fields
        assert 'gainToPain' in ingester.alltime_field_mapping
        assert 'dailySharpe' in ingester.alltime_field_mapping
        assert 'meanNumConsecWins' in ingester.alltime_field_mapping


if __name__ == "__main__":
    pytest.main([__file__, "-v"])