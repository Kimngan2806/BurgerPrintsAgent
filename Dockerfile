# One Render web service: nginx -> Next.js / FastAPI on loopback.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
ENV NEXT_TELEMETRY_DISABLED=1
ENV API_PROXY_TARGET=http://127.0.0.1:8000
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NEXT_TELEMETRY_DISABLED=1
RUN apt-get update && apt-get install -y --no-install-recommends nginx ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
WORKDIR /app/backend
COPY backend/requirements-runtime.txt ./requirements-runtime.txt
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY backend/ ./
COPY --from=frontend-build /build/frontend/.next/standalone/ /app/frontend/
COPY --from=frontend-build /build/frontend/.next/static/ /app/frontend/.next/static/
COPY --from=frontend-build /build/frontend/public/ /app/frontend/public/
COPY deploy/ /app/deploy/
EXPOSE 10000
CMD ["python", "/app/deploy/start.py"]
