# Dockerfile for Render Backend Deployment
# CashOut Forecast API — SIH 2026

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend ./backend
COPY data ./data
COPY docs ./docs
COPY frontend ./frontend
COPY models ./models
COPY scripts ./scripts

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose port (Render sets $PORT dynamically)
EXPOSE 8000

# Start command with dynamic PORT binding
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
