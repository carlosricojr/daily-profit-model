"""
Utility to discover active logins from existing data sources for efficient account ingestion.
This allows us to fetch only accounts that have actual data instead of all ~1M historical accounts.
"""

import os
import sys
from datetime import datetime, date
from typing import List, Set, Optional
import argparse

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ..utils.database import DatabaseManager
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class ActiveLoginDiscoverer:
    """Discovers active logins from existing data sources."""

    def __init__(self):
        """Initialize the login discoverer."""
        self.db_manager = DatabaseManager()

    def discover_logins_from_date_range(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_activity_threshold: int = 1,
    ) -> Set[str]:
        """
        Discover active logins from data sources within a date range.

        Args:
            start_date: Start date for discovery (optional)
            end_date: End date for discovery (optional)
            min_activity_threshold: Minimum number of records to consider login active

        Returns:
            Set of active login IDs
        """
        logger.info(f"Discovering active logins from {start_date} to {end_date}")

        active_logins = set()

        # Build date filter clause if dates provided
        date_filter = ""
        params = []
        if start_date and end_date:
            date_filter = "WHERE date BETWEEN %s AND %s"
            params = [start_date, end_date]
        elif start_date:
            date_filter = "WHERE date >= %s"
            params = [start_date]
        elif end_date:
            date_filter = "WHERE date <= %s"
            params = [end_date]

        # 1. Check daily metrics (most reliable source)
        try:
            query = f"""
                SELECT login, COUNT(*) as activity_count
                FROM prop_trading_model.raw_metrics_daily 
                {date_filter}
                GROUP BY login
                HAVING COUNT(*) >= %s
            """

            results = self.db_manager.model_db.fetch_all(
                query, params + [min_activity_threshold]
            )

            for row in results:
                active_logins.add(row["login"])

            logger.info(f"Found {len(active_logins)} active logins from daily metrics")

        except Exception as e:
            logger.warning(f"Could not query daily metrics: {e}")

        # 2. Check hourly metrics if available
        try:
            query = f"""
                SELECT login, COUNT(*) as activity_count
                FROM prop_trading_model.raw_metrics_hourly 
                {date_filter}
                GROUP BY login
                HAVING COUNT(*) >= %s
            """

            results = self.db_manager.model_db.fetch_all(
                query, params + [min_activity_threshold]
            )

            hourly_logins = set(row["login"] for row in results)
            active_logins.update(hourly_logins)

            logger.info(
                f"Added {len(hourly_logins - active_logins)} new logins from hourly metrics"
            )

        except Exception as e:
            logger.warning(f"Could not query hourly metrics: {e}")

        # 3. Check trades data if available
        try:
            # Adjust date filter for trades (uses trade_date column)
            trade_date_filter = (
                date_filter.replace("date", "trade_date") if date_filter else ""
            )

            query = f"""
                SELECT login, COUNT(*) as activity_count
                FROM prop_trading_model.raw_trades_closed 
                {trade_date_filter}
                GROUP BY login
                HAVING COUNT(*) >= %s
            """

            results = self.db_manager.model_db.fetch_all(
                query, params + [min_activity_threshold]
            )

            trade_logins = set(row["login"] for row in results)
            new_trade_logins = trade_logins - active_logins
            active_logins.update(trade_logins)

            logger.info(f"Added {len(new_trade_logins)} new logins from trades data")

        except Exception as e:
            logger.warning(f"Could not query trades data: {e}")

        # 4. Check staging snapshots if available
        try:
            query = f"""
                SELECT login, COUNT(*) as activity_count
                FROM prop_trading_model.stg_accounts_daily_snapshots 
                {date_filter}
                GROUP BY login
                HAVING COUNT(*) >= %s
            """

            results = self.db_manager.model_db.fetch_all(
                query, params + [min_activity_threshold]
            )

            staging_logins = set(row["login"] for row in results)
            new_staging_logins = staging_logins - active_logins
            active_logins.update(staging_logins)

            logger.info(f"Added {len(new_staging_logins)} new logins from staging data")

        except Exception as e:
            logger.warning(f"Could not query staging data: {e}")

        logger.info(f"Total discovered active logins: {len(active_logins)}")
        return active_logins

    def discover_logins_from_existing_accounts(
        self, days_back: int = 30, min_activity_threshold: int = 1
    ) -> Set[str]:
        """
        Discover logins from recently updated accounts.

        Args:
            days_back: Number of days to look back for account updates
            min_activity_threshold: Not used here, kept for consistency

        Returns:
            Set of login IDs from recently updated accounts
        """
        logger.info(
            f"Discovering logins from accounts updated in last {days_back} days"
        )

        try:
            query = """
                SELECT DISTINCT login
                FROM prop_trading_model.raw_accounts_data 
                WHERE updated_at >= CURRENT_DATE - INTERVAL '%s days'
                   OR ingestion_timestamp >= CURRENT_DATE - INTERVAL '%s days'
            """

            results = self.db_manager.model_db.fetch_all(query, [days_back, days_back])
            logins = set(row["login"] for row in results)

            logger.info(f"Found {len(logins)} logins from recently updated accounts")
            return logins

        except Exception as e:
            logger.warning(f"Could not query accounts data: {e}")
            return set()

    def get_active_logins_for_ingestion(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        include_recent_accounts: bool = True,
        min_activity_threshold: int = 1,
    ) -> List[str]:
        """
        Get the optimal list of active logins for account ingestion.

        Args:
            start_date: Start date for discovery
            end_date: End date for discovery
            include_recent_accounts: Whether to include recently updated accounts
            min_activity_threshold: Minimum activity level to consider login active

        Returns:
            List of active login IDs
        """
        all_logins = set()

        # Get logins from data sources within date range
        if start_date or end_date:
            data_logins = self.discover_logins_from_date_range(
                start_date=start_date,
                end_date=end_date,
                min_activity_threshold=min_activity_threshold,
            )
            all_logins.update(data_logins)

        # Optionally include recently updated accounts
        if include_recent_accounts:
            recent_logins = self.discover_logins_from_existing_accounts()
            all_logins.update(recent_logins)

        # Convert to sorted list for consistent output
        active_logins = sorted(list(all_logins))

        logger.info(f"Final active logins count: {len(active_logins)}")
        return active_logins

    def close(self):
        """Clean up resources."""
        if hasattr(self, "db_manager"):
            self.db_manager.close()


def main():
    """Command-line interface for discovering active logins."""
    parser = argparse.ArgumentParser(
        description="Discover active logins for efficient account ingestion"
    )
    parser.add_argument(
        "--start-date", type=str, help="Start date (YYYY-MM-DD) for login discovery"
    )
    parser.add_argument(
        "--end-date", type=str, help="End date (YYYY-MM-DD) for login discovery"
    )
    parser.add_argument(
        "--min-activity",
        type=int,
        default=1,
        help="Minimum activity threshold (default: 1)",
    )
    parser.add_argument(
        "--no-recent",
        action="store_true",
        help="Do not include recently updated accounts",
    )
    parser.add_argument(
        "--output-file", type=str, help="Output file to save login list (one per line)"
    )
    parser.add_argument(
        "--output-format",
        choices=["list", "comma"],
        default="list",
        help="Output format: list (one per line) or comma-separated",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    from utils.logging_config import setup_logging

    setup_logging(log_level=args.log_level, log_file="discover_active_logins")

    # Parse dates
    start_date = None
    end_date = None

    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(
                f"Invalid start date format: {args.start_date}. Use YYYY-MM-DD"
            )
            sys.exit(1)

    if args.end_date:
        try:
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid end date format: {args.end_date}. Use YYYY-MM-DD")
            sys.exit(1)

    # Discover active logins
    discoverer = ActiveLoginDiscoverer()

    try:
        active_logins = discoverer.get_active_logins_for_ingestion(
            start_date=start_date,
            end_date=end_date,
            include_recent_accounts=not args.no_recent,
            min_activity_threshold=args.min_activity,
        )

        # Output results
        if args.output_file:
            with open(args.output_file, "w") as f:
                if args.output_format == "comma":
                    f.write(",".join(active_logins))
                else:
                    for login in active_logins:
                        f.write(f"{login}\n")
            logger.info(f"Active logins saved to {args.output_file}")
        else:
            if args.output_format == "comma":
                print(",".join(active_logins))
            else:
                for login in active_logins:
                    print(login)

        logger.info(f"Discovery complete. Found {len(active_logins)} active logins.")

    finally:
        discoverer.close()


if __name__ == "__main__":
    main()
