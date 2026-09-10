PYTHON ?= uv run python
MANAGE = $(PYTHON) manage.py
PORT ?= 8000

.PHONY: help install run migrate makemigrations mig shell superuser check test collectstatic clean docker-up docker-down docker-build docker-logs docker-shell docker-migrate

help:
	@echo "Available make commands:"
	@echo "  make install        Install project dependencies using uv"
	@echo "  make run            Run development server (default port 8000; override with PORT=<port>)"
	@echo "  make migrate        Apply database migrations (optional: app=<app_name>)"
	@echo "  make makemigrations Create database migrations (optional: app=<app_name>)"
	@echo "  make mig            Create and apply database migrations at once (optional: app=<app_name>)"
	@echo "  make shell          Open Django interactive shell"
	@echo "  make superuser      Create a Django superuser"
	@echo "  make check          Run Django system checks"
	@echo "  make test           Run Django test suite"
	@echo "  make collectstatic  Collect static files into STATIC_ROOT"
	@echo "  make clean          Clean Python bytecode and cache files"
	@echo "  make docker-up      Start Docker containers (db and web) in background"
	@echo "  make docker-down    Stop and remove Docker containers"
	@echo "  make docker-build   Build or rebuild Docker image"
	@echo "  make docker-logs    Follow Docker container logs"
	@echo "  make docker-shell   Open Django shell inside web container"
	@echo "  make docker-migrate Run migrations inside web container"

install:
	uv sync

run:
	$(MANAGE) runserver 0.0.0.0:$(PORT)

migrate:
	$(MANAGE) migrate $(app)

makemigrations:
	$(MANAGE) makemigrations $(app)

mig:
	$(MANAGE) makemigrations $(app)
	$(MANAGE) migrate $(app)

shell:
	$(MANAGE) shell

superuser:
	$(MANAGE) createsuperuser

check:
	$(MANAGE) check

test:
	$(MANAGE) test

collectstatic:
	$(MANAGE) collectstatic --noinput

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[co]" -delete

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-build:
	docker compose build

docker-logs:
	docker compose logs -f

docker-shell:
	docker compose exec web python manage.py shell

docker-migrate:
	docker compose exec web python manage.py migrate

