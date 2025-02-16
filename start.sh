#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Initialize the database (this will recreate tables if needed)
python -c "from app import app; from database import init_db; init_db(app)"

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

# Start the scheduler process as scheduleruser
echo "Starting scheduler process..."
su -s /bin/bash scheduleruser -c "python run_scheduler.py & echo \$! > /app/run/scheduler.pid"

# Start the Flask app as flaskuser and save its PID
echo "Starting Flask application..."
su -s /bin/bash flaskuser -c "python app.py & echo \$! > /app/run/flask.pid"

# Wait for either process to exit
wait -n $(cat /app/run/flask.pid) $(cat /app/run/scheduler.pid)

# Cleanup and exit
cleanup
