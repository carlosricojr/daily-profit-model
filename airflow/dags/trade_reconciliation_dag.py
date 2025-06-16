from __future__ import annotations

"""Corrected DAG implementing full trade reconciliation functionality.

This DAG implements the complete trade reconciliation process as specified:
- Detailed issue detection (missing tables, count mismatches, date gaps)
- Resolution attempts (database-side only, API integration requires additional setup)
- Failed attempt tracking
- Batch processing for performance on large datasets

Runs at 23:00 America/New_York by default (cron: ``0 23 * * *``)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.timetables.trigger import CronTriggerTimetable

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

def maintain_trade_recon_table(**_):
    """Maintenance wrapper that includes NULL fixes and stats refresh."""
    import subprocess
    import tempfile
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent
    
    maintenance_script = """
import sys
sys.path.insert(0, '/opt/airflow')
sys.path.insert(0, '/opt/airflow/src')

from src.data_quality.trade_reconciliation_production import fix_all_null_account_ids
from src.data_quality.maintain_trade_recon import refresh_all_account_ids
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    # Fix any NULL account_ids first (uses batch processing)
    logger.info("Fixing NULL account_ids...")
    fix_results = fix_all_null_account_ids()
    logger.info(f"[trade_recon] Null account_id fix results: {json.dumps(fix_results)}")
    
    # Refresh materialized view and update stats
    logger.info("Refreshing account list and stats...")
    refresh_all_account_ids()
    logger.info("[trade_recon] Maintenance completed successfully")
    
except Exception as e:
    logger.error(f"Maintenance failed: {e}")
    raise
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='_maintain_recon.py', delete=False) as f:
        f.write(maintenance_script)
        script_file = Path(f.name)
    
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(script_file)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"Maintenance failed: {result.stderr}")
        
        print(result.stdout)
    finally:
        if script_file.exists():
            script_file.unlink()


def run_reconciliation(retry_failed: bool = False, **_):
    """Run the main reconciliation job with full issue detection."""
    import subprocess
    import tempfile
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent
    
    reconciliation_script = f"""
import sys
sys.path.insert(0, '/opt/airflow')
sys.path.insert(0, '/opt/airflow/src')

from src.data_quality.trade_reconciliation_production import reconcile_all_mismatched_accounts
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    logger.info("Starting trade reconciliation...")
    summary = reconcile_all_mismatched_accounts(retry_failed={retry_failed})
    
    logger.info(f"[trade_recon] Reconciliation summary:")
    logger.info(f"  Total processed: {{summary['total_processed']}}")
    logger.info(f"  Fully resolved: {{summary['fully_resolved']}}")
    logger.info(f"  Partially resolved: {{summary['partially_resolved']}}")
    logger.info(f"  Failed: {{summary['failed']}}")
    
    # Check failure rate
    if summary["total_processed"] > 0:
        failure_rate = summary["failed"] / summary["total_processed"]
        if failure_rate > 0.1:
            raise RuntimeError(
                f"High failure rate: {{summary['failed']}}/{{summary['total_processed']}} ({{failure_rate:.1%}})"
            )
    
except Exception as e:
    logger.error(f"Reconciliation failed: {{e}}")
    raise
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='_run_reconciliation.py', delete=False) as f:
        f.write(reconciliation_script)
        script_file = Path(f.name)
    
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(script_file)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=7200  # 2 hour timeout for full reconciliation
        )
        
        if result.returncode != 0:
            raise Exception(f"Reconciliation failed: {result.stderr}")
        
        print(result.stdout)
    finally:
        if script_file.exists():
            script_file.unlink()


def generate_reconciliation_report(**_):
    """Generate a summary report of reconciliation status."""
    import subprocess
    import tempfile
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent
    
    report_script = """
import sys
sys.path.insert(0, '/opt/airflow')
sys.path.insert(0, '/opt/airflow/src')

from src.data_quality.trade_reconciliation_production import generate_reconciliation_report
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    report = generate_reconciliation_report()
    
    logger.info("=" * 50)
    logger.info("TRADE RECONCILIATION STATUS REPORT")
    logger.info(f"Generated: {datetime.now()}")
    logger.info("=" * 50)
    
    # Overall statistics
    overall = report['overall']
    logger.info(f"Total Accounts: {overall['total_accounts']}")
    logger.info(f"Fully Reconciled: {overall['reconciled']} ({overall['reconciliation_percentage']:.1f}%)")
    logger.info(f"Needs Reconciliation: {overall['needs_reconciliation']}")
    logger.info(f"Has Failures: {overall['has_failures']}")
    logger.info(f"Has Issues: {overall['has_issues']}")
    
    # Issue breakdown
    if report.get('issues_by_type'):
        logger.info("\\nIssue Breakdown:")
        for issue in report['issues_by_type']:
            logger.info(f"  - {issue['issue_type']} (severity {issue['severity']}): {issue['account_count']} accounts")
    
    # Recent activity
    if report.get('recent_activity'):
        logger.info("\\nRecent Activity (last 7 days):")
        for activity in report['recent_activity']:
            logger.info(f"  - {activity['check_date']}: {activity['accounts_checked']} checked, {activity['resolved']} resolved, {activity['failed']} failed")
    
    logger.info("=" * 50)
    
except Exception as e:
    logger.error(f"Report generation failed: {e}")
    raise
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='_generate_report.py', delete=False) as f:
        f.write(report_script)
        script_file = Path(f.name)
    
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(script_file)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"Report generation failed: {result.stderr}")
        
        print(result.stdout)
    finally:
        if script_file.exists():
            script_file.unlink()


# ---------------------------------------------------------------------------
# Primary nightly DAG with full functionality
# ---------------------------------------------------------------------------

dag = DAG(
    "trade_reconciliation",
    default_args=DEFAULT_ARGS,
    description="Nightly trade reconciliation with full issue detection",
    schedule=CronTriggerTimetable(
        "0 23 * * *",
        timezone="America/New_York"
    ),
    catchup=False,
    max_active_runs=1,
)

# Task 1: Maintain trade_recon table (fix NULLs, refresh MV, update stats)
maintain_task = PythonOperator(
    task_id="maintain_trade_recon_table",
    python_callable=maintain_trade_recon_table,
    dag=dag,
)

# Task 2: Run reconciliation (detect issues, attempt resolutions)
reconcile_task = PythonOperator(
    task_id="run_reconciliation",
    python_callable=run_reconciliation,
    op_kwargs={"retry_failed": False},
    dag=dag,
)

# Task 3: Generate status report
report_task = PythonOperator(
    task_id="generate_reconciliation_report",
    python_callable=generate_reconciliation_report,
    dag=dag,
)

# Define task dependencies
maintain_task >> reconcile_task >> report_task

# ---------------------------------------------------------------------------
# Manual-trigger DAG for retrying failed accounts
# ---------------------------------------------------------------------------

retry_dag = DAG(
    "trade_reconciliation_retry",
    default_args=DEFAULT_ARGS,
    description="Manual retry of failed trade reconciliations",
    schedule=None,
    catchup=False,
)

retry_reconcile_task = PythonOperator(
    task_id="run_reconciliation_with_retry",
    python_callable=run_reconciliation,
    op_kwargs={"retry_failed": True},
    dag=retry_dag,
)