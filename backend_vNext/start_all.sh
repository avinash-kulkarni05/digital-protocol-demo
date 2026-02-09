#!/bin/bash
# Start all backend services for Protocol Digitalization vNext
# Usage: ./start_all.sh [--no-redis] [--no-celery]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
START_REDIS=true
START_CELERY=true
API_PORT=8080

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-redis)
            START_REDIS=false
            shift
            ;;
        --no-celery)
            START_CELERY=false
            shift
            ;;
        --port)
            API_PORT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: ./start_all.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-redis    Skip starting Redis (use if already running)"
            echo "  --no-celery   Skip starting Celery worker"
            echo "  --port PORT   API server port (default: 8080)"
            echo "  -h, --help    Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create tmp directory for logs
mkdir -p "$SCRIPT_DIR/tmp"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Protocol Digitalization Backend - Service Starter    ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to check if a port is in use
check_port() {
    lsof -ti:$1 >/dev/null 2>&1
}

# Function to kill process on port
kill_port() {
    local port=$1
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Killing existing process on port $port...${NC}"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Activate virtual environment
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo -e "${GREEN}✓${NC} Activating virtual environment..."
    source "$SCRIPT_DIR/venv/bin/activate"
else
    echo -e "${RED}✗${NC} Virtual environment not found at $SCRIPT_DIR/venv"
    echo "  Create it with: python3.10 -m venv venv && pip install -r requirements.txt"
    exit 1
fi

# Start Redis
if [ "$START_REDIS" = true ]; then
    echo ""
    echo -e "${BLUE}[1/3] Redis Server${NC}"

    # Check if Redis is already running
    if check_port 6379; then
        echo -e "${GREEN}✓${NC} Redis already running on port 6379"
    else
        # Check if redis-server is available
        if command -v redis-server &> /dev/null; then
            echo -e "${YELLOW}→${NC} Starting Redis server..."
            redis-server --daemonize yes --logfile "$SCRIPT_DIR/tmp/redis.log" --pidfile "$SCRIPT_DIR/tmp/redis.pid"
            sleep 1
            if check_port 6379; then
                echo -e "${GREEN}✓${NC} Redis started on port 6379"
            else
                echo -e "${RED}✗${NC} Failed to start Redis"
            fi
        elif command -v brew &> /dev/null; then
            echo -e "${YELLOW}→${NC} Starting Redis via Homebrew..."
            brew services start redis 2>/dev/null || true
            sleep 2
            if check_port 6379; then
                echo -e "${GREEN}✓${NC} Redis started via Homebrew"
            else
                echo -e "${RED}✗${NC} Failed to start Redis. Install with: brew install redis"
                echo -e "${YELLOW}!${NC} Continuing without Redis (will use synchronous fallback)"
            fi
        else
            echo -e "${RED}✗${NC} Redis not installed. Install with: brew install redis"
            echo -e "${YELLOW}!${NC} Continuing without Redis (will use synchronous fallback)"
        fi
    fi
else
    echo -e "${YELLOW}→${NC} Skipping Redis (--no-redis flag)"
fi

# Start Celery Worker
if [ "$START_CELERY" = true ]; then
    echo ""
    echo -e "${BLUE}[2/3] Celery Worker${NC}"

    # Check if Redis is available for Celery
    if check_port 6379; then
        # Kill any existing Celery workers
        pkill -f "celery.*backend_vnext" 2>/dev/null || true
        sleep 1

        echo -e "${YELLOW}→${NC} Starting Celery worker..."
        celery -A app.celery_app worker \
            --loglevel=INFO \
            --concurrency=1 \
            --queues=extraction \
            --logfile="$SCRIPT_DIR/tmp/celery.log" \
            --pidfile="$SCRIPT_DIR/tmp/celery.pid" \
            --detach

        sleep 2
        if pgrep -f "celery.*backend_vnext" > /dev/null; then
            echo -e "${GREEN}✓${NC} Celery worker started"
        else
            echo -e "${RED}✗${NC} Failed to start Celery worker"
            echo -e "${YELLOW}!${NC} Check logs at: $SCRIPT_DIR/tmp/celery.log"
        fi
    else
        echo -e "${YELLOW}!${NC} Skipping Celery (Redis not available)"
    fi
else
    echo -e "${YELLOW}→${NC} Skipping Celery (--no-celery flag)"
fi

# Start API Server
echo ""
echo -e "${BLUE}[3/3] FastAPI Server${NC}"

# Kill existing process on API port
kill_port $API_PORT

echo -e "${YELLOW}→${NC} Starting FastAPI server on port $API_PORT..."
nohup python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $API_PORT \
    --reload \
    > "$SCRIPT_DIR/tmp/api.log" 2>&1 &

API_PID=$!
echo $API_PID > "$SCRIPT_DIR/tmp/api.pid"
sleep 2

if check_port $API_PORT; then
    echo -e "${GREEN}✓${NC} FastAPI server started on http://localhost:$API_PORT"
else
    echo -e "${RED}✗${NC} Failed to start FastAPI server"
    echo -e "${YELLOW}!${NC} Check logs at: $SCRIPT_DIR/tmp/api.log"
    exit 1
fi

# Summary
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}All services started!${NC}"
echo ""
echo -e "  ${BLUE}API Server:${NC}    http://localhost:$API_PORT"
echo -e "  ${BLUE}API Docs:${NC}      http://localhost:$API_PORT/docs"
if check_port 6379; then
    echo -e "  ${BLUE}Redis:${NC}         localhost:6379"
fi
if pgrep -f "celery.*backend_vnext" > /dev/null; then
    echo -e "  ${BLUE}Celery:${NC}        Running (1 worker)"
fi
echo ""
echo -e "${BLUE}Logs:${NC}"
echo -e "  API:     $SCRIPT_DIR/tmp/api.log"
if [ "$START_REDIS" = true ] && [ -f "$SCRIPT_DIR/tmp/redis.log" ]; then
    echo -e "  Redis:   $SCRIPT_DIR/tmp/redis.log"
fi
if [ "$START_CELERY" = true ] && [ -f "$SCRIPT_DIR/tmp/celery.log" ]; then
    echo -e "  Celery:  $SCRIPT_DIR/tmp/celery.log"
fi
echo ""
echo -e "${YELLOW}To stop all services:${NC} ./stop_all.sh"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
