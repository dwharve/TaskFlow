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

# Create a non-root user
RUN useradd -m appuser && \
    chown -R appuser:appuser /app

# Copy application files
COPY . .

# Create instance directory for SQLite database
RUN mkdir -p instance && chown -R appuser:appuser instance

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5000

# Copy the start.sh script
COPY start.sh /app/start.sh

# Make the script executable
RUN chmod +x /app/start.sh

# Set the entrypoint
ENTRYPOINT ["/app/start.sh"] 