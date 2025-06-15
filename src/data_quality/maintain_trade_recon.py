from __future__ import annotations

"""Utility script to keep the trade_recon table in sync and up-to-date.

This is invoked from Airflow and can be executed manually via CLI.  It wraps
common helper functions:

* refresh_all_account_ids – refresh materialized view + upsert new accounts
* update_all_stats          – recompute trade_recon stats for every account

Both helpers rely exclusively on database‐side logic (materialized view +
`update_trade_recon_stats()` PL/pgSQL function) so they are fast and safe.
"""

import logging
from utils.database import get_db_manager

logger = logging.getLogger(__name__)

db_manager = get_db_manager()


def refresh_all_account_ids() -> None:
    """Refresh materialised view and insert any new account IDs into trade_recon."""

    with db_manager.model_db.get_connection() as conn:
        with conn.cursor() as cur:
            # Refresh materialised view (try concurrent first, fall back to regular)
            logger.info("Refreshing mv_all_account_ids …")
            try:
                cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_all_account_ids")
                logger.info("Materialized view refreshed successfully (concurrent mode)")
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Concurrent refresh failed: {error_msg}")
                
                # If it's a concurrent refresh issue, fall back to regular refresh
                if "concurrently" in error_msg.lower() or "ObjectNotInPrerequisiteState" in str(type(e)):
                    logger.info("Falling back to non-concurrent refresh")
                    cur.execute("REFRESH MATERIALIZED VIEW prop_trading_model.mv_all_account_ids")
                    logger.info("Materialized view refreshed successfully (non-concurrent mode)")
                else:
                    # Re-raise if it's a different error
                    raise

            logger.info("Inserting new account_ids into trade_recon …")
            cur.execute(
                """
                INSERT INTO prop_trading_model.trade_recon (account_id)
                SELECT account_id
                FROM prop_trading_model.mv_all_account_ids
                ON CONFLICT DO NOTHING
                """
            )

            # Recompute stats for *all* accounts (the SQL function handles upsert)
            logger.info("Updating stats for every account …")
            cur.execute(
                """
                SELECT prop_trading_model.update_trade_recon_stats(account_id)
                FROM   prop_trading_model.trade_recon
                """
            )

    logger.info("Trade recon maintenance finished")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    refresh_all_account_ids() 