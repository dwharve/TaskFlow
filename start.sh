#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Initialize the database with migrations
python -c "from app import app, initialize_database; initialize_database(app)"

# Start supervisord
exec /usr/bin/supervisord -n -c /app/supervisord.conf
