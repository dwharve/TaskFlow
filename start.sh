#!/bin/sh
# Initialize the database
python -c "from app import init_db; init_db()"

# Start the scheduler in the background
python -c "from app import app, scheduler; scheduler.start()" &

# Start Gunicorn
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers $WORKERS \
    --timeout $TIMEOUT \
    --access-logfile - \
    --error-logfile - \
    --log-level $LOG_LEVEL \
    --worker-class sync \
    app:app
