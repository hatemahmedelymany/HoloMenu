"""
Prometheus metric instrumentation definitions.
"""
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter("http_requests_total", "Total requests", ["route", "status_code"])
REQUEST_LATENCY = Histogram("http_request_duration_ms", "Request latency", ["route"])
