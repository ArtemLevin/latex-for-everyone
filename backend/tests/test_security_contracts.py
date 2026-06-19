"""Static regression contracts for security hardening and quality gates."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_makefile_exposes_stage_four_quality_gates():
    makefile = _read("Makefile")

    assert ".PHONY: lint" in makefile
    assert "QUALITY_PY_FILES :=" in makefile
    assert "ruff check $(QUALITY_PY_FILES)" in makefile
    assert ".PHONY: format-check" in makefile
    assert "ruff format --check $(QUALITY_PY_FILES)" in makefile
    assert ".PHONY: test-coverage" in makefile
    assert "--cov=app --cov-report=term-missing" in makefile
    assert "check: compileall frontend-check lint format-check test" in makefile


def test_ci_runs_backend_quality_frontend_static_and_docker_build():
    workflow = _read(".github/workflows/ci.yml")

    assert "backend-quality:" in workflow
    assert "astral-sh/setup-uv@v4" in workflow
    assert "uv sync --all-groups" in workflow
    assert "make compileall" in workflow
    assert "make lint" in workflow
    assert "make format-check" in workflow
    assert "make test" in workflow
    assert "frontend-static:" in workflow
    assert "make frontend-check" in workflow
    assert "docker-build:" in workflow


def test_ruff_and_coverage_tools_are_declared_for_quality_gates():
    pyproject = _read("pyproject.toml")

    assert '"ruff==0.6.9"' in pyproject
    assert '"pytest-cov==5.0.0"' in pyproject
    assert "[tool.ruff]" in pyproject
    assert "line-length = 120" in pyproject
    assert "[tool.ruff.lint]" in pyproject
    assert 'select = ["E9", "F821"]' in pyproject


def test_docs_describe_quality_gate_workflow():
    readme = _read("README.md")
    agent_workflow = _read("docs/ai-agent-workflow.md")

    for expected in ["make lint", "make format-check", "make test-coverage", "make check"]:
        assert expected in readme
        assert expected in agent_workflow
