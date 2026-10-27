FROM python:3.12-slim

# ffmpeg merges video + audio and converts to MP3.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno runs YouTube's JavaScript challenges for yt-dlp (needs Deno >= 2.3).
COPY --from=denoland/deno:bin-2.9.8 /deno /usr/local/bin/deno

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH \
    DOWNLOAD_DIR=/downloads

# Run as a normal user, not root. The venv belongs to that user so yt-dlp can self-update.
RUN useradd --create-home --uid 1000 app \
    && python -m venv /opt/venv \
    && mkdir -p /downloads /app/data /app/state \
    && chown -R app:app /opt/venv /downloads /app

WORKDIR /app
USER app

COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --chown=app:app bot ./bot

ENTRYPOINT ["sh", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-m", "bot"]
