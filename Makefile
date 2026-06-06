SHELL := /bin/bash

# ---- Project paths ---------------------------------------------------------
ROOT_DIR := $(CURDIR)
BACKEND_DIR := $(ROOT_DIR)/backend
FRONTEND_DIR := $(ROOT_DIR)/frontend
FRONTEND_JS_FILES := $(sort $(wildcard $(FRONTEND_DIR)/js/*.js))

# ---- Runtime configuration ------------------------------------------------
HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 8080
PYTHON ?= python3
UV ?= uv
UV_PROJECT := --project $(ROOT_DIR)
PYTHONPATH_BACKEND := PYTHONPATH=$(BACKEND_DIR)
BACKEND_URL := http://localhost:$(BACKEND_PORT)
FRONTEND_URL := http://localhost:$(FRONTEND_PORT)/main.html
AI_PROVIDER ?= ollama
AI_MODEL ?= gemma4
LATEX_COMPILER ?= pdflatex

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available make targets.
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- uv environment --------------------------------------------------------
.PHONY: uv-version
uv-version: ## Print the installed uv version.
	$(UV) --version

.PHONY: sync
sync: ## Create/update the uv environment with app and dev dependencies.
	$(UV) sync --all-groups

.PHONY: lock
lock: ## Update uv.lock from pyproject.toml.
	$(UV) lock

.PHONY: pip-sync
pip-sync: ## Alternative: install backend/requirements.txt into the uv environment.
	$(UV) pip install -r $(BACKEND_DIR)/requirements.txt

# ---- Local servers ---------------------------------------------------------
.PHONY: backend
backend: ## Run the FastAPI backend with uvicorn on BACKEND_PORT (default: 8000).
	cd $(BACKEND_DIR) && $(UV) run $(UV_PROJECT) uvicorn app.main:app --reload --host $(HOST) --port $(BACKEND_PORT)

.PHONY: frontend
frontend: ## Serve frontend/main.html on FRONTEND_PORT (default: 8080).
	$(PYTHON) -m http.server $(FRONTEND_PORT) --directory $(FRONTEND_DIR)

.PHONY: open
open: ## Print URLs to open after starting backend and frontend.
	@echo "Backend:  $(BACKEND_URL)"
	@echo "API docs: $(BACKEND_URL)/api/docs"
	@echo "Health:   $(BACKEND_URL)/api/health"
	@echo "Frontend: $(FRONTEND_URL)"

.PHONY: health
health: ## Call the backend health endpoint.
	curl -fsS $(BACKEND_URL)/api/health
	@echo

.PHONY: ai-provider-status
ai-provider-status: ## Check configured AI provider/model: make ai-provider-status AI_PROVIDER=ollama AI_MODEL=gemma4.
	curl -fsS "$(BACKEND_URL)/api/generation/providers/status?provider=$(AI_PROVIDER)&model=$(AI_MODEL)"
	@echo

.PHONY: ai-validate-smoke
ai-validate-smoke: ## Validate a minimal LaTeX document through the generation validator endpoint.
	curl -fsS -X POST "$(BACKEND_URL)/api/generation/validate" -H "Content-Type: application/json" --data '{"latex_code":"\\documentclass{article}\\begin{document}Smoke\\end{document}"}'
	@echo

.PHONY: latex-check
latex-check: ## Check pdflatex and Russian babel/T2A support needed for generated Russian PDFs.
	@command -v $(LATEX_COMPILER) >/dev/null || (echo "$(LATEX_COMPILER) not found. Install TeX Live, e.g. sudo apt install texlive-latex-base" && exit 1)
	@command -v kpsewhich >/dev/null || (echo "kpsewhich not found. Install TeX Live binaries, e.g. sudo apt install texlive-base" && exit 1)
	@kpsewhich russian.ldf >/dev/null || (echo "russian.ldf not found. Install Russian babel support: sudo apt install texlive-lang-cyrillic" && exit 1)
	@kpsewhich t2aenc.def >/dev/null || (echo "t2aenc.def not found. Install T2A/Cyrillic support: sudo apt install texlive-lang-cyrillic" && exit 1)
	@echo "LaTeX Russian support is available."

# ---- Tests and checks ------------------------------------------------------
.PHONY: test
test: ## Run backend tests through uv.
	cd $(BACKEND_DIR) && $(PYTHONPATH_BACKEND) $(UV) run $(UV_PROJECT) pytest tests/ -q

.PHONY: test-verbose
test-verbose: ## Run backend tests through uv with verbose output.
	cd $(BACKEND_DIR) && $(PYTHONPATH_BACKEND) $(UV) run $(UV_PROJECT) pytest tests/ -v

.PHONY: compileall
compileall: ## Compile backend Python files to catch syntax errors.
	$(UV) run $(UV_PROJECT) $(PYTHON) -m compileall $(BACKEND_DIR)/app

.PHONY: frontend-check
frontend-check: ## Run node --check for frontend JavaScript files.
	@test -n "$(FRONTEND_JS_FILES)" || (echo "No frontend JavaScript files found" && exit 1)
	node --check $(FRONTEND_JS_FILES)

.PHONY: check
check: compileall frontend-check test ## Run all local checks.

# ---- Database and migrations ----------------------------------------------
.PHONY: migrate
migrate: ## Run Alembic migrations against the configured backend database.
	cd $(BACKEND_DIR) && $(UV) run $(UV_PROJECT) alembic upgrade head

.PHONY: migration
migration: ## Create an Alembic migration: make migration MSG="message".
	@test -n "$(MSG)" || (echo 'Usage: make migration MSG="message"' && exit 1)
	cd $(BACKEND_DIR) && $(UV) run $(UV_PROJECT) alembic revision --autogenerate -m "$(MSG)"

# ---- Docker ----------------------------------------------------------------
.PHONY: docker-up
docker-up: ## Build and run backend/nginx with docker compose.
	cd $(BACKEND_DIR) && docker-compose up --build

.PHONY: docker-down
docker-down: ## Stop docker compose services.
	cd $(BACKEND_DIR) && docker-compose down

.PHONY: docker-logs
docker-logs: ## Follow docker compose logs.
	cd $(BACKEND_DIR) && docker-compose logs -f

# ---- Cleanup ---------------------------------------------------------------
.PHONY: clean
clean: ## Remove local test databases and Python/test caches.
	rm -f $(BACKEND_DIR)/latexed.db $(BACKEND_DIR)/test_latexed.db $(ROOT_DIR)/latexed.db $(ROOT_DIR)/test_latexed.db
	find $(ROOT_DIR) -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +

.PHONY: clean-artifacts
clean-artifacts: ## Remove local compile/export artifacts from the default /tmp Latexed directories.
	rm -rf /tmp/latexed_compiles /tmp/latexed_uploads

.PHONY: clean-venv
clean-venv: ## Remove the uv virtual environment.
	rm -rf $(ROOT_DIR)/.venv
