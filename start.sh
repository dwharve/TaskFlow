#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Function to cleanup processes
cleanup() {
    echo "Cleaning up processes..."
    if [ -f /app/run/scheduler.pid ]; then
        kill $(cat /app/run/scheduler.pid) 2>/dev/null
    fi
    if [ -f /app/run/flask.pid ]; then
        kill $(cat /app/run/flask.pid) 2>/dev/null
    fi
    exit 0
}

# Set up trap for cleanup
trap cleanup SIGTERM SIGINT SIGQUIT

# Initialize the database first and wait for it to complete
echo "Initializing database..."
python -c "from app import app; from database import init_db; init_db(app)"

# Ensure database file has correct permissions after initialization
chown appuser:appgroup /app/instance/database.db
chmod 660 /app/instance/database.db

# Start the Flask app first and wait for it to be ready
echo "Starting Flask application..."
su -s /bin/bash appuser -c "python app.py & echo \$! > /app/run/flask.pid"

# Wait for database to be accessible (max 30 seconds)
MAX_TRIES=30
COUNTER=0
while [ $COUNTER -lt $MAX_TRIES ]; do
    if python -c "import sqlite3; sqlite3.connect('/app/instance/database.db')" 2>/dev/null; then
        echo "Database is ready"
        break
    fi
    echo "Waiting for database to be ready... ($COUNTER/$MAX_TRIES)"
    sleep 1
    COUNTER=$((COUNTER + 1))
done

if [ $COUNTER -eq $MAX_TRIES ]; then
    echo "Database failed to become ready in time"
    cleanup
    exit 1
fi

# Start the scheduler process
echo "Starting scheduler process..."
su -s /bin/bash appuser -c "python run_scheduler.py & echo \$! > /app/run/scheduler.pid"

# Wait for either process to exit
wait -n $(cat /app/run/flask.pid) $(cat /app/run/scheduler.pid)

# Cleanup and exit
cleanup
