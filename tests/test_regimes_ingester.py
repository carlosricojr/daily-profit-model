"""
Test suite for the enhanced regimes ingester.
Tests regimes_daily data ingestion from Supabase with production features.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
import json
import tempfile
from pathlib import Path
import numpy as np

from src.data_ingestion.ingest_regimes import RegimesIngester


class TestRegimesIngester(unittest.TestCase):
    """Test the enhanced regimes ingester."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # Mock database manager
        self.mock_db_manager = Mock()
        self.mock_model_db = Mock()
        self.mock_source_db = Mock()
        self.mock_db_manager.model_db = self.mock_model_db
        self.mock_db_manager.source_db = self.mock_source_db

        # Patch the dependencies
        self.patches = [patch("src.data_ingestion.base_ingester.get_db_manager")]

        self.mock_get_db = self.patches[0].start()
        self.mock_get_db.return_value = self.mock_db_manager

        self.ingester = RegimesIngester(checkpoint_dir=self.temp_dir)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_regime_record(self):
        """Test regime record validation."""
        # Valid regime
        valid_regime = {
            "date": date(2024, 1, 15),
            "market_news": {"news": "Market update"},
            "instruments": {"EURUSD": 1.0850},
            "country_economic_indicators": {"US": {"GDP": 2.5}},
            "news_analysis": {"sentiment": "positive"},
            "summary": {"key_points": ["point1", "point2"]},
            "vector_daily_regime": [0.1, 0.2, 0.3, 0.4, 0.5],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        is_valid, errors = self.ingester._validate_record(valid_regime)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # Invalid regime - missing date
        invalid_regime = valid_regime.copy()
        invalid_regime["date"] = None

        is_valid, errors = self.ingester._validate_record(invalid_regime)
        self.assertFalse(is_valid)
        self.assertIn("missing_date", errors)

        # Invalid regime - wrong vector dimensions
        invalid_vector = valid_regime.copy()
        invalid_vector["vector_daily_regime"] = [0.1, 0.2]  # Too short

        is_valid, errors = self.ingester._validate_record(invalid_vector)
        self.assertFalse(is_valid)
        self.assertIn("invalid_vector_dimension", errors)

        # Invalid regime - vector values out of range
        invalid_values = valid_regime.copy()
        invalid_values["vector_daily_regime"] = [0.1, 0.2, 1.5, 0.4, 0.5]  # 1.5 > 1

        is_valid, errors = self.ingester._validate_record(invalid_values)
        self.assertFalse(is_valid)
        self.assertIn("vector_values_out_of_range", errors)

    def test_transform_regime_record(self):
        """Test regime record transformation."""
        # Mock row from database cursor
        raw_row = (
            date(2024, 1, 15),  # date
            {"news": "Market update"},  # market_news
            {"EURUSD": 1.0850},  # instruments
            {"US": {"GDP": 2.5}},  # country_economic_indicators
            {"sentiment": "positive"},  # news_analysis
            {"key_points": ["point1", "point2"]},  # summary
            [0.1, 0.2, 0.3, 0.4, 0.5],  # vector_daily_regime
            datetime(2024, 1, 15, 10, 0, 0),  # created_at
            datetime(2024, 1, 15, 12, 0, 0),  # updated_at
        )

        transformed = self.ingester._transform_regime_record(raw_row)

        self.assertEqual(transformed["date"], date(2024, 1, 15))
        self.assertIsInstance(transformed["market_news"], str)  # Should be JSON string
        self.assertIsInstance(transformed["instruments"], str)
        self.assertEqual(transformed["vector_daily_regime"], [0.1, 0.2, 0.3, 0.4, 0.5])
        self.assertIn("ingestion_timestamp", transformed)

    def test_vector_handling(self):
        """Test handling of vector_daily_regime in different formats."""
        # Test numpy array
        np_array = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        row_np = (date(2024, 1, 15), {}, {}, {}, {}, {}, np_array, None, None)
        transformed = self.ingester._transform_regime_record(row_np)
        self.assertIsInstance(transformed["vector_daily_regime"], list)
        self.assertEqual(len(transformed["vector_daily_regime"]), 5)

        # Test string representation
        str_vector = "[0.1, 0.2, 0.3, 0.4, 0.5]"
        row_str = (date(2024, 1, 15), {}, {}, {}, {}, {}, str_vector, None, None)
        transformed = self.ingester._transform_regime_record(row_str)
        self.assertEqual(transformed["vector_daily_regime"], [0.1, 0.2, 0.3, 0.4, 0.5])

        # Test numpy string format
        np_str = "0.1 0.2 0.3 0.4 0.5"
        row_np_str = (date(2024, 1, 15), {}, {}, {}, {}, {}, np_str, None, None)
        transformed = self.ingester._transform_regime_record(row_np_str)
        self.assertEqual(len(transformed["vector_daily_regime"]), 5)

    def test_date_range_processing(self):
        """Test date range determination and processing."""
        # Mock cursor for source database
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_source_db.get_connection.return_value = mock_conn

        # Mock model database for insert
        mock_model_conn = MagicMock()
        mock_model_cursor = MagicMock()
        mock_model_conn.__enter__ = Mock(return_value=mock_model_conn)
        mock_model_conn.__exit__ = Mock(return_value=None)
        mock_model_conn.cursor.return_value.__enter__ = Mock(
            return_value=mock_model_cursor
        )
        mock_model_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_model_conn

        # Mock data for 5 days
        mock_data = []
        for i in range(5):
            mock_data.append(
                (
                    date(2024, 1, 10 + i),
                    {"news": f"Day {i}"},
                    {},
                    {},
                    {},
                    {},
                    [0.1] * 5,
                    datetime.now(),
                    datetime.now(),
                )
            )

        # Return data in batches
        mock_cursor.fetchmany.side_effect = [
            mock_data[:2],
            mock_data[2:4],
            mock_data[4:],
            [],
        ]

        # Run ingestion
        result = self.ingester.ingest_regimes(
            start_date=date(2024, 1, 10), end_date=date(2024, 1, 14)
        )

        self.assertEqual(result, 5)

        # Verify query was called with correct date range
        mock_cursor.execute.assert_called_once()
        query_args = mock_cursor.execute.call_args
        self.assertIn("WHERE date >= %s AND date <= %s", query_args[0][0])
        self.assertEqual(query_args[0][1], (date(2024, 1, 10), date(2024, 1, 14)))

    def test_checkpoint_resume(self):
        """Test resuming from checkpoint."""
        # Create a checkpoint file
        checkpoint_data = {
            "ingestion_type": "regimes",
            "last_processed_date": "2024-01-12",
            "total_records": 100,
            "timestamp": datetime.now().isoformat(),
        }

        checkpoint_file = Path(self.temp_dir) / "regimes_checkpoint.json"
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f)

        # Mock database connections
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_source_db.get_connection.return_value = mock_conn

        mock_model_conn = MagicMock()
        mock_model_cursor = MagicMock()
        mock_model_conn.__enter__ = Mock(return_value=mock_model_conn)
        mock_model_conn.__exit__ = Mock(return_value=None)
        mock_model_conn.cursor.return_value.__enter__ = Mock(
            return_value=mock_model_cursor
        )
        mock_model_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_model_conn

        # Mock data
        mock_cursor.fetchmany.side_effect = [[], []]  # No new data

        # Run ingestion with resume
        self.ingester.ingest_regimes(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 15),
            resume_from_checkpoint=True,
        )

        # Should resume from checkpoint date + 1
        query_args = mock_cursor.execute.call_args
        self.assertEqual(
            query_args[0][1][0], date(2024, 1, 13)
        )  # Start from day after checkpoint

    def test_incremental_load(self):
        """Test incremental load functionality."""
        # Mock getting latest date
        self.mock_model_db.execute_query.return_value = [
            {"max_date": date(2024, 1, 10)}
        ]

        # Mock database connections
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_source_db.get_connection.return_value = mock_conn

        mock_model_conn = MagicMock()
        self.mock_model_db.get_connection.return_value = mock_model_conn

        # Mock data
        mock_cursor.fetchmany.return_value = []

        # Run incremental ingestion
        self.ingester.ingest_regimes(incremental=True)

        # Should query from latest date + 1
        query_args = mock_cursor.execute.call_args
        self.assertEqual(query_args[0][1][0], date(2024, 1, 11))

    def test_json_field_handling(self):
        """Test handling of JSON fields."""
        # Test various JSON field formats
        test_cases = [
            ({"key": "value"}, True),  # Dict should be converted to JSON string
            ('{"key": "value"}', False),  # Already a string
            (None, False),  # None should stay None
            (["item1", "item2"], True),  # List should be converted
        ]

        for value, should_convert in test_cases:
            row = (date(2024, 1, 15), value, {}, {}, {}, {}, [0.1] * 5, None, None)
            transformed = self.ingester._transform_regime_record(row)

            if should_convert and value is not None:
                self.assertIsInstance(transformed["market_news"], str)
                self.assertEqual(json.loads(transformed["market_news"]), value)
            else:
                self.assertEqual(transformed["market_news"], value)

    def test_duplicate_handling(self):
        """Test handling of duplicate regime records."""
        # Mock database connections
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_source_db.get_connection.return_value = mock_conn

        mock_model_conn = MagicMock()
        mock_model_cursor = MagicMock()
        mock_model_conn.__enter__ = Mock(return_value=mock_model_conn)
        mock_model_conn.__exit__ = Mock(return_value=None)
        mock_model_conn.cursor.return_value.__enter__ = Mock(
            return_value=mock_model_cursor
        )
        mock_model_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_model_conn

        # Create duplicate data (same date)
        duplicate_date = date(2024, 1, 15)
        mock_data = [
            (duplicate_date, {}, {}, {}, {}, {}, [0.1] * 5, None, None),
            (
                duplicate_date,
                {},
                {},
                {},
                {},
                {},
                [0.2] * 5,
                None,
                None,
            ),  # Different vector but same date
            (date(2024, 1, 16), {}, {}, {}, {}, {}, [0.3] * 5, None, None),
        ]

        mock_cursor.fetchmany.side_effect = [mock_data, []]

        # Run ingestion with deduplication
        self.ingester.ingest_regimes(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 16),
            enable_deduplication=True,
        )

        # Check metrics
        self.assertEqual(self.ingester.metrics.total_records, 3)
        self.assertEqual(self.ingester.metrics.new_records, 2)  # Only 2 unique dates
        self.assertEqual(self.ingester.metrics.duplicate_records, 1)


if __name__ == "__main__":
    unittest.main()
