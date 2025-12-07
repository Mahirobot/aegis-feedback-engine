import logging
import sys


def setup_logging():
    """
    Centralized logging configuration.
    Configures the root logger and the application specific logger.
    """
    # 1. format: "Time - Level - Message"
    log_format = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 2. Handler: Stream to stdout (Standard for Containerized apps)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)

    # 3. Configure the specific app logger
    logger = logging.getLogger("aegis")
    logger.setLevel(logging.INFO)

    # Prevent duplicate logs if re-initialized
    if not logger.handlers:
        logger.addHandler(console_handler)

    # Optional: Configure Uvicorn logger to match our format
    logging.getLogger("uvicorn.access").handlers = [console_handler]

    return logger
