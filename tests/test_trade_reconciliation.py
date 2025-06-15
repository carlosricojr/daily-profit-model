import pytest
from unittest.mock import MagicMock, patch
from datetime import date

# Import the module after patching get_db_manager so the class picks up the stub

@pytest.fixture
def stub_db_manager():
    """Return a stubbed db_manager with MagicMock connections."""
    class StubModelDB:
        def __init__(self):
            self.execute_query = MagicMock()
            self.execute_update = MagicMock(return_value=0)
            self.get_connection = MagicMock()

    stub = MagicMock()
    stub.model_db = StubModelDB()
    return stub


@pytest.fixture
def reconciler(stub_db_manager):
    # Patch get_db_manager before importing to ensure TradeReconciliation uses stub
    with patch('src.data_quality.trade_reconciliation.get_db_manager', return_value=stub_db_manager):
        from src.data_quality.trade_reconciliation import TradeReconciliation
        yield TradeReconciliation()


def test_check_presence_consistency_missing_tables(reconciler):
    recon = {
        'has_alltime': True,
        'has_daily': False,
        'has_hourly': True,
        'num_trades_alltime': 100,
        'has_raw_closed': True,
    }
    issues = reconciler._check_presence_consistency(recon)
    assert issues, "Expect presence issue when daily metrics are missing"
    first = issues[0]
    assert first['type'] == 'missing_metrics_tables'
    assert 'raw_metrics_daily' in first['description']


def test_check_trade_count_consistency_detects_mismatch(reconciler):
    recon = {
        'num_trades_alltime': 100,
        'num_trades_daily': 90,
        'num_trades_hourly': 95,
        'num_trades_raw_closed': 100,
    }
    issues = reconciler._check_trade_count_consistency(recon)
    assert issues, "Should flag mismatching counts"
    assert issues[0]['type'] == 'trade_count_mismatch'


def test_check_null_account_ids_detects_issues(reconciler, stub_db_manager):
    # Prepare stub DB responses – first metrics details, then closed count, then open count
    stub_db_manager.model_db.execute_query.side_effect = [
        [{'login': '27792', 'platform': 7, 'broker': 4}],  # metrics lookup
        [{'count': 5}],  # closed trades missing account_id
        [{'count': 3}],  # open trades missing account_id
    ]
    issues = reconciler._check_null_account_ids('acc-1', {})
    # We should have two issues (closed + open)
    assert len(issues) == 2
    kinds = {i['type'] for i in issues}
    assert 'null_account_id_closed_trades' in kinds
    assert 'null_account_id_open_trades' in kinds


def test_assign_account_id_closed_trades_happy_path(reconciler, stub_db_manager):
    # Arrange execute_update returns rows updated, verify query returns zero remaining
    stub_db_manager.model_db.execute_update.return_value = 10
    stub_db_manager.model_db.execute_query.side_effect = [ [{'count': 0}] ]
    issue = {
        'metadata': {'login': '27792', 'platform': 7, 'broker': 4}
    }
    success = reconciler._assign_account_id_closed_trades('acc-1', issue)
    assert success is True
    stub_db_manager.model_db.execute_update.assert_called_once()


def test_assign_account_id_open_trades_happy_path(reconciler, stub_db_manager):
    stub_db_manager.model_db.execute_update.return_value = 8
    stub_db_manager.model_db.execute_query.side_effect = [ [{'count': 0}] ]
    issue = {
        'metadata': {'login': '27792', 'platform': 7, 'broker': 4}
    }
    success = reconciler._assign_account_id_open_trades('acc-1', issue)
    assert success is True


def test_attempt_resolution_dispatches_correct_method(reconciler):
    # Monkeypatch one internal method to flag it was called
    called = {}
    def fake_method(a, b=None):
        called['yes'] = True
        return True
    reconciler._fetch_all_closed_trades = fake_method  # type: ignore
    issue = {'resolution_strategy': 'fetch_all_closed_trades'}
    assert reconciler._attempt_resolution('acc-1', issue) is True
    assert called.get('yes')


def test_fix_all_null_account_ids_runs_updates(stub_db_manager):
    # Patch module level function after patching get_db_manager
    with patch('src.data_quality.trade_reconciliation.get_db_manager', return_value=stub_db_manager):
        from src.data_quality.trade_reconciliation import fix_all_null_account_ids
        stub_db_manager.model_db.execute_update.side_effect = [20, 15]
        stub_db_manager.model_db.execute_query.return_value = []
        results = fix_all_null_account_ids()
        assert results['closed_trades_updated'] == 20
        assert results['open_trades_updated'] == 15
        # execute_update called twice
        assert stub_db_manager.model_db.execute_update.call_count == 2 