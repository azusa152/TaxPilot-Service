FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Playwright requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev gosu \
    # Playwright dependencies
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early
RUN useradd --create-home appuser

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

# Install Playwright browsers as appuser
RUN chown -R appuser:appuser /app
USER appuser
RUN playwright install chromium

# Switch back to root to copy files and set up entrypoint
USER root

# Copy application code
COPY . .
RUN chown -R appuser:appuser /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
