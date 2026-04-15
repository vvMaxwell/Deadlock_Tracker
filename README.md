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

- `deploy/bootstrap-vps.sh` installs Docker, Compose, Git, and opens ports `22` and `80`
- `deploy/docker-compose.yml` runs the FastAPI app behind Nginx
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

For custom domains behind Cloudflare, place the Cloudflare Origin certificate and key on the VPS at:

- `/home/deadlockdeploy/certs/origin.crt`
- `/home/deadlockdeploy/certs/origin.key`
