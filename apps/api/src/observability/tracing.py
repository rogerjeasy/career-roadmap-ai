"""OpenTelemetry tracing — distributed traces shipped to OTLP collector.

For Grafana Tempo / Jaeger compatibility. Sentry handles its own gen_ai.* spans
on top of this.
"""
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.config import settings


def setup_tracing(app: FastAPI) -> None:
    """Configure OTel tracer provider and instrument frameworks."""
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        }
    )

    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Auto-instrument — these wrap the libraries automatically.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics,/livez,/readyz")
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()