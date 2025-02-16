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

# Install required system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends util-linux sqlite3 && \
    rm -rf /var/lib/apt/lists/*

# Copy application files
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p /app/instance /app/logs /app/run && \
    groupadd -r appgroup && \
    useradd -r -g appgroup appuser && \
    # Set base permissions
    chown -R appuser:appgroup /app && \
    # Make start script executable
    chmod +x /app/start.sh

# Switch to non-root user - will be overridden by start.sh for specific processes
USER appuser

# Expose port
EXPOSE 5000

# Set the entrypoint
ENTRYPOINT ["/app/start.sh"] 