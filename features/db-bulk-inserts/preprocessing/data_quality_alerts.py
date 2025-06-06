"""
Automated data quality alerting system.
Sends notifications via multiple channels when data quality issues are detected.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date
from dataclasses import dataclass, asdict
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    
try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertChannel(Enum):
    """Available alert channels."""
    EMAIL = "email"
    SLACK = "slack"
    KAFKA = "kafka"
    WEBHOOK = "webhook"
    DATABASE = "database"


@dataclass
class DataQualityAlert:
    """Data quality alert definition."""
    alert_id: str
    timestamp: datetime
    severity: AlertSeverity
    alert_type: str
    title: str
    description: str
    affected_table: Optional[str] = None
    affected_records: Optional[int] = None
    metrics: Optional[Dict[str, Any]] = None
    recommended_action: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AlertManager:
    """Manages data quality alerts and notifications."""
    
    def __init__(self, db_manager, config: Optional[Dict[str, Any]] = None):
        """
        Initialize alert manager.
        
        Args:
            db_manager: Database manager instance
            config: Alert configuration dictionary
        """
        self.db_manager = db_manager
        self.config = config or self._load_default_config()
        self.channels = self._initialize_channels()
        
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default alert configuration."""
        return {
            "email": {
                "enabled": True,
                "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
                "smtp_port": int(os.getenv("SMTP_PORT", "587")),
                "smtp_user": os.getenv("SMTP_USER"),
                "smtp_password": os.getenv("SMTP_PASSWORD"),
                "from_email": os.getenv("ALERT_FROM_EMAIL", "alerts@tradingmodel.com"),
                "from_name": "Trading Model Alerts",
                "to_emails": os.getenv("ALERT_TO_EMAILS", "").split(",")
            },
            "slack": {
                "enabled": SLACK_AVAILABLE and bool(os.getenv("SLACK_BOT_TOKEN")),
                "bot_token": os.getenv("SLACK_BOT_TOKEN"),
                "channel": os.getenv("SLACK_ALERT_CHANNEL", "#data-quality-alerts")
            },
            "kafka": {
                "enabled": KAFKA_AVAILABLE and bool(os.getenv("KAFKA_BOOTSTRAP_SERVERS")),
                "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
                "topic": os.getenv("KAFKA_ALERT_TOPIC", "data-quality-alerts")
            },
            "database": {
                "enabled": True,
                "table_name": "data_quality_alerts"
            },
            "severity_thresholds": {
                "critical": ["email", "slack", "database"],
                "high": ["email", "slack", "database"],
                "medium": ["slack", "database"],
                "low": ["database"],
                "info": ["database"]
            }
        }
    
    def _initialize_channels(self) -> Dict[str, Any]:
        """Initialize alert channels based on configuration."""
        channels = {}
        
        # Initialize Slack client
        if self.config["slack"]["enabled"] and SLACK_AVAILABLE:
            try:
                channels["slack"] = WebClient(token=self.config["slack"]["bot_token"])
                logger.info("Slack alert channel initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Slack channel: {str(e)}")
        
        # Initialize Kafka producer
        if self.config["kafka"]["enabled"] and KAFKA_AVAILABLE:
            try:
                channels["kafka"] = KafkaProducer(
                    bootstrap_servers=self.config["kafka"]["bootstrap_servers"],
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                logger.info("Kafka alert channel initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Kafka channel: {str(e)}")
        
        return channels
    
    def send_alert(self, alert: DataQualityAlert) -> Dict[str, bool]:
        """
        Send alert through configured channels.
        
        Args:
            alert: Alert to send
            
        Returns:
            Dictionary of channel results
        """
        results = {}
        
        # Determine which channels to use based on severity
        channels_to_use = self.config["severity_thresholds"].get(
            alert.severity.value, ["database"]
        )
        
        for channel in channels_to_use:
            try:
                if channel == "email" and self.config["email"]["enabled"]:
                    results["email"] = self._send_email_alert(alert)
                elif channel == "slack" and self.config["slack"]["enabled"]:
                    results["slack"] = self._send_slack_alert(alert)
                elif channel == "kafka" and self.config["kafka"]["enabled"]:
                    results["kafka"] = self._send_kafka_alert(alert)
                elif channel == "database" and self.config["database"]["enabled"]:
                    results["database"] = self._save_alert_to_database(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {channel}: {str(e)}")
                results[channel] = False
        
        return results
    
    def _send_email_alert(self, alert: DataQualityAlert) -> bool:
        """Send alert via email."""
        try:
            email_config = self.config["email"]
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.title}"
            msg['From'] = formataddr((email_config["from_name"], email_config["from_email"]))
            msg['To'] = ", ".join(email_config["to_emails"])
            
            # Create email body
            text_body = self._format_alert_text(alert)
            html_body = self._format_alert_html(alert)
            
            # Attach parts
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(email_config["smtp_host"], email_config["smtp_port"]) as server:
                server.starttls()
                if email_config["smtp_user"] and email_config["smtp_password"]:
                    server.login(email_config["smtp_user"], email_config["smtp_password"])
                server.send_message(msg)
            
            logger.info(f"Email alert sent: {alert.alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {str(e)}")
            return False
    
    def _send_slack_alert(self, alert: DataQualityAlert) -> bool:
        """Send alert via Slack."""
        if "slack" not in self.channels:
            return False
        
        try:
            # Format message blocks
            blocks = self._format_slack_blocks(alert)
            
            # Send message
            self.channels["slack"].chat_postMessage(
                channel=self.config["slack"]["channel"],
                text=f"{alert.severity.value.upper()}: {alert.title}",
                blocks=blocks
            )
            
            logger.info(f"Slack alert sent: {alert.alert_id}")
            return True
            
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}")
            return False
    
    def _send_kafka_alert(self, alert: DataQualityAlert) -> bool:
        """Send alert via Kafka."""
        if "kafka" not in self.channels:
            return False
        
        try:
            # Convert alert to dictionary
            alert_dict = asdict(alert)
            alert_dict['timestamp'] = alert_dict['timestamp'].isoformat()
            alert_dict['severity'] = alert.severity.value
            
            # Send to Kafka
            future = self.channels["kafka"].send(
                self.config["kafka"]["topic"],
                value=alert_dict,
                key=alert.alert_id.encode('utf-8')
            )
            
            # Wait for send to complete
            future.get(timeout=10)
            
            logger.info(f"Kafka alert sent: {alert.alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Kafka alert: {str(e)}")
            return False
    
    def _save_alert_to_database(self, alert: DataQualityAlert) -> bool:
        """Save alert to database."""
        try:
            query = """
            INSERT INTO data_quality_alerts (
                alert_id, timestamp, severity, alert_type, title, description,
                affected_table, affected_records, metrics, recommended_action, details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                alert.alert_id,
                alert.timestamp,
                alert.severity.value,
                alert.alert_type,
                alert.title,
                alert.description,
                alert.affected_table,
                alert.affected_records,
                json.dumps(alert.metrics) if alert.metrics else None,
                alert.recommended_action,
                json.dumps(alert.details) if alert.details else None
            )
            
            self.db_manager.model_db.execute_command(query, params)
            logger.info(f"Alert saved to database: {alert.alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save alert to database: {str(e)}")
            return False
    
    def _format_alert_text(self, alert: DataQualityAlert) -> str:
        """Format alert as plain text."""
        lines = [
            "DATA QUALITY ALERT",
            "==================",
            "",
            f"Severity: {alert.severity.value.upper()}",
            f"Type: {alert.alert_type}",
            f"Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Title: {alert.title}",
            f"Description: {alert.description}",
            ""
        ]
        
        if alert.affected_table:
            lines.append(f"Affected Table: {alert.affected_table}")
        if alert.affected_records:
            lines.append(f"Affected Records: {alert.affected_records:,}")
        
        if alert.metrics:
            lines.extend([
                "",
                "Metrics:",
                "--------"
            ])
            for key, value in alert.metrics.items():
                lines.append(f"  {key}: {value}")
        
        if alert.recommended_action:
            lines.extend([
                "",
                "Recommended Action:",
                f"{alert.recommended_action}"
            ])
        
        return "\n".join(lines)
    
    def _format_alert_html(self, alert: DataQualityAlert) -> str:
        """Format alert as HTML."""
        severity_colors = {
            "critical": "#D32F2F",
            "high": "#F57C00",
            "medium": "#FBC02D",
            "low": "#388E3C",
            "info": "#1976D2"
        }
        
        color = severity_colors.get(alert.severity.value, "#000000")
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <div style="border-left: 4px solid {color}; padding-left: 20px;">
                <h2 style="color: {color};">DATA QUALITY ALERT</h2>
                
                <table style="border-collapse: collapse; width: 100%;">
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Severity:</td>
                        <td style="padding: 8px;">{alert.severity.value.upper()}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Type:</td>
                        <td style="padding: 8px;">{alert.alert_type}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Time:</td>
                        <td style="padding: 8px;">{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
                    </tr>
                </table>
                
                <h3>{alert.title}</h3>
                <p>{alert.description}</p>
        """
        
        if alert.affected_table or alert.affected_records:
            html += """
                <h4>Impact</h4>
                <ul>
            """
            if alert.affected_table:
                html += f"<li>Table: {alert.affected_table}</li>"
            if alert.affected_records:
                html += f"<li>Records: {alert.affected_records:,}</li>"
            html += "</ul>"
        
        if alert.metrics:
            html += """
                <h4>Metrics</h4>
                <table style="border-collapse: collapse;">
            """
            for key, value in alert.metrics.items():
                html += f"""
                    <tr>
                        <td style="padding: 4px 16px 4px 0; font-weight: bold;">{key}:</td>
                        <td style="padding: 4px;">{value}</td>
                    </tr>
                """
            html += "</table>"
        
        if alert.recommended_action:
            html += f"""
                <h4>Recommended Action</h4>
                <p style="background-color: #f5f5f5; padding: 10px; border-radius: 4px;">
                    {alert.recommended_action}
                </p>
            """
        
        html += """
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _format_slack_blocks(self, alert: DataQualityAlert) -> List[Dict]:
        """Format alert as Slack blocks."""
        emoji_map = {
            "critical": ":rotating_light:",
            "high": ":warning:",
            "medium": ":information_source:",
            "low": ":white_check_mark:",
            "info": ":speech_balloon:"
        }
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji_map.get(alert.severity.value, '')} {alert.title}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{alert.severity.value.upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:*\n{alert.alert_type}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{alert.description}"
                }
            }
        ]
        
        if alert.affected_table or alert.affected_records:
            fields = []
            if alert.affected_table:
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*Table:*\n{alert.affected_table}"
                })
            if alert.affected_records:
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*Records:*\n{alert.affected_records:,}"
                })
            
            blocks.append({
                "type": "section",
                "fields": fields
            })
        
        if alert.metrics:
            metric_text = "\n".join([f"• {k}: {v}" for k, v in alert.metrics.items()])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Metrics:*\n{metric_text}"
                }
            })
        
        if alert.recommended_action:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommended Action:*\n{alert.recommended_action}"
                }
            })
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Alert ID: {alert.alert_id} | Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })
        
        return blocks
    
    def check_and_alert_data_quality(self, validation_results: List[Any],
                                   anomaly_results: List[Any]) -> List[DataQualityAlert]:
        """
        Check validation and anomaly results and generate alerts.
        
        Args:
            validation_results: List of validation results
            anomaly_results: List of anomaly detection results
            
        Returns:
            List of generated alerts
        """
        alerts = []
        
        # Check validation failures
        critical_failures = [r for r in validation_results 
                           if hasattr(r, 'status') and r.status.value == 'failed' 
                           and hasattr(r, 'severity') and r.severity == 'error']
        
        if critical_failures:
            alert = DataQualityAlert(
                alert_id=f"VAL_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                timestamp=datetime.now(),
                severity=AlertSeverity.CRITICAL,
                alert_type="validation_failure",
                title="Critical Data Validation Failures",
                description=f"{len(critical_failures)} critical validation rules failed",
                metrics={
                    "failed_rules": len(critical_failures),
                    "rules": [f.rule_name for f in critical_failures[:5]]  # First 5
                },
                recommended_action="Investigate and fix data quality issues immediately"
            )
            alerts.append(alert)
        
        # Check high severity anomalies
        high_anomalies = [a for a in anomaly_results 
                         if hasattr(a, 'severity') and a.severity == 'high']
        
        if len(high_anomalies) > 5:  # Alert if many high severity anomalies
            alert = DataQualityAlert(
                alert_id=f"ANOM_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                timestamp=datetime.now(),
                severity=AlertSeverity.HIGH,
                alert_type="anomaly_detection",
                title="Multiple High Severity Anomalies Detected",
                description=f"{len(high_anomalies)} high severity anomalies detected",
                metrics={
                    "anomaly_count": len(high_anomalies),
                    "affected_accounts": len(set(a.account_id for a in high_anomalies))
                },
                recommended_action="Review anomaly detection report and investigate accounts"
            )
            alerts.append(alert)
        
        # Send all generated alerts
        for alert in alerts:
            self.send_alert(alert)
        
        return alerts
    
    def get_alert_history(self, start_date: date, end_date: date,
                         severity: Optional[AlertSeverity] = None) -> List[Dict]:
        """Get historical alerts from database."""
        query = """
        SELECT * FROM data_quality_alerts
        WHERE timestamp::date BETWEEN %s AND %s
        """
        params = [start_date, end_date]
        
        if severity:
            query += " AND severity = %s"
            params.append(severity.value)
        
        query += " ORDER BY timestamp DESC"
        
        return self.db_manager.model_db.execute_query(query, tuple(params))