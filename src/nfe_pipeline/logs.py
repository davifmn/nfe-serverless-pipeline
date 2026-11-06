"""Structured JSON logs (CloudWatch Logs Insights can filter on any field)."""

from __future__ import annotations

import json
import logging
import os
import sys

_logger = logging.getLogger("nfe_pipeline")
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    _logger.propagate = False


def log(event: str, level: int = logging.INFO, **fields) -> None:
    _logger.log(level, json.dumps({"event": event, **fields}, default=str))
