FROM node:22-slim AS frontend-builder
# Give vite + tsc enough heap to finish a production build on
# memory-constrained Railway builders (default was OOM-killed during
# `vite build`, surfacing as a BuildKit "context canceled" error).
ENV NODE_OPTIONS=--max-old-space-size=4096
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund --prefer-offline
COPY shared/ /app/shared/
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt constraints.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefer-binary --progress-bar off -r requirements.txt -c constraints.txt
RUN playwright install chromium

COPY . ./
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Railway injects PORT at runtime; default to 8000
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --ws-ping-interval 20 --ws-ping-timeout 30"]
