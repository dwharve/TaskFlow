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
    rm -f /app/run/*.pid
    exit 0
}

# Set up trap for cleanup
trap cleanup SIGTERM SIGINT SIGQUIT

# Create necessary files with correct permissions
touch /app/run/flask.pid /app/run/scheduler.pid
chown appuser:appgroup /app/run/*.pid
chmod 660 /app/run/*.pid

# Ensure database directory and file have correct permissions
chown -R appuser:appgroup /app/instance
chmod 775 /app/instance
touch /app/instance/database.db
chown appuser:appgroup /app/instance/database.db
chmod 660 /app/instance/database.db

# Remove any stale SQLite journal files
rm -f /app/instance/database.db-journal

# Switch to appuser for all operations
exec setpriv --reuid=appuser --regid=appgroup --init-groups bash << 'EOF'

# Initialize the database
echo "Initializing database..."
python -c "from app import app; from database import init_db; init_db(app)"

# Start the Flask app
echo "Starting Flask application..."
python app.py & echo $! > /app/run/flask.pid

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
    exit 1
fi

# Start the scheduler process
echo "Starting scheduler process..."
python run_scheduler.py & echo $! > /app/run/scheduler.pid

# Wait for either process to exit
wait -n $(cat /app/run/flask.pid) $(cat /app/run/scheduler.pid)

EOF

# Cleanup and exit
cleanup
