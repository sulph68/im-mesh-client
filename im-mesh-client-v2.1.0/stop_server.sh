#!/bin/bash

# Meshtastic Web Client Stop Script

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PID_FILE="./server.pid"

echo -e "${BLUE}🛑 Stopping Meshtastic Web Client${NC}"
echo "===================================="

# Function to stop server cleanly
stop_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}Stopping server (PID: $PID)...${NC}"
            
            # Send TERM signal first
            kill -TERM $PID 2>/dev/null
            
            # Wait up to 10 seconds for graceful shutdown
            for i in {1..10}; do
                if ! ps -p $PID > /dev/null 2>&1; then
                    echo -e "${GREEN}✓ Server stopped gracefully${NC}"
                    rm -f "$PID_FILE"
                    return 0
                fi
                sleep 1
            done
            
            # Force kill if still running
            if ps -p $PID > /dev/null 2>&1; then
                echo -e "${RED}Force killing server...${NC}"
                kill -9 $PID 2>/dev/null
                sleep 1
                
                if ! ps -p $PID > /dev/null 2>&1; then
                    echo -e "${GREEN}✓ Server forcefully stopped${NC}"
                else
                    echo -e "${RED}❌ Failed to stop server${NC}"
                    return 1
                fi
            fi
        else
            echo -e "${YELLOW}⚠️  Server not running (PID file stale)${NC}"
        fi
        
        rm -f "$PID_FILE"
    else
        echo -e "${YELLOW}⚠️  No PID file found${NC}"
    fi
    
    # Kill any remaining Python processes as backup
    echo -e "${YELLOW}Checking for remaining Python processes...${NC}"
    REMAINING=$(pkill -f "python3 main.py" 2>/dev/null; echo $?)
    
    if [ "$REMAINING" -eq 0 ]; then
        echo -e "${GREEN}✓ Cleaned up remaining processes${NC}"
    else
        echo -e "${GREEN}✓ No remaining processes found${NC}"
    fi
    
    return 0
}

# Stop the server
stop_server

echo ""
echo -e "${GREEN}🎯 Meshtastic Web Client stopped${NC}"