#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Initialize the database (this will recreate tables if needed)
python -c "from app import app, init_db; init_db()"

# Start gunicorn with thread-safe configuration
gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --threads 2 \
    --worker-class gthread \
    --worker-connections 1000 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --log-level info \
    --config python:wsgi \
    wsgi:app
