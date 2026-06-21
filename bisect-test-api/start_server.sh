#!/bin/bash
# Usage: bash start_server.sh
uvicorn main:app --host 0.0.0.0 --port 8000 &
echo $! > server.pid
sleep 1  # wait for startup
