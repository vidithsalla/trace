from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import Lock


@dataclass(slots=True)
class MetricSummary:
    count: int
    total_ms: float
    max_ms: float

    @property
    def avg_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_ms / self.count


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._request_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latencies: dict[str, MetricSummary] = {}

    def observe_request(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        route = _normalize_path(path)
        with self._lock:
            self._request_counts[(method, route, status_code)] += 1
            current = self._latencies.get(route, MetricSummary(0, 0.0, 0.0))
            self._latencies[route] = MetricSummary(
                count=current.count + 1,
                total_ms=current.total_ms + latency_ms,
                max_ms=max(current.max_ms, latency_ms),
            )

    def render_prometheus(self) -> str:
        lines = [
            "# HELP trace_http_requests_total Total Trace HTTP requests.",
            "# TYPE trace_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status_code), count in sorted(self._request_counts.items()):
                lines.append(
                    'trace_http_requests_total{'
                    f'method="{method}",route="{route}",status_code="{status_code}"'
                    f"}} {count}"
                )
            lines.extend(
                [
                    "# HELP trace_http_request_latency_ms_avg Average Trace HTTP request latency.",
                    "# TYPE trace_http_request_latency_ms_avg gauge",
                ]
            )
            for route, summary in sorted(self._latencies.items()):
                lines.append(f'trace_http_request_latency_ms_avg{{route="{route}"}} {summary.avg_ms:.3f}')
                lines.append(f'trace_http_request_latency_ms_max{{route="{route}"}} {summary.max_ms:.3f}')
        return "\n".join(lines) + "\n"


def _normalize_path(path: str) -> str:
    parts = []
    for part in path.strip("/").split("/"):
        if not part:
            continue
        if len(part) >= 32 and "-" in part:
            parts.append("{id}")
        elif part.isdigit():
            parts.append("{number}")
        else:
            parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


metrics_registry = MetricsRegistry()
