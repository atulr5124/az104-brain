#!/bin/bash

# Wrapper for ingest.py
# Usage: ./ingest.sh "Topic Name" <ms_learn_url>
# Activates venv automatically so you don't have to think about it

# Activate virtual environment
source venv/bin/activate

# Pass all arguments through to the Python script
python ingest.py "$1" "$2"