"""OpenTelemetry provider setup for the Phoenix reasoning ledger."""

from __future__ import annotations

import os
from typing import Mapping

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_phoenix_telemetry(phoenix_endpoint: str) -> TracerProvider:
    """Configure the global OpenTelemetry tracer provider for Arize Phoenix."""

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "autoreach-ai",
                "telemetry.destination": "arize-phoenix",
            }
        )
    )
    exporter = OTLPSpanExporter(endpoint=phoenix_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def setup_phoenix_telemetry_from_env(
    env: Mapping[str, str] | None = None,
) -> TracerProvider | None:
    """Configure the global tracer provider when Phoenix env is present."""

    values = env if env is not None else os.environ
    endpoint = (values.get("AUTOREACH_PHOENIX_ENDPOINT") or "").strip()
    if not endpoint:
        return None
    return setup_phoenix_telemetry(endpoint)
