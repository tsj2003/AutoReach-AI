"""Enabled Phoenix telemetry provider with proper configuration.

This replaces the defensive import with a fully functional Phoenix trace export
that's enabled by default for production deployments.
"""

from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    OTLP_AVAILABLE = True
except Exception as exc:
    OTLP_AVAILABLE = False
    OTLP_IMPORT_ERROR = exc
    logger.warning(f"OTLP exporter not available: {exc}")


DEFAULT_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"


def setup_phoenix_telemetry(
    phoenix_endpoint: str = DEFAULT_PHOENIX_ENDPOINT,
    service_name: str = "autoreach-ai",
    console_export: bool = False
) -> TracerProvider:
    """Configure the global OpenTelemetry tracer provider for Arize Phoenix."""

    provider = TracerProvider(
        resource=Resource.create({
            SERVICE_NAME: service_name,
            "telemetry.destination": "arize-phoenix",
            "deployment.environment": os.getenv("AUTOREACH_ENV", "development"),
        })
    )

    # Add Phoenix exporter if available
    if OTLP_AVAILABLE:
        try:
            exporter = OTLPSpanExporter(endpoint=phoenix_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"Phoenix telemetry configured: {phoenix_endpoint}")
        except Exception as e:
            logger.error(f"Failed to configure Phoenix exporter: {e}")
            # Fall back to console export
            console_export = True

    # Add console exporter as fallback or for debugging
    if console_export or not OTLP_AVAILABLE:
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("Console telemetry exporter configured")

    trace.set_tracer_provider(provider)
    return provider


def setup_phoenix_telemetry_from_env(
    env: Optional[Mapping[str, str]] = None,
    fallback_to_console: bool = True
) -> Optional[TracerProvider]:
    """Configure the global tracer provider from environment variables.

    Environment variables:
        AUTOREACH_PHOENIX_ENDPOINT: Phoenix endpoint URL
        AUTOREACH_SERVICE_NAME: Service name for telemetry
        AUTOREACH_ENABLE_CONSOLE_TELEMETRY: Enable console export (true/false)
        AUTOREACH_DISABLE_TELEMETRY: Disable all telemetry (true/false)

    Returns None if telemetry is explicitly disabled, otherwise returns the provider.
    """

    values = env if env is not None else os.environ

    # Check if telemetry is explicitly disabled
    if values.get("AUTOREACH_DISABLE_TELEMETRY", "").strip().lower() in ("1", "true", "yes"):
        logger.info("Telemetry explicitly disabled via AUTOREACH_DISABLE_TELEMETRY")
        return None

    # Get Phoenix endpoint (default to localhost for development)
    endpoint = (values.get("AUTOREACH_PHOENIX_ENDPOINT") or "").strip()
    if not endpoint:
        endpoint = DEFAULT_PHOENIX_ENDPOINT
        logger.info(f"Using default Phoenix endpoint: {endpoint}")

    # Get service name
    service_name = (values.get("AUTOREACH_SERVICE_NAME") or "").strip()
    if not service_name:
        service_name = "autoreach-ai"

    # Check if console export is requested
    console_export = values.get("AUTOREACH_ENABLE_CONSOLE_TELEMETRY", "").strip().lower() in ("1", "true", "yes")

    try:
        return setup_phoenix_telemetry(
            phoenix_endpoint=endpoint,
            service_name=service_name,
            console_export=console_export
        )
    except Exception as e:
        logger.error(f"Failed to setup Phoenix telemetry: {e}")
        if fallback_to_console:
            logger.info("Falling back to console telemetry")
            return setup_phoenix_telemetry(
                phoenix_endpoint="",
                service_name=service_name,
                console_export=True
            )
        return None


def get_tracer(name: str = "autoreach") -> trace.Tracer:
    """Get a tracer instance for the current application."""
    return trace.get_tracer(name)


class TelemetryContext:
    """Context manager for creating telemetry spans."""

    def __init__(self, name: str, attributes: Optional[dict] = None):
        self._name = name
        self._attributes = attributes or {}
        self._span = None

    def __enter__(self):
        tracer = get_tracer()
        self._span = tracer.start_as_current_span(self._name, attributes=self._attributes)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span:
            if exc_type is not None:
                self._span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc_val)))
            self._span.end()


def trace_function(name: Optional[str] = None):
    """Decorator to automatically trace function execution."""
    def decorator(func):
        span_name = name or f"{func.__module__}.{func.__name__}"
        
        async def async_wrapper(*args, **kwargs):
            with TelemetryContext(span_name):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            with TelemetryContext(span_name):
                return func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
