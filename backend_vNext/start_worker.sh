#!/bin/bash
# Start Celery worker for backend_vNext
#
# Usage:
#   ./start_worker.sh [--concurrency N]
#
# Prerequisites:
#   - Redis must be running
#   - Virtual environment must be activated

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment if not already active
if [[ -z "$VIRTUAL_ENV" ]]; then
    if [[ -f "venv/bin/activate" ]]; then
        source venv/bin/activate
        echo "Activated virtual environment"
    else
        echo "Error: Virtual environment not found. Run: python -m venv venv"
        exit 1
    fi
fi

# Parse arguments
CONCURRENCY=1
while [[ $# -gt 0 ]]; do
    case $1 in
        --concurrency)
            CONCURRENCY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "Starting Celery worker with concurrency=$CONCURRENCY..."
echo "Queue: extraction"

# Start Celery worker
celery -A app.celery_app worker \
    --loglevel=INFO \
    --concurrency=$CONCURRENCY \
    --queues=extraction \
    --hostname=worker@%h
