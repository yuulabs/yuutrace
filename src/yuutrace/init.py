from __future__ import annotations

import atexit
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult


DEFAULT_ENDPOINT = "http://localhost:4318/v1/traces"


class _QuietExporter(SpanExporter):
    """Wrapper that suppresses export errors instead of crashing the process.

    Network failures during span export should not propagate to business code.
    """

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Any) -> SpanExportResult:
        try:
            return self._inner.export(spans)
        except Exception:
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        try:
            self._inner.shutdown()
        except Exception:
            return


class TracingNotInitializedError(RuntimeError):
    """Raised when ``conversation()`` is called before ``init()``.

    Either call ``yuutrace.init(...)`` at process startup, or configure
    OpenTelemetry externally via ``trace.set_tracer_provider(...)``.
    """


def init(
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    service_name: str = "yuutrace",
    service_version: str | None = None,
    timeout_seconds: float = 10.0,
) -> None:
    """Initialize the OTLP trace exporter.

    Sets up a ``TracerProvider`` with a ``BatchSpanProcessor`` that exports
    spans to the given OTLP/HTTP endpoint.  If OpenTelemetry is already
    configured (i.e. a non-proxy ``TracerProvider`` exists), this is a no-op
    so yuutrace can coexist with existing instrumentation.

    Parameters
    ----------
    endpoint:
        OTLP/HTTP endpoint URL (default ``http://localhost:4318/v1/traces``).
    service_name:
        ``service.name`` resource attribute (default ``"yuutrace"``).
    service_version:
        Optional ``service.version`` resource attribute.
    timeout_seconds:
        HTTP export timeout in seconds (default ``10.0``).
    """
    provider = trace.get_tracer_provider()
    if not _is_proxy_tracer_provider(provider):
        return

    resource_attrs: dict[str, Any] = {"service.name": service_name}
    if service_version is not None:
        resource_attrs["service.version"] = service_version
    resource = Resource.create(resource_attrs)

    tracer_provider = TracerProvider(resource=resource)
    import requests

    session = requests.Session()
    session.trust_env = False
    exporter = _QuietExporter(
        OTLPSpanExporter(endpoint=endpoint, timeout=timeout_seconds, session=session)
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(tracer_provider)
    atexit.register(tracer_provider.shutdown)


def is_initialized() -> bool:
    return not _is_proxy_tracer_provider(trace.get_tracer_provider())


def require_initialized() -> None:
    if is_initialized():
        return
    raise TracingNotInitializedError(
        "Tracing is not initialized. "
        "Call yuutrace.init(...) at process startup, "
        "or configure OpenTelemetry by setting a TracerProvider "
        "(trace.set_tracer_provider(...)) before using ytrace.conversation()."
    )


def _is_proxy_tracer_provider(provider: object) -> bool:
    return provider.__class__.__name__ == "ProxyTracerProvider"
