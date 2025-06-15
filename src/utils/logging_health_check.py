"""
Health check module for logging infrastructure.
Verifies that logging is properly configured and working.
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple

from .logging_config import (
    setup_logging,
    get_logger,
    set_correlation_id,
    LoggingContext,
    log_metrics,
)


class LoggingHealthChecker:
    """Performs health checks on the logging infrastructure."""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.test_results = []

    def check_basic_logging(self) -> Tuple[bool, str]:
        """Test basic logging functionality."""
        try:
            test_logger = get_logger("health_check.basic")
            test_logger.info("Basic logging test")
            test_logger.debug("Debug level test")
            test_logger.warning("Warning level test")
            test_logger.error("Error level test")
            return True, "Basic logging working"
        except Exception as e:
            return False, f"Basic logging failed: {str(e)}"

    def check_structured_logging(self) -> Tuple[bool, str]:
        """Test structured logging with JSON format."""
        try:
            test_logger = get_logger("health_check.structured")
            test_logger.info(
                "Structured logging test",
                test_field="value",
                nested_data={"key": "value", "number": 123},
                timestamp=datetime.utcnow().isoformat(),
            )
            return True, "Structured logging working"
        except Exception as e:
            return False, f"Structured logging failed: {str(e)}"

    def check_correlation_id(self) -> Tuple[bool, str]:
        """Test correlation ID functionality."""
        try:
            correlation_id = set_correlation_id()
            test_logger = get_logger("health_check.correlation")
            test_logger.info("Correlation ID test", correlation_id=correlation_id)

            # Verify correlation ID is maintained
            if correlation_id:
                return True, f"Correlation ID working: {correlation_id}"
            else:
                return False, "Correlation ID not generated"
        except Exception as e:
            return False, f"Correlation ID failed: {str(e)}"

    def check_context_management(self) -> Tuple[bool, str]:
        """Test logging context management."""
        try:
            test_logger = get_logger("health_check.context")

            with LoggingContext(user_id="test_user", operation="health_check"):
                test_logger.info("Context management test")

            return True, "Context management working"
        except Exception as e:
            return False, f"Context management failed: {str(e)}"

    def check_file_rotation(self) -> Tuple[bool, str]:
        """Test log file rotation."""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Setup logging with small rotation size
                setup_logging(
                    log_dir=temp_dir,
                    log_file="rotation_test",
                    enable_rotation=True,
                    max_bytes=1024,  # 1KB for testing
                    backup_count=3,
                )

                test_logger = get_logger("health_check.rotation")

                # Write enough data to trigger rotation
                for i in range(100):
                    test_logger.info(f"Rotation test message {i}" * 10)

                # Check if rotation files were created
                log_files = list(Path(temp_dir).glob("rotation_test.log*"))
                if len(log_files) > 1:
                    return True, f"Log rotation working: {len(log_files)} files created"
                else:
                    return False, "Log rotation not triggered"

        except Exception as e:
            return False, f"Log rotation failed: {str(e)}"

    def check_performance_metrics(self) -> Tuple[bool, str]:
        """Test performance metrics logging."""
        try:
            test_logger = get_logger("health_check.metrics")

            metrics = {"test_metric": 123.45, "test_counter": 1000, "test_gauge": 0.75}

            log_metrics(
                logger=test_logger,
                operation="health_check",
                metrics=metrics,
                status="test",
            )

            return True, "Performance metrics logging working"
        except Exception as e:
            return False, f"Performance metrics failed: {str(e)}"

    def check_json_format(self) -> Tuple[bool, str]:
        """Test JSON log format."""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+", suffix=".log", delete=False
            ) as tmp:
                tmp_path = tmp.name

            try:
                # Setup logging with JSON format to temp file
                setup_logging(
                    log_file=Path(tmp_path).stem,
                    log_dir=Path(tmp_path).parent,
                    enable_json=True,
                    enable_rotation=False,
                )

                test_logger = get_logger("health_check.json")
                test_logger.info("JSON format test", test_data={"key": "value"})

                # Read and parse the log file
                with open(tmp_path, "r") as f:
                    for line in f:
                        if line.strip():
                            try:
                                json.loads(line)
                            except json.JSONDecodeError:
                                return False, f"Invalid JSON in log: {line}"

                return True, "JSON format validation passed"

            finally:
                # Cleanup
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            return False, f"JSON format check failed: {str(e)}"

    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks and return results."""
        checks = [
            ("basic_logging", self.check_basic_logging),
            ("structured_logging", self.check_structured_logging),
            ("correlation_id", self.check_correlation_id),
            ("context_management", self.check_context_management),
            ("file_rotation", self.check_file_rotation),
            ("performance_metrics", self.check_performance_metrics),
            ("json_format", self.check_json_format),
        ]

        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
            "summary": {"total": len(checks), "passed": 0, "failed": 0},
        }

        for check_name, check_func in checks:
            try:
                passed, message = check_func()
                results["checks"][check_name] = {"passed": passed, "message": message}
                if passed:
                    results["summary"]["passed"] += 1
                else:
                    results["summary"]["failed"] += 1

            except Exception as e:
                results["checks"][check_name] = {
                    "passed": False,
                    "message": f"Check failed with exception: {str(e)}",
                }
                results["summary"]["failed"] += 1

        results["healthy"] = results["summary"]["failed"] == 0

        # Log the results
        self.logger.info(
            "Logging health check completed",
            healthy=results["healthy"],
            passed=results["summary"]["passed"],
            failed=results["summary"]["failed"],
        )

        return results


def main():
    """Run logging health checks."""
    print("Running logging infrastructure health checks...")
    print("-" * 60)

    # Setup basic logging for the health check
    setup_logging(log_level="DEBUG")

    checker = LoggingHealthChecker()
    results = checker.run_all_checks()

    # Print results
    print(f"\nHealth Check Results - {results['timestamp']}")
    print("-" * 60)

    for check_name, check_result in results["checks"].items():
        status = "✓ PASS" if check_result["passed"] else "✗ FAIL"
        print(f"{status} {check_name:20} - {check_result['message']}")

    print("-" * 60)
    print(
        f"Summary: {results['summary']['passed']}/{results['summary']['total']} checks passed"
    )
    print(f"Overall Status: {'HEALTHY' if results['healthy'] else 'UNHEALTHY'}")

    # Return exit code based on health
    return 0 if results["healthy"] else 1


if __name__ == "__main__":
    exit(main())
