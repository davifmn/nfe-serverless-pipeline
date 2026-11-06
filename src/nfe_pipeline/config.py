"""Settings read from the environment the Terraform module sets on each function."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True)
class Settings:
    table_name: str
    bucket: str
    event_bus: str
    rejected_prefix: str = "rejected/"
    max_object_bytes: int = 2 * 1024 * 1024


@cache
def settings() -> Settings:
    return Settings(
        table_name=os.environ["TABLE_NAME"],
        bucket=os.environ["BUCKET_NAME"],
        event_bus=os.environ.get("EVENT_BUS_NAME", "default"),
        rejected_prefix=os.environ.get("REJECTED_PREFIX", "rejected/"),
    )


@cache
def clients():
    """boto3 clients are created once per Lambda execution environment, not per request."""
    import boto3

    return {
        "s3": boto3.client("s3"),
        "events": boto3.client("events"),
        "table": boto3.resource("dynamodb").Table(settings().table_name),
    }
