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

# Create app group and users
RUN groupadd -r appgroup && \
    useradd -r -g appgroup flaskuser && \
    useradd -r -g appgroup scheduleruser

# Create necessary directories with appropriate permissions
RUN mkdir -p /app/instance /app/logs && \
    chown -R flaskuser:appgroup /app && \
    chmod -R 750 /app && \
    chmod 770 /app/instance /app/logs

# Copy application files
COPY . .

# Set specific permissions for shared resources
RUN chown -R flaskuser:appgroup /app/instance && \
    chmod 770 /app/instance && \
    chown flaskuser:appgroup /app/database.db 2>/dev/null || true && \
    chmod 660 /app/database.db 2>/dev/null || true && \
    chmod 750 /app/*.py && \
    chmod 770 /app/start.sh

# Create a directory for process management
RUN mkdir -p /app/run && \
    chown -R flaskuser:appgroup /app/run && \
    chmod 770 /app/run

# Create pid files with correct permissions
RUN touch /app/run/flask.pid /app/run/scheduler.pid && \
    chown flaskuser:appgroup /app/run/flask.pid && \
    chown scheduleruser:appgroup /app/run/scheduler.pid && \
    chmod 660 /app/run/*.pid

# Switch to non-root user - will be overridden by start.sh for specific processes
USER flaskuser

# Expose port
EXPOSE 5000

# Set the entrypoint
ENTRYPOINT ["/app/start.sh"] 