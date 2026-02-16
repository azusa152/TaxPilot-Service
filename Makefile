.PHONY: start stop test lint format migrate frontend-dev frontend-build help

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

frontend-dev: ## Start frontend in dev mode
	docker-compose run --rm -p 3000:3000 frontend npm run dev

frontend-build: ## Build frontend production bundle
	docker-compose run --rm frontend npm run build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
