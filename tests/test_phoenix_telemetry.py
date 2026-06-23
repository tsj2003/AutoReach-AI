import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from engine.runtime.context import ExecutionResult, TenantContext
from engine.telemetry.provider import setup_phoenix_telemetry
from engine.telemetry.tracer import TracedWorkerContext


@pytest.fixture
def mock_otlp_exporter():
    """Mocks the HTTP exporter so we don't send real network requests during tests."""
    with patch("engine.telemetry.provider.OTLPSpanExporter") as mock_exporter:
        yield mock_exporter


def test_telemetry_provider_configures_arize_endpoint(mock_otlp_exporter):
    """Forces the provider to configure a real OpenTelemetry export pipeline."""
    provider = setup_phoenix_telemetry(phoenix_endpoint="http://localhost:6006/v1/traces")

    assert isinstance(provider, TracerProvider)

    mock_otlp_exporter.assert_called_once()
    call_kwargs = mock_otlp_exporter.call_args.kwargs
    assert call_kwargs["endpoint"] == "http://localhost:6006/v1/traces"


def test_telemetry_provider_can_initialize_from_env(mock_otlp_exporter):
    from engine.telemetry.provider import setup_phoenix_telemetry_from_env

    provider = setup_phoenix_telemetry_from_env(
        {"AUTOREACH_PHOENIX_ENDPOINT": "http://phoenix:6006/v1/traces"}
    )

    assert isinstance(provider, TracerProvider)
    assert mock_otlp_exporter.call_args.kwargs["endpoint"] == "http://phoenix:6006/v1/traces"


@pytest.mark.asyncio
async def test_traced_worker_emits_valid_span():
    """Verifies the wrapper outputs completed spans to the configured processor."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    memory_exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))

    base_worker = MagicMock()
    base_worker.execute_task = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            output={"status": "drafted"},
            duration_ms=100.0,
        )
    )

    traced_worker = TracedWorkerContext(base_executor=base_worker)
    tenant = TenantContext(
        tenant_id="t-telemetry",
        campaign_id="c-1",
        variables={},
        encrypted_secrets={},
    )

    with patch("engine.telemetry.tracer.trace.get_tracer", return_value=provider.get_tracer("test")):
        await traced_worker.execute_task("draft_email", {"lead": "test@acme.com"}, tenant)

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == "draft_email"
    assert span.attributes["openinference.span.kind"] == "AGENT"
    assert span.attributes["tenant.id"] == "t-telemetry"
    assert json.loads(span.attributes["output.value"]) == {"status": "drafted"}
