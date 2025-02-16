#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Initialize database and migrations
echo "Initializing database and migrations..."

# Create instance directory if it doesn't exist
mkdir -p instance

# Initialize migrations if migrations directory doesn't exist or is empty
if [ ! -d "migrations" ] || [ -z "$(ls -A migrations)" ]; then
    echo "Initializing migrations directory..."
    flask db init
fi

# Generate initial migration
echo "Generating migration..."
flask db migrate -m "Initial migration"

# Apply migrations
echo "Applying migrations..."
flask db upgrade

# Start gunicorn
echo "Starting gunicorn..."
gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 1 \
    --threads 2 \
    --worker-class gthread \
    --worker-connections 1000 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --log-level info \
    app:app
