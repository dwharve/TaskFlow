#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Create log directory if it doesn't exist
mkdir -p /var/log

# Initialize the database (this will recreate tables if needed)
python -c "from app import app; from database import init_db; init_db(app)"

# Start supervisor to manage both gunicorn and scheduler
exec supervisord -c supervisord.conf
