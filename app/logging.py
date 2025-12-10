import logging
import sys


def setup_logging():
    """
    Configures the root logger for JSON-friendly output (simulated here)
    and attaches handlers to stdout.
    """
    # 1. Define Format
    log_format = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 2. Define Handler (Stream to Console)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)

    # 3. Setup 'aegis' logger
    logger = logging.getLogger("aegis")
    logger.setLevel(logging.INFO)

    # Prevent duplicate logs if function is called multiple times
    if not logger.handlers:
        logger.addHandler(console_handler)

    # 4. Silence noisy libraries if needed
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger
