FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
RUN pip install --no-cache-dir uv
RUN npm install -g wrangler pnpm

COPY backend /app/backend

WORKDIR /app/backend
CMD ["./scripts/start_celery_worker.sh"]
