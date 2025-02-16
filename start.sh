#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Ensure instance directory exists with proper permissions
mkdir -p /app/instance
chmod 777 /app/instance

# Initialize the database with migrations
python -c "from app import app, initialize_database; initialize_database(app)"

# Start supervisord
exec /usr/bin/supervisord -n -c /app/supervisord.conf
