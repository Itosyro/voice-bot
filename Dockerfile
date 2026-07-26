FROM python:3.11-slim

# ffmpeg — нарезка длинных голосовых и звук из видео; git — синк skills.
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
    chmod +x scripts/entrypoint.sh && \
    chown -R appuser:appuser /app

USER appuser

# /app/data — файловая база SQLite и рабочие файлы; монтируется томом,
# чтобы переживать пересборку образа.
VOLUME ["/app/data"]

ENTRYPOINT ["./scripts/entrypoint.sh"]
