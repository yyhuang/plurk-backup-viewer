# Base image with Python, uv, cloudflared, libicu, custom SQLite + ICU tokenizer.
# Build locally:  docker build -f Dockerfile.base -t plurk-backup-viewer-base .
# Or pull from Docker Hub (see CLAUDE.md for details).
ARG BASE_IMAGE=yyhuang21/plurk-backup-viewer-base:latest
FROM ${BASE_IMAGE}

# Copy tools and install dependencies
WORKDIR /app
COPY tools/ /app/tools/
RUN cd /app/tools && uv sync --frozen --no-dev

# Copy entrypoint
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# viewer/ and backup data are mounted at runtime
# viewer/ → /app/viewer/
# backup → /data/backup/

EXPOSE 8000 8001

ENTRYPOINT ["/app/entrypoint.sh"]
