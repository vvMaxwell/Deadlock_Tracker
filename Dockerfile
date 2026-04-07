FROM python:3.13-slim

WORKDIR /app
ENV DEADLOCK_WEB_HOST=0.0.0.0

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY src ./src
COPY assets ./assets

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "apps/web.py"]
