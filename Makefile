PYTHON ?= uv run python
MANAGE = $(PYTHON) manage.py
PORT ?= 8000

.PHONY: help install run migrate makemigrations mig shell superuser check test collectstatic clean

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
