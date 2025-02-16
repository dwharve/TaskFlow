#!/bin/bash

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Ensure instance directory exists with proper permissions
INSTANCE_DIR="/app/instance"
mkdir -p "$INSTANCE_DIR"
chmod 777 "$INSTANCE_DIR"

# Create empty database file if it doesn't exist
DB_FILE="$INSTANCE_DIR/database.db"
touch "$DB_FILE"
chmod 666 "$DB_FILE"

# Create migrations directory with proper permissions
mkdir -p migrations
chmod 777 migrations

# Clean up migrations directory if it's not properly initialized
if [ ! -f "migrations/env.py" ] || [ ! -f "migrations/script.py.mako" ] || [ ! -f "migrations/alembic.ini" ]; then
    echo "Cleaning up migrations directory..."
    rm -rf migrations/*
fi

# Initialize the database with migrations
echo "Initializing database..."
python -c "from app import app, initialize_database; initialize_database(app)" || exit 1
echo "Database initialization complete"

# Start supervisord
exec /usr/bin/supervisord -n -c /app/supervisord.conf
