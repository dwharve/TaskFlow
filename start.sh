#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Create necessary directories
mkdir -p /var/log /etc/supervisor/conf.d instance

# Copy supervisord config to the correct location
cp supervisord.conf /etc/supervisor/conf.d/

# Initialize the database with migrations
python -c "from app import app, initialize_database; initialize_database(app)"

# Start supervisord
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
