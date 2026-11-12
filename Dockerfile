# On-site image: the service, the web app and the bundled packs in one container.
# docker build -t ludwig . && docker run -p 8000:8000 -v ludwig-data:/data ludwig

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LUDWIG_DATABASE_URL=sqlite:////data/ludwig.db \
    LUDWIG_STORAGE_DIR=/data/storage \
    LUDWIG_PACKS_DIR=/app/packs \
    LUDWIG_WEB_DIR=/app/web
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[api]"
COPY packs/ packs/
COPY --from=web /web/dist/ web/
RUN useradd --system --uid 1000 ludwig && mkdir /data && chown ludwig /data
USER ludwig
VOLUME /data
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["ludwig", "serve", "--host", "0.0.0.0", "--port", "8000"]
