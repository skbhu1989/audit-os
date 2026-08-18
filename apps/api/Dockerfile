FROM python:3.12-slim

WORKDIR /app

# System deps needed by asyncpg/bcrypt build chains on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Fails loudly at container startup (not silently at first request) if
# required secrets aren't provided — see app/security.py and app/db.py's
# own ENVIRONMENT=production checks. This is the enforcement mechanism for
# that check in an actual deployed container.
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Runs as a non-root user — a slim image runs as root by default otherwise.
RUN useradd --create-home appuser
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
