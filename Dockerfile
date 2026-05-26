FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --group appuser

COPY --chown=appuser:appgroup . .
RUN pip install --no-cache-dir -e .
USER appuser

CMD ["sh", "-c", "alembic upgrade head && python scripts/sync_skills.py && python -m src.main"]
