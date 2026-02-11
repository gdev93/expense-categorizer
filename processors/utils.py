import os
import time
import random
import logging
from typing import Callable, Any, Type, Iterable

logger = logging.getLogger(__name__)

def retry_with_backoff[T](
    # any argument, any response type
    func: Callable[..., T],
    max_retries: int | None = None,
    base_delay: float | None = None,
    exceptions: Type[Exception] | Iterable[Type[Exception]] = Exception,
    on_failure: Any | Callable[[], Any] = None,
    *args: Any,
    **kwargs: Any
) -> T:
    """
    Utility function to retry a method when it fails with exponential backoff and jitter.
    
    :param func: The function to execute.
    :param max_retries: Maximum number of retries. If None, uses RETRY_MAX_RETRIES env var (default: 5).
    :param base_delay: Base delay for backoff in seconds. If None, uses RETRY_BASE_DELAY env var (default: 2).
    :param exceptions: Exception or tuple of exceptions to catch.
    :param on_failure: Value to return or callable to execute when all retries fail. If None, the last exception is raised.
    :param args: Positional arguments for func.
    :param kwargs: Keyword arguments for func.
    :return: The result of func or on_failure.
    """
    if max_retries is None:
        max_retries = int(os.environ.get('RETRY_MAX_RETRIES', 5))
    if base_delay is None:
        base_delay = float(os.environ.get('RETRY_BASE_DELAY', 2))
        
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            is_last_attempt = (attempt == max_retries - 1)
            
            if is_last_attempt:
                logger.error(f"⚠️ {func.__name__} failed after {max_retries} attempts: {str(e)}")
                if on_failure is not None:
                    if callable(on_failure):
                        return on_failure()
                    return on_failure
                raise e
            
            # Exponential backoff with Jitter
            sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
            logger.warning(
                f"⚠️ {func.__name__} Error (Attempt {attempt + 1}/{max_retries}). "
                f"Retrying in {sleep_time:.2f}s... Error: {str(e)}"
            )
            time.sleep(sleep_time)
