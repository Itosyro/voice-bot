COMPOSE ?= docker compose -f docker-compose.server.yml

.PHONY: install up down restart logs status update shell backup test lint

install:      ## Первичная установка на сервер (спросит токен и ключ)
	bash scripts/install-server.sh

up:           ## Запустить бота
	$(COMPOSE) up -d

down:         ## Остановить бота
	$(COMPOSE) down

restart:      ## Перезапустить
	$(COMPOSE) restart

logs:         ## Живые логи (Ctrl+C — выйти)
	$(COMPOSE) logs -f --tail 100

status:       ## Работает ли бот
	$(COMPOSE) ps

update:       ## Забрать свежий код с GitHub и перезапустить
	git pull && $(COMPOSE) up -d --build

shell:        ## Зайти внутрь контейнера
	$(COMPOSE) exec bot sh

backup:       ## Сохранить базу в backup-<дата>.db рядом с проектом
	docker cp voice-bot:/app/data/voicebot.db ./backup-$$(date +%Y%m%d-%H%M).db && \
	echo "Готово: backup-$$(date +%Y%m%d-%H%M).db"

test:         ## Прогнать тесты локально
	python -m pytest tests/ -q

lint:         ## Линт и формат
	ruff check . && ruff format --check .
