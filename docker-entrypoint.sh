#!/bin/bash
set -e

# Initialize DB if needed
if [ ! -f /data/tickets.db ]; then
    echo "Seeding database..."
    python3 -c "from app import app,init_db; app.app_context().push(); init_db()"
fi

# Start gunicorn
exec "$@"
