"""Lock-free in-memory accumulator for HTTP request metrics."""

from __future__ import annotations


class EndpointMetricsCollector:
    """Accumulates per-request data. drain() aggregates and resets the buffer.

    append() is GIL-atomic for CPython lists so no explicit lock is needed.
    """

    def __init__(self) -> None:
        self._buf: list[tuple[str, str, int, float, int, int]] = []

    def record(
        self,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
        req_bytes: int = 0,
        resp_bytes: int = 0,
    ) -> None:
        self._buf.append((method, path, status, duration_ms, req_bytes, resp_bytes))

    def drain(self) -> dict:
        buf, self._buf = self._buf, []
        if not buf:
            return {}

        per_endpoint: dict[str, dict] = {}
        for method, path, status, ms, req_b, resp_b in buf:
            key = f"{method} {path}"
            if key not in per_endpoint:
                per_endpoint[key] = {
                    "count": 0,
                    "total_ms": 0.0,
                    "durations": [],
                    "errors_4xx": 0,
                    "errors_5xx": 0,
                    "status_codes": {},
                    "total_req_bytes": 0,
                    "total_resp_bytes": 0,
                }
            s = per_endpoint[key]
            s["count"] += 1
            s["total_ms"] += ms
            s["durations"].append(ms)
            s["total_req_bytes"] += req_b
            s["total_resp_bytes"] += resp_b
            if 400 <= status < 500:
                s["errors_4xx"] += 1
            elif status >= 500:
                s["errors_5xx"] += 1
            code = str(status)
            s["status_codes"][code] = s["status_codes"].get(code, 0) + 1

        total_requests = total_4xx = total_5xx = 0
        total_ms = total_req_bytes = total_resp_bytes = 0
        endpoints: dict[str, dict] = {}

        for key, s in per_endpoint.items():
            n = s["count"]
            sorted_d = sorted(s["durations"])
            p95_idx = max(0, int(n * 0.95) - 1)
            endpoints[key] = {
                "count": n,
                "avg_ms": round(s["total_ms"] / n, 1),
                "p95_ms": round(sorted_d[p95_idx], 1),
                "errors_4xx": s["errors_4xx"],
                "errors_5xx": s["errors_5xx"],
                "status_codes": s["status_codes"],
                "avg_req_bytes": round(s["total_req_bytes"] / n) if n else 0,
                "avg_resp_bytes": round(s["total_resp_bytes"] / n) if n else 0,
                "total_req_bytes": s["total_req_bytes"],
                "total_resp_bytes": s["total_resp_bytes"],
            }
            total_requests += n
            total_4xx += s["errors_4xx"]
            total_5xx += s["errors_5xx"]
            total_ms += s["total_ms"]
            total_req_bytes += s["total_req_bytes"]
            total_resp_bytes += s["total_resp_bytes"]

        return {
            "total_requests": total_requests,
            "total_errors_4xx": total_4xx,
            "total_errors_5xx": total_5xx,
            "avg_latency_ms": round(total_ms / total_requests, 1) if total_requests else 0.0,
            "total_req_bytes": total_req_bytes,
            "total_resp_bytes": total_resp_bytes,
            "endpoints": endpoints,
        }
