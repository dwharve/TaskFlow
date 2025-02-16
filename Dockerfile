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
    DATABASE_URL=sqlite:///instance/database.db \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO \
    WORKERS=4 \
    TIMEOUT=120

# Copy application files
COPY . .

# Create app group and users
RUN groupadd -r appgroup && \
    useradd -r -g appgroup appuser && \
    mkdir -p /app/instance /app/logs && \
    chown -R appuser:appgroup /app && \
    chmod -R 750 /app && \
    chmod 770 /app/instance /app/logs

# Create and set permissions for database directory
RUN mkdir -p /app/instance && \
    chown -R appuser:appgroup /app/instance && \
    chmod 770 /app/instance && \
    touch /app/instance/database.db && \
    chown appuser:appgroup /app/instance/database.db && \
    chmod 660 /app/instance/database.db

# Create directory for process management
RUN mkdir -p /app/run && \
    chown -R appuser:appgroup /app/run && \
    chmod 770 /app/run && \
    touch /app/run/flask.pid /app/run/scheduler.pid && \
    chown appuser:appgroup /app/run/*.pid && \
    chmod 660 /app/run/*.pid

# Make scripts executable
RUN chmod 770 /app/start.sh

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5000

# Set the entrypoint
ENTRYPOINT ["/app/start.sh"] 