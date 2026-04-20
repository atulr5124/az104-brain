#!/bin/bash

# Get the directory where this script lives
# This ensures the script always runs from the project root
# regardless of where you call it from

# Activate project virtual environment
source venv/bin/activate

# Pass all arguments through to the Python script
if [ -n "$1" ]; then
    python bulk_ingest.py "$1"
else
    python bulk_ingest.py
fi