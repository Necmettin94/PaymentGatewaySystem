.PHONY: help up down build rebuild migrate test lint logs shell seed clean pre-commit-install pre-commit-run pre-commit-update

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start all services
	docker compose up -d
	@echo "Services started successfully!\nAPI: http://localhost:8000\nSwagger: http://localhost:8000/docs\nFlower: http://localhost:5555\nRabbitMQ: http://localhost:15672"

down: ## Stop all services
	docker compose down

build: ## Build docker images
	docker compose build

rebuild: down build up ## Rebuild and restart all services

migrate: ## Run database migrations
	docker compose exec api alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="your message")
	docker compose exec api alembic revision --autogenerate -m "$(msg)"

migrate-rollback: ## Rollback last migration
	docker compose exec api alembic downgrade -1

migrate-history: ## Show migration history
	docker compose exec api alembic history

test: ## Run all tests with coverage
	docker compose exec api pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

test-unit: ## Run unit tests only
	docker compose exec api pytest tests/unit/ -v

test-integration: ## Run integration tests only
	docker compose exec api pytest tests/integration/ -v

test-watch: ## Run tests in watch mode
	docker compose exec api ptw tests/ -- -v

lint: ## Run linters (black, isort, ruff)
	docker compose exec api black app/ tests/ --check
	docker compose exec api isort app/ tests/ --check-only
	docker compose exec api ruff check app/ tests/

format: ## Format code with black and isort
	docker compose exec api black app/ tests/
	docker compose exec api isort app/ tests/

type-check: ## Run mypy type checking
	docker compose exec api mypy app/

pre-commit-install: ## Install pre-commit hooks
	docker compose exec api pre-commit install
	@echo "Pre-commit hooks installed"

pre-commit-run: ## Run pre-commit on all files
	docker compose exec api pre-commit run --all-files

pre-commit-update: ## Update pre-commit hooks to latest versions
	docker compose exec api pre-commit autoupdate

logs: ## Show logs from all services
	docker compose logs -f

logs-api: ## Show API logs
	docker compose logs -f api

logs-worker: ## Show Celery worker logs
	docker compose logs -f celery_worker

logs-flower: ## Show Flower logs
	docker compose logs -f flower

shell: ## Access application Python shell
	docker compose exec api python

shell-db: ## Access PostgreSQL shell
	docker compose exec postgres psql -U payment_user -d payment_gateway

shell-redis: ## Access Redis CLI
	docker compose exec redis redis-cli

shell-bash: ## Access API container bash
	docker compose exec api /bin/bash

seed: ## Seed database with test data
	docker compose exec api python scripts/seed_data.py

clean: down ## Stop services and remove volumes
	docker compose down -v
	@echo "Cleaned up containers and volumes"

clean-all: clean ## Clean everything including built images
	docker compose down -v --rmi all
	rm -rf __pycache__ .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Deep clean completed"

ps: ## Show running containers
	docker compose ps

restart-api: ## Restart API service only
	docker compose restart api

restart-worker: ## Restart Celery worker only
	docker compose restart celery_worker

restart-flower: ## Restart Flower monitoring
	docker compose restart flower

init: build migrate seed ## Initialize project (build, migrate, seed)
	@echo "Project initialized successfully!"
	@echo "Run 'make up' to start the services"

health: ## Check health of all services
	@echo "Checking service health..."
	@docker compose exec postgres pg_isready -U payment_user || echo "PostgreSQL is down"
	@docker compose exec redis redis-cli ping || echo "Redis is down"
	@docker compose exec rabbitmq rabbitmq-diagnostics ping || echo "RabbitMQ is down"
	@curl -f http://localhost:8000/health || echo "API is down"
	@echo "Health check completed"

backup-db: ## Backup database
	docker compose exec postgres pg_dump -U payment_user payment_gateway > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Database backed up"

restore-db: ## Restore database (usage: make restore-db file=backup.sql)
	docker compose exec -T postgres psql -U payment_user payment_gateway < $(file)
	@echo "Database restored"
