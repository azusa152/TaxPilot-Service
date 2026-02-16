.PHONY: start stop test lint format migrate help

start: ## Start all services
	docker-compose up --build

stop: ## Stop all services
	docker-compose down

test: ## Run tests
	docker-compose run --rm api pytest -v

lint: ## Lint code with ruff
	docker-compose run --rm api ruff check src/ tests/

format: ## Format code with ruff
	docker-compose run --rm api ruff format src/ tests/

migrate: ## Generate a new migration (usage: make migrate msg="description")
	docker-compose run --rm api alembic revision --autogenerate -m "$(msg)"

migrate-up: ## Apply all pending migrations
	docker-compose run --rm api alembic upgrade head

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
