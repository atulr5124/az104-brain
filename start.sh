#!/bin/bash

# Starts the az104-brain web server
# Usage: ./start.sh

source venv/bin/activate
echo "Starting az104-brain..."
echo "Open http://localhost:5000 in your browser"
python server.py