"""
SLA monitoring and alerting system for the pipeline.
Tracks performance metrics and sends alerts when SLAs are violated.
"""

import json
import logging
import smtplib
import time
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
import os

from utils.database import get_db_manager

logger = logging.getLogger(__name__)


@dataclass
class SLAMetric:
    """Definition of an SLA metric."""

    name: str
    description: str
    warning_threshold: float
    critical_threshold: float
    unit: str
    direction: str  # 'above', 'below' - determines if threshold is maximum or minimum
    measurement_window: int  # minutes
    evaluation_frequency: int  # minutes
    enabled: bool = True


@dataclass
class SLAViolation:
    """Record of an SLA violation."""

    metric_name: str
    timestamp: datetime
    actual_value: float
    threshold_value: float
    severity: str  # 'warning', 'critical'
    description: str
    context: Dict[str, Any]


@dataclass
class AlertRule:
    """Definition of an alerting rule."""

    name: str
    conditions: List[str]  # List of metric names that trigger this alert
    severity_threshold: str  # 'warning', 'critical'
    cooldown_minutes: int  # Minimum time between alerts
    notification_channels: List[str]  # 'email', 'webhook', 'database'
    enabled: bool = True


class SLAMonitor:
    """Monitors SLA compliance and sends alerts for violations."""

    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize SLA monitor.

        Args:
            config_file: Path to SLA configuration file
        """
        self.db_manager = get_db_manager()
        self.config_file = config_file or Path("./sla_config.json")
        self.state_file = Path("./sla_state.json")

        # Load configuration
        self.sla_metrics = self._load_sla_config()
        self.alert_rules = self._load_alert_rules()

        # Load state (last alert times, etc.)
        self.state = self._load_state()

        # Violation history
        self.violation_history: List[SLAViolation] = []

        # Alert channels
        self.alert_channels = {
            "email": self._send_email_alert,
            "webhook": self._send_webhook_alert,
            "database": self._log_alert_to_database,
        }

    def _load_sla_config(self) -> Dict[str, SLAMetric]:
        """Load SLA metric definitions."""
        default_config = {
            "pipeline_duration": SLAMetric(
                name="pipeline_duration",
                description="Total pipeline execution time",
                warning_threshold=240.0,  # 4 hours
                critical_threshold=360.0,  # 6 hours
                unit="minutes",
                direction="above",
                measurement_window=60,
                evaluation_frequency=30,
            ),
            "data_freshness": SLAMetric(
                name="data_freshness",
                description="Age of the most recent data",
                warning_threshold=25.0,  # 25 hours
                critical_threshold=48.0,  # 48 hours
                unit="hours",
                direction="above",
                measurement_window=60,
                evaluation_frequency=60,
            ),
            "api_response_time": SLAMetric(
                name="api_response_time",
                description="Average API response time",
                warning_threshold=2000.0,  # 2 seconds
                critical_threshold=10000.0,  # 10 seconds
                unit="milliseconds",
                direction="above",
                measurement_window=30,
                evaluation_frequency=15,
            ),
            "database_query_time": SLAMetric(
                name="database_query_time",
                description="Average database query time",
                warning_threshold=1000.0,  # 1 second
                critical_threshold=5000.0,  # 5 seconds
                unit="milliseconds",
                direction="above",
                measurement_window=30,
                evaluation_frequency=15,
            ),
            "model_accuracy": SLAMetric(
                name="model_accuracy",
                description="Model prediction accuracy (R² score)",
                warning_threshold=0.1,  # Below 10% R²
                critical_threshold=0.05,  # Below 5% R²
                unit="r_squared",
                direction="below",
                measurement_window=1440,  # 24 hours
                evaluation_frequency=360,  # 6 hours
            ),
            "disk_space": SLAMetric(
                name="disk_space",
                description="Disk space usage percentage",
                warning_threshold=80.0,  # 80% full
                critical_threshold=90.0,  # 90% full
                unit="percent",
                direction="above",
                measurement_window=60,
                evaluation_frequency=30,
            ),
            "prediction_coverage": SLAMetric(
                name="prediction_coverage",
                description="Percentage of accounts with daily predictions",
                warning_threshold=90.0,  # Below 90% coverage
                critical_threshold=80.0,  # Below 80% coverage
                unit="percent",
                direction="below",
                measurement_window=1440,
                evaluation_frequency=360,
            ),
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    config_data = json.load(f)

                # Update with loaded config
                for name, metric_data in config_data.get("sla_metrics", {}).items():
                    if name in default_config:
                        # Update existing metric
                        metric = default_config[name]
                        for key, value in metric_data.items():
                            if hasattr(metric, key):
                                setattr(metric, key, value)
                    else:
                        # Create new metric
                        default_config[name] = SLAMetric(**metric_data)

            except Exception as e:
                logger.error(f"Failed to load SLA config: {e}")

        return default_config

    def _load_alert_rules(self) -> Dict[str, AlertRule]:
        """Load alert rule definitions."""
        default_rules = {
            "pipeline_performance": AlertRule(
                name="pipeline_performance",
                conditions=["pipeline_duration", "database_query_time"],
                severity_threshold="warning",
                cooldown_minutes=60,
                notification_channels=["email", "database"],
            ),
            "data_quality": AlertRule(
                name="data_quality",
                conditions=["data_freshness", "prediction_coverage"],
                severity_threshold="warning",
                cooldown_minutes=120,
                notification_channels=["email", "database"],
            ),
            "system_resources": AlertRule(
                name="system_resources",
                conditions=["disk_space"],
                severity_threshold="warning",
                cooldown_minutes=30,
                notification_channels=["email", "database"],
            ),
            "critical_failures": AlertRule(
                name="critical_failures",
                conditions=["pipeline_duration", "data_freshness", "model_accuracy"],
                severity_threshold="critical",
                cooldown_minutes=15,
                notification_channels=["email", "webhook", "database"],
            ),
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    config_data = json.load(f)

                for name, rule_data in config_data.get("alert_rules", {}).items():
                    if name in default_rules:
                        rule = default_rules[name]
                        for key, value in rule_data.items():
                            if hasattr(rule, key):
                                setattr(rule, key, value)
                    else:
                        default_rules[name] = AlertRule(**rule_data)

            except Exception as e:
                logger.error(f"Failed to load alert rules: {e}")

        return default_rules

    def _load_state(self) -> Dict[str, Any]:
        """Load monitor state."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load SLA state: {e}")

        return {
            "last_alert_times": {},
            "violation_counts": {},
            "last_evaluation_times": {},
        }

    def _save_state(self):
        """Save monitor state."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, default=str, indent=2)
        except Exception as e:
            logger.error(f"Failed to save SLA state: {e}")

    def evaluate_slas(self) -> Dict[str, Any]:
        """
        Evaluate all SLA metrics and detect violations.

        Returns:
            Dictionary containing evaluation results and violations
        """
        evaluation_start = datetime.now()
        results = {
            "timestamp": evaluation_start.isoformat(),
            "evaluated_metrics": [],
            "violations": [],
            "alerts_sent": [],
            "summary": {
                "total_metrics": len(self.sla_metrics),
                "evaluated": 0,
                "violations": 0,
                "alerts": 0,
            },
        }

        logger.info("Starting SLA evaluation...")

        # Evaluate each metric
        for metric_name, metric in self.sla_metrics.items():
            if not metric.enabled:
                continue

            # Check if it's time to evaluate this metric
            last_eval = self.state["last_evaluation_times"].get(metric_name)
            if last_eval:
                last_eval_time = datetime.fromisoformat(last_eval)
                if (
                    evaluation_start - last_eval_time
                ).total_seconds() < metric.evaluation_frequency * 60:
                    continue

            try:
                # Get current metric value
                metric_value = self._get_metric_value(metric_name, metric)

                if metric_value is not None:
                    results["evaluated_metrics"].append(
                        {
                            "name": metric_name,
                            "value": metric_value,
                            "unit": metric.unit,
                            "status": "healthy",
                        }
                    )

                    # Check for violations
                    violation = self._check_violation(metric, metric_value)

                    if violation:
                        results["violations"].append(asdict(violation))
                        results["summary"]["violations"] += 1
                        self.violation_history.append(violation)

                        # Update evaluated metric status
                        results["evaluated_metrics"][-1]["status"] = violation.severity

                        # Check alert rules
                        alerts = self._process_violation(violation)
                        results["alerts_sent"].extend(alerts)
                        results["summary"]["alerts"] += len(alerts)

                # Update last evaluation time
                self.state["last_evaluation_times"][metric_name] = (
                    evaluation_start.isoformat()
                )
                results["summary"]["evaluated"] += 1

            except Exception as e:
                logger.error(f"Failed to evaluate SLA metric {metric_name}: {e}")
                results["evaluated_metrics"].append(
                    {"name": metric_name, "status": "error", "error": str(e)}
                )

        # Save state
        self._save_state()

        # Log to database
        self._log_evaluation_to_database(results)

        evaluation_duration = (datetime.now() - evaluation_start).total_seconds()
        results["evaluation_duration_seconds"] = evaluation_duration

        logger.info(
            f"SLA evaluation completed in {evaluation_duration:.2f}s - "
            f"{results['summary']['violations']} violations, {results['summary']['alerts']} alerts"
        )

        return results

    def _get_metric_value(self, metric_name: str, metric: SLAMetric) -> Optional[float]:
        """Get current value for an SLA metric."""
        try:
            if metric_name == "pipeline_duration":
                return self._get_pipeline_duration()
            elif metric_name == "data_freshness":
                return self._get_data_freshness()
            elif metric_name == "api_response_time":
                return self._get_api_response_time()
            elif metric_name == "database_query_time":
                return self._get_database_query_time()
            elif metric_name == "model_accuracy":
                return self._get_model_accuracy()
            elif metric_name == "disk_space":
                return self._get_disk_space()
            elif metric_name == "prediction_coverage":
                return self._get_prediction_coverage()
            else:
                logger.warning(f"Unknown metric: {metric_name}")
                return None

        except Exception as e:
            logger.error(f"Error getting metric {metric_name}: {e}")
            return None

    def _get_pipeline_duration(self) -> Optional[float]:
        """Get average pipeline execution duration in minutes."""
        query = """
        SELECT AVG(EXTRACT(EPOCH FROM (end_time - start_time))/60) as avg_duration_minutes
        FROM prop_trading_model.pipeline_execution_log
        WHERE execution_date >= CURRENT_DATE - INTERVAL '7 days'
        AND end_time IS NOT NULL
        AND status = 'success'
        """

        result = self.db_manager.model_db.execute_query(query)
        if result and result[0]["avg_duration_minutes"]:
            return float(result[0]["avg_duration_minutes"])
        return None

    def _get_data_freshness(self) -> Optional[float]:
        """Get data freshness in hours."""
        query = """
        SELECT EXTRACT(EPOCH FROM (NOW() - MAX(ingestion_timestamp)))/3600 as hours_old
        FROM prop_trading_model.raw_metrics_daily
        WHERE metric_date >= CURRENT_DATE - INTERVAL '3 days'
        """

        result = self.db_manager.model_db.execute_query(query)
        if result and result[0]["hours_old"]:
            return float(result[0]["hours_old"])
        return None

    def _get_api_response_time(self) -> Optional[float]:
        """Get average API response time from recent health checks."""
        # This would typically come from a monitoring table
        # For now, we'll simulate or use a simple test
        import requests
        import time

        try:
            api_base_url = os.getenv(
                "RISK_API_BASE_URL", "https://d3m1s17i9h2y69.cloudfront.net"
            )
            start_time = time.time()
            response = requests.get(f"{api_base_url}/accounts", timeout=30)
            response_time = (time.time() - start_time) * 1000

            if response.status_code == 200:
                return response_time
        except Exception as e:
            logger.warning(f"API response time check failed: {e}")

        return None

    def _get_database_query_time(self) -> Optional[float]:
        """Get average database query time in milliseconds."""
        test_query = "SELECT COUNT(*) FROM prop_trading_model.raw_accounts_data WHERE ingestion_timestamp >= CURRENT_DATE"

        try:
            start_time = time.time()
            self.db_manager.model_db.execute_query(test_query)
            query_time = (time.time() - start_time) * 1000
            return query_time
        except Exception as e:
            logger.warning(f"Database query time check failed: {e}")
            return None

    def _get_model_accuracy(self) -> Optional[float]:
        """Get latest model accuracy (R² score)."""
        query = """
        SELECT val_r2
        FROM prop_trading_model.model_registry
        WHERE is_active = true
        ORDER BY created_at DESC
        LIMIT 1
        """

        result = self.db_manager.model_db.execute_query(query)
        if result and result[0]["val_r2"]:
            return float(result[0]["val_r2"])
        return None

    def _get_disk_space(self) -> Optional[float]:
        """Get disk space usage percentage."""
        import psutil

        try:
            disk_usage = psutil.disk_usage("/")
            return disk_usage.percent
        except Exception as e:
            logger.warning(f"Disk space check failed: {e}")
            return None

    def _get_prediction_coverage(self) -> Optional[float]:
        """Get percentage of accounts with recent predictions."""
        query = """
        WITH active_accounts AS (
            SELECT COUNT(DISTINCT login) as total_accounts
            FROM prop_trading_model.raw_accounts_data
            WHERE DATE(ingestion_timestamp) >= CURRENT_DATE - INTERVAL '1 day'
        ),
        predicted_accounts AS (
            SELECT COUNT(DISTINCT login) as predicted_accounts
            FROM prop_trading_model.model_predictions
            WHERE prediction_date >= CURRENT_DATE - INTERVAL '1 day'
        )
        SELECT 
            CASE 
                WHEN aa.total_accounts > 0 
                THEN (pa.predicted_accounts::float / aa.total_accounts::float) * 100
                ELSE 0 
            END as coverage_percent
        FROM active_accounts aa, predicted_accounts pa
        """

        result = self.db_manager.model_db.execute_query(query)
        if result and result[0]["coverage_percent"] is not None:
            return float(result[0]["coverage_percent"])
        return None

    def _check_violation(
        self, metric: SLAMetric, value: float
    ) -> Optional[SLAViolation]:
        """Check if a metric value violates SLA thresholds."""
        violation = None

        if metric.direction == "above":
            if value >= metric.critical_threshold:
                violation = SLAViolation(
                    metric_name=metric.name,
                    timestamp=datetime.now(),
                    actual_value=value,
                    threshold_value=metric.critical_threshold,
                    severity="critical",
                    description=f"{metric.description} exceeded critical threshold",
                    context={"metric": asdict(metric)},
                )
            elif value >= metric.warning_threshold:
                violation = SLAViolation(
                    metric_name=metric.name,
                    timestamp=datetime.now(),
                    actual_value=value,
                    threshold_value=metric.warning_threshold,
                    severity="warning",
                    description=f"{metric.description} exceeded warning threshold",
                    context={"metric": asdict(metric)},
                )
        elif metric.direction == "below":
            if value <= metric.critical_threshold:
                violation = SLAViolation(
                    metric_name=metric.name,
                    timestamp=datetime.now(),
                    actual_value=value,
                    threshold_value=metric.critical_threshold,
                    severity="critical",
                    description=f"{metric.description} below critical threshold",
                    context={"metric": asdict(metric)},
                )
            elif value <= metric.warning_threshold:
                violation = SLAViolation(
                    metric_name=metric.name,
                    timestamp=datetime.now(),
                    actual_value=value,
                    threshold_value=metric.warning_threshold,
                    severity="warning",
                    description=f"{metric.description} below warning threshold",
                    context={"metric": asdict(metric)},
                )

        return violation

    def _process_violation(self, violation: SLAViolation) -> List[Dict[str, Any]]:
        """Process a violation and send appropriate alerts."""
        alerts_sent = []

        # Find applicable alert rules
        for rule_name, rule in self.alert_rules.items():
            if not rule.enabled:
                continue

            # Check if this violation triggers this rule
            if violation.metric_name in rule.conditions:
                # Check severity threshold
                if (
                    rule.severity_threshold == "warning"
                    and violation.severity in ["warning", "critical"]
                ) or (
                    rule.severity_threshold == "critical"
                    and violation.severity == "critical"
                ):
                    # Check cooldown period
                    last_alert_key = f"{rule_name}_{violation.metric_name}"
                    last_alert_time = self.state["last_alert_times"].get(last_alert_key)

                    if last_alert_time:
                        last_alert_dt = datetime.fromisoformat(last_alert_time)
                        if (
                            datetime.now() - last_alert_dt
                        ).total_seconds() < rule.cooldown_minutes * 60:
                            continue

                    # Send alerts
                    for channel in rule.notification_channels:
                        try:
                            alert_result = self.alert_channels[channel](violation, rule)
                            alerts_sent.append(
                                {
                                    "rule": rule_name,
                                    "channel": channel,
                                    "timestamp": datetime.now().isoformat(),
                                    "success": alert_result.get("success", False),
                                    "message": alert_result.get("message", ""),
                                }
                            )
                        except Exception as e:
                            logger.error(f"Failed to send alert via {channel}: {e}")
                            alerts_sent.append(
                                {
                                    "rule": rule_name,
                                    "channel": channel,
                                    "timestamp": datetime.now().isoformat(),
                                    "success": False,
                                    "error": str(e),
                                }
                            )

                    # Update last alert time
                    self.state["last_alert_times"][last_alert_key] = (
                        datetime.now().isoformat()
                    )

        return alerts_sent

    def _send_email_alert(
        self, violation: SLAViolation, rule: AlertRule
    ) -> Dict[str, Any]:
        """Send email alert for SLA violation."""
        try:
            # Email configuration from environment
            smtp_server = os.getenv("SMTP_SERVER", "localhost")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_username = os.getenv("SMTP_USERNAME", "")
            smtp_password = os.getenv("SMTP_PASSWORD", "")
            from_email = os.getenv("ALERT_FROM_EMAIL", "alerts@company.com")
            to_emails = os.getenv("ALERT_TO_EMAILS", "admin@company.com").split(",")

            subject = (
                f"[{violation.severity.upper()}] SLA Violation: {violation.metric_name}"
            )

            body = f"""
SLA Violation Alert

Metric: {violation.metric_name}
Description: {violation.description}
Severity: {violation.severity}
Current Value: {violation.actual_value}
Threshold: {violation.threshold_value}
Timestamp: {violation.timestamp}

Alert Rule: {rule.name}
Cooldown Period: {rule.cooldown_minutes} minutes

Please investigate and take appropriate action.

Best regards,
Pipeline Monitoring System
            """

            msg = MimeMultipart()
            msg["From"] = from_email
            msg["To"] = ", ".join(to_emails)
            msg["Subject"] = subject
            msg.attach(MimeText(body, "plain"))

            if smtp_username and smtp_password:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
                server.quit()

                return {
                    "success": True,
                    "message": f"Email sent to {len(to_emails)} recipients",
                }
            else:
                logger.warning("Email credentials not configured, skipping email alert")
                return {"success": False, "message": "Email credentials not configured"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _send_webhook_alert(
        self, violation: SLAViolation, rule: AlertRule
    ) -> Dict[str, Any]:
        """Send webhook alert for SLA violation."""
        try:
            webhook_url = os.getenv("WEBHOOK_URL")
            if not webhook_url:
                return {"success": False, "message": "Webhook URL not configured"}

            payload = {
                "alert_type": "sla_violation",
                "severity": violation.severity,
                "metric_name": violation.metric_name,
                "description": violation.description,
                "actual_value": violation.actual_value,
                "threshold_value": violation.threshold_value,
                "timestamp": violation.timestamp.isoformat(),
                "rule_name": rule.name,
            }

            import requests

            response = requests.post(webhook_url, json=payload, timeout=30)

            if response.status_code == 200:
                return {"success": True, "message": "Webhook sent successfully"}
            else:
                return {
                    "success": False,
                    "message": f"Webhook failed with status {response.status_code}",
                }

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _log_alert_to_database(
        self, violation: SLAViolation, rule: AlertRule
    ) -> Dict[str, Any]:
        """Log alert to database."""
        try:
            query = """
            INSERT INTO prop_trading_model.sla_alerts 
            (metric_name, severity, actual_value, threshold_value, description, rule_name, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            # Create table if it doesn't exist
            create_table_query = """
            CREATE TABLE IF NOT EXISTS prop_trading_model.sla_alerts (
                id SERIAL PRIMARY KEY,
                metric_name VARCHAR(100) NOT NULL,
                severity VARCHAR(20) NOT NULL,
                actual_value DECIMAL(18, 4),
                threshold_value DECIMAL(18, 4),
                description TEXT,
                rule_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """

            self.db_manager.model_db.execute_command(create_table_query)

            self.db_manager.model_db.execute_command(
                query,
                (
                    violation.metric_name,
                    violation.severity,
                    violation.actual_value,
                    violation.threshold_value,
                    violation.description,
                    rule.name,
                    violation.timestamp,
                ),
            )

            return {"success": True, "message": "Alert logged to database"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _log_evaluation_to_database(self, results: Dict[str, Any]):
        """Log SLA evaluation results to database."""
        try:
            # Create table if it doesn't exist
            create_table_query = """
            CREATE TABLE IF NOT EXISTS prop_trading_model.sla_evaluations (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                total_metrics INTEGER,
                evaluated_metrics INTEGER,
                violations INTEGER,
                alerts_sent INTEGER,
                evaluation_duration_seconds DECIMAL(10, 3),
                results_json JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """

            self.db_manager.model_db.execute_command(create_table_query)

            insert_query = """
            INSERT INTO prop_trading_model.sla_evaluations 
            (timestamp, total_metrics, evaluated_metrics, violations, alerts_sent, evaluation_duration_seconds, results_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            self.db_manager.model_db.execute_command(
                insert_query,
                (
                    datetime.fromisoformat(results["timestamp"]),
                    results["summary"]["total_metrics"],
                    results["summary"]["evaluated"],
                    results["summary"]["violations"],
                    results["summary"]["alerts"],
                    results.get("evaluation_duration_seconds", 0),
                    json.dumps(results),
                ),
            )

        except Exception as e:
            logger.error(f"Failed to log SLA evaluation to database: {e}")

    def get_sla_dashboard_data(self) -> Dict[str, Any]:
        """Get data for SLA monitoring dashboard."""
        try:
            dashboard_data = {
                "timestamp": datetime.now().isoformat(),
                "sla_metrics": {},
                "recent_violations": [],
                "alert_summary": {},
                "trends": {},
            }

            # Get current metric values
            for metric_name, metric in self.sla_metrics.items():
                if metric.enabled:
                    current_value = self._get_metric_value(metric_name, metric)
                    status = "healthy"

                    if current_value is not None:
                        if metric.direction == "above":
                            if current_value >= metric.critical_threshold:
                                status = "critical"
                            elif current_value >= metric.warning_threshold:
                                status = "warning"
                        elif metric.direction == "below":
                            if current_value <= metric.critical_threshold:
                                status = "critical"
                            elif current_value <= metric.warning_threshold:
                                status = "warning"

                    dashboard_data["sla_metrics"][metric_name] = {
                        "current_value": current_value,
                        "warning_threshold": metric.warning_threshold,
                        "critical_threshold": metric.critical_threshold,
                        "unit": metric.unit,
                        "status": status,
                        "description": metric.description,
                    }

            # Get recent violations
            if hasattr(self, "violation_history"):
                recent_violations = [
                    asdict(v)
                    for v in self.violation_history[-10:]  # Last 10 violations
                ]
                dashboard_data["recent_violations"] = recent_violations

            # Get alert summary from database
            alert_summary_query = """
            SELECT 
                DATE(created_at) as alert_date,
                severity,
                COUNT(*) as alert_count
            FROM prop_trading_model.sla_alerts
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(created_at), severity
            ORDER BY alert_date DESC
            """

            try:
                alert_results = self.db_manager.model_db.execute_query(
                    alert_summary_query
                )
                dashboard_data["alert_summary"] = [dict(row) for row in alert_results]
            except Exception as e:
                logger.warning(f"Failed to get alert summary: {e}")
                dashboard_data["alert_summary"] = []

            return dashboard_data

        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {"error": str(e)}


def create_default_sla_config(config_file: Path = None):
    """Create a default SLA configuration file."""
    config_file = config_file or Path("./sla_config.json")

    default_config = {
        "sla_metrics": {
            "pipeline_duration": {
                "name": "pipeline_duration",
                "description": "Total pipeline execution time",
                "warning_threshold": 240.0,
                "critical_threshold": 360.0,
                "unit": "minutes",
                "direction": "above",
                "measurement_window": 60,
                "evaluation_frequency": 30,
                "enabled": True,
            },
            "data_freshness": {
                "name": "data_freshness",
                "description": "Age of the most recent data",
                "warning_threshold": 25.0,
                "critical_threshold": 48.0,
                "unit": "hours",
                "direction": "above",
                "measurement_window": 60,
                "evaluation_frequency": 60,
                "enabled": True,
            },
        },
        "alert_rules": {
            "critical_failures": {
                "name": "critical_failures",
                "conditions": ["pipeline_duration", "data_freshness"],
                "severity_threshold": "critical",
                "cooldown_minutes": 15,
                "notification_channels": ["email", "database"],
                "enabled": True,
            }
        },
    }

    with open(config_file, "w") as f:
        json.dump(default_config, f, indent=2)

    logger.info(f"Created default SLA configuration at {config_file}")


if __name__ == "__main__":
    # Example usage
    monitor = SLAMonitor()
    results = monitor.evaluate_slas()
    print(json.dumps(results, indent=2, default=str))
