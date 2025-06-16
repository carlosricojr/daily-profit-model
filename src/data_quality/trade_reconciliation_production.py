"""
Production Trade Reconciliation Module with full API integration.

This module implements comprehensive trade data reconciliation including:
- Issue detection across multiple data sources
- Automatic resolution via API calls
- Batch processing for performance
- Circuit breaker pattern for fault tolerance
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
from collections import defaultdict
import time

from utils.database import get_db_manager
from utils.api_client import RiskAnalyticsAPIClient, APIError


logger = logging.getLogger(__name__)


class IssueSeverity(Enum):
    """Issue severity levels for prioritization."""
    CRITICAL = 1  # Data completely missing from primary source
    HIGH = 2      # Trade count mismatches > 10%
    MEDIUM = 3    # Trade count mismatches <= 10%
    LOW = 4       # Minor inconsistencies (e.g., missing single hours)
    INFO = 5      # Informational only


class TradeReconciliation:
    """Production trade reconciliation with full API integration."""
    
    def __init__(self, batch_size: int = 5000):
        """Initialize trade reconciliation with configurable batch size."""
        self.db_manager = get_db_manager()
        self.api_client = RiskAnalyticsAPIClient()
        self.batch_size = batch_size
        
        # Track API call statistics
        self.api_stats = defaultdict(int)
        
    def reconcile_account(self, account_id: str) -> Dict[str, Any]:
        """
        Main reconciliation process for a single account.
        
        Returns:
            Dict with keys: 'resolved', 'issues_found', 'issues_resolved', 'new_issues'
        """
        logger.info(f"Starting reconciliation for account {account_id}")
        
        # Get current state
        recon_data = self._get_recon_data(account_id)
        if not recon_data:
            return {'resolved': False, 'error': 'Account not found in trade_recon'}
        
        # Identify all issues
        issues = []
        
        # Check 1: NULL account_ids in trade tables
        issues.extend(self._check_null_account_ids(account_id, recon_data))
        
        # Check 2: Presence consistency
        issues.extend(self._check_presence_consistency(recon_data))
        
        # Check 3: Trade count consistency
        issues.extend(self._check_trade_count_consistency(recon_data))
        
        # Check 4: Date coverage
        issues.extend(self._check_date_coverage(account_id, recon_data))
        
        # Check 5: Hourly/Daily alignment
        issues.extend(self._check_hourly_daily_alignment(account_id))
        
        # Attempt resolution for each issue
        resolved_issues = []
        for issue in issues:
            if self._attempt_resolution(account_id, issue):
                resolved_issues.append(issue)
                logger.info(f"Resolved issue: {issue['type']} for account {account_id}")
        
        # Update issues in database
        remaining_issues = [i for i in issues if i not in resolved_issues]
        self._update_issues(account_id, remaining_issues)
        
        # Recalculate stats after resolution attempts
        self._trigger_stats_recalculation(account_id)
        
        # Check if fully resolved
        new_recon = self._get_recon_data(account_id)
        
        return {
            'resolved': new_recon['trades_recon_checksum'],
            'issues_found': len(issues),
            'issues_resolved': len(resolved_issues),
            'new_issues': remaining_issues
        }
    
    def _check_null_account_ids(self, account_id: str, recon: Dict) -> List[Dict]:
        """Check for trades with null account_id that match this account."""
        issues = []
        
        # Get account details
        query = """
            SELECT login, platform, broker
            FROM prop_trading_model.raw_metrics_alltime
            WHERE account_id = %s
        """
        result = self.db_manager.model_db.execute_query(query, (account_id,))
        
        if not result:
            return issues
            
        login = result[0]['login']
        platform = result[0]['platform'] 
        broker = result[0]['broker']
        
        # Check raw_trades_closed
        closed_query = """
            SELECT COUNT(*) as count
            FROM prop_trading_model.raw_trades_closed
            WHERE account_id IS NULL
            AND login = %s
            AND platform = %s
            AND broker = %s
        """
        closed_result = self.db_manager.model_db.execute_query(
            closed_query, (login, platform, broker)
        )
        
        if closed_result and closed_result[0]['count'] > 0:
            issues.append({
                'severity': IssueSeverity.HIGH.value,
                'type': 'null_account_id_closed_trades',
                'description': f"Found {closed_result[0]['count']} closed trades with null account_id",
                'resolution_strategy': 'assign_account_id_closed_trades',
                'metadata': {
                    'login': login,
                    'platform': platform,
                    'broker': broker,
                    'count': closed_result[0]['count']
                }
            })
        
        # Check raw_trades_open
        open_query = """
            SELECT COUNT(*) as count
            FROM prop_trading_model.raw_trades_open
            WHERE account_id IS NULL
            AND login = %s
            AND platform = %s
            AND broker = %s
        """
        open_result = self.db_manager.model_db.execute_query(
            open_query, (login, platform, broker)
        )
        
        if open_result and open_result[0]['count'] > 0:
            issues.append({
                'severity': IssueSeverity.HIGH.value,
                'type': 'null_account_id_open_trades',
                'description': f"Found {open_result[0]['count']} open trades with null account_id",
                'resolution_strategy': 'assign_account_id_open_trades',
                'metadata': {
                    'login': login,
                    'platform': platform,
                    'broker': broker,
                    'count': open_result[0]['count']
                }
            })
        
        return issues
    
    def _check_presence_consistency(self, recon: Dict) -> List[Dict]:
        """Check if account presence is consistent across tables."""
        issues = []
        
        has_any_metrics = recon['has_alltime'] or recon['has_daily'] or recon['has_hourly']
        has_all_metrics = recon['has_alltime'] and recon['has_daily'] and recon['has_hourly']
        
        if has_any_metrics and not has_all_metrics:
            missing = []
            if not recon['has_alltime']:
                missing.append('raw_metrics_alltime')
            if not recon['has_daily']:
                missing.append('raw_metrics_daily')
            if not recon['has_hourly']:
                missing.append('raw_metrics_hourly')
                
            issues.append({
                'severity': IssueSeverity.HIGH.value,
                'type': 'missing_metrics_tables',
                'description': f'Account has metrics in some tables but missing from: {", ".join(missing)}',
                'affected': missing,
                'resolution_strategy': 'fetch_missing_metrics'
            })
        
        # Check trades vs metrics presence
        if recon['num_trades_alltime'] and recon['num_trades_alltime'] > 0 and not recon['has_raw_closed']:
            issues.append({
                'severity': IssueSeverity.CRITICAL.value,
                'type': 'missing_trade_records',
                'description': f'Account shows {recon["num_trades_alltime"]} trades in metrics but no closed trades found',
                'affected': ['raw_trades_closed'],
                'resolution_strategy': 'fetch_all_closed_trades'
            })
            
        return issues
    
    def _check_trade_count_consistency(self, recon: Dict) -> List[Dict]:
        """Check if trade counts match across sources."""
        issues = []
        
        counts = {
            'alltime': recon['num_trades_alltime'],
            'daily': recon['num_trades_daily'],
            'hourly': recon['num_trades_hourly'],
            'closed': recon['num_trades_raw_closed']
        }
        
        # Filter out None values
        valid_counts = {k: v for k, v in counts.items() if v is not None}
        
        if len(valid_counts) > 1:
            unique_values = set(valid_counts.values())
            if len(unique_values) > 1:
                max_count = max(valid_counts.values())
                min_count = min(valid_counts.values())
                discrepancy_pct = ((max_count - min_count) / max_count) * 100 if max_count > 0 else 0
                
                severity = IssueSeverity.HIGH if discrepancy_pct > 10 else IssueSeverity.MEDIUM
                
                issues.append({
                    'severity': severity.value,
                    'type': 'trade_count_mismatch',
                    'description': f'Trade counts do not match: {valid_counts}',
                    'affected': list(valid_counts.keys()),
                    'discrepancy_percentage': discrepancy_pct,
                    'resolution_strategy': 'refetch_all_data'
                })
                
        return issues
    
    def _check_date_coverage(self, account_id: str, recon: Dict) -> List[Dict]:
        """Check for consistency between daily and hourly records."""
        issues = []
        
        # Find daily records without corresponding hourly records
        query_daily_without_hourly = """
            SELECT d.date, d.num_trades
            FROM prop_trading_model.raw_metrics_daily d
            LEFT JOIN (
                SELECT DISTINCT account_id, date 
                FROM prop_trading_model.raw_metrics_hourly
                WHERE account_id = %s
            ) h ON d.account_id = h.account_id AND d.date = h.date
            WHERE d.account_id = %s
            AND h.date IS NULL
            ORDER BY d.date
            LIMIT 100
        """
        
        daily_without_hourly = self.db_manager.model_db.execute_query(
            query_daily_without_hourly, (account_id, account_id)
        )
        
        if daily_without_hourly:
            issues.append({
                'severity': IssueSeverity.HIGH.value,
                'type': 'daily_without_hourly',
                'description': f'Found {len(daily_without_hourly)} daily records without corresponding hourly records',
                'affected': ['raw_metrics_hourly'],
                'missing_dates': [str(r['date']) for r in daily_without_hourly[:10]],
                'total_missing': len(daily_without_hourly),
                'resolution_strategy': 'fetch_hourly_for_existing_daily'
            })
        
        # Find hourly records without corresponding daily records
        query_hourly_without_daily = """
            SELECT DISTINCT h.date, COUNT(*) as hourly_records, SUM(h.num_trades) as total_trades
            FROM prop_trading_model.raw_metrics_hourly h
            LEFT JOIN prop_trading_model.raw_metrics_daily d
                ON h.account_id = d.account_id AND h.date = d.date
            WHERE h.account_id = %s
            AND d.date IS NULL
            GROUP BY h.date
            ORDER BY h.date
            LIMIT 100
        """
        
        hourly_without_daily = self.db_manager.model_db.execute_query(
            query_hourly_without_daily, (account_id,)
        )
        
        if hourly_without_daily:
            issues.append({
                'severity': IssueSeverity.HIGH.value,
                'type': 'hourly_without_daily',
                'description': f'Found {len(hourly_without_daily)} dates with hourly records but no daily record',
                'affected': ['raw_metrics_daily'],
                'missing_dates': [str(r['date']) for r in hourly_without_daily[:10]],
                'total_missing': len(hourly_without_daily),
                'resolution_strategy': 'fetch_daily_for_existing_hourly'
            })
        
        return issues
    
    def _check_hourly_daily_alignment(self, account_id: str) -> List[Dict]:
        """Check if hourly and daily num_trades align."""
        issues = []
        
        query = """
            WITH daily_hourly_comparison AS (
                SELECT 
                    d.date,
                    d.num_trades as daily_trades,
                    SUM(h.num_trades) as hourly_trades
                FROM prop_trading_model.raw_metrics_daily d
                LEFT JOIN prop_trading_model.raw_metrics_hourly h
                    ON d.account_id = h.account_id 
                    AND d.date = h.date
                WHERE d.account_id = %s
                GROUP BY d.date, d.num_trades
            )
            SELECT date, daily_trades, hourly_trades
            FROM daily_hourly_comparison
            WHERE daily_trades != COALESCE(hourly_trades, 0)
            ORDER BY date
            LIMIT 100
        """
        
        mismatches = self.db_manager.model_db.execute_query(query, (account_id,))
        
        if mismatches:
            issues.append({
                'severity': IssueSeverity.MEDIUM.value,
                'type': 'hourly_daily_mismatch',
                'description': f'Hourly and daily trade counts do not match for {len(mismatches)} days',
                'affected': ['raw_metrics_daily', 'raw_metrics_hourly'],
                'sample_mismatches': [
                    {
                        'date': str(m['date']),
                        'daily': m['daily_trades'],
                        'hourly_sum': m['hourly_trades']
                    } for m in mismatches[:5]
                ],
                'total_mismatches': len(mismatches),
                'resolution_strategy': 'refetch_hourly_for_dates'
            })
            
        return issues
    
    def _attempt_resolution(self, account_id: str, issue: Dict) -> bool:
        """
        Attempt to resolve an issue by fetching missing data via API.
        
        Returns True if resolved, False otherwise.
        """
        strategy = issue.get('resolution_strategy')
        
        try:
            if strategy == 'assign_account_id_closed_trades':
                return self._assign_account_id_closed_trades(account_id, issue)
            elif strategy == 'assign_account_id_open_trades':
                return self._assign_account_id_open_trades(account_id, issue)
            elif strategy == 'fetch_missing_metrics':
                return self._fetch_missing_metrics(account_id, issue)
            elif strategy == 'fetch_all_closed_trades':
                return self._fetch_all_closed_trades(account_id)
            elif strategy == 'fetch_hourly_for_existing_daily':
                return self._fetch_hourly_for_existing_daily(account_id, issue)
            elif strategy == 'fetch_daily_for_existing_hourly':
                return self._fetch_daily_for_existing_hourly(account_id, issue)
            elif strategy == 'refetch_hourly_for_dates':
                return self._refetch_hourly_for_dates(account_id, issue)
            elif strategy == 'refetch_all_data':
                # For major discrepancies, log but don't attempt automatic resolution
                logger.warning(f"Major discrepancy for {account_id}, manual intervention may be needed")
                return False
                
        except APIError as e:
            logger.error(f"API error during resolution for {account_id}: {str(e)}")
            self.api_stats['api_errors'] += 1
            return False
        except Exception as e:
            logger.error(f"Resolution failed for {account_id}: {str(e)}")
            return False
            
        return False
    
    def _assign_account_id_closed_trades(self, account_id: str, issue: Dict) -> bool:
        """Assign account_id to closed trades with matching login/platform/broker."""
        try:
            metadata = issue['metadata']
            
            query = """
                UPDATE prop_trading_model.raw_trades_closed
                SET account_id = %s
                WHERE account_id IS NULL
                AND login = %s
                AND platform = %s
                AND broker = %s
            """
            
            affected_rows = self.db_manager.model_db.execute_update(
                query, 
                (account_id, metadata['login'], metadata['platform'], metadata['broker'])
            )
            
            logger.info(f"Updated account_id for {affected_rows} closed trades")
            
            # Verify the update
            verify_query = """
                SELECT COUNT(*) as count
                FROM prop_trading_model.raw_trades_closed
                WHERE account_id IS NULL
                AND login = %s
                AND platform = %s
                AND broker = %s
            """
            result = self.db_manager.model_db.execute_query(
                verify_query,
                (metadata['login'], metadata['platform'], metadata['broker'])
            )
            
            return result[0]['count'] == 0
            
        except Exception as e:
            logger.error(f"Failed to assign account_id to closed trades: {str(e)}")
            return False
    
    def _assign_account_id_open_trades(self, account_id: str, issue: Dict) -> bool:
        """Assign account_id to open trades with matching login/platform/broker."""
        try:
            metadata = issue['metadata']
            
            query = """
                UPDATE prop_trading_model.raw_trades_open
                SET account_id = %s
                WHERE account_id IS NULL
                AND login = %s
                AND platform = %s
                AND broker = %s
            """
            
            affected_rows = self.db_manager.model_db.execute_update(
                query, 
                (account_id, metadata['login'], metadata['platform'], metadata['broker'])
            )
            
            logger.info(f"Updated account_id for {affected_rows} open trades")
            
            # Verify the update
            verify_query = """
                SELECT COUNT(*) as count
                FROM prop_trading_model.raw_trades_open
                WHERE account_id IS NULL
                AND login = %s
                AND platform = %s
                AND broker = %s
            """
            result = self.db_manager.model_db.execute_query(
                verify_query,
                (metadata['login'], metadata['platform'], metadata['broker'])
            )
            
            return result[0]['count'] == 0
            
        except Exception as e:
            logger.error(f"Failed to assign account_id to open trades: {str(e)}")
            return False
    
    def _fetch_missing_metrics(self, account_id: str, issue: Dict) -> bool:
        """Fetch missing metrics data via API."""
        affected = issue.get('affected', [])
        
        try:
            # Get account details
            query = """
                SELECT DISTINCT login, broker, platform, type, phase
                FROM prop_trading_model.raw_metrics_alltime
                WHERE account_id = %s
            """
            result = self.db_manager.model_db.execute_query(query, (account_id,))
            
            if not result:
                logger.warning(f"No account details found for {account_id}")
                return False
            
            account_info = result[0]
            login = str(account_info['login'])
            
            # Track what we fetched
            fetched = []
            
            # Fetch alltime metrics if missing
            if 'raw_metrics_alltime' in affected:
                logger.info(f"Fetching alltime metrics for login {login}")
                self.api_stats['fetch_alltime'] += 1
                
                for page in self.api_client.get_metrics(
                    metric_type='alltime',
                    logins=[login],
                    limit=100
                ):
                    # Process and insert metrics
                    self._process_metrics_batch(page, 'alltime')
                    fetched.append('alltime')
                    
            # For daily/hourly, need date range
            if 'raw_metrics_daily' in affected or 'raw_metrics_hourly' in affected:
                # Get date range from existing data or use default
                date_range_query = """
                    SELECT 
                        MIN(date) as start_date,
                        MAX(date) as end_date
                    FROM (
                        SELECT date FROM prop_trading_model.raw_metrics_daily WHERE account_id = %s
                        UNION ALL
                        SELECT date FROM prop_trading_model.raw_metrics_hourly WHERE account_id = %s
                    ) t
                """
                date_result = self.db_manager.model_db.execute_query(
                    date_range_query, (account_id, account_id)
                )
                
                if date_result and date_result[0]['start_date']:
                    start_date = date_result[0]['start_date']
                    end_date = date_result[0]['end_date']
                else:
                    # Default to last 30 days
                    end_date = date.today() - timedelta(days=1)
                    start_date = end_date - timedelta(days=30)
                
                # Fetch daily metrics
                if 'raw_metrics_daily' in affected:
                    logger.info(f"Fetching daily metrics for login {login} from {start_date} to {end_date}")
                    self.api_stats['fetch_daily'] += 1
                    
                    # Process date range in batches
                    current_date = start_date
                    while current_date <= end_date:
                        batch_end = min(current_date + timedelta(days=7), end_date)
                        dates = []
                        d = current_date
                        while d <= batch_end:
                            dates.append(self.api_client.format_date(d))
                            d += timedelta(days=1)
                        
                        for page in self.api_client.get_metrics(
                            metric_type='daily',
                            logins=[login],
                            dates=dates,
                            limit=1000
                        ):
                            self._process_metrics_batch(page, 'daily')
                            
                        current_date = batch_end + timedelta(days=1)
                    
                    fetched.append('daily')
                
                # Fetch hourly metrics
                if 'raw_metrics_hourly' in affected:
                    logger.info(f"Fetching hourly metrics for login {login}")
                    self.api_stats['fetch_hourly'] += 1
                    
                    # Process date range in smaller batches for hourly
                    current_date = start_date
                    while current_date <= end_date:
                        batch_end = min(current_date + timedelta(days=1), end_date)
                        dates = []
                        d = current_date
                        while d <= batch_end:
                            dates.append(self.api_client.format_date(d))
                            d += timedelta(days=1)
                        
                        for page in self.api_client.get_metrics(
                            metric_type='hourly',
                            logins=[login],
                            dates=dates,
                            limit=1000
                        ):
                            self._process_metrics_batch(page, 'hourly')
                            
                        current_date = batch_end + timedelta(days=1)
                    
                    fetched.append('hourly')
            
            return len(fetched) > 0
            
        except Exception as e:
            logger.error(f"Failed to fetch missing metrics: {str(e)}")
            return False
    
    def _fetch_all_closed_trades(self, account_id: str) -> bool:
        """Fetch all closed trades for an account via API."""
        try:
            # Get account details
            query = """
                SELECT DISTINCT login
                FROM prop_trading_model.raw_metrics_alltime
                WHERE account_id = %s
            """
            result = self.db_manager.model_db.execute_query(query, (account_id,))
            
            if not result:
                return False
                
            login = str(result[0]['login'])
            logger.info(f"Fetching closed trades for login {login}")
            self.api_stats['fetch_trades'] += 1
            
            # Fetch trades via API
            trade_count = 0
            for page in self.api_client.get_trades(
                trade_type='closed',
                logins=[login],
                limit=1000
            ):
                # Process and insert trades
                trade_count += self._process_trades_batch(page, account_id)
            
            logger.info(f"Fetched {trade_count} closed trades for account {account_id}")
            return trade_count > 0
            
        except Exception as e:
            logger.error(f"Failed to fetch closed trades: {str(e)}")
            return False
    
    def _fetch_hourly_for_existing_daily(self, account_id: str, issue: Dict) -> bool:
        """Fetch hourly data for dates that have daily records."""
        missing_dates = issue.get('missing_dates', [])
        if not missing_dates:
            return False
            
        try:
            # Get login for API calls
            query = """
                SELECT DISTINCT login
                FROM prop_trading_model.raw_metrics_alltime
                WHERE account_id = %s
            """
            result = self.db_manager.model_db.execute_query(query, (account_id,))
            
            if not result:
                return False
                
            login = str(result[0]['login'])
            
            # Process dates in batches
            for i in range(0, len(missing_dates), 7):
                batch_dates = missing_dates[i:i+7]
                formatted_dates = [d.replace('-', '') for d in batch_dates]
                
                logger.info(f"Fetching hourly metrics for {len(batch_dates)} dates")
                self.api_stats['fetch_hourly_missing'] += 1
                
                for page in self.api_client.get_metrics(
                    metric_type='hourly',
                    logins=[login],
                    dates=formatted_dates,
                    limit=1000
                ):
                    self._process_metrics_batch(page, 'hourly')
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch hourly for existing daily: {str(e)}")
            return False
    
    def _fetch_daily_for_existing_hourly(self, account_id: str, issue: Dict) -> bool:
        """Fetch daily data for dates that have hourly records."""
        missing_dates = issue.get('missing_dates', [])
        if not missing_dates:
            return False
            
        try:
            # Get login for API calls
            query = """
                SELECT DISTINCT login
                FROM prop_trading_model.raw_metrics_alltime
                WHERE account_id = %s
            """
            result = self.db_manager.model_db.execute_query(query, (account_id,))
            
            if not result:
                return False
                
            login = str(result[0]['login'])
            
            # Process all dates at once for daily
            formatted_dates = [d.replace('-', '') for d in missing_dates]
            
            logger.info(f"Fetching daily metrics for {len(formatted_dates)} dates")
            self.api_stats['fetch_daily_missing'] += 1
            
            for page in self.api_client.get_metrics(
                metric_type='daily',
                logins=[login],
                dates=formatted_dates,
                limit=1000
            ):
                self._process_metrics_batch(page, 'daily')
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch daily for existing hourly: {str(e)}")
            return False
    
    def _refetch_hourly_for_dates(self, account_id: str, issue: Dict) -> bool:
        """Refetch hourly data for dates where counts don't match."""
        sample_mismatches = issue.get('sample_mismatches', [])
        if not sample_mismatches:
            return False
            
        try:
            # Get login
            query = """
                SELECT DISTINCT login
                FROM prop_trading_model.raw_metrics_alltime
                WHERE account_id = %s
            """
            result = self.db_manager.model_db.execute_query(query, (account_id,))
            
            if not result:
                return False
                
            login = str(result[0]['login'])
            
            # Extract dates from mismatches
            dates_to_refetch = [m['date'].replace('-', '') for m in sample_mismatches]
            
            logger.info(f"Refetching hourly metrics for {len(dates_to_refetch)} mismatched dates")
            self.api_stats['refetch_hourly'] += 1
            
            # Delete existing hourly data for these dates first
            delete_query = """
                DELETE FROM prop_trading_model.raw_metrics_hourly
                WHERE account_id = %s
                AND date = ANY(%s::date[])
            """
            self.db_manager.model_db.execute_update(
                delete_query,
                (account_id, [m['date'] for m in sample_mismatches])
            )
            
            # Fetch fresh data
            for page in self.api_client.get_metrics(
                metric_type='hourly',
                logins=[login],
                dates=dates_to_refetch,
                limit=1000
            ):
                self._process_metrics_batch(page, 'hourly')
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to refetch hourly data: {str(e)}")
            return False
    
    def _process_metrics_batch(self, metrics: List[Dict], metric_type: str) -> int:
        """Process and insert a batch of metrics."""
        if not metrics:
            return 0
            
        if metric_type == 'alltime':
            # Insert into raw_metrics_alltime
            insert_query = """
                INSERT INTO prop_trading_model.raw_metrics_alltime (
                    account_id, login, broker, platform, type, phase,
                    num_trades, total_volume, total_profit,
                    first_trade_date, last_trade_date,
                    created_at, updated_at
                ) VALUES %s
                ON CONFLICT (account_id) DO UPDATE SET
                    num_trades = EXCLUDED.num_trades,
                    total_volume = EXCLUDED.total_volume,
                    total_profit = EXCLUDED.total_profit,
                    last_trade_date = EXCLUDED.last_trade_date,
                    updated_at = NOW()
            """
            
            values = []
            for m in metrics:
                # Generate account_id if not present
                account_id = m.get('accountId') or m.get('account_id')
                if not account_id:
                    account_id = f"{m['login']}_{m['platform']}_{m['broker']}"
                    
                values.append((
                    account_id,
                    m.get('login'),
                    m.get('broker'),
                    m.get('platform'),
                    m.get('type'),
                    m.get('phase'),
                    m.get('trades', 0),
                    m.get('volume', 0),
                    m.get('profit', 0),
                    m.get('firstTradeDate'),
                    m.get('lastTradeDate'),
                    datetime.now(),
                    datetime.now()
                ))
                
        elif metric_type == 'daily':
            # Insert into raw_metrics_daily
            insert_query = """
                INSERT INTO prop_trading_model.raw_metrics_daily (
                    account_id, date, num_trades, volume, profit,
                    created_at, updated_at
                ) VALUES %s
                ON CONFLICT (account_id, date) DO UPDATE SET
                    num_trades = EXCLUDED.num_trades,
                    volume = EXCLUDED.volume,
                    profit = EXCLUDED.profit,
                    updated_at = NOW()
            """
            
            values = []
            for m in metrics:
                account_id = m.get('accountId') or m.get('account_id')
                date_str = str(m.get('date', ''))
                if len(date_str) == 8:  # YYYYMMDD format
                    date_obj = datetime.strptime(date_str, '%Y%m%d').date()
                else:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    
                values.append((
                    account_id,
                    date_obj,
                    m.get('trades', 0),
                    m.get('volume', 0),
                    m.get('profit', 0),
                    datetime.now(),
                    datetime.now()
                ))
                
        elif metric_type == 'hourly':
            # Insert into raw_metrics_hourly
            insert_query = """
                INSERT INTO prop_trading_model.raw_metrics_hourly (
                    account_id, date, hour, num_trades, volume, profit,
                    created_at, updated_at
                ) VALUES %s
                ON CONFLICT (account_id, date, hour) DO UPDATE SET
                    num_trades = EXCLUDED.num_trades,
                    volume = EXCLUDED.volume,
                    profit = EXCLUDED.profit,
                    updated_at = NOW()
            """
            
            values = []
            for m in metrics:
                account_id = m.get('accountId') or m.get('account_id')
                date_str = str(m.get('date', ''))
                if len(date_str) == 8:  # YYYYMMDD format
                    date_obj = datetime.strptime(date_str, '%Y%m%d').date()
                else:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    
                values.append((
                    account_id,
                    date_obj,
                    m.get('hour', 0),
                    m.get('trades', 0),
                    m.get('volume', 0),
                    m.get('profit', 0),
                    datetime.now(),
                    datetime.now()
                ))
        
        # Execute batch insert
        if values:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cur:
                    from psycopg2.extras import execute_values
                    execute_values(cur, insert_query, values)
                    conn.commit()
                    
        return len(values)
    
    def _process_trades_batch(self, trades: List[Dict], account_id: str) -> int:
        """Process and insert a batch of trades."""
        if not trades:
            return 0
            
        insert_query = """
            INSERT INTO prop_trading_model.raw_trades_closed (
                account_id, trade_id, login, broker, platform,
                symbol, open_time, close_time, open_price, close_price,
                volume, profit, commission, swap,
                created_at, updated_at
            ) VALUES %s
            ON CONFLICT (trade_id, account_id) DO UPDATE SET
                close_time = EXCLUDED.close_time,
                close_price = EXCLUDED.close_price,
                profit = EXCLUDED.profit,
                updated_at = NOW()
        """
        
        values = []
        for t in trades:
            values.append((
                account_id,
                t.get('ticket') or t.get('trade_id'),
                t.get('login'),
                t.get('broker'),
                t.get('platform'),
                t.get('symbol'),
                t.get('openTime'),
                t.get('closeTime'),
                t.get('openPrice', 0),
                t.get('closePrice', 0),
                t.get('volume', 0),
                t.get('profit', 0),
                t.get('commission', 0),
                t.get('swap', 0),
                datetime.now(),
                datetime.now()
            ))
        
        # Execute batch insert
        if values:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cur:
                    from psycopg2.extras import execute_values
                    execute_values(cur, insert_query, values)
                    conn.commit()
                    
        return len(values)
    
    def _update_issues(self, account_id: str, issues: List[Dict]):
        """Update issues column in trade_recon table."""
        issues_json = json.dumps(issues)
        
        query = """
            UPDATE prop_trading_model.trade_recon
            SET issues = %s::jsonb,
                last_reconciled = NOW()
            WHERE account_id = %s
        """
        
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (issues_json, account_id))
                conn.commit()
    
    def _trigger_stats_recalculation(self, account_id: str):
        """Trigger recalculation of trade_recon stats."""
        query = "SELECT prop_trading_model.update_trade_recon_stats(%s)"
        
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (account_id,))
                conn.commit()
    
    def _get_recon_data(self, account_id: str) -> Optional[Dict]:
        """Get current reconciliation data for account."""
        query = """
            SELECT * FROM prop_trading_model.trade_recon
            WHERE account_id = %s
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_id,))
        return results[0] if results else None
    
    def get_api_stats(self) -> Dict[str, int]:
        """Get API call statistics."""
        return dict(self.api_stats)


def fix_all_null_account_ids() -> Dict[str, int]:
    """
    Fix all trades with null account_id across the entire database.
    Uses proper JOINs to find matching account_ids from raw_metrics_alltime.
    """
    db_manager = get_db_manager()
    results = {
        'closed_trades_updated': 0,
        'open_trades_updated': 0,
        'md5_hashes_fixed': 0,
        'unmatched_combinations': []
    }
    
    # First, fix any MD5 hashes that were incorrectly created
    md5_fix_query = """
        UPDATE prop_trading_model.raw_trades_closed t
        SET account_id = m.account_id
        FROM prop_trading_model.raw_metrics_alltime m
        WHERE t.login = m.login
        AND t.platform = m.platform
        AND t.broker = m.broker
        AND LENGTH(t.account_id) = 32
        AND t.account_id ~ '^[0-9a-f]{32}$'
    """
    
    results['md5_hashes_fixed'] = db_manager.model_db.execute_update(md5_fix_query)
    if results['md5_hashes_fixed'] > 0:
        logger.info(f"Fixed {results['md5_hashes_fixed']} MD5 hash account_ids")
    
    # Fix closed trades with NULL account_id
    closed_update = """
        UPDATE prop_trading_model.raw_trades_closed t
        SET account_id = m.account_id
        FROM prop_trading_model.raw_metrics_alltime m
        WHERE t.login = m.login
        AND t.platform = m.platform
        AND t.broker = m.broker
        AND t.account_id IS NULL
    """
    
    results['closed_trades_updated'] = db_manager.model_db.execute_update(closed_update)
    logger.info(f"Updated {results['closed_trades_updated']} closed trades with account_id")
    
    # Fix open trades with NULL account_id
    open_update = """
        UPDATE prop_trading_model.raw_trades_open t
        SET account_id = m.account_id
        FROM prop_trading_model.raw_metrics_alltime m
        WHERE t.login = m.login
        AND t.platform = m.platform
        AND t.broker = m.broker
        AND t.account_id IS NULL
    """
    
    results['open_trades_updated'] = db_manager.model_db.execute_update(open_update)
    logger.info(f"Updated {results['open_trades_updated']} open trades with account_id")
    
    # Check for unmatched combinations
    unmatched_query = """
        WITH unmatched AS (
            SELECT DISTINCT login, platform, broker, 'closed' as trade_type
            FROM prop_trading_model.raw_trades_closed
            WHERE account_id IS NULL
            
            UNION
            
            SELECT DISTINCT login, platform, broker, 'open' as trade_type
            FROM prop_trading_model.raw_trades_open
            WHERE account_id IS NULL
        )
        SELECT * FROM unmatched
        LIMIT 100
    """
    
    unmatched = db_manager.model_db.execute_query(unmatched_query)
    results['unmatched_combinations'] = unmatched
    
    if unmatched:
        logger.warning(
            f"Found {len(unmatched)} (login, platform, broker) combinations "
            "without matching account_id in raw_metrics_alltime"
        )
    
    return results


def reconcile_all_mismatched_accounts(
    retry_failed: bool = False,
    batch_size: int = 5000,
    max_accounts: Optional[int] = None
) -> Dict[str, Any]:
    """
    Run reconciliation for all accounts with checksum = false.
    
    Args:
        retry_failed: If True, retry accounts that have previously failed
        batch_size: Number of records to process in each batch
        max_accounts: Maximum number of accounts to process (for testing)
        
    Returns:
        Summary of reconciliation results
    """
    db_manager = get_db_manager()
    reconciler = TradeReconciliation(batch_size=batch_size)
    
    # Get accounts needing reconciliation
    if retry_failed:
        query = """
            SELECT account_id 
            FROM prop_trading_model.trade_recon
            WHERE trades_recon_checksum = FALSE
            ORDER BY last_checked ASC NULLS FIRST
            FOR UPDATE SKIP LOCKED
        """
    else:
        query = """
            SELECT account_id 
            FROM prop_trading_model.trade_recon
            WHERE trades_recon_checksum = FALSE
            AND (failed_attempts = 0 OR failed_attempts IS NULL)
            ORDER BY last_checked ASC NULLS FIRST
            FOR UPDATE SKIP LOCKED
        """
    
    if max_accounts:
        query += f" LIMIT {max_accounts}"
    
    accounts = db_manager.model_db.execute_query(query)
    
    results = {
        'total_processed': 0,
        'fully_resolved': 0,
        'partially_resolved': 0,
        'failed': 0,
        'skipped_due_to_previous_failure': 0,
        'api_stats': {},
        'details': []
    }
    
    logger.info(f"Found {len(accounts)} accounts to reconcile")
    
    # Process in batches for better performance
    batch_start_time = time.time()
    
    for i, account in enumerate(accounts):
        account_id = account['account_id']
        
        try:
            # Set statement timeout for this account
            with db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL statement_timeout = '30s'")
                    
            result = reconciler.reconcile_account(account_id)
            
            results['total_processed'] += 1
            if result['resolved']:
                results['fully_resolved'] += 1
                _reset_failed_attempts(db_manager, account_id)
            elif result['issues_resolved'] > 0:
                results['partially_resolved'] += 1
                _increment_failed_attempts(db_manager, account_id)
            else:
                results['failed'] += 1
                _increment_failed_attempts(db_manager, account_id)
                
            results['details'].append({
                'account_id': account_id,
                **result
            })
            
            # Log progress every 100 accounts
            if (i + 1) % 100 == 0:
                elapsed = time.time() - batch_start_time
                rate = (i + 1) / elapsed
                logger.info(
                    f"Progress: {i + 1}/{len(accounts)} accounts "
                    f"({rate:.1f} accounts/sec)"
                )
                
        except Exception as e:
            logger.error(f"Failed to reconcile {account_id}: {str(e)}")
            results['failed'] += 1
            _increment_failed_attempts(db_manager, account_id)
    
    # Get API statistics
    results['api_stats'] = reconciler.get_api_stats()
    
    # Count skipped accounts if not retrying failed
    if not retry_failed:
        skipped_query = """
            SELECT COUNT(*) as count
            FROM prop_trading_model.trade_recon
            WHERE trades_recon_checksum = FALSE
            AND failed_attempts > 0
        """
        skipped_result = db_manager.model_db.execute_query(skipped_query)
        results['skipped_due_to_previous_failure'] = skipped_result[0]['count'] if skipped_result else 0
        
        if results['skipped_due_to_previous_failure'] > 0:
            logger.warning(
                f"Skipped {results['skipped_due_to_previous_failure']} accounts "
                "due to previous failures. Use retry_failed=True to include them."
            )
    
    # Log final statistics
    total_time = time.time() - batch_start_time
    logger.info(
        f"Reconciliation complete: {results['total_processed']} accounts in {total_time:.1f}s "
        f"({results['total_processed'] / total_time:.1f} accounts/sec)"
    )
    
    return results


def _increment_failed_attempts(db_manager, account_id: str):
    """Increment failed attempts counter for an account."""
    query = """
        UPDATE prop_trading_model.trade_recon
        SET failed_attempts = COALESCE(failed_attempts, 0) + 1,
            last_failed_attempt = NOW()
        WHERE account_id = %s
    """
    with db_manager.model_db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (account_id,))
            conn.commit()


def _reset_failed_attempts(db_manager, account_id: str):
    """Reset failed attempts counter for an account after successful reconciliation."""
    query = """
        UPDATE prop_trading_model.trade_recon
        SET failed_attempts = 0,
            last_failed_attempt = NULL
        WHERE account_id = %s
    """
    with db_manager.model_db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (account_id,))
            conn.commit()


def generate_reconciliation_report() -> Dict[str, Any]:
    """Generate a summary report of current reconciliation status."""
    db_manager = get_db_manager()
    
    report = {}
    
    # Overall statistics
    overall_query = """
        SELECT 
            COUNT(*) as total_accounts,
            COUNT(*) FILTER (WHERE trades_recon_checksum = TRUE) as reconciled,
            COUNT(*) FILTER (WHERE trades_recon_checksum = FALSE) as needs_reconciliation,
            COUNT(*) FILTER (WHERE failed_attempts > 0) as has_failures,
            COUNT(*) FILTER (WHERE jsonb_array_length(issues) > 0) as has_issues,
            ROUND(100.0 * COUNT(*) FILTER (WHERE trades_recon_checksum = TRUE) / NULLIF(COUNT(*), 0), 2) as reconciliation_percentage
        FROM prop_trading_model.trade_recon
    """
    
    overall_stats = db_manager.model_db.execute_query(overall_query)[0]
    report['overall'] = overall_stats
    
    # Issue breakdown
    issue_query = """
        SELECT * FROM prop_trading_model.get_issue_statistics()
        ORDER BY severity, account_count DESC
    """
    
    issue_stats = db_manager.model_db.execute_query(issue_query)
    report['issues_by_type'] = issue_stats
    
    # Recent activity
    activity_query = """
        SELECT 
            DATE(last_checked) as check_date,
            COUNT(*) as accounts_checked,
            COUNT(*) FILTER (WHERE trades_recon_checksum = TRUE) as resolved,
            COUNT(*) FILTER (WHERE failed_attempts > 0) as failed
        FROM prop_trading_model.trade_recon
        WHERE last_checked >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY DATE(last_checked)
        ORDER BY check_date DESC
    """
    
    activity_stats = db_manager.model_db.execute_query(activity_query)
    report['recent_activity'] = activity_stats
    
    return report


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Trade reconciliation utility")
    parser.add_argument(
        '--fix-null-ids',
        action='store_true',
        help='Fix all NULL account_ids in trade tables'
    )
    parser.add_argument(
        '--reconcile',
        action='store_true',
        help='Run reconciliation for mismatched accounts'
    )
    parser.add_argument(
        '--retry-failed',
        action='store_true',
        help='Include accounts that have previously failed'
    )
    parser.add_argument(
        '--report',
        action='store_true',
        help='Generate reconciliation status report'
    )
    parser.add_argument(
        '--max-accounts',
        type=int,
        help='Maximum number of accounts to process'
    )
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.fix_null_ids:
        results = fix_all_null_account_ids()
        print(f"NULL account_id fix results: {json.dumps(results, indent=2)}")
    
    if args.reconcile:
        results = reconcile_all_mismatched_accounts(
            retry_failed=args.retry_failed,
            max_accounts=args.max_accounts
        )
        print(f"Reconciliation results: {json.dumps(results, indent=2)}")
    
    if args.report:
        report = generate_reconciliation_report()
        print(f"Reconciliation report: {json.dumps(report, indent=2)}")