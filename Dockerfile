FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin bot \
    && mkdir -p /app/data \
    && chown bot:bot /app/data

USER bot

CMD ["python", "-m", "bot"]
