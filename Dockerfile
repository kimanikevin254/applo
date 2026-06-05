FROM python:3.13-slim

# System deps for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    curl wget gnupg ca-certificates \
    # Chromium runtime deps
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (layer cache)
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Install Playwright browsers
RUN uv run playwright install chromium

# Copy source
COPY . .

# Install the project itself
RUN uv sync --no-dev

# Create data directories
RUN mkdir -p data/resumes data/output logs

EXPOSE 8000

CMD ["uv", "run", "python", "run.py"]
