import logging

def get_logger():
    """Return a simple logger."""
    return logging.getLogger("plantie")

def setup_logging():
    """Configure logging (called from main)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    return get_logger()