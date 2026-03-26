import functools
import time
import random
from typing import Callable, Any
import httpx
from utils.logger import get_logger

log = get_logger(__name__)

def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    exceptions: tuple = (httpx.HTTPError, ConnectionError, TimeoutError),
) -> Callable:
    """
    Exponential backoff retry decorator.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retries = 0
            while retries <= max_retries:
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        log.error(f"Max retries ({max_retries}) reached for {fn.__name__}: {e}")
                        raise
                    
                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** (retries - 1)), max_delay)
                    jitter = delay * 0.1 * (random.random() * 2 - 1)
                    sleep_time = delay + jitter
                    
                    log.warning(f"Retry {retries}/{max_retries} for {fn.__name__} in {sleep_time:.2f}s: {e}")
                    time.sleep(sleep_time)
            return None
        return wrapper
    return decorator
