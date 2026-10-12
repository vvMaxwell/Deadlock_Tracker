# Deadlock Tracker

Deadlock Tracker is a professional Python repo that ships two products from one shared codebase:

- A public Deadlock stat tracker website built with FastAPI
- A public Discord bot focused entirely on Deadlock profile and match tracking

## Project Structure

```text
apps/
  discord_bot.py
  web.py
assets/
  rem.png
src/deadlock_tracker/
  bot/
  clients/
  presentation/
  services/
  web/
  config.py
  models.py
tests/
```

## Setup

```bash
pip install -e .[dev]
```

Copy `.env.example` to `.env`, then run:

```bash
python apps/web.py
python apps/discord_bot.py
```

Set `DEADLOCK_API_KEY` in `.env` or `deploy/app.env` to unlock protected Deadlock API endpoints like player match history. The app sends it as the `X-API-KEY` header and does not expose it in URLs.

## October 2026 API compatibility

- Match details preserve all 13 `stats[].gold_sources` categories (kills, damage,
  souls, and orb souls) and show the final recorded breakdown for each player.
  Missing values remain unavailable rather than becoming zero. Unknown future
  source IDs are retained. These are cumulative REST snapshots, not deltas.
- The shared client supports `/v1/analytics/hero-swap-stats` and the list/single
  `/v1/assets/convars` endpoints, including optional `client_version` selection.
  Convar defaults retain their native JSON types; they are compiled defaults,
  not necessarily the values active on a game server.
- This app does not ingest Parquet data dumps. For a future importer, the removed
  `stats.custom_user_stats` column is replaced by `custom_user_stats_deltas`
  (`Map(String, Array(Int32))`). Reconstruct each stat independently with a running
  sum, including negative deltas. Dumps now use zstd level 9. Do not apply this
  conversion to REST match metadata, which still returns absolute snapshots.

## Stack

- Website: FastAPI with Jinja templates and custom CSS
- Discord bot: `discord.py`
- Shared logic: Python service layer for Deadlock API lookups and stat formatting

## Docker

```bash
docker build -t deadlock-tracker-web .
docker run --rm -p 8000:8000 deadlock-tracker-web
```

If Docker does not start, make sure Docker Desktop is running first.

## VPS Deployment

This repo includes a production deployment path for a Linux VPS:

- `deploy/bootstrap-vps.sh` installs Docker, Compose, and Git
- CloudPanel handles public Nginx reverse proxying and SSL on ports `80` and `443`
- `deploy/docker-compose.yml` only runs the FastAPI app container
- The Docker app binds FastAPI to `127.0.0.1:8000`
- CloudPanel should reverse proxy `deadlockstattracker.com` to `http://127.0.0.1:8000`
- `.github/workflows/deploy.yml` deploys the latest `main` branch over SSH

Initial server bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/vvMaxwell/Deadlock_Tracker/main/deploy/bootstrap-vps.sh | sudo bash
```

GitHub Actions secrets expected by the deploy workflow:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PORT` (optional, defaults to `22`)
- `DEPLOY_PATH` (optional, defaults to `/opt/deadlock-tracker`)

For the Deadlock API key itself, do not commit it and do not use a GitHub Actions variable. Put it in the server-side `deploy/app.env` file as `DEADLOCK_API_KEY=...`, or template that file from a GitHub Actions secret if you later automate env sync.

For custom domains behind Cloudflare, CloudPanel should manage the origin certificate. Cloudflare SSL can use `Full`, then switch to `Full (strict)` once a valid origin or Let's Encrypt certificate is installed in CloudPanel.
