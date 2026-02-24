#!/bin/bash
# Stop all backend services for Protocol Digitalization vNext
# Usage: ./stop_all.sh [--keep-redis]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

KEEP_REDIS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --keep-redis)
            KEEP_REDIS=true
            shift
            ;;
        -h|--help)
            echo "Usage: ./stop_all.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --keep-redis  Don't stop Redis server"
            echo "  -h, --help    Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}Stopping backend services...${NC}"
echo ""

# Stop API Server
echo -e "${YELLOW}→${NC} Stopping FastAPI server..."
if [ -f "$SCRIPT_DIR/tmp/api.pid" ]; then
    API_PID=$(cat "$SCRIPT_DIR/tmp/api.pid")
    kill $API_PID 2>/dev/null || true
    rm -f "$SCRIPT_DIR/tmp/api.pid"
fi
# Also kill by port
lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
echo -e "${GREEN}✓${NC} FastAPI server stopped"

# Stop Celery Worker
echo -e "${YELLOW}→${NC} Stopping Celery worker..."
if [ -f "$SCRIPT_DIR/tmp/celery.pid" ]; then
    CELERY_PID=$(cat "$SCRIPT_DIR/tmp/celery.pid")
    kill $CELERY_PID 2>/dev/null || true
    rm -f "$SCRIPT_DIR/tmp/celery.pid"
fi
pkill -f "celery.*backend_vnext" 2>/dev/null || true
echo -e "${GREEN}✓${NC} Celery worker stopped"

# Stop Redis
if [ "$KEEP_REDIS" = false ]; then
    echo -e "${YELLOW}→${NC} Stopping Redis server..."
    if [ -f "$SCRIPT_DIR/tmp/redis.pid" ]; then
        REDIS_PID=$(cat "$SCRIPT_DIR/tmp/redis.pid")
        kill $REDIS_PID 2>/dev/null || true
        rm -f "$SCRIPT_DIR/tmp/redis.pid"
    fi
    # Try homebrew stop
    if command -v brew &> /dev/null; then
        brew services stop redis 2>/dev/null || true
    fi
    # Try redis-cli shutdown
    redis-cli shutdown 2>/dev/null || true
    echo -e "${GREEN}✓${NC} Redis server stopped"
else
    echo -e "${YELLOW}!${NC} Keeping Redis running (--keep-redis flag)"
fi

echo ""
echo -e "${GREEN}All services stopped.${NC}"
