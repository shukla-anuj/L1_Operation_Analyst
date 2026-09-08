"""Environment-neutral log providers for local Floci and AWS CloudWatch."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Protocol


class LogProvider(Protocol):
    def fetch_logs(self, service: str, resource: str | None, start: datetime, end: datetime, pattern: str | None = None) -> List[Dict[str, Any]]:
        ...


class FlociLogProvider:
    def __init__(self, client: Any):
        self.client = client

    def fetch_logs(self, service, resource, start, end, pattern=None):
        return self.client.fetch_logs(service=service, resource=resource, start=start, end=end, pattern=pattern)


class CloudWatchLogProvider:
    def __init__(self, logs_client: Any = None, log_groups: Dict[str, str] | None = None):
        if logs_client is None:
            import boto3
            logs_client = boto3.client("logs", region_name=os.getenv("AWS_REGION"))
        self.client = logs_client
        self.log_groups = log_groups or {}

    def fetch_logs(self, service, resource, start, end, pattern=None):
        log_group = self.log_groups.get(service)
        if not log_group:
            return []
        response = self.client.filter_log_events(
            logGroupName=log_group,
            startTime=int(start.timestamp() * 1000),
            endTime=int(end.timestamp() * 1000),
            filterPattern=pattern or "",
        )
        return [{
            "id": event.get("eventId"),
            "timestamp": event.get("timestamp"),
            "message": event.get("message", ""),
            "service": service,
            "resource": resource,
        } for event in response.get("events", [])]
