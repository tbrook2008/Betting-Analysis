"""
utils/logger.py — Rich-based logger for the entire project.
Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Hello!")
"""
import logging
from rich.logging import RichHandler
import config

_handlers = [
    RichHandler(
        rich_tracebacks=True,
        show_path=False,
        markup=True,
    )
]

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(message)s",
    datefmt="[%X]",
    handlers=_handlers,
)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that uses the Rich handler."""
    return logging.getLogger(name)
