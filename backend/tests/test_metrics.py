from app.schemas import ReadinessCheckResponse, ReadinessResponse
from app.services.metrics import build_prometheus_metrics


def test_prometheus_metrics_render_readiness_jobs_and_request_control():
    readiness = ReadinessResponse(
        status="degraded",
        checks={
            "database": ReadinessCheckResponse(status="ok", message="ok", details={}),
            "generation_jobs": ReadinessCheckResponse(
                status="error",
                message="stale",
                details={
                    "counts": {"queued": 2, "running": 1, "completed": 5, "failed": 1, "canceled": 0},
                    "backlog": 3,
                    "stale_running": 1,
                },
            ),
            "ai_request_control": ReadinessCheckResponse(status="ok", message="redis", details={"backend": "redis"}),
        },
    )

    output = build_prometheus_metrics(
        readiness,
        {
            "backend": "redis",
            "shared": True,
            "healthy": True,
            "rate_limit_decisions": {"allowed": 7, "limited": 2},
            "in_flight_decisions": {"accepted": 4, "duplicate": 1},
        },
    )

    assert 'latexed_readiness_status{status="degraded"} 1' in output
    assert 'latexed_readiness_check_status{check="generation_jobs",status="error"} 1' in output
    assert 'latexed_generation_jobs_total{status="queued"} 2' in output
    assert "latexed_generation_jobs_backlog 3" in output
    assert "latexed_generation_jobs_stale_running 1" in output
    assert 'latexed_ai_request_control_backend_info{backend="redis",shared="true"} 1' in output
    assert 'latexed_ai_request_control_backend_up{backend="redis"} 1' in output
    assert 'latexed_ai_request_control_rate_limit_decisions_total{decision="limited"} 2' in output
    assert 'latexed_ai_request_control_in_flight_decisions_total{decision="duplicate"} 1' in output


def test_prometheus_metrics_escape_label_values():
    readiness = ReadinessResponse(
        status="ready",
        checks={
            'odd"check': ReadinessCheckResponse(status="ok", message="ok", details={}),
        },
    )

    output = build_prometheus_metrics(readiness, {"backend": 'redis"one', "shared": True, "healthy": False})

    assert 'check="odd\\"check"' in output
    assert 'latexed_ai_request_control_backend_up{backend="redis\\"one"} 0' in output
