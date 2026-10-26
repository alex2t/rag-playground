# Release image (D05): the node stage builds the React app, the python stage serves it and the API.
# Build from the repo root: docker build -f backend/Dockerfile --build-arg APP_VERSION=<git-sha> .

FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --locked --no-install-project
COPY backend/src ./src
RUN uv sync --locked
COPY --from=frontend /app/frontend/dist /app/frontend/dist

ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION \
    STATIC_DIR=/app/frontend/dist \
    PATH="/app/backend/.venv/bin:$PATH"
RUN useradd --system app
USER app
EXPOSE 8000
CMD ["uvicorn", "rag_playground.main:app", "--host", "0.0.0.0", "--port", "8000"]
