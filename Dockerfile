# Use Python 3.11 slim as the base image
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set environment variables for the application
ENV FLASK_APP=app.py \
    FLASK_ENV=production \
    DATABASE_URL=sqlite:///database.db \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO \
    WORKERS=4 \
    TIMEOUT=120

# Install supervisor and create necessary directories
RUN apt-get update && \
    apt-get install -y --no-install-recommends supervisor && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/log/supervisor /var/run/supervisor && \
    chmod 777 /var/log/supervisor /var/run/supervisor

# Copy application files
COPY . .

# Create instance directory for SQLite database and log directory
RUN mkdir -p instance /var/log && \
    chmod 777 instance /var/log

# Make the script executable
RUN chmod +x /app/start.sh

# Expose port
EXPOSE 5000

# Set the entrypoint
ENTRYPOINT ["/app/start.sh"] 