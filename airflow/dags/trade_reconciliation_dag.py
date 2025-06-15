from __future__ import annotations

"""DAG that maintains and reconciles trade data integrity every night.

Runs at 23:00 America/New_York by default (cron: ``0 23 * * *``) and performs:

1. `maintain_trade_recon_table` – refresh materialized view, upsert new accounts,
   recompute stats, _and_ fix null account_ids via `fix_all_null_account_ids()`.
2. `run_reconciliation`         – reconcile each account; by default skips
   previously-failed accounts unless the DAG parameter *retry_failed* is set.

A second DAG *trade_reconciliation_retry* can be triggered manually to include
previously failed accounts.
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.timetables.trigger import CronTriggerTimetable

# Airflow <-> project modules are imported lazily inside callables to avoid
# heavy imports during DAG-bagging.

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
    """Maintenance wrapper executed by Airflow."""
    import subprocess
    from pathlib import Path
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent
    
    # Run maintenance script using uv
    maintenance_script = """
from src.data_quality.maintain_trade_recon import refresh_all_account_ids
from src.data_quality.trade_reconciliation import fix_all_null_account_ids

fix_results = fix_all_null_account_ids()
print(f"[trade_recon] Null-account_id fix results → {fix_results}")

refresh_all_account_ids()
"""
    
    # Write script to temp file
    script_file = project_root / "temp_maintain_trade_recon.py"
    with open(script_file, 'w') as f:
        f.write(maintenance_script)
    
    try:
        # Execute using uv run
        result = subprocess.run(
            ["uv", "run", "--env-file", ".env", "python", str(script_file)],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise Exception(f"Maintenance failed: {result.stderr}")
        
        print(result.stdout)
    finally:
        # Clean up temp file
        if script_file.exists():
            script_file.unlink()


def run_reconciliation(retry_failed: bool = False, **_):
    """Run the main reconciliation job."""
    import subprocess
    from pathlib import Path
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent
    
    # Run reconciliation script using uv
    reconciliation_script = f"""
from src.data_quality.trade_reconciliation import reconcile_all_mismatched_accounts

summary = reconcile_all_mismatched_accounts(retry_failed={retry_failed})
print(f"[trade_recon] Reconciliation summary → {{summary}}")

if summary["failed"] > summary["total_processed"] * 0.1:
    raise RuntimeError(
        f"High failure rate: {{summary['failed']}}/{{summary['total_processed']}}"
    )
"""
    
    # Write script to temp file
    script_file = project_root / "temp_run_reconciliation.py"
    with open(script_file, 'w') as f:
        f.write(reconciliation_script)
    
    try:
        # Execute using uv run
        result = subprocess.run(
            ["uv", "run", "--env-file", ".env", "python", str(script_file)],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise Exception(f"Reconciliation failed: {result.stderr}")
        
        print(result.stdout)
    finally:
        # Clean up temp file
        if script_file.exists():
            script_file.unlink()

# ---------------------------------------------------------------------------
# Primary nightly DAG (skips previously failed accounts)
# ---------------------------------------------------------------------------

dag = DAG(
    "trade_reconciliation",
    default_args=DEFAULT_ARGS,
    description="Nightly trade reconciliation & maintenance",
    schedule=CronTriggerTimetable(
        "0 23 * * *",
        timezone="America/New_York"
    ),
    catchup=False,
    max_active_runs=1,
)

maintain_task = PythonOperator(
    task_id="maintain_trade_recon_table",
    python_callable=maintain_trade_recon_table,
    dag=dag,
)

reconcile_task = PythonOperator(
    task_id="run_reconciliation",
    python_callable=run_reconciliation,
    op_kwargs={"retry_failed": False},
    dag=dag,
)

maintain_task >> reconcile_task

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