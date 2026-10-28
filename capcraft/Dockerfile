# One container: builds the React app, then serves it and the API from FastAPI.
FROM node:22-slim AS web
WORKDIR /w
COPY web/package.json web/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY capcraft capcraft
COPY capcraft_api capcraft_api
COPY data data
RUN pip install --no-cache-dir ".[api]"
COPY --from=web /w/dist web/dist
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn capcraft_api.main:app --host 0.0.0.0 --port ${PORT}"]
