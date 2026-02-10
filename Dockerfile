FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install cloudflared and ICU runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl libicu76 \
    && ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" -o /tmp/cloudflared.deb \
    && dpkg -i /tmp/cloudflared.deb \
    && rm /tmp/cloudflared.deb \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install custom SQLite + ICU tokenizer from pre-built tarball
ADD viewer/lib/linux-amd64-libs.tar.gz /usr/local/lib/
RUN ln -sf libsqlite3.so /usr/local/lib/libsqlite3.so.0 && ldconfig

# Copy tools and install dependencies
WORKDIR /app
COPY tools/ /app/tools/
RUN cd /app/tools && uv sync --frozen \
    && cd /app/tools && uv run playwright install chromium --with-deps

# Copy entrypoint
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# viewer/ and backup data are mounted at runtime
# viewer/ → /app/viewer/
# backup → /data/backup/

EXPOSE 8000 8001

ENTRYPOINT ["/app/entrypoint.sh"]
