"""OpenTelemetry provider setup for the Phoenix reasoning ledger.

Trace export is an optional, endpoint-gated feature. The OTLP exporter drags in
protobuf, whose C extension can be incompatible with newer Python runtimes; we
therefore import the exporter defensively so that a broken build degrades to
"no export" instead of crashing app boot. The in-process tracer (and the trace
ids stamped onto actions) works regardless — only export needs the exporter.
"""

from __future__ import annotations

import logging
import os
from typing import Mapping

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
except Exception as exc:  # pragma: no cover - runtime-dependent (protobuf build)
    OTLPSpanExporter = None  # type: ignore[assignment]
    _EXPORTER_IMPORT_ERROR: Exception | None = exc
else:
    _EXPORTER_IMPORT_ERROR = None


def setup_phoenix_telemetry(phoenix_endpoint: str) -> TracerProvider:
    """Configure the global OpenTelemetry tracer provider for Arize Phoenix."""

    if OTLPSpanExporter is None:
        raise RuntimeError(
            "OTLP span exporter is unavailable in this runtime"
        ) from _EXPORTER_IMPORT_ERROR

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
) -> "TracerProvider | None":
    """Configure the global tracer provider when Phoenix env is present.

    Returns None (and leaves the in-process tracer intact) when no endpoint is
    configured, or when the OTLP exporter cannot be imported/initialised. A
    failed exporter must never take down app boot.
    """

    values = env if env is not None else os.environ
    endpoint = (values.get("AUTOREACH_PHOENIX_ENDPOINT") or "").strip()
    if not endpoint:
        return None
    try:
        return setup_phoenix_telemetry(endpoint)
    except Exception:  # pragma: no cover - depends on runtime exporter deps
        logger.warning(
            "AUTOREACH_PHOENIX_ENDPOINT is set but the OTLP exporter could not be "
            "initialised; continuing without trace export.",
            exc_info=True,
        )
        return None
