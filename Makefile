SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
CIRCLECI ?= circleci
PY_PROJECTS := services/gateway services/orders tests/security
ROTATE ?= 0
REQUIRE_ENV = @test -f .env || { echo "error: .env not found; run 'make bootstrap' first" >&2; exit 1; }
LOAD_ENV = set -a && . ./.env && set +a

.PHONY: help bootstrap up down ps logs migrate seed reset test test-integration lint lint-py typecheck fmt

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-17s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Create .env and generate credentials (ROTATE=1 regenerates all)
	@ROTATE=$(ROTATE) scripts/bootstrap.sh

up: ## Build and start the stack, wait until services are healthy
	$(REQUIRE_ENV)
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Follow service logs
	$(COMPOSE) logs -f --tail=200

migrate: ## Apply database migrations (one-shot jobs with the schema-owner roles)
	$(REQUIRE_ENV)
	$(COMPOSE) run --rm orders-migrate migrate
	$(COMPOSE) run --rm gateway-migrate migrate

seed: migrate ## Load deterministic seed data and apply Keycloak settings
	$(COMPOSE) run --rm orders-migrate seed
	@$(LOAD_ENV) && $(COMPOSE) exec -T -e KEYCLOAK_ADMIN_USER -e KEYCLOAK_ADMIN_PASSWORD \
		-e DEMO_USER_PASSWORD -e WEB_CLIENT_SECRET \
		keycloak bash /opt/mayushi/configure.sh

reset: ## Wipe volumes, restart and reseed
	$(COMPOSE) down -v --remove-orphans
	$(MAKE) up
	$(MAKE) seed

test: ## Run unit tests
	@for svc in $(PY_PROJECTS); do \
		echo "== $$svc"; uv run --directory $$svc pytest -q || exit 1; \
	done

test-integration: ## Run integration tests against the running stack
	$(REQUIRE_ENV)
	@$(LOAD_ENV) && uv run --directory services/gateway pytest -q -m integration
	@$(LOAD_ENV) && uv run --directory tests/security pytest -q -m integration

lint-py: ## Ruff lint and format check
	@for svc in $(PY_PROJECTS); do \
		echo "== $$svc"; \
		uv run --directory $$svc ruff check . || exit 1; \
		uv run --directory $$svc ruff format --check . || exit 1; \
	done

typecheck: ## mypy (strict)
	@for svc in $(PY_PROJECTS); do \
		echo "== $$svc"; uv run --directory $$svc mypy || exit 1; \
	done

fmt: ## Apply ruff formatting and safe fixes
	@for svc in $(PY_PROJECTS); do \
		uv run --directory $$svc ruff check --fix . ; \
		uv run --directory $$svc ruff format . ; \
	done

lint: lint-py ## All linters, plus CI and compose config validation
	$(CIRCLECI) config validate --skip-update-check .circleci/config.yml
	$(COMPOSE) config --quiet
