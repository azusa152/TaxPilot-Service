.PHONY: up down test lint format migrate apply help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Start all services (db, api, dashboard)
	docker-compose up --build

down: ## Stop all services
	docker-compose down

test: ## Run backend tests
	docker-compose run --rm api pytest

lint: ## Run ruff linter on backend code
	cd backend && ruff check src/ tests/

format: ## Format and fix backend code with ruff
	cd backend && ruff check --fix src/ tests/ && ruff format src/ tests/

migrate: ## Generate a new migration (usage: make migrate msg="description")
	docker-compose run --rm api alembic revision --autogenerate -m "$(msg)"

apply: ## Apply all pending migrations
	docker-compose run --rm api alembic upgrade head
