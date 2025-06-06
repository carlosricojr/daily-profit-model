"""
Anomaly detection module for identifying unusual patterns in account metrics.
Uses multiple algorithms to detect different types of anomalies.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date
import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum

# Anomaly detection libraries
from sklearn.preprocessing import StandardScaler
from pyod.models.iforest import IForest
from pyod.models.lof import LOF
from pyod.models.auto_encoder import AutoEncoder
from pyod.models.combination import average
import prophet
from prophet import Prophet

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of anomalies detected."""

    POINT_ANOMALY = "point_anomaly"  # Single data point outlier
    CONTEXTUAL_ANOMALY = "contextual_anomaly"  # Anomaly in specific context
    COLLECTIVE_ANOMALY = "collective_anomaly"  # Group of data points forming anomaly
    TREND_ANOMALY = "trend_anomaly"  # Deviation from expected trend
    SEASONAL_ANOMALY = "seasonal_anomaly"  # Deviation from seasonal pattern


@dataclass
class AnomalyResult:
    """Container for anomaly detection results."""

    account_id: str
    date: date
    anomaly_type: AnomalyType
    anomaly_score: float
    feature_contributions: Dict[str, float]
    description: str
    severity: str  # low, medium, high
    recommended_action: Optional[str] = None


class AnomalyDetector:
    """Comprehensive anomaly detection for account metrics."""

    def __init__(self, db_manager):
        """Initialize anomaly detector."""
        self.db_manager = db_manager
        self.scaler = StandardScaler()
        self.models = {}
        self._initialize_models()

    def _initialize_models(self):
        """Initialize various anomaly detection models."""
        # Isolation Forest for general outlier detection
        self.models["isolation_forest"] = IForest(
            contamination=0.05, random_state=42, n_estimators=100
        )

        # Local Outlier Factor for density-based detection
        self.models["lof"] = LOF(contamination=0.05, n_neighbors=20, novelty=False)

        # AutoEncoder for complex pattern detection
        self.models["autoencoder"] = AutoEncoder(
            hidden_neurons=[64, 32, 32, 64], contamination=0.05, epochs=50, verbose=0
        )

    def detect_anomalies(
        self, start_date: date, end_date: date, account_ids: Optional[List[str]] = None
    ) -> List[AnomalyResult]:
        """
        Detect anomalies in account metrics for a date range.

        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            account_ids: Optional list of specific accounts to analyze

        Returns:
            List of detected anomalies
        """
        logger.info(f"Starting anomaly detection from {start_date} to {end_date}")

        anomalies = []

        # Get data for analysis
        data = self._fetch_account_metrics(start_date, end_date, account_ids)

        if data.empty:
            logger.warning("No data found for anomaly detection")
            return anomalies

        # Detect different types of anomalies
        anomalies.extend(self._detect_point_anomalies(data))
        anomalies.extend(self._detect_contextual_anomalies(data))
        anomalies.extend(self._detect_collective_anomalies(data))
        anomalies.extend(self._detect_trend_anomalies(data))

        # Sort by severity and date
        anomalies.sort(key=lambda x: (x.severity, x.date), reverse=True)

        logger.info(f"Detected {len(anomalies)} anomalies")
        return anomalies

    def _fetch_account_metrics(
        self, start_date: date, end_date: date, account_ids: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """Fetch account metrics data for analysis."""
        query = """
        SELECT 
            s.account_id,
            s.date,
            s.current_balance,
            s.current_equity,
            s.distance_to_profit_target,
            s.distance_to_max_drawdown,
            s.days_since_first_trade,
            s.active_trading_days_count,
            m.net_profit,
            m.gross_profit,
            m.gross_loss,
            m.total_trades,
            m.win_rate,
            m.profit_factor,
            m.lots_traded,
            m.volume_traded,
            LAG(s.current_balance, 1) OVER (PARTITION BY s.account_id ORDER BY s.date) as prev_balance,
            LAG(m.net_profit, 1) OVER (PARTITION BY s.account_id ORDER BY s.date) as prev_profit
        FROM stg_accounts_daily_snapshots s
        LEFT JOIN raw_metrics_daily m ON s.account_id = m.account_id AND s.date = m.date
        WHERE s.date BETWEEN %s AND %s
        """

        params = [start_date, end_date]

        if account_ids:
            placeholders = ",".join(["%s"] * len(account_ids))
            query += f" AND s.account_id IN ({placeholders})"
            params.extend(account_ids)

        query += " ORDER BY s.account_id, s.date"

        return self.db_manager.model_db.execute_query_df(query, tuple(params))

    def _detect_point_anomalies(self, data: pd.DataFrame) -> List[AnomalyResult]:
        """Detect point anomalies using ensemble methods."""
        anomalies = []

        # Features for point anomaly detection
        features = [
            "current_balance",
            "current_equity",
            "net_profit",
            "total_trades",
            "win_rate",
            "profit_factor",
            "volume_traded",
        ]

        # Filter to valid features
        valid_features = [f for f in features if f in data.columns]

        # Prepare data
        X = data[valid_features].fillna(0)

        if len(X) < 10:  # Need minimum samples
            return anomalies

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Train models and get predictions
        predictions = {}
        scores = {}

        for model_name, model in self.models.items():
            try:
                if model_name == "autoencoder" and X_scaled.shape[0] < 100:
                    continue  # Skip autoencoder for small datasets

                model.fit(X_scaled)
                predictions[model_name] = model.predict(X_scaled)
                scores[model_name] = model.decision_scores_
            except Exception as e:
                logger.warning(f"Error in {model_name}: {str(e)}")
                continue

        if not predictions:
            return anomalies

        # Ensemble predictions
        ensemble_scores = average(list(scores.values()))
        threshold = np.percentile(ensemble_scores, 95)  # Top 5% as anomalies

        # Create anomaly results
        for idx, (_, row) in enumerate(data.iterrows()):
            if ensemble_scores[idx] > threshold:
                # Calculate feature contributions
                feature_scores = {}
                for i, feature in enumerate(valid_features):
                    if i < X_scaled.shape[1]:
                        feature_scores[feature] = abs(X_scaled[idx, i])

                # Determine severity
                severity = self._calculate_severity(ensemble_scores[idx], threshold)

                anomalies.append(
                    AnomalyResult(
                        account_id=row["account_id"],
                        date=row["date"],
                        anomaly_type=AnomalyType.POINT_ANOMALY,
                        anomaly_score=float(ensemble_scores[idx]),
                        feature_contributions=feature_scores,
                        description="Unusual combination of metrics detected",
                        severity=severity,
                        recommended_action="Review account activity for unusual patterns",
                    )
                )

        return anomalies

    def _detect_contextual_anomalies(self, data: pd.DataFrame) -> List[AnomalyResult]:
        """Detect anomalies based on account context."""
        anomalies = []

        # Group by account to analyze in context
        for account_id, account_data in data.groupby("account_id"):
            if len(account_data) < 7:  # Need at least a week of data
                continue

            # Calculate rolling statistics
            account_data = account_data.sort_values("date")
            account_data["balance_change"] = account_data[
                "current_balance"
            ].pct_change()
            account_data["profit_zscore"] = (
                account_data["net_profit"]
                - account_data["net_profit"].rolling(7).mean()
            ) / account_data["net_profit"].rolling(7).std()

            # Detect sudden balance changes
            balance_threshold = 3  # 3 standard deviations
            balance_anomalies = account_data[
                abs(account_data["profit_zscore"]) > balance_threshold
            ]

            for _, row in balance_anomalies.iterrows():
                if pd.notna(row["profit_zscore"]):
                    anomalies.append(
                        AnomalyResult(
                            account_id=account_id,
                            date=row["date"],
                            anomaly_type=AnomalyType.CONTEXTUAL_ANOMALY,
                            anomaly_score=abs(float(row["profit_zscore"])),
                            feature_contributions={
                                "profit_zscore": float(row["profit_zscore"])
                            },
                            description=f"Profit deviation: {row['profit_zscore']:.2f} std devs from 7-day average",
                            severity="high"
                            if abs(row["profit_zscore"]) > 4
                            else "medium",
                            recommended_action="Investigate trading activity for this day",
                        )
                    )

        return anomalies

    def _detect_collective_anomalies(self, data: pd.DataFrame) -> List[AnomalyResult]:
        """Detect anomalies in groups of related accounts."""
        anomalies = []

        # Analyze accounts by similar characteristics
        # Group by balance ranges
        data["balance_range"] = pd.cut(
            data["current_balance"],
            bins=[0, 10000, 50000, 100000, float("inf")],
            labels=["small", "medium", "large", "very_large"],
        )

        for (date_val, balance_range), group in data.groupby(["date", "balance_range"]):
            if len(group) < 5:  # Need minimum group size
                continue

            # Check if group behavior is anomalous
            group_profit = group["net_profit"].sum()

            # Compare with historical average for this balance range
            hist_query = """
            SELECT 
                AVG(net_profit) as avg_profit,
                AVG(win_rate) as avg_win_rate,
                STDDEV(net_profit) as std_profit
            FROM raw_metrics_daily m
            JOIN stg_accounts_daily_snapshots s ON m.account_id = s.account_id AND m.date = s.date
            WHERE s.current_balance BETWEEN %s AND %s
            AND s.date < %s
            AND s.date >= %s - INTERVAL '30 days'
            """

            balance_bounds = {
                "small": (0, 10000),
                "medium": (10000, 50000),
                "large": (50000, 100000),
                "very_large": (100000, float("inf")),
            }

            bounds = balance_bounds.get(balance_range, (0, float("inf")))
            hist_data = self.db_manager.model_db.execute_query(
                hist_query, (bounds[0], bounds[1], date_val, date_val)
            )

            if hist_data and hist_data[0]["avg_profit"] is not None:
                avg_profit = hist_data[0]["avg_profit"]
                std_profit = hist_data[0]["std_profit"] or 1

                z_score = (group_profit / len(group) - avg_profit) / std_profit

                if abs(z_score) > 2.5:
                    anomalies.append(
                        AnomalyResult(
                            account_id=f"GROUP_{balance_range}",
                            date=date_val,
                            anomaly_type=AnomalyType.COLLECTIVE_ANOMALY,
                            anomaly_score=abs(float(z_score)),
                            feature_contributions={
                                "group_size": len(group),
                                "avg_profit_deviation": float(z_score),
                            },
                            description=f"{balance_range} accounts showing unusual collective behavior",
                            severity="medium",
                            recommended_action=f"Review all {balance_range} accounts for systemic issues",
                        )
                    )

        return anomalies

    def _detect_trend_anomalies(self, data: pd.DataFrame) -> List[AnomalyResult]:
        """Detect anomalies in account trends using Prophet."""
        anomalies = []

        # Analyze each account's balance trend
        for account_id, account_data in data.groupby("account_id"):
            if len(account_data) < 30:  # Need sufficient history
                continue

            # Prepare data for Prophet
            prophet_data = account_data[["date", "current_balance"]].rename(
                columns={"date": "ds", "current_balance": "y"}
            )
            prophet_data = prophet_data.sort_values("ds")

            try:
                # Suppress Prophet logging
                prophet.logger.setLevel(logging.ERROR)

                # Fit model
                model = Prophet(
                    changepoint_prior_scale=0.05,
                    seasonality_mode="multiplicative",
                    daily_seasonality=False,
                    weekly_seasonality=True,
                    yearly_seasonality=False,
                )
                model.fit(prophet_data)

                # Make predictions
                forecast = model.predict(prophet_data)

                # Calculate prediction intervals
                forecast["anomaly"] = (
                    prophet_data["y"].values < forecast["yhat_lower"]
                ) | (prophet_data["y"].values > forecast["yhat_upper"])

                # Identify anomalous points
                anomaly_dates = forecast[forecast["anomaly"]]["ds"].values

                for anomaly_date in anomaly_dates:
                    idx = forecast[forecast["ds"] == anomaly_date].index[0]
                    actual = prophet_data.iloc[idx]["y"]
                    expected = forecast.iloc[idx]["yhat"]
                    deviation = abs(actual - expected) / expected

                    if deviation > 0.2:  # 20% deviation threshold
                        anomalies.append(
                            AnomalyResult(
                                account_id=account_id,
                                date=pd.Timestamp(anomaly_date).date(),
                                anomaly_type=AnomalyType.TREND_ANOMALY,
                                anomaly_score=float(deviation),
                                feature_contributions={
                                    "actual_balance": float(actual),
                                    "expected_balance": float(expected),
                                    "deviation_pct": float(deviation * 100),
                                },
                                description=f"Balance deviates {deviation * 100:.1f}% from expected trend",
                                severity="high" if deviation > 0.5 else "medium",
                                recommended_action="Investigate cause of trend deviation",
                            )
                        )

            except Exception as e:
                logger.warning(
                    f"Prophet analysis failed for account {account_id}: {str(e)}"
                )
                continue

        return anomalies

    def _calculate_severity(self, score: float, threshold: float) -> str:
        """Calculate anomaly severity based on score."""
        if score > threshold * 2:
            return "high"
        elif score > threshold * 1.5:
            return "medium"
        else:
            return "low"

    def detect_real_time_anomaly(
        self, account_id: str, metrics: Dict[str, float]
    ) -> Optional[AnomalyResult]:
        """
        Detect anomalies in real-time for a single account.

        Args:
            account_id: Account to check
            metrics: Current metrics dictionary

        Returns:
            AnomalyResult if anomaly detected, None otherwise
        """
        # Get historical data for comparison
        query = """
        SELECT 
            AVG(current_balance) as avg_balance,
            STDDEV(current_balance) as std_balance,
            AVG(net_profit) as avg_profit,
            STDDEV(net_profit) as std_profit,
            AVG(win_rate) as avg_win_rate,
            AVG(total_trades) as avg_trades
        FROM stg_accounts_daily_snapshots s
        LEFT JOIN raw_metrics_daily m ON s.account_id = m.account_id AND s.date = m.date
        WHERE s.account_id = %s
        AND s.date >= CURRENT_DATE - INTERVAL '30 days'
        """

        hist_stats = self.db_manager.model_db.execute_query(query, (account_id,))

        if not hist_stats or hist_stats[0]["avg_balance"] is None:
            return None

        stats = hist_stats[0]

        # Check for anomalies
        anomaly_checks = []

        # Balance check
        if "current_balance" in metrics and stats["std_balance"]:
            balance_z = (metrics["current_balance"] - stats["avg_balance"]) / stats[
                "std_balance"
            ]
            if abs(balance_z) > 3:
                anomaly_checks.append(("balance", balance_z))

        # Profit check
        if "net_profit" in metrics and stats["std_profit"]:
            profit_z = (metrics["net_profit"] - stats["avg_profit"]) / stats[
                "std_profit"
            ]
            if abs(profit_z) > 3:
                anomaly_checks.append(("profit", profit_z))

        # Win rate check
        if "win_rate" in metrics and stats["avg_win_rate"]:
            win_rate_dev = abs(metrics["win_rate"] - stats["avg_win_rate"])
            if win_rate_dev > 20:  # 20% deviation
                anomaly_checks.append(("win_rate", win_rate_dev))

        if anomaly_checks:
            # Create anomaly result
            feature_contributions = {
                check[0]: float(check[1]) for check in anomaly_checks
            }
            max_score = max(abs(check[1]) for check in anomaly_checks)

            return AnomalyResult(
                account_id=account_id,
                date=datetime.now().date(),
                anomaly_type=AnomalyType.POINT_ANOMALY,
                anomaly_score=float(max_score),
                feature_contributions=feature_contributions,
                description=f"Real-time anomaly detected in {len(anomaly_checks)} metrics",
                severity=self._calculate_severity(max_score, 3),
                recommended_action="Immediate review required",
            )

        return None

    def generate_anomaly_report(
        self, anomalies: List[AnomalyResult], output_file: Optional[str] = None
    ) -> str:
        """Generate a comprehensive anomaly detection report."""
        report_lines = [
            "=" * 80,
            "ANOMALY DETECTION REPORT",
            f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            "",
        ]

        if not anomalies:
            report_lines.append("No anomalies detected.")
            return "\n".join(report_lines)

        # Summary
        report_lines.extend(
            [
                "SUMMARY",
                "-" * 40,
                f"Total Anomalies: {len(anomalies)}",
                f"High Severity: {sum(1 for a in anomalies if a.severity == 'high')}",
                f"Medium Severity: {sum(1 for a in anomalies if a.severity == 'medium')}",
                f"Low Severity: {sum(1 for a in anomalies if a.severity == 'low')}",
                "",
            ]
        )

        # Group by type
        by_type = {}
        for anomaly in anomalies:
            if anomaly.anomaly_type not in by_type:
                by_type[anomaly.anomaly_type] = []
            by_type[anomaly.anomaly_type].append(anomaly)

        report_lines.extend(["ANOMALIES BY TYPE", "-" * 40])
        for anomaly_type, type_anomalies in by_type.items():
            report_lines.append(f"{anomaly_type.value}: {len(type_anomalies)}")
        report_lines.append("")

        # High severity anomalies detail
        high_severity = [a for a in anomalies if a.severity == "high"]
        if high_severity:
            report_lines.extend(["HIGH SEVERITY ANOMALIES", "-" * 40])
            for anomaly in high_severity[:10]:  # Limit to top 10
                report_lines.extend(
                    [
                        f"Account: {anomaly.account_id}",
                        f"Date: {anomaly.date}",
                        f"Type: {anomaly.anomaly_type.value}",
                        f"Score: {anomaly.anomaly_score:.2f}",
                        f"Description: {anomaly.description}",
                        f"Action: {anomaly.recommended_action}",
                        "",
                    ]
                )

        # Account-wise summary
        by_account = {}
        for anomaly in anomalies:
            if not anomaly.account_id.startswith("GROUP_"):
                if anomaly.account_id not in by_account:
                    by_account[anomaly.account_id] = 0
                by_account[anomaly.account_id] += 1

        if by_account:
            report_lines.extend(["TOP ANOMALOUS ACCOUNTS", "-" * 40])
            top_accounts = sorted(by_account.items(), key=lambda x: x[1], reverse=True)[
                :10
            ]
            for account_id, count in top_accounts:
                report_lines.append(f"{account_id}: {count} anomalies")

        report = "\n".join(report_lines)

        if output_file:
            with open(output_file, "w") as f:
                f.write(report)
            logger.info(f"Anomaly report saved to {output_file}")

        return report
