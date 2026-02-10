# Plurk Backup Viewer

English | [繁體中文](README.zh-TW.md)

Enhanced viewer for Plurk backup data with full-text search, link search, and CJK support.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)

## Quick Start

```bash
git clone https://github.com/user/plurk-backup-viewer
cd plurk-backup-viewer
docker compose up
```

1. Open the admin interface at http://localhost:8001
2. Upload your Plurk backup `.zip` file
3. Click **Build Database**
4. (Optional) Click **Fetch Link Metadata** to make shared links searchable
5. Your search is live at http://localhost:8000

## Ports

| Port | Description |
|------|-------------|
| `8000` | Search interface |
| `8001` | Admin interface (local only) |

## Updating Your Backup

When you export a new backup from Plurk, use the admin interface at http://localhost:8001 to re-upload and rebuild.

## Cloudflare Tunnel (Optional)

To expose the search interface via Cloudflare Tunnel:

```bash
TUNNEL_TOKEN=your-token docker compose up
```

## Development

For local setup without Docker, CLI commands, and project architecture, see [DEVELOPMENT.md](DEVELOPMENT.md).

## License

MIT
