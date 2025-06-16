import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "run_database_tests",
    "run_codebase_tests",
    "run_all_tests",
]


def _run_cmd(cmd: List[str], src_dir: Path, env_overrides: Dict[str, str]) -> Tuple[bool, str]:
    """Run *cmd* in *src_dir* with merged env; return (ok, combined_output)."""
    try:
        logger.info("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            cwd=src_dir,
            capture_output=True,
            text=True,
            env={**os.environ, **env_overrides},
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            logger.error("Command failed (exit %s): %s", result.returncode, output.strip())
            return False, output
        logger.debug(output.strip())
        return True, output
    except FileNotFoundError:
        logger.exception("Required executable not found in PATH.")
        return False, ""
    except Exception:
        logger.exception("Unexpected error while running subprocess.")
        return False, ""


def run_database_tests(src_dir: Path, *, dry_run: bool = False) -> Dict[str, str]:
    """Apply migrations (or preview) and execute pgTAP tests.

    Returns a dict with at least a ``status`` key (success|failed|pending_changes).
    """

    db_pass = os.getenv("DB_PASSWORD")
    if not db_pass:
        logger.error("Environment variable DB_PASSWORD is not set; cannot test database.")
        return {"status": "failed"}

    env_extra = {
        "SUPABASE_DB_PASSWORD": db_pass,
    }

    # 1) supabase db push (or --dry-run)
    push_cmd: List[str] = ["npx", "supabase", "db", "push"]
    if dry_run:
        push_cmd.append("--dry-run")

    ok, push_out = _run_cmd(push_cmd, src_dir, env_extra)
    if not ok:
        return {"status": "failed"}

    if dry_run:
        up_to_date = "Remote database is up to date." in push_out
        if up_to_date:
            logger.info("Database is already up-to-date (dry-run).")
            return {"status": "success", "dry_run": "true"}
        logger.warning("Database changes are pending (dry-run).")
        return {"status": "pending_changes", "dry_run": "true"}

    # 2) supabase test db --linked
    test_cmd: List[str] = ["npx", "supabase", "test", "db", "--linked"]

    ok, test_out = _run_cmd(test_cmd, src_dir, env_extra)
    if not ok:
        return {"status": "failed"}

    tests_pass = "Result: PASS" in test_out and "All tests successful." in test_out
    if tests_pass:
        logger.info("Database tests passed successfully.")
        return {"status": "success"}

    logger.error("Database tests failed. Review pgTAP output for details.")
    return {"status": "failed"}


def run_codebase_tests(src_dir: Path, *, dry_run: bool = False) -> Dict[str, str]:
    """Execute pytest test-suite.

    Looks for a top-level ``tests`` directory next to the project root (parent of
    ``src_dir``). Falls back to cwd discovery if not found.
    """

    project_root = src_dir.parent
    tests_path = project_root / "tests"

    if dry_run:
        location = str(tests_path) if tests_path.exists() else str(project_root)
        logger.info("DRY RUN: Would execute pytest in %s", location)
        return {"status": "dry_run"}

    if tests_path.exists():
        cmd = [sys.executable, "-m", "pytest", "-q", str(tests_path)]
        cwd = project_root
    else:
        # default discovery from project root
        cmd = [sys.executable, "-m", "pytest", "-q"]
        cwd = project_root

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, text=True)

    if result.returncode == 0:
        logger.info("Codebase tests passed successfully.")
        return {"status": "success"}

    logger.error("Codebase tests failed (exit %s).", result.returncode)
    return {"status": "failed"}


def run_all_tests(src_dir: Path, *, dry_run: bool = False) -> Dict[str, Dict[str, str]]:
    """Run database + codebase tests and return combined dict."""

    result = {
        "status": "success",
        "tests": {
            "database": run_database_tests(src_dir, dry_run=dry_run),
            "codebase": run_codebase_tests(src_dir, dry_run=dry_run),
        },
    }

    if any(t["status"] != "success" for t in result["tests"].values() if t):
        result["status"] = "failed"

    return result 