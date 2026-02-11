import unittest
from unittest.mock import MagicMock, patch
from processors.utils import retry_with_backoff
import os

class TestUtils(unittest.TestCase):
    def test_retry_with_backoff_success(self):
        func = MagicMock(return_value="success")
        func.__name__ = "test_func"
        result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertEqual(result, "success")
        self.assertEqual(func.call_count, 1)

    def test_retry_with_backoff_retry_then_success(self):
        func = MagicMock(side_effect=[Exception("fail"), "success"])
        func.__name__ = "test_func"
        with patch('time.sleep'): # Don't actually sleep
            result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertEqual(result, "success")
        self.assertEqual(func.call_count, 2)

    def test_retry_with_backoff_max_retries_reached(self):
        func = MagicMock(side_effect=Exception("fail"))
        func.__name__ = "test_func"
        with patch('time.sleep'):
            with self.assertRaises(Exception):
                retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertEqual(func.call_count, 3)

    def test_retry_with_backoff_on_failure_return_value(self):
        func = MagicMock(side_effect=Exception("fail"))
        func.__name__ = "test_func"
        with patch('time.sleep'):
            result = retry_with_backoff(func, max_retries=3, base_delay=0.01, on_failure="failed_value")
        self.assertEqual(result, "failed_value")
        self.assertEqual(func.call_count, 3)

    def test_retry_with_backoff_on_failure_callable(self):
        func = MagicMock(side_effect=Exception("fail"))
        func.__name__ = "test_func"
        on_failure = MagicMock(return_value="callable_failed_value")
        with patch('time.sleep'):
            result = retry_with_backoff(func, max_retries=3, base_delay=0.01, on_failure=on_failure)
        self.assertEqual(result, "callable_failed_value")
        self.assertEqual(func.call_count, 3)
        on_failure.assert_called_once()

    def test_retry_with_backoff_env_vars(self):
        func = MagicMock(side_effect=Exception("fail"))
        func.__name__ = "test_func"
        with patch.dict(os.environ, {'RETRY_MAX_RETRIES': '2', 'RETRY_BASE_DELAY': '0.01'}):
            with patch('time.sleep'):
                with self.assertRaises(Exception):
                    retry_with_backoff(func)
        self.assertEqual(func.call_count, 2)
