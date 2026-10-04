"""Process logging, initialized at startup without replacing existing handlers."""

import logging


def configure_logging(level: str) -> None:
    # basicConfig installs a handler only once, including across app lifespans.
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("app").setLevel(level)
    # Our request logger omits query strings; Uvicorn's access logger does not.
    logging.getLogger("uvicorn.access").disabled = True
    # HTTP client diagnostics may include URLs and protocol-level data.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
