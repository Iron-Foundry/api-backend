"""Lock-free in-memory accumulator for outbound HTTP request metrics."""

from __future__ import annotations

from typing import Any


class OutboundHttpCollector:
    """Accumulates per-call data for outgoing HTTP requests.

    record() is GIL-atomic for CPython lists so no explicit lock is needed.
    drain() aggregates and resets the buffer.
    """

    def __init__(self) -> None:
        self._buf: list[tuple[str, str, str, int, float]] = []

    def record(
        self,
        target: str,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
    ) -> None:
        self._buf.append((target, method, path, status, duration_ms))

    def drain(self) -> dict[str, Any]:
        buf, self._buf = self._buf, []
        if not buf:
            return {}

        per_endpoint: dict[str, dict[str, Any]] = {}
        per_target: dict[str, dict[str, Any]] = {}

        for target, method, path, status, ms in buf:
            key = f"{target} {method} {path}"
            if key not in per_endpoint:
                per_endpoint[key] = {
                    "count": 0,
                    "total_ms": 0.0,
                    "durations": [],
                    "errors_4xx": 0,
                    "errors_5xx": 0,
                    "status_codes": {},
                }
            s = per_endpoint[key]
            s["count"] += 1
            s["total_ms"] += ms
            s["durations"].append(ms)
            if 400 <= status < 500:
                s["errors_4xx"] += 1
            elif status >= 500:
                s["errors_5xx"] += 1
            code = str(status)
            s["status_codes"][code] = s["status_codes"].get(code, 0) + 1

            if target not in per_target:
                per_target[target] = {
                    "count": 0,
                    "errors_4xx": 0,
                    "errors_5xx": 0,
                    "total_ms": 0.0,
                }
            t = per_target[target]
            t["count"] += 1
            t["total_ms"] += ms
            if 400 <= status < 500:
                t["errors_4xx"] += 1
            elif status >= 500:
                t["errors_5xx"] += 1

        total_calls = total_4xx = total_5xx = 0
        endpoints: dict[str, dict[str, Any]] = {}

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
            }
            total_calls += n
            total_4xx += s["errors_4xx"]
            total_5xx += s["errors_5xx"]

        by_target = {
            target: {
                "count": d["count"],
                "errors_4xx": d["errors_4xx"],
                "errors_5xx": d["errors_5xx"],
                "avg_ms": round(d["total_ms"] / d["count"], 1) if d["count"] else 0.0,
            }
            for target, d in per_target.items()
        }

        return {
            "total_calls": total_calls,
            "total_errors_4xx": total_4xx,
            "total_errors_5xx": total_5xx,
            "by_target": by_target,
            "endpoints": endpoints,
        }
