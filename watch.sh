#!/bin/bash
source venv/bin/activate

echo "Starting file watcher..."
echo "Drop files into inputs/ to auto-ingest them."
echo "Press Ctrl+C to stop."

python watch.py