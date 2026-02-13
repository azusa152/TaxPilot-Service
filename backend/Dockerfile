FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for asyncpg and markitdown
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

# Copy application code
COPY . .

# Install the project in editable mode for src package resolution
RUN pip install --no-cache-dir -e ".[dev]"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
