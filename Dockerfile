FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Run as a non-root user so an RCE in a native lib (e.g. ffmpeg) cannot
# trivially escalate to root inside the container.
RUN useradd --create-home --uid 1000 appuser

COPY --chown=appuser:appuser . .
RUN pip install --no-cache-dir -e . && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

# Миграции и синк skills — best-effort: их падение (мёртвая БД, GitHub недоступен)
# не должно ронять запуск бота в restart-loop. Бот умеет работать деградированно.
CMD ["sh", "-c", "alembic upgrade head || echo 'WARN: migrations failed, continuing'; python scripts/sync_skills.py || echo 'WARN: skills sync failed, continuing'; python -m src.main"]
