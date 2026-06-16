from collections.abc import Mapping
from typing import Any

from app.schemas import ReadinessResponse

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
READINESS_STATUSES = ("ready", "degraded", "not_ready")
CHECK_STATUSES = ("ok", "missing", "skipped", "error")


def _escape_label_value(value: object) -> str:
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_labels(labels: Mapping[str, object]) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{_escape_label_value(value)}"' for key, value in sorted(labels.items()))
    return f"{{{rendered}}}"


def _metric_line(name: str, value: int | float, labels: Mapping[str, object] | None = None) -> str:
    return f"{name}{_format_labels(labels or {})} {value}"


def _append_help(lines: list[str], name: str, help_text: str, metric_type: str = "gauge") -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {metric_type}")


def _append_readiness_metrics(lines: list[str], readiness: ReadinessResponse) -> None:
    _append_help(lines, "latexed_readiness_status", "Current aggregate readiness status as one-hot gauges.")
    for status in READINESS_STATUSES:
        lines.append(_metric_line("latexed_readiness_status", int(readiness.status == status), {"status": status}))

    _append_help(lines, "latexed_readiness_check_status", "Per-check readiness status as one-hot gauges.")
    for check_name, check in sorted(readiness.checks.items()):
        for status in CHECK_STATUSES:
            lines.append(
                _metric_line(
                    "latexed_readiness_check_status",
                    int(check.status == status),
                    {"check": check_name, "status": status},
                )
            )


def _append_generation_job_metrics(lines: list[str], readiness: ReadinessResponse) -> None:
    generation_jobs = readiness.checks.get("generation_jobs")
    if generation_jobs is None:
        return
    details = generation_jobs.details
    counts = details.get("counts", {})
    if isinstance(counts, Mapping):
        _append_help(lines, "latexed_generation_jobs_total", "Generation jobs by persisted status.")
        for status in ("queued", "running", "completed", "failed", "canceled"):
            value = counts.get(status, 0)
            lines.append(_metric_line("latexed_generation_jobs_total", int(value or 0), {"status": status}))

    _append_help(lines, "latexed_generation_jobs_backlog", "Queued plus running generation jobs.")
    lines.append(_metric_line("latexed_generation_jobs_backlog", int(details.get("backlog", 0) or 0)))
    _append_help(lines, "latexed_generation_jobs_stale_running", "Generation jobs stuck in running beyond the stale threshold.")
    lines.append(_metric_line("latexed_generation_jobs_stale_running", int(details.get("stale_running", 0) or 0)))


def _append_request_control_metrics(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    backend = snapshot.get("backend", "unknown")
    shared = str(bool(snapshot.get("shared", False))).lower()
    _append_help(lines, "latexed_ai_request_control_backend_info", "Configured AI request-control backend information.")
    lines.append(_metric_line("latexed_ai_request_control_backend_info", 1, {"backend": backend, "shared": shared}))
    _append_help(lines, "latexed_ai_request_control_backend_up", "Whether the configured AI request-control backend health check passed.")
    lines.append(_metric_line("latexed_ai_request_control_backend_up", int(bool(snapshot.get("healthy", True))), {"backend": backend}))

    rate_limit_decisions = snapshot.get("rate_limit_decisions", {})
    if isinstance(rate_limit_decisions, Mapping):
        _append_help(
            lines,
            "latexed_ai_request_control_rate_limit_decisions_total",
            "Process-local AI rate-limit decisions since startup.",
            "counter",
        )
        for decision in ("allowed", "limited", "error"):
            lines.append(
                _metric_line(
                    "latexed_ai_request_control_rate_limit_decisions_total",
                    int(rate_limit_decisions.get(decision, 0) or 0),
                    {"decision": decision},
                )
            )

    in_flight_decisions = snapshot.get("in_flight_decisions", {})
    if isinstance(in_flight_decisions, Mapping):
        _append_help(
            lines,
            "latexed_ai_request_control_in_flight_decisions_total",
            "Process-local AI duplicate-guard decisions since startup.",
            "counter",
        )
        for decision in ("accepted", "duplicate", "error"):
            lines.append(
                _metric_line(
                    "latexed_ai_request_control_in_flight_decisions_total",
                    int(in_flight_decisions.get(decision, 0) or 0),
                    {"decision": decision},
                )
            )


def build_prometheus_metrics(readiness: ReadinessResponse, request_control_snapshot: Mapping[str, Any]) -> str:
    """Render low-cardinality operational metrics without user prompts/materials."""
    lines: list[str] = []
    _append_readiness_metrics(lines, readiness)
    _append_generation_job_metrics(lines, readiness)
    _append_request_control_metrics(lines, request_control_snapshot)
    return "\n".join(lines) + "\n"
