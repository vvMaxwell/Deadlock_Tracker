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
