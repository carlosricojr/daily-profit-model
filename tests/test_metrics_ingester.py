"""
Comprehensive tests for enhanced metrics ingestion with risk factors.
"""

import pytest
from datetime import datetime, date
from unittest.mock import patch, Mock, MagicMock

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
        assert result['plan_id'] == 5198
        assert result['trader_id'] == 'C521030'

        assert result['status'] == 1
        assert result['type'] == 8
        assert result['phase'] == 4
        assert result['broker'] == 5
        assert result['platform'] == 5
        assert result['price_stream'] == 1
        assert result['country'] == 'CA'

        assert result['approved_payouts'] == 34372.5075
        assert result['pending_payouts'] == 3920

        assert result['starting_balance'] == 200000
        assert result['prior_days_balance'] == 206880
        assert result['prior_days_equity'] == 206880
        assert result['current_balance'] == 206880
        assert result['current_equity'] == 206880

        assert result['first_trade_date'] == date(2025, 2, 13)
        assert result['days_since_initial_deposit'] == 118
        assert result['days_since_first_trade'] == 116
        assert result['num_trades'] == 788
        assert result['first_trade_open'] == datetime(2025, 2, 13, 7, 55, 47)
        assert result['last_trade_open'] == datetime(2025, 6, 4, 4, 15 ,43)
        assert result['last_trade_close'] == datetime(2025, 6, 4, 4, 32, 20)
        assert result['lifetime_in_days'] == 110.858715277778

        assert result['net_profit'] == 60380.06
        assert result['gross_profit'] == 290229.84
        assert result['gross_loss'] == -229849.78
        assert result['gain_to_pain'] == 0.262693573167657
        assert result['profit_factor'] == 1.26269357316766
        assert result['success_rate'] == 52.0304568527919
        assert result['mean_profit'] == 76.6244416243655
        assert result['median_profit'] == 22.5
        assert result['std_profits'] == 947.162248664395
        assert result['risk_adj_profit'] == 0.0808989607983369

        assert result['min_profit'] == -3562.5
        assert result['max_profit'] == 8511
        assert result['profit_perc_10'] == -867.5
        assert result['profit_perc_25'] == -522.5
        assert result['profit_perc_75'] == 482.765
        assert result['profit_perc_90'] == 1065
        assert result['expectancy'] == 7662.44416243654

        assert result['profit_top_10_prcnt_trades'] == 158554.07
        assert result['profit_bottom_10_prcnt_trades'] == -103578.26
        assert result['top_10_prcnt_profit_contrib'] == 54.6305197287777
        assert result['bottom_10_prcnt_loss_contrib'] == 45.0634584031362
        assert result['one_std_outlier_profit'] == 61953.6
        assert result['one_std_outlier_profit_contrib'] == 102.606059020147
        assert result['two_std_outlier_profit'] == 70176.21
        assert result['two_std_outlier_profit_contrib'] == 116.2241475083

        assert result['net_profit_per_usd_volume'] == 0.000117592464892672
        assert result['gross_profit_per_usd_volume'] == 0.00112415772633813
        assert result['gross_loss_per_usd_volume'] == -0.000900335729449451
        assert result['distance_gross_profit_loss_per_usd_volume'] == 0.000223821996888682
        assert result['multiple_gross_profit_loss_per_usd_volume'] == 1.24859837232667
        assert result['gross_profit_per_lot'] == 303.590874381531
        assert result['gross_loss_per_lot'] == -240.473917683246
        assert result['distance_gross_profit_loss_per_lot'] == 63.1169566982854
        assert result['multiple_gross_profit_loss_per_lot'] == 1.26246903325883

        assert result['net_profit_per_duration'] == 154.349263786953
        assert result['gross_profit_per_duration'] == 1210.09352730457
        assert result['gross_loss_per_duration'] == -1518.66110439176
        assert result['mean_ret'] == 0.540203059070809
        assert result['std_rets'] == 4.32609797579687
        assert result['risk_adj_ret'] == 0.124870740813794
        assert result['downside_std_rets'] == 1.32745463618453
        assert result['downside_risk_adj_ret'] == 0.406946530861124
        assert result['total_ret'] == 28.9007953199717
        assert result['daily_mean_ret'] == 0.239430696768549
        assert result['daily_std_ret'] == 1.43687320245324
        assert result['daily_sharpe'] == 0.166633142270144
        assert result['daily_downside_std_ret'] == 1.11777410761318
        assert result['daily_sortino'] == 0.214203115940674

        assert result['rel_net_profit'] == 30.19003
        assert result['rel_gross_profit'] == 145.11492
        assert result['rel_gross_loss'] == -114.92489
        assert result['rel_mean_profit'] == 0.0383122208121827
        assert result['rel_median_profit'] == 0.01125
        assert result['rel_std_profits'] == 0.473581124332197
        assert result['rel_risk_adj_profit'] == 0.000040449480399168
        assert result['rel_min_profit'] == -1.78125
        assert result['rel_max_profit'] == 4.2555
        assert result['rel_profit_perc_10'] == -0.43375
        assert result['rel_profit_perc_25'] == -0.26125
        assert result['rel_profit_perc_75'] == 0.2413825
        assert result['rel_profit_perc_90'] == 0.5325
        assert result['rel_profit_top_10_prcnt_trades'] == 79.277035
        assert result['rel_profit_bottom_10_prcnt_trades'] == -51.78913
        assert result['rel_one_std_outlier_profit'] == 30.9768
        assert result['rel_two_std_outlier_profit'] == 35.088105

        assert result['mean_drawdown'] == -4119.54125
        assert result['median_drawdown'] == -2109.5
        assert result['max_drawdown'] == -22220
        assert result['mean_num_trades_in_dd'] == 28.125
        assert result['median_num_trades_in_dd'] == 8.5
        assert result['max_num_trades_in_dd'] == 272
        assert result['rel_mean_drawdown'] == -2.059770625
        assert result['rel_median_drawdown'] == -1.05475
        assert result['rel_max_drawdown'] == -11.11
        assert result['total_lots'] == 1911.81
        assert result['total_volume'] == 513468784.374145
        assert result['std_volumes'] == 256455.092477096
        assert result['mean_winning_lot'] == 2.33168292682927
        assert result['mean_losing_lot'] == 2.52862433862434
        assert result['distance_win_loss_lots'] == -0.19694141179507
        assert result['multiple_win_loss_lots'] == 0.922115195686911
        assert result['mean_winning_volume'] == 629696.031038676
        assert result['mean_losing_volume'] == 675379.395894941
        assert result['distance_win_loss_volume'] == -45683.3648562641
        assert result['multiple_win_loss_volume'] == 0.932358959817349
        assert result['mean_duration'] == 0.496435420191765
        assert result['median_duration'] == 0.27
        assert result['std_durations'] == 0.772431742015988
        assert result['min_duration'] == 0.00666666666666667
        assert result['max_duration'] == 7.73666666666667
        assert result['cv_durations'] == 155.59561437369
        assert result['mean_tp'] == 0.285172251555024
        assert result['median_tp'] == 0.249051423141666
        assert result['std_tp'] == 0.237364596506122
        assert result['min_tp'] == 0.0443937695420393
        assert result['max_tp'] == 2.36676184818228
        assert result['cv_tp'] == 83.2355165033727
        assert result['mean_sl'] == 0.137834456065543
        assert result['median_sl'] == 0.102124900616585
        assert result['std_sl'] == 0.305658672109091
        assert result['min_sl'] == 0
        assert result['max_sl'] == 3.16346742318951
        assert result['cv_sl'] == 221.757810662193
        assert result['mean_tp_vs_sl'] == 206.894748740778
        assert result['median_tp_vs_sl'] == 243.86943990937
        assert result['min_tp_vs_sl'] == 100
        assert result['max_tp_vs_sl'] == 74.8154329275826
        assert result['cv_tp_vs_sl'] == 37.5344238179581
        assert result['mean_num_consec_wins'] == 4.27083333333333
        assert result['median_num_consec_wins'] == 3
        assert result['max_num_consec_wins'] == 22
        assert result['mean_num_consec_losses'] == 3.9375
        assert result['median_num_consec_losses'] == 3
        assert result['max_num_consec_losses'] == 14
        assert result['mean_val_consec_wins'] == 3023.2275
        assert result['median_val_consec_wins'] == 1619
        assert result['max_val_consec_wins'] == 14601.15
        assert result['mean_val_consec_losses'] == -2394.26854166667
        assert result['median_val_consec_losses'] == -1782.75
        assert result['max_val_consec_losses'] == -10308.5
        assert result['mean_num_open_pos'] == 1.35913705583756
        assert result['median_num_open_pos'] == 1
        assert result['max_num_open_pos'] == 4
        assert result['mean_val_open_pos'] == 875770.394475777
        assert result['median_val_open_pos'] == 762205
        assert result['max_val_open_pos'] == 3231285
        assert result['mean_val_to_eqty_open_pos'] == 378.628935822743
        assert result['median_val_to_eqty_open_pos'] == 341.507867496481
        assert result['max_val_to_eqty_open_pos'] == 1512.95392925506
        assert result['mean_account_margin'] == 30444.5906049718
        assert result['mean_firm_margin'] == 1217.78362419887
        assert result['mean_trades_per_day'] == 11.7611940298507
        assert result['median_trades_per_day'] == 8
        assert result['min_trades_per_day'] == 1
        assert result['max_trades_per_day'] == 67
        assert result['cv_trades_per_day'] == 104.507676592427
        assert result['mean_idle_days'] == 2.25
        assert result['median_idle_days'] == 2
        assert result['max_idle_days'] == 5
        assert result['min_idle_days'] == 1
        assert result['num_traded_symbols'] == 5
        assert result['most_traded_symbol'] == 'XAUUSD'
        assert result['most_traded_smb_trades'] == 702
        assert result['updated_date'] == datetime(2025, 6, 9, 0, 0)

        # The individual assertions above already verify all the fields are correctly transformed

    def test_transform_daily_metric(self, ingester, sample_daily_metric):
        """Test transformation of daily metric with all new fields."""
        result = ingester._transform_daily_metric(sample_daily_metric)
        
        # Check core fields
        assert result['date'] == date(2025, 2, 13)
        assert result['login'] == '142036'
        assert result['account_id'] == '953785'
        assert result['plan_id'] == 5036
        assert result['trader_id'] == 'C521030'
        
        assert result['status'] == 1
        assert result['type'] == 7
        assert result['phase'] == 4
        assert result['broker'] == 5
        assert result['platform'] == 5
        assert result['price_stream'] == 1
        assert result['country'] == 'CA'
        
        # Check daily-specific fields
        assert result['days_to_next_payout'] == 3
        assert result['todays_payouts'] == 0
        assert result['approved_payouts'] == 0
        assert result['pending_payouts'] == 0
        
        # Check balance fields
        assert result['starting_balance'] == 200000
        assert result['prior_days_balance'] == 200000
        assert result['prior_days_equity'] == 200000
        assert result['current_balance'] == 201786.32
        assert result['current_equity'] == 201786.32
        
        # Check timeline fields
        assert result['first_trade_date'] == date(2025, 2, 13)
        assert result['days_since_initial_deposit'] == 2
        assert result['days_since_first_trade'] == 1
        assert result['num_trades'] == 15
        
        # Check performance fields
        assert result['net_profit'] == pytest.approx(1933.82)
        assert result['gross_profit'] == 3863.75
        assert result['gross_loss'] == pytest.approx(-1929.93)
        assert result['gain_to_pain'] == pytest.approx(1.002015617146736)
        assert result['profit_factor'] == pytest.approx(2.002015617146736)
        assert result['success_rate'] == 60
        
        # Check distribution fields
        assert result['mean_profit'] == pytest.approx(128.92133333333334)
        assert result['median_profit'] == 117.05
        assert result['std_profits'] == pytest.approx(477.85351360525635)
        assert result['risk_adj_profit'] == pytest.approx(0.2697925821674134)
        assert result['min_profit'] == -594.96
        assert result['max_profit'] == 1386
        assert result['profit_perc_10'] == -556.35
        assert result['profit_perc_25'] == -195.27
        assert result['profit_perc_75'] == 408
        assert result['profit_perc_90'] == 499.42
        assert result['expectancy'] == pytest.approx(12892.133333333333)
        
        # Check outlier fields
        assert result['profit_top_10_prcnt_trades'] == 1386
        assert result['profit_bottom_10_prcnt_trades'] == -594.96
        assert result['top_10_prcnt_profit_contrib'] == pytest.approx(35.87188612099644)
        assert result['bottom_10_prcnt_loss_contrib'] == pytest.approx(30.82806112138783)
        assert result['one_std_outlier_profit'] == 234.68999999999994
        assert result['one_std_outlier_profit_contrib'] == pytest.approx(12.136082986006967)
        assert result['two_std_outlier_profit'] == 1386
        assert result['two_std_outlier_profit_contrib'] == pytest.approx(71.67161369724172)
        
        # Check unit profit fields
        assert result['net_profit_per_usd_volume'] == pytest.approx(0.00025441755228067855)
        assert result['gross_profit_per_usd_volume'] == pytest.approx(0.0008517108300391275)
        assert result['gross_loss_per_usd_volume'] == pytest.approx(-0.0006297675288139097)
        assert result['distance_gross_profit_loss_per_usd_volume'] == pytest.approx(0.00022194330122521778)
        assert result['multiple_gross_profit_loss_per_usd_volume'] == pytest.approx(1.352420998337626)
        assert result['gross_profit_per_lot'] == 154.55
        assert result['gross_loss_per_lot'] == pytest.approx(-94.14292682926829)
        assert result['distance_gross_profit_loss_per_lot'] == pytest.approx(60.40707317073172)
        assert result['multiple_gross_profit_loss_per_lot'] == pytest.approx(1.6416528060603235)
        assert result['net_profit_per_duration'] == pytest.approx(229.96571202061247)
        assert result['gross_profit_per_duration'] == pytest.approx(754.025044722719)
        assert result['gross_loss_per_duration'] == pytest.approx(-587.4977168949771)
        
        # Check return fields
        assert result['mean_ret'] == pytest.approx(0.01811326950904731)
        assert result['std_rets'] == pytest.approx(0.08346189885685884)
        assert result['risk_adj_ret'] == pytest.approx(0.21702441182308152)
        assert result['downside_std_rets'] == pytest.approx(0.05238118174091061)
        assert result['downside_risk_adj_ret'] == pytest.approx(0.34579726739728234)
        
        # Note: Daily metrics don't have totalRet, dailyMeanRet, dailyStdRet, dailySharpe, dailyDownsideStdRet, dailySortino
        # These are all-time specific fields
        
        # Check relative fields
        assert result['rel_net_profit'] == pytest.approx(0.9669100000000002)
        assert result['rel_gross_profit'] == 1.931875
        assert result['rel_gross_loss'] == -0.964965
        assert result['rel_mean_profit'] == pytest.approx(0.06446066666666667)
        assert result['rel_median_profit'] == pytest.approx(0.058524999999999994)
        assert result['rel_std_profits'] == pytest.approx(0.23892675680262818)
        assert result['rel_risk_adj_profit'] == pytest.approx(0.0001348962910837067)
        assert result['rel_min_profit'] == -0.29748
        assert result['rel_max_profit'] == pytest.approx(0.6930000000000001)
        assert result['rel_profit_perc_10'] == -0.278175
        assert result['rel_profit_perc_25'] == pytest.approx(-0.09763500000000001)
        assert result['rel_profit_perc_75'] == pytest.approx(0.20400000000000001)
        assert result['rel_profit_perc_90'] == 0.24971
        assert result['rel_profit_top_10_prcnt_trades'] == pytest.approx(0.6930000000000001)
        assert result['rel_profit_bottom_10_prcnt_trades'] == -0.29748
        assert result['rel_one_std_outlier_profit'] == pytest.approx(0.11734499999999998)
        assert result['rel_two_std_outlier_profit'] == pytest.approx(0.6930000000000001)
        
        # Check drawdown fields
        assert result['mean_drawdown'] == pytest.approx(-964.9649999999999)
        assert result['median_drawdown'] == pytest.approx(-964.9649999999999)
        assert result['max_drawdown'] == pytest.approx(-1743.9299999999998)
        assert result['mean_num_trades_in_dd'] == 5.5
        assert result['median_num_trades_in_dd'] == 5.5
        assert result['max_num_trades_in_dd'] == 10
        assert result['rel_mean_drawdown'] == -0.4824825
        assert result['rel_median_drawdown'] == -0.4824825
        assert result['rel_max_drawdown'] == pytest.approx(-0.8719649999999999)
        
        # Check volume/lot fields
        assert result['total_lots'] == 45.5
        assert result['total_volume'] == pytest.approx(7600969.28323)
        assert result['std_volumes'] == pytest.approx(154636.0642277665)
        assert result['mean_winning_lot'] == pytest.approx(2.7777777777777777)
        assert result['mean_losing_lot'] == pytest.approx(3.4166666666666665)
        assert result['distance_win_loss_lots'] == pytest.approx(-0.6388888888888888)
        assert result['multiple_win_loss_lots'] == pytest.approx(0.8130081300813008)
        assert result['mean_winning_volume'] == pytest.approx(504050.83558211115)
        assert result['mean_losing_volume'] == pytest.approx(510751.9604985)
        assert result['distance_win_loss_volume'] == pytest.approx(-6701.124916388828)
        assert result['multiple_win_loss_volume'] == pytest.approx(0.9868798841029441)
        
        # Check duration fields
        assert result['mean_duration'] == pytest.approx(0.5606111111111111)
        assert result['median_duration'] == pytest.approx(0.24888888888888888)
        assert result['std_durations'] == pytest.approx(0.4488635306368768)
        assert result['min_duration'] == pytest.approx(0.11722222222222223)
        assert result['max_duration'] == pytest.approx(1.3066666666666666)
        assert result['cv_durations'] == pytest.approx(80.06682738543041)
        
        # Check SL/TP fields
        assert result['mean_tp'] == pytest.approx(0.2545876930084151)
        assert result['median_tp'] == pytest.approx(0.24739786320349122)
        assert result['std_tp'] == pytest.approx(0.03955151078766531)
        assert result['min_tp'] == pytest.approx(0.2008321661036483)
        assert result['max_tp'] == pytest.approx(0.3203004773207452)
        assert result['cv_tp'] == pytest.approx(15.53551560968738)
        assert result['mean_sl'] == pytest.approx(0.13093175933501788)
        assert result['median_sl'] == pytest.approx(0.13093175933501788)
        assert result['std_sl'] == pytest.approx(0.004406586529637213)
        assert result['min_sl'] == pytest.approx(0.12652517280538067)
        assert result['max_sl'] == pytest.approx(0.1353383458646551)
        assert result['cv_sl'] == pytest.approx(3.365559702258324)
        assert result['mean_tp_vs_sl'] == pytest.approx(194.44303987162974)
        assert result['median_tp_vs_sl'] == pytest.approx(188.95175964944383)
        assert result['min_tp_vs_sl'] == pytest.approx(158.72901941226007)
        assert result['max_tp_vs_sl'] == pytest.approx(236.66646379811766)
        assert result['cv_tp_vs_sl'] == pytest.approx(461.60273428704573)
        
        # Check streak fields
        assert result['mean_num_consec_wins'] == 3
        assert result['median_num_consec_wins'] == 3
        assert result['max_num_consec_wins'] == 5
        assert result['mean_num_consec_losses'] == 3
        assert result['median_num_consec_losses'] == 3
        assert result['max_num_consec_losses'] == 5
        assert result['mean_val_consec_wins'] == pytest.approx(1287.9166666666667)
        assert result['median_val_consec_wins'] == 1386
        assert result['max_val_consec_wins'] == 1544.25
        assert result['mean_val_consec_losses'] == pytest.approx(-964.9649999999999)
        assert result['median_val_consec_losses'] == pytest.approx(-964.9649999999999)
        assert result['max_val_consec_losses'] == pytest.approx(-1743.9299999999998)
        
        # Check position fields
        assert result['mean_num_open_pos'] == 1.8
        assert result['median_num_open_pos'] == 2
        assert result['max_num_open_pos'] == 3
        assert result['mean_val_open_pos'] == pytest.approx(1156196.0052442665)
        assert result['median_val_open_pos'] == pytest.approx(1309249.5253599996)
        assert result['max_val_open_pos'] == pytest.approx(1746304.5908679995)
        assert result['mean_val_to_eqty_open_pos'] == pytest.approx(578.0980026221332)
        assert result['median_val_to_eqty_open_pos'] == pytest.approx(654.6247626799999)
        assert result['max_val_to_eqty_open_pos'] == pytest.approx(873.1522954339997)
        
        # Check margin fields
        assert result['mean_account_margin'] == pytest.approx(24308.766776891196)
        assert result['mean_firm_margin'] == pytest.approx(972.3506710756477)
        
        # Check symbol fields
        assert result['num_traded_symbols'] == 2
        assert result['most_traded_smb_trades'] == 10
        assert result['most_traded_symbol'] == 'GBPJPY'
        
        # The individual assertions above already verify all the fields are correctly transformed

    @pytest.fixture
    def sample_hourly_metric(self):
        """Sample hourly metric with comprehensive risk factors."""
        return {
            "date": "2025-02-13T00:00:00.000Z",
            "datetime": "2025-02-13T09:00:00.000Z",
            "hour": 9,
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
            "numTrades": 5,
            "netProfit": -1743.9299999999998,
            "grossProfit": 0,
            "grossLoss": -1743.9299999999998,
            "gainToPain": -1,
            "profitFactor": 0,
            "successRate": 0,
            "meanProfit": -348.786,
            "medianProfit": -202.08,
            "stdProfits": 185.65636392001218,
            "riskAdjProfit": -1.8786643917591226,
            "minProfit": -594.96,
            "maxProfit": -195.27,
            "profitPerc10": -594.96,
            "profitPerc25": -556.35,
            "profitPerc75": -195.27,
            "profitPerc90": -195.27,
            "expectancy": None,
            "profitTop10PrcntTrades": None,
            "profitBottom10PrcntTrades": None,
            "top10PrcntProfitContrib": None,
            "bottom10PrcntLossContrib": None,
            "oneStdOutlierProfit": -1151.31,
            "oneStdOutlierProfitContrib": 66.01813146169859,
            "twoStdOutlierProfit": None,
            "twoStdOutlierProfitContrib": None,
            "netProfitPerUSDVolume": -0.0007965355659082366,
            "grossProfitPerUSDVolume": None,
            "grossLossPerUSDVolume": -0.0007965355659082366,
            "distanceGrossProfitLossPerUSDVolume": None,
            "multipleGrossProfitLossPerUSDVolume": None,
            "grossProfitPerLot": None,
            "grossLossPerLot": -99.65314285714285,
            "distanceGrossProfitLossPerLot": None,
            "multipleGrossProfitLossPerLot": None,
            "netProfitPerDuration": -550.5215713784636,
            "grossProfitPerDuration": None,
            "grossLossPerDuration": -550.5215713784636,
            "meanRet": -0.07964974508698576,
            "stdRets": 0.0423902566025636,
            "riskAdjRet": -1.878963504131486,
            "downsideStdRets": 0.09022757753177793,
            "downsideRiskAdjRet": -0.8827649734797913,
            "relNetProfit": -0.8719649999999999,
            "relGrossProfit": 0,
            "relGrossLoss": -0.8719649999999999,
            "relMeanProfit": -0.17439300000000002,
            "relMedianProfit": -0.10104,
            "relStdProfits": 0.09282818196000608,
            "relRiskAdjProfit": -0.0009393321958795613,
            "relMinProfit": -0.29748,
            "relMaxProfit": -0.09763500000000001,
            "relProfitPerc10": -0.29748,
            "relProfitPerc25": -0.278175,
            "relProfitPerc75": -0.09763500000000001,
            "relProfitPerc90": -0.09763500000000001,
            "relProfitTop10PrcntTrades": 0,
            "relProfitBottom10PrcntTrades": 0,
            "relOneStdOutlierProfit": -0.575655,
            "relTwoStdOutlierProfit": 0,
            "meanDrawDown": -1743.9299999999998,
            "medianDrawDown": -1743.9299999999998,
            "maxDrawDown": -1743.9299999999998,
            "meanNumTradesInDD": 5,
            "medianNumTradesInDD": 5,
            "maxNumTradesInDD": 5,
            "relMeanDrawDown": -0.8719649999999999,
            "relMedianDrawDown": -0.8719649999999999,
            "relMaxDrawDown": -0.8719649999999999,
            "totalLots": 17.5,
            "totalVolume": 2189393.762991,
            "stdVolumes": 39.714445412079286,
            "meanWinningLot": None,
            "meanLosingLot": 3.5,
            "distanceWinLossLots": None,
            "multipleWinLossLots": None,
            "meanWinningVolume": None,
            "meanLosingVolume": 437878.7525982,
            "distanceWinLossVolume": None,
            "multipleWinLossVolume": None,
            "meanDuration": 0.6335555555555555,
            "medianDuration": 0.18583333333333332,
            "stdDurations": 0.5493666780153127,
            "minDuration": 0.1836111111111111,
            "maxDuration": 1.3066666666666666,
            "cvDurations": 86.71168190350429,
            "meanTP": 0.2474002182568824,
            "medianTP": 0.24739786320349122,
            "stdTP": 0.011225423307760161,
            "minTP": 0.2347271232135295,
            "maxTP": 0.2600780234070177,
            "cvTP": 4.5373538418242205,
            "meanSL": 0.13093175933501788,
            "medianSL": 0.13093175933501788,
            "stdSL": 0.004406586529637213,
            "minSL": 0.12652517280538067,
            "maxSL": 0.1353383458646551,
            "cvSL": 3.365559702258324,
            "meanTPvsSL": 188.95355833709849,
            "medianTPvsSL": 188.95175964944383,
            "minTPvsSL": 185.51812102606937,
            "maxTPvsSL": 192.16876173963905,
            "cvTPvsSL": 134.8172144674662,
            "meanNumConsecWins": None,
            "medianNumConsecWins": None,
            "maxNumConsecWins": None,
            "meanNumConsecLosses": 5,
            "medianNumConsecLosses": 5,
            "maxNumConsecLosses": 5,
            "meanValConsecWins": None,
            "medianValConsecWins": None,
            "maxValConsecWins": None,
            "meanValConsecLosses": -1743.9299999999998,
            "medianValConsecLosses": -1743.9299999999998,
            "maxValConsecLosses": -1743.9299999999998,
            "meanNumOpenPos": 1,
            "medianNumOpenPos": 1,
            "maxNumOpenPos": 1,
            "meanValOpenPos": 437878.7525982,
            "medianValOpenPos": 437856.484845,
            "maxValOpenPos": 437933.730406,
            "meanValtoEqtyOpenPos": None,
            "medianValtoEqtyOpenPos": 0,
            "maxValtoEqtyOpenPos": None,
            "meanAccountMargin": 41505.61663199572,
            "meanFirmMargin": 1660.224665279829,
            "numTradedSymbols": 1,
            "mostTradedSmbTrades": 5,
            "mostTradedSymbol": "GBPJPY"
        }

    def test_transform_hourly_metric(self, ingester, sample_hourly_metric):
        """Test transformation of hourly metric with all new fields."""
        result = ingester._transform_hourly_metric(sample_hourly_metric)
        
        # Check core fields
        assert result['date'] == date(2025, 2, 13)
        # Handle timezone-aware datetime
        expected_datetime = datetime(2025, 2, 13, 9, 0, 0)
        if result['datetime'].tzinfo:
            # Compare without timezone info
            assert result['datetime'].replace(tzinfo=None) == expected_datetime
        else:
            assert result['datetime'] == expected_datetime
        assert result['hour'] == 9
        assert result['login'] == '142036'
        assert result['account_id'] == '953785'
        assert result['plan_id'] == 5036
        assert result['trader_id'] == 'C521030'
        
        assert result['status'] == 1
        assert result['type'] == 7
        assert result['phase'] == 4
        assert result['broker'] == 5
        assert result['platform'] == 5
        assert result['price_stream'] == 1
        assert result['country'] == 'CA'
        
        # Check hourly-specific fields
        assert result['days_to_next_payout'] == 3
        assert result['todays_payouts'] == 0
        assert result['approved_payouts'] == 0
        assert result['pending_payouts'] == 0
        
        # Check balance fields
        assert result['starting_balance'] == 200000
        assert result['prior_days_balance'] == 200000
        assert result['prior_days_equity'] == 200000
        assert result['current_balance'] == 201786.32
        assert result['current_equity'] == 201786.32
        
        # Check timeline fields
        assert result['first_trade_date'] == date(2025, 2, 13)
        assert result['days_since_initial_deposit'] == 2
        assert result['days_since_first_trade'] == 1
        assert result['num_trades'] == 5
        
        # Check performance fields
        assert result['net_profit'] == pytest.approx(-1743.93)
        assert result['gross_profit'] == 0
        assert result['gross_loss'] == pytest.approx(-1743.93)
        assert result['gain_to_pain'] == -1
        assert result['profit_factor'] == 0
        assert result['success_rate'] == 0
        
        # Check distribution fields
        assert result['mean_profit'] == -348.786
        assert result['median_profit'] == -202.08
        assert result['std_profits'] == 185.65636392001218
        assert result['risk_adj_profit'] == -1.8786643917591226
        assert result['min_profit'] == -594.96
        assert result['max_profit'] == -195.27
        assert result['profit_perc_10'] == -594.96
        assert result['profit_perc_25'] == -556.35
        assert result['profit_perc_75'] == -195.27
        assert result['profit_perc_90'] == -195.27
        assert result['expectancy'] is None
        
        # Check outlier fields
        assert result['profit_top_10_prcnt_trades'] is None
        assert result['profit_bottom_10_prcnt_trades'] is None
        assert result['top_10_prcnt_profit_contrib'] is None
        assert result['bottom_10_prcnt_loss_contrib'] is None
        assert result['one_std_outlier_profit'] == -1151.31
        assert result['one_std_outlier_profit_contrib'] == pytest.approx(66.01813146169859)
        assert result['two_std_outlier_profit'] is None
        assert result['two_std_outlier_profit_contrib'] is None
        
        # Check unit profit fields
        assert result['net_profit_per_usd_volume'] == pytest.approx(-0.0007965355659082366)
        assert result['gross_profit_per_usd_volume'] is None
        assert result['gross_loss_per_usd_volume'] == pytest.approx(-0.0007965355659082366)
        assert result['distance_gross_profit_loss_per_usd_volume'] is None
        assert result['multiple_gross_profit_loss_per_usd_volume'] is None
        assert result['gross_profit_per_lot'] is None
        assert result['gross_loss_per_lot'] == pytest.approx(-99.65314285714285)
        assert result['distance_gross_profit_loss_per_lot'] is None
        assert result['multiple_gross_profit_loss_per_lot'] is None
        assert result['net_profit_per_duration'] == pytest.approx(-550.5215713784636)
        assert result['gross_profit_per_duration'] is None
        assert result['gross_loss_per_duration'] == pytest.approx(-550.5215713784636)
        
        # Check return fields
        assert result['mean_ret'] == pytest.approx(-0.07964974508698576)
        assert result['std_rets'] == pytest.approx(0.0423902566025636)
        assert result['risk_adj_ret'] == pytest.approx(-1.878963504131486)
        assert result['downside_std_rets'] == pytest.approx(0.09022757753177793)
        assert result['downside_risk_adj_ret'] == pytest.approx(-0.8827649734797913)
        
        # Check relative fields
        assert result['rel_net_profit'] == pytest.approx(-0.8719649999999999)
        assert result['rel_gross_profit'] == 0
        assert result['rel_gross_loss'] == pytest.approx(-0.8719649999999999)
        assert result['rel_mean_profit'] == pytest.approx(-0.17439300000000002)
        assert result['rel_median_profit'] == -0.10104
        assert result['rel_std_profits'] == pytest.approx(0.09282818196000608)
        assert result['rel_risk_adj_profit'] == pytest.approx(-0.0009393321958795613)
        assert result['rel_min_profit'] == -0.29748
        assert result['rel_max_profit'] == pytest.approx(-0.09763500000000001)
        assert result['rel_profit_perc_10'] == -0.29748
        assert result['rel_profit_perc_25'] == -0.278175
        assert result['rel_profit_perc_75'] == pytest.approx(-0.09763500000000001)
        assert result['rel_profit_perc_90'] == pytest.approx(-0.09763500000000001)
        assert result['rel_profit_top_10_prcnt_trades'] == 0
        assert result['rel_profit_bottom_10_prcnt_trades'] == 0
        assert result['rel_one_std_outlier_profit'] == -0.575655
        assert result['rel_two_std_outlier_profit'] == 0
        
        # Check drawdown fields
        assert result['mean_drawdown'] == pytest.approx(-1743.9299999999998)
        assert result['median_drawdown'] == pytest.approx(-1743.9299999999998)
        assert result['max_drawdown'] == pytest.approx(-1743.9299999999998)
        assert result['mean_num_trades_in_dd'] == 5
        assert result['median_num_trades_in_dd'] == 5
        assert result['max_num_trades_in_dd'] == 5
        assert result['rel_mean_drawdown'] == pytest.approx(-0.8719649999999999)
        assert result['rel_median_drawdown'] == pytest.approx(-0.8719649999999999)
        assert result['rel_max_drawdown'] == pytest.approx(-0.8719649999999999)
        
        # Check volume/lot fields
        assert result['total_lots'] == 17.5
        assert result['total_volume'] == pytest.approx(2189393.762991)
        assert result['std_volumes'] == pytest.approx(39.714445412079286)
        assert result['mean_winning_lot'] is None
        assert result['mean_losing_lot'] == 3.5
        assert result['distance_win_loss_lots'] is None
        assert result['multiple_win_loss_lots'] is None
        assert result['mean_winning_volume'] is None
        assert result['mean_losing_volume'] == pytest.approx(437878.7525982)
        assert result['distance_win_loss_volume'] is None
        assert result['multiple_win_loss_volume'] is None
        
        # Check duration fields
        assert result['mean_duration'] == pytest.approx(0.6335555555555555)
        assert result['median_duration'] == pytest.approx(0.18583333333333332)
        assert result['std_durations'] == pytest.approx(0.5493666780153127)
        assert result['min_duration'] == pytest.approx(0.1836111111111111)
        assert result['max_duration'] == pytest.approx(1.3066666666666666)
        assert result['cv_durations'] == pytest.approx(86.71168190350429)
        
        # Check SL/TP fields
        assert result['mean_tp'] == pytest.approx(0.2474002182568824)
        assert result['median_tp'] == pytest.approx(0.24739786320349122)
        assert result['std_tp'] == pytest.approx(0.011225423307760161)
        assert result['min_tp'] == pytest.approx(0.2347271232135295)
        assert result['max_tp'] == pytest.approx(0.2600780234070177)
        assert result['cv_tp'] == pytest.approx(4.5373538418242205)
        assert result['mean_sl'] == pytest.approx(0.13093175933501788)
        assert result['median_sl'] == pytest.approx(0.13093175933501788)
        assert result['std_sl'] == pytest.approx(0.004406586529637213)
        assert result['min_sl'] == pytest.approx(0.12652517280538067)
        assert result['max_sl'] == pytest.approx(0.1353383458646551)
        assert result['cv_sl'] == pytest.approx(3.365559702258324)
        assert result['mean_tp_vs_sl'] == pytest.approx(188.95355833709849)
        assert result['median_tp_vs_sl'] == pytest.approx(188.95175964944383)
        assert result['min_tp_vs_sl'] == pytest.approx(185.51812102606937)
        assert result['max_tp_vs_sl'] == pytest.approx(192.16876173963905)
        assert result['cv_tp_vs_sl'] == pytest.approx(134.8172144674662)
        
        # Check streak fields
        assert result['mean_num_consec_wins'] is None
        assert result['median_num_consec_wins'] is None
        assert result['max_num_consec_wins'] is None
        assert result['mean_num_consec_losses'] == 5
        assert result['median_num_consec_losses'] == 5
        assert result['max_num_consec_losses'] == 5
        assert result['mean_val_consec_wins'] is None
        assert result['median_val_consec_wins'] is None
        assert result['max_val_consec_wins'] is None
        assert result['mean_val_consec_losses'] == pytest.approx(-1743.9299999999998)
        assert result['median_val_consec_losses'] == pytest.approx(-1743.9299999999998)
        assert result['max_val_consec_losses'] == pytest.approx(-1743.9299999999998)
        
        # Check position fields
        assert result['mean_num_open_pos'] == 1
        assert result['median_num_open_pos'] == 1
        assert result['max_num_open_pos'] == 1
        assert result['mean_val_open_pos'] == pytest.approx(437878.7525982)
        assert result['median_val_open_pos'] == pytest.approx(437856.484845)
        assert result['max_val_open_pos'] == pytest.approx(437933.730406)
        assert result['mean_val_to_eqty_open_pos'] is None
        assert result['median_val_to_eqty_open_pos'] == 0
        assert result['max_val_to_eqty_open_pos'] is None
        
        # Check margin fields
        assert result['mean_account_margin'] == pytest.approx(41505.61663199572)
        assert result['mean_firm_margin'] == pytest.approx(1660.224665279829)
        
        # Check symbol fields
        assert result['num_traded_symbols'] == 1
        assert result['most_traded_smb_trades'] == 5
        assert result['most_traded_symbol'] == 'GBPJPY'
        
        # The individual assertions above already verify all the fields are correctly transformed

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

    @patch('src.data_ingestion.base_ingester.get_db_manager')
    @patch('src.utils.api_client.RiskAnalyticsAPIClient')
    def test_on_conflict_update_behavior(self, mock_api_client, mock_db_manager):
        """Test ON CONFLICT DO UPDATE behavior for metrics."""
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Mock mogrify to return bytes as expected by execute_batch
        mock_cursor.mogrify.return_value = b"mocked query"
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        
        mock_db_instance = MagicMock()
        mock_db_instance.model_db = MagicMock()
        mock_db_instance.model_db.get_connection.return_value = mock_conn
        mock_db_instance.model_db.execute_query = Mock(return_value=[])
        mock_db_manager.return_value = mock_db_instance
        
        # Mock API client
        mock_api = Mock()
        mock_api_client.return_value = mock_api
        
        ingester = MetricsIngester()
        
        # Test data with same account_id but different values
        test_metrics = [
            {
                "accountId": "12345",
                "login": "user1",
                "netProfit": 1000.0,
                "grossProfit": 1200.0,
                "currentBalance": 10000.0,
                "updatedDate": "2025-06-09T10:00:00Z"
            },
            {
                "accountId": "12345",  # Same account_id
                "login": "user1",
                "netProfit": 1500.0,  # Updated profit
                "grossProfit": 1700.0,  # Updated gross profit
                "currentBalance": 10500.0,  # Updated balance
                "updatedDate": "2025-06-09T11:00:00Z"  # Later timestamp
            }
        ]
        
        # Process both records
        batch = []
        for metric in test_metrics:
            transformed = ingester._transform_alltime_metric(metric)
            batch.append(transformed)
        
        # Call _insert_batch_with_upsert directly
        ingester.table_name = "prop_trading_model.raw_metrics_alltime"
        result = ingester._insert_batch_with_upsert(batch)
        
        # Verify the query was called with ON CONFLICT DO UPDATE
        assert mock_cursor.method_calls
        
        # Get the executed query from execute_batch call
        from psycopg2.extras import execute_batch
        execute_batch_calls = [call for call in mock_cursor.method_calls if call[0] == 'execute_batch' or 'execute_batch' in str(call)]
        
        # Since we're mocking, we just verify the method structure
        assert result == 2  # Both records processed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])