"""
Feature Monitoring Dashboard - Version 2
Real-time monitoring of feature quality, drift, and importance.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
import pandas as pd
import argparse
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class FeatureMonitoringDashboard:
    """Comprehensive feature monitoring and visualization."""

    def __init__(self):
        self.db_manager = get_db_manager()
        self.feature_table = "feature_store_account_daily"
        self.training_table = "model_training_input"

    def generate_monitoring_report(
        self, lookback_days: int = 30, output_html: bool = True
    ) -> Dict[str, Any]:
        """Generate comprehensive monitoring report."""
        logger.info(f"Generating monitoring report for last {lookback_days} days")

        report = {
            "generated_at": datetime.now().isoformat(),
            "lookback_days": lookback_days,
            "sections": {},
        }

        # 1. Feature Quality Metrics
        report["sections"]["quality"] = self._analyze_feature_quality(lookback_days)

        # 2. Feature Drift Analysis
        report["sections"]["drift"] = self._analyze_feature_drift(lookback_days)

        # 3. Feature Importance Trends
        report["sections"]["importance"] = self._analyze_feature_importance()

        # 4. Data Pipeline Health
        report["sections"]["pipeline_health"] = self._analyze_pipeline_health(
            lookback_days
        )

        # 5. Training Data Statistics
        report["sections"]["training_data"] = self._analyze_training_data(lookback_days)

        # 6. Anomaly Detection
        report["sections"]["anomalies"] = self._detect_anomalies(lookback_days)

        # Generate visualizations if requested
        if output_html:
            self._generate_html_dashboard(report)

        return report

    def _analyze_feature_quality(self, lookback_days: int) -> Dict[str, Any]:
        """Analyze feature quality metrics."""
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        # Get feature quality trends
        quality_query = """
        SELECT 
            feature_name,
            metric_date,
            coverage_pct,
            mean_value,
            std_value,
            anomaly_count,
            null_count,
            zero_count
        FROM feature_quality_metrics
        WHERE metric_date >= %s AND metric_date <= %s
        ORDER BY feature_name, metric_date
        """

        quality_df = self.db_manager.model_db.execute_query_df(
            quality_query, (start_date, end_date)
        )

        quality_analysis = {"summary": {}, "trends": {}, "alerts": []}

        if not quality_df.empty:
            # Calculate summary statistics
            latest_date = quality_df["metric_date"].max()
            latest_quality = quality_df[quality_df["metric_date"] == latest_date]

            quality_analysis["summary"] = {
                "avg_coverage": latest_quality["coverage_pct"].mean(),
                "features_monitored": latest_quality["feature_name"].nunique(),
                "low_coverage_features": latest_quality[
                    latest_quality["coverage_pct"] < 90
                ]["feature_name"].tolist(),
            }

            # Analyze trends for key features
            key_features = ["current_balance", "rolling_pnl_avg_5d", "trades_count_5d"]
            for feature in key_features:
                feature_data = quality_df[quality_df["feature_name"] == feature]
                if not feature_data.empty:
                    quality_analysis["trends"][feature] = {
                        "coverage_trend": feature_data[
                            ["metric_date", "coverage_pct"]
                        ].to_dict("records"),
                        "mean_trend": feature_data[
                            ["metric_date", "mean_value"]
                        ].to_dict("records"),
                        "anomaly_trend": feature_data[
                            ["metric_date", "anomaly_count"]
                        ].to_dict("records"),
                    }

            # Generate alerts
            problem_features = latest_quality[
                (latest_quality["coverage_pct"] < 80)
                | (
                    latest_quality["anomaly_count"]
                    > latest_quality["null_count"] * 0.01
                )
            ]

            for _, feature in problem_features.iterrows():
                quality_analysis["alerts"].append(
                    {
                        "feature": feature["feature_name"],
                        "issue": "low_coverage"
                        if feature["coverage_pct"] < 80
                        else "high_anomalies",
                        "severity": "high"
                        if feature["coverage_pct"] < 50
                        else "medium",
                        "details": f"Coverage: {feature['coverage_pct']:.1f}%, Anomalies: {feature['anomaly_count']}",
                    }
                )

        return quality_analysis

    def _analyze_feature_drift(self, lookback_days: int) -> Dict[str, Any]:
        """Analyze feature drift patterns."""
        # Get recent drift measurements
        drift_query = """
        SELECT 
            feature_name,
            comparison_date,
            drift_type,
            drift_score,
            is_significant
        FROM feature_drift
        WHERE comparison_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY comparison_date DESC, drift_score DESC
        """

        drift_df = self.db_manager.model_db.execute_query_df(
            drift_query, (lookback_days,)
        )

        drift_analysis = {"summary": {}, "drifting_features": [], "drift_timeline": {}}

        if not drift_df.empty:
            # Summary statistics
            total_checks = len(drift_df)
            significant_drifts = drift_df["is_significant"].sum()

            drift_analysis["summary"] = {
                "total_drift_checks": total_checks,
                "significant_drifts": int(significant_drifts),
                "drift_rate": (significant_drifts / total_checks * 100)
                if total_checks > 0
                else 0,
            }

            # Find consistently drifting features
            feature_drift_counts = (
                drift_df[drift_df["is_significant"]].groupby("feature_name").size()
            )
            if not feature_drift_counts.empty:
                drift_analysis["drifting_features"] = [
                    {
                        "feature": feature,
                        "drift_count": int(count),
                        "drift_types": drift_df[
                            (drift_df["feature_name"] == feature)
                            & drift_df["is_significant"]
                        ]["drift_type"]
                        .unique()
                        .tolist(),
                    }
                    for feature, count in feature_drift_counts.items()
                    if count >= 2  # At least 2 significant drifts
                ]

            # Create drift timeline
            timeline_data = (
                drift_df[drift_df["is_significant"]]
                .groupby(["comparison_date", "drift_type"])
                .size()
                .reset_index(name="count")
            )

            for drift_type in ["distribution", "mean", "variance"]:
                type_data = timeline_data[timeline_data["drift_type"] == drift_type]
                if not type_data.empty:
                    drift_analysis["drift_timeline"][drift_type] = type_data[
                        ["comparison_date", "count"]
                    ].to_dict("records")

        return drift_analysis

    def _analyze_feature_importance(self) -> Dict[str, Any]:
        """Analyze feature importance trends."""
        # Get recent feature importance scores
        importance_query = """
        SELECT 
            fi.feature_name,
            fi.importance_score,
            fi.importance_rank,
            fi.calculation_date,
            fi.model_version
        FROM feature_importance fi
        INNER JOIN (
            SELECT model_version, MAX(calculation_date) as latest_date
            FROM feature_importance
            GROUP BY model_version
        ) latest ON fi.model_version = latest.model_version 
                AND fi.calculation_date = latest.latest_date
        ORDER BY fi.importance_rank
        LIMIT 50
        """

        importance_df = self.db_manager.model_db.execute_query_df(importance_query)

        importance_analysis = {
            "top_features": [],
            "feature_stability": {},
            "version_comparison": {},
        }

        if not importance_df.empty:
            # Top features from latest model
            latest_version = importance_df["model_version"].iloc[0]
            latest_importance = importance_df[
                importance_df["model_version"] == latest_version
            ]

            importance_analysis["top_features"] = [
                {
                    "rank": int(row["importance_rank"]),
                    "feature": row["feature_name"],
                    "score": float(row["importance_score"]),
                }
                for _, row in latest_importance.head(20).iterrows()
            ]

            # Feature stability across versions
            stability_query = """
            SELECT 
                feature_name,
                STDDEV(importance_rank) as rank_std,
                AVG(importance_rank) as avg_rank,
                COUNT(DISTINCT model_version) as version_count
            FROM feature_importance
            WHERE importance_rank <= 30
            GROUP BY feature_name
            HAVING COUNT(DISTINCT model_version) >= 2
            ORDER BY rank_std
            """

            stability_df = self.db_manager.model_db.execute_query_df(stability_query)

            if not stability_df.empty:
                importance_analysis["feature_stability"] = {
                    "stable_features": stability_df.head(10)["feature_name"].tolist(),
                    "unstable_features": stability_df.tail(10)["feature_name"].tolist(),
                }

        return importance_analysis

    def _analyze_pipeline_health(self, lookback_days: int) -> Dict[str, Any]:
        """Analyze data pipeline health metrics."""
        # Get pipeline execution history
        pipeline_query = """
        SELECT 
            pipeline_stage,
            execution_date,
            status,
            records_processed,
            execution_details->>'duration_seconds' as duration,
            error_message
        FROM pipeline_executions
        WHERE execution_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY execution_date DESC
        """

        pipeline_df = self.db_manager.model_db.execute_query_df(
            pipeline_query, (lookback_days,)
        )

        health_analysis = {
            "summary": {},
            "stage_performance": {},
            "recent_failures": [],
        }

        if not pipeline_df.empty:
            # Calculate success rates by stage
            stage_stats = (
                pipeline_df.groupby("pipeline_stage")
                .agg(
                    {
                        "status": lambda x: (x == "success").sum() / len(x) * 100,
                        "records_processed": "mean",
                        "duration": lambda x: pd.to_numeric(x, errors="coerce").mean(),
                    }
                )
                .round(2)
            )

            health_analysis["summary"] = {
                "total_executions": len(pipeline_df),
                "overall_success_rate": (pipeline_df["status"] == "success").sum()
                / len(pipeline_df)
                * 100,
                "stages_monitored": pipeline_df["pipeline_stage"].nunique(),
            }

            # Stage performance details
            for stage in stage_stats.index:
                stage_data = pipeline_df[pipeline_df["pipeline_stage"] == stage]
                health_analysis["stage_performance"][stage] = {
                    "success_rate": float(stage_stats.loc[stage, "status"]),
                    "avg_records": float(stage_stats.loc[stage, "records_processed"]),
                    "avg_duration_seconds": float(stage_stats.loc[stage, "duration"])
                    if pd.notna(stage_stats.loc[stage, "duration"])
                    else None,
                    "last_run": stage_data["execution_date"].max().isoformat()
                    if not stage_data.empty
                    else None,
                }

            # Recent failures
            failures = pipeline_df[pipeline_df["status"] == "failed"].head(10)
            health_analysis["recent_failures"] = [
                {
                    "stage": row["pipeline_stage"],
                    "date": row["execution_date"].isoformat(),
                    "error": row["error_message"][:200]
                    if row["error_message"]
                    else "Unknown error",
                }
                for _, row in failures.iterrows()
            ]

        return health_analysis

    def _analyze_training_data(self, lookback_days: int) -> Dict[str, Any]:
        """Analyze training data statistics."""
        # Get recent training data stats
        stats_query = """
        SELECT 
            build_date,
            total_records,
            unique_accounts,
            target_mean,
            target_std,
            win_rate,
            data_quality_score
        FROM training_data_stats
        WHERE build_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY build_date DESC
        """

        stats_df = self.db_manager.model_db.execute_query_df(
            stats_query, (lookback_days,)
        )

        training_analysis = {"summary": {}, "trends": {}, "quality_issues": []}

        if not stats_df.empty:
            latest_stats = stats_df.iloc[0]

            training_analysis["summary"] = {
                "latest_build_date": latest_stats["build_date"].isoformat(),
                "total_records": int(latest_stats["total_records"]),
                "unique_accounts": int(latest_stats["unique_accounts"]),
                "avg_win_rate": float(latest_stats["win_rate"]),
                "data_quality_score": float(latest_stats["data_quality_score"]),
            }

            # Trends over time
            training_analysis["trends"] = {
                "record_count": stats_df[["build_date", "total_records"]].to_dict(
                    "records"
                ),
                "win_rate": stats_df[["build_date", "win_rate"]].to_dict("records"),
                "quality_score": stats_df[["build_date", "data_quality_score"]].to_dict(
                    "records"
                ),
            }

            # Check for quality issues
            quality_issues_query = """
            SELECT 
                issue_type,
                issue_severity,
                affected_records,
                issue_description
            FROM training_data_quality_issues
            WHERE check_date >= CURRENT_DATE - INTERVAL '7 days'
                AND resolution_status = 'open'
            ORDER BY 
                CASE issue_severity 
                    WHEN 'critical' THEN 1 
                    WHEN 'warning' THEN 2 
                    ELSE 3 
                END,
                affected_records DESC
            """

            issues_df = self.db_manager.model_db.execute_query_df(quality_issues_query)

            if not issues_df.empty:
                training_analysis["quality_issues"] = [
                    {
                        "type": row["issue_type"],
                        "severity": row["issue_severity"],
                        "affected_records": int(row["affected_records"]),
                        "description": row["issue_description"],
                    }
                    for _, row in issues_df.iterrows()
                ]

        return training_analysis

    def _detect_anomalies(self, lookback_days: int) -> Dict[str, Any]:
        """Detect anomalies in recent data."""
        anomalies = {
            "feature_anomalies": [],
            "pipeline_anomalies": [],
            "data_anomalies": [],
        }

        # 1. Feature value anomalies
        anomaly_query = f"""
        SELECT 
            feature_name,
            COUNT(*) as anomaly_days,
            AVG(anomaly_count) as avg_anomalies,
            MAX(anomaly_count) as max_anomalies
        FROM feature_quality_metrics
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
            AND anomaly_count > 0
        GROUP BY feature_name
        HAVING COUNT(*) >= 3  -- At least 3 days with anomalies
        ORDER BY avg_anomalies DESC
        LIMIT 10
        """

        feature_anomalies = self.db_manager.model_db.execute_query(anomaly_query)

        if feature_anomalies:
            anomalies["feature_anomalies"] = [
                {
                    "feature": row["feature_name"],
                    "anomaly_days": row["anomaly_days"],
                    "avg_anomalies_per_day": round(row["avg_anomalies"], 2),
                    "severity": "high" if row["avg_anomalies"] > 100 else "medium",
                }
                for row in feature_anomalies
            ]

        # 2. Pipeline processing anomalies
        pipeline_anomaly_query = """
        SELECT 
            pipeline_stage,
            AVG(CAST(execution_details->>'duration_seconds' AS FLOAT)) as avg_duration,
            STDDEV(CAST(execution_details->>'duration_seconds' AS FLOAT)) as std_duration,
            MAX(CAST(execution_details->>'duration_seconds' AS FLOAT)) as max_duration
        FROM pipeline_executions
        WHERE execution_date >= CURRENT_DATE - INTERVAL '%s days'
            AND status = 'success'
            AND execution_details->>'duration_seconds' IS NOT NULL
        GROUP BY pipeline_stage
        """

        pipeline_stats = self.db_manager.model_db.execute_query_df(
            pipeline_anomaly_query, (lookback_days,)
        )

        if not pipeline_stats.empty:
            for _, row in pipeline_stats.iterrows():
                if pd.notna(row["avg_duration"]) and pd.notna(row["std_duration"]):
                    # Flag if max duration > mean + 3*std
                    threshold = row["avg_duration"] + 3 * row["std_duration"]
                    if row["max_duration"] > threshold:
                        anomalies["pipeline_anomalies"].append(
                            {
                                "stage": row["pipeline_stage"],
                                "issue": "execution_time_spike",
                                "max_duration": round(row["max_duration"], 2),
                                "expected_max": round(threshold, 2),
                            }
                        )

        # 3. Data volume anomalies
        volume_query = """
        SELECT 
            DATE(execution_date) as date,
            pipeline_stage,
            records_processed
        FROM pipeline_executions
        WHERE execution_date >= CURRENT_DATE - INTERVAL '%s days'
            AND status = 'success'
            AND records_processed IS NOT NULL
        ORDER BY execution_date
        """

        volume_df = self.db_manager.model_db.execute_query_df(
            volume_query, (lookback_days,)
        )

        if not volume_df.empty:
            for stage in volume_df["pipeline_stage"].unique():
                stage_data = volume_df[volume_df["pipeline_stage"] == stage][
                    "records_processed"
                ]
                if len(stage_data) >= 5:
                    mean_vol = stage_data.mean()
                    std_vol = stage_data.std()

                    # Check for significant drops or spikes
                    latest_vol = stage_data.iloc[-1]
                    if abs(latest_vol - mean_vol) > 2 * std_vol:
                        anomalies["data_anomalies"].append(
                            {
                                "stage": stage,
                                "issue": "volume_anomaly",
                                "latest_volume": int(latest_vol),
                                "expected_range": f"{int(mean_vol - 2 * std_vol)} - {int(mean_vol + 2 * std_vol)}",
                            }
                        )

        return anomalies

    def _generate_html_dashboard(self, report: Dict[str, Any]):
        """Generate interactive HTML dashboard."""
        # Create figure with subplots
        fig = make_subplots(
            rows=3,
            cols=2,
            subplot_titles=(
                "Feature Coverage Trends",
                "Feature Drift Timeline",
                "Top 20 Important Features",
                "Pipeline Success Rates",
                "Training Data Volume",
                "Data Quality Score Trend",
            ),
            specs=[
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "bar"}, {"type": "bar"}],
                [{"type": "scatter"}, {"type": "scatter"}],
            ],
        )

        # 1. Feature Coverage Trends
        quality_section = report["sections"].get("quality", {})
        if "trends" in quality_section:
            for feature, trends in quality_section["trends"].items():
                if "coverage_trend" in trends:
                    coverage_data = trends["coverage_trend"]
                    if coverage_data:
                        dates = [d["metric_date"] for d in coverage_data]
                        values = [d["coverage_pct"] for d in coverage_data]
                        fig.add_trace(
                            go.Scatter(
                                x=dates, y=values, name=feature, mode="lines+markers"
                            ),
                            row=1,
                            col=1,
                        )

        # 2. Feature Drift Timeline
        drift_section = report["sections"].get("drift", {})
        if "drift_timeline" in drift_section:
            for drift_type, timeline in drift_section["drift_timeline"].items():
                if timeline:
                    dates = [d["comparison_date"] for d in timeline]
                    counts = [d["count"] for d in timeline]
                    fig.add_trace(
                        go.Scatter(
                            x=dates,
                            y=counts,
                            name=f"{drift_type} drift",
                            mode="lines+markers",
                        ),
                        row=1,
                        col=2,
                    )

        # 3. Top Feature Importance
        importance_section = report["sections"].get("importance", {})
        if "top_features" in importance_section:
            top_features = importance_section["top_features"][:20]
            if top_features:
                features = [f["feature"] for f in top_features]
                scores = [f["score"] for f in top_features]
                fig.add_trace(
                    go.Bar(x=features, y=scores, name="Importance Score"), row=2, col=1
                )

        # 4. Pipeline Success Rates
        pipeline_section = report["sections"].get("pipeline_health", {})
        if "stage_performance" in pipeline_section:
            stages = list(pipeline_section["stage_performance"].keys())
            success_rates = [
                pipeline_section["stage_performance"][s]["success_rate"] for s in stages
            ]
            fig.add_trace(
                go.Bar(x=stages, y=success_rates, name="Success Rate %"), row=2, col=2
            )

        # 5. Training Data Volume
        training_section = report["sections"].get("training_data", {})
        if (
            "trends" in training_section
            and "record_count" in training_section["trends"]
        ):
            volume_trend = training_section["trends"]["record_count"]
            if volume_trend:
                dates = [d["build_date"] for d in volume_trend]
                volumes = [d["total_records"] for d in volume_trend]
                fig.add_trace(
                    go.Scatter(
                        x=dates, y=volumes, mode="lines+markers", name="Records"
                    ),
                    row=3,
                    col=1,
                )

        # 6. Data Quality Score
        if (
            "trends" in training_section
            and "quality_score" in training_section["trends"]
        ):
            quality_trend = training_section["trends"]["quality_score"]
            if quality_trend:
                dates = [d["build_date"] for d in quality_trend]
                scores = [d["data_quality_score"] for d in quality_trend]
                fig.add_trace(
                    go.Scatter(
                        x=dates, y=scores, mode="lines+markers", name="Quality Score"
                    ),
                    row=3,
                    col=2,
                )

        # Update layout
        fig.update_layout(
            height=1200,
            showlegend=True,
            title_text=f"Feature Engineering Monitoring Dashboard - Generated {report['generated_at']}",
            title_font_size=20,
        )

        # Update axes
        fig.update_xaxes(tickangle=-45)
        fig.update_yaxes(title_text="Coverage %", row=1, col=1)
        fig.update_yaxes(title_text="Drift Count", row=1, col=2)
        fig.update_yaxes(title_text="Importance Score", row=2, col=1)
        fig.update_yaxes(title_text="Success Rate %", row=2, col=2)
        fig.update_yaxes(title_text="Record Count", row=3, col=1)
        fig.update_yaxes(title_text="Quality Score", row=3, col=2)

        # Save to HTML
        output_file = f"feature_monitoring_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        # Create full HTML with summary statistics
        html_content = f"""
        <html>
        <head>
            <title>Feature Engineering Monitoring Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .summary {{ background-color: #f0f0f0; padding: 20px; margin-bottom: 20px; }}
                .alert {{ background-color: #ffe6e6; padding: 10px; margin: 10px 0; }}
                .metric {{ display: inline-block; margin: 10px 20px; }}
                .metric-value {{ font-size: 24px; font-weight: bold; }}
                .metric-label {{ color: #666; }}
            </style>
        </head>
        <body>
            <h1>Feature Engineering Monitoring Dashboard</h1>
            
            <div class="summary">
                <h2>Summary Metrics</h2>
                <div class="metric">
                    <div class="metric-value">{quality_section.get("summary", {}).get("avg_coverage", 0):.1f}%</div>
                    <div class="metric-label">Avg Feature Coverage</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{drift_section.get("summary", {}).get("drift_rate", 0):.1f}%</div>
                    <div class="metric-label">Feature Drift Rate</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{pipeline_section.get("summary", {}).get("overall_success_rate", 0):.1f}%</div>
                    <div class="metric-label">Pipeline Success Rate</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{training_section.get("summary", {}).get("data_quality_score", 0):.1f}</div>
                    <div class="metric-label">Data Quality Score</div>
                </div>
            </div>
            
            <div class="alerts">
                <h2>Active Alerts</h2>
        """

        # Add alerts
        all_alerts = []
        if "alerts" in quality_section:
            all_alerts.extend(quality_section["alerts"])

        anomalies = report["sections"].get("anomalies", {})
        for anomaly_type, anomaly_list in anomalies.items():
            for anomaly in anomaly_list:
                all_alerts.append(
                    {
                        "feature": anomaly.get(
                            "feature", anomaly.get("stage", "Unknown")
                        ),
                        "issue": anomaly.get("issue", anomaly_type),
                        "severity": anomaly.get("severity", "medium"),
                        "details": str(anomaly),
                    }
                )

        if all_alerts:
            for alert in all_alerts[:10]:  # Show top 10 alerts
                html_content += f"""
                <div class="alert">
                    <strong>{alert["feature"]}</strong> - {alert["issue"]} 
                    (Severity: {alert["severity"]})
                </div>
                """
        else:
            html_content += "<p>No active alerts</p>"

        html_content += """
            </div>
            
            <h2>Detailed Visualizations</h2>
        """

        # Add plotly chart
        html_content += fig.to_html(include_plotlyjs="cdn", div_id="plotly-chart")

        html_content += """
        </body>
        </html>
        """

        # Save HTML file
        with open(output_file, "w") as f:
            f.write(html_content)

        logger.info(f"Dashboard saved to {output_file}")

        return output_file

    def get_feature_recommendations(self) -> List[Dict[str, Any]]:
        """Generate recommendations for feature improvements."""
        recommendations = []

        # 1. Check for low coverage features
        low_coverage_query = """
        SELECT feature_name, AVG(coverage_pct) as avg_coverage
        FROM feature_quality_metrics
        WHERE metric_date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY feature_name
        HAVING AVG(coverage_pct) < 80
        ORDER BY avg_coverage
        LIMIT 5
        """

        low_coverage = self.db_manager.model_db.execute_query(low_coverage_query)

        for feature in low_coverage:
            recommendations.append(
                {
                    "type": "improve_coverage",
                    "feature": feature["feature_name"],
                    "priority": "high",
                    "recommendation": f"Feature '{feature['feature_name']}' has only {feature['avg_coverage']:.1f}% coverage. "
                    f"Investigate data sources and improve null handling.",
                }
            )

        # 2. Check for drifting features
        drift_query = """
        SELECT feature_name, COUNT(*) as drift_count
        FROM feature_drift
        WHERE comparison_date >= CURRENT_DATE - INTERVAL '14 days'
            AND is_significant = TRUE
        GROUP BY feature_name
        HAVING COUNT(*) >= 3
        ORDER BY drift_count DESC
        LIMIT 5
        """

        drifting_features = self.db_manager.model_db.execute_query(drift_query)

        for feature in drifting_features:
            recommendations.append(
                {
                    "type": "address_drift",
                    "feature": feature["feature_name"],
                    "priority": "medium",
                    "recommendation": f"Feature '{feature['feature_name']}' showed significant drift {feature['drift_count']} times. "
                    f"Consider retraining models or updating feature calculation.",
                }
            )

        # 3. Check for unstable important features
        stability_query = """
        WITH feature_ranks AS (
            SELECT 
                feature_name,
                importance_rank,
                model_version
            FROM feature_importance
            WHERE importance_rank <= 20
        ),
        rank_variance AS (
            SELECT 
                feature_name,
                STDDEV(importance_rank) as rank_std,
                AVG(importance_rank) as avg_rank,
                COUNT(DISTINCT model_version) as version_count
            FROM feature_ranks
            GROUP BY feature_name
            HAVING COUNT(DISTINCT model_version) >= 3
        )
        SELECT feature_name, rank_std, avg_rank
        FROM rank_variance
        WHERE rank_std > 5
        ORDER BY rank_std DESC
        LIMIT 3
        """

        unstable_features = self.db_manager.model_db.execute_query(stability_query)

        for feature in unstable_features:
            recommendations.append(
                {
                    "type": "stabilize_feature",
                    "feature": feature["feature_name"],
                    "priority": "medium",
                    "recommendation": f"Feature '{feature['feature_name']}' has unstable importance (std: {feature['rank_std']:.1f}). "
                    f"Review feature engineering logic for consistency.",
                }
            )

        return recommendations


def main():
    """Run feature monitoring dashboard."""
    parser = argparse.ArgumentParser(description="Monitor feature engineering pipeline")
    parser.add_argument(
        "--lookback-days", type=int, default=30, help="Number of days to look back"
    )
    parser.add_argument(
        "--output-html",
        action="store_true",
        default=True,
        help="Generate HTML dashboard",
    )
    parser.add_argument(
        "--recommendations",
        action="store_true",
        help="Generate feature improvement recommendations",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file="feature_monitoring")

    # Create dashboard
    dashboard = FeatureMonitoringDashboard()

    try:
        # Generate monitoring report
        report = dashboard.generate_monitoring_report(
            lookback_days=args.lookback_days, output_html=args.output_html
        )

        # Print summary
        print("\n" + "=" * 60)
        print("FEATURE MONITORING SUMMARY")
        print("=" * 60)

        for section_name, section_data in report["sections"].items():
            if "summary" in section_data:
                print(f"\n{section_name.upper()}:")
                for key, value in section_data["summary"].items():
                    print(f"  {key}: {value}")

        # Generate recommendations if requested
        if args.recommendations:
            print("\n" + "=" * 60)
            print("RECOMMENDATIONS")
            print("=" * 60)

            recommendations = dashboard.get_feature_recommendations()
            for i, rec in enumerate(recommendations, 1):
                print(f"\n{i}. [{rec['priority'].upper()}] {rec['type']}")
                print(f"   Feature: {rec['feature']}")
                print(f"   {rec['recommendation']}")

        print("\n" + "=" * 60)

    except Exception as e:
        logger.error(f"Monitoring failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
