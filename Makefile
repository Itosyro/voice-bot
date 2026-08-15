COMPOSE ?= docker compose -f docker-compose.server.yml

.PHONY: help install up down restart logs status update reconfigure shell backup migrate test lint

# Голый `make` на новом сервере печатает шпаргалку, а не запускает установку.
.DEFAULT_GOAL := help

help:         ## Показать список команд
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t— /'

install:      ## Первичная установка на сервер (спросит токен и ключ)
	bash scripts/install-server.sh

up:           ## Запустить бота
	$(COMPOSE) up -d

down:         ## Остановить бота
	$(COMPOSE) down

restart:      ## Перезапустить (подхватывает изменения в .env)
	$(COMPOSE) up -d --force-recreate

logs:         ## Живые логи (Ctrl+C — выйти)
	$(COMPOSE) logs -f --tail 100

status:       ## Работает ли бот
	$(COMPOSE) ps

update:       ## Забрать свежий код с GitHub и перезапустить
	git pull && $(COMPOSE) up -d --build

reconfigure:  ## Ввести ключи заново (старый .env сохранится в .env.bak)
	@test -f .env && cp .env .env.bak && rm .env && echo "Старый .env сохранён как .env.bak" || true
	bash scripts/install-server.sh

shell:        ## Зайти внутрь контейнера
	$(COMPOSE) exec bot sh

backup:       ## Сохранить базу в backup-<дата>.db рядом с проектом
	@# База в WAL-режиме: сырой docker cp .db без -wal даёт устаревшую или битую
	@# копию. Снимок делаем тем же sqlite3.backup(), что и миграция.
	$(COMPOSE) exec -T bot python -c "from src.migrate import snapshot_db; snapshot_db('/app/data/backup.db')"
	@f=backup-$$(date +%Y%m%d-%H%M).db; \
	 docker cp voice-bot:/app/data/backup.db "./$$f" && \
	 $(COMPOSE) exec -T bot rm -f /app/data/backup.db && \
	 echo "Готово: $$f"

migrate:      ## Прислать архив миграции (.env + база) админу в Telegram
	$(COMPOSE) run --rm --no-deps --entrypoint "python -m src.migrate" bot

test:         ## Прогнать тесты локально
	python -m pytest tests/ -q

lint:         ## Линт и формат
	ruff check . && ruff format --check .
