#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Create log directory if it doesn't exist
mkdir -p /var/log

# Initialize the database if it doesn't exist
python -c "from database import init_db; init_db()"

# Start supervisord
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
